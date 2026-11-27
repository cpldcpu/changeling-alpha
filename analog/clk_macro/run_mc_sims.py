#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Run post-layout Magic hierarchical PEX Monte Carlo mismatch verification (IHP SG13CMOS5L)."""

import concurrent.futures
import csv
import os
import re
import shutil
import statistics
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALOG_DIR = HERE.parent
RESULTS_DIR = ANALOG_DIR / "results"
BUILD_PEX = HERE / "build" / "pex"
PEX_SPICE = BUILD_PEX / "rpe_clk_analog_pex.spice"
MC_PEX_SPICE = BUILD_PEX / "rpe_clk_analog_pex_mc.spice"

PDK_ROOT = os.environ.get(
    "PDK_ROOT",
    "/home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008",
)
PDK = os.environ.get("PDK", "ihp-sg13cmos5l")

MAX_WORKERS = min(10, max(1, int((os.cpu_count() or 4) * 0.75)))
DEFAULT_NGSPICE = "/nix/store/mclawsglbgvysxshnl8rx09d1k7ld8bn-ngspice-45/bin/ngspice"
NGSPICE_BIN = DEFAULT_NGSPICE if Path(DEFAULT_NGSPICE).exists() else (shutil.which("ngspice") or DEFAULT_NGSPICE)

MC_SEEDS = list(range(1001, 1041))  # 40 deterministic mismatch samples
MM_MODELS = {"sg13_lv_nmos", "sg13_lv_pmos", "sg13_hv_nmos", "sg13_hv_pmos", "sg13_hv_svaricap", "rppd"}


def build_mc_netlist() -> int:
    """Create MC netlist copy with mm_ok=1 enabled on every supported PDK device instance."""
    if not PEX_SPICE.exists():
        raise FileNotFoundError(f"Run extract_pex.py first: {PEX_SPICE}")
    out_lines: list[str] = []
    patched = 0
    for line in PEX_SPICE.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith(("*", ".")) and s[0].upper() == "X":
            toks = s.split()
            hit = any(tok in MM_MODELS for tok in toks)
            if hit:
                clean = re.sub(r"\s+mm_ok=\S+", "", line)
                line = clean + " mm_ok=1"
                patched += 1
        out_lines.append(line)
    assert patched >= 50, f"Expected >=50 mm_ok patches in PEX netlist, got {patched}"
    MC_PEX_SPICE.write_text("\n".join(out_lines) + "\n")
    return patched


def detect_best_trim() -> int:
    """Read post-layout tt 60 MHz nominal trim code from clk_macro_pex.csv."""
    pex_csv = RESULTS_DIR / "clk_macro_pex.csv"
    if pex_csv.exists():
        with open(pex_csv, newline="") as f:
            cands = [
                r for r in csv.DictReader(f)
                if r["mode"] == "ring_only" and r["corner"] == "tt"
            ]
        if cands:
            best = min(cands, key=lambda r: abs(float(r["ring_MHz"]) - 60.0))
            return int(best["trim"])
    return 202


def parse_vals(out: str, names: list[str]) -> dict[str, float]:
    vals = {}
    for n in names:
        m = re.search(rf"^\s*{re.escape(n)}\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out, re.MULTILINE | re.IGNORECASE)
        if not m:
            raise ValueError(f"Could not parse '{n}' from ngspice output:\n{out[-1200:]}")
        vals[n] = float(m.group(1))
    return vals


def run_ngspice(deck_text: str, tag: str, expected_names: list[str]) -> tuple[dict[str, float], bool]:
    BUILD_PEX.mkdir(parents=True, exist_ok=True)
    deck_path = BUILD_PEX / f"{tag}.sp"
    out_path = BUILD_PEX / f"{tag}.out"
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["PDK_ROOT"] = PDK_ROOT
    env["PDK"] = PDK

    if deck_path.exists() and out_path.exists() and deck_path.read_text() == deck_text:
        cached = out_path.read_text()
        try:
            return parse_vals(cached, expected_names), cached.startswith("* trap_retry=1\n")
        except ValueError:
            pass

    deck_path.write_text(deck_text)
    res = subprocess.run([NGSPICE_BIN, "-b", str(deck_path)], cwd=ANALOG_DIR, env=env, capture_output=True, text=True)
    combined = res.stdout + "\n" + res.stderr
    try:
        if res.returncode != 0 or "Timestep too small" in combined:
            raise RuntimeError(combined[-1200:])
        vals = parse_vals(res.stdout, expected_names)
        out_path.write_text(res.stdout)
        return vals, False
    except (RuntimeError, ValueError):
        print(f"[mc retry trap] {tag}", flush=True)
        trap_deck = deck_text.replace("method=gear reltol=1e-3", "method=trap reltol=3e-3")
        trap_path = BUILD_PEX / f"{tag}_trap.sp"
        trap_path.write_text(trap_deck)
        res2 = subprocess.run([NGSPICE_BIN, "-b", str(trap_path)], cwd=ANALOG_DIR, env=env, capture_output=True, text=True)
        if res2.returncode != 0 or "Timestep too small" in (res2.stdout + res2.stderr):
            raise RuntimeError(f"ngspice failed for {tag} (even with trap):\n{res2.stdout[-1200:]}\n{res2.stderr[-1200:]}")
        vals = parse_vals(res2.stdout, expected_names)
        out_path.write_text("* trap_retry=1\n" + res2.stdout)
        return vals, True


def trim_sources(trim: int, vdd: float = 1.20) -> str:
    return "\n".join(f"Vtrim{i} trim{i} GND dc {vdd if ((trim >> i) & 1) else 0.0}" for i in range(8)) + "\n"


def sim_ring_mc(seed: int, trim: int) -> tuple[dict[str, float], bool]:
    vdd, vh, temp = 1.20, 0.60, 25
    deck = (
        f"* MC mismatch ring_only seed={seed} trim={trim}\n"
        f".options seed={seed} temp={temp} method=gear reltol=1e-3 rshunt=1e12\n"
        f".lib cornerMOSlv.lib mos_tt_mismatch\n"
        f".lib cornerMOShv.lib mos_tt_mismatch\n"
        f".lib cornerRES.lib res_typ_mismatch\n"
        f".lib cornerCAP.lib cap_typ_mismatch\n"
        f".include {MC_PEX_SPICE}\n"
        f"Xmac VDD GND en_ring en_relax trim0 trim1 trim2 trim3 trim4 trim5 trim6 trim7 clk clk_slow rpe_clk_analog\n"
        f"{trim_sources(trim, vdd)}"
        f"Vdd VDD GND dc {vdd}\nVen_ring en_ring GND dc {vdd}\nVen_relax en_relax GND dc 0\n"
        f".save v(clk) v(clk_slow) i(Vdd)\n"
        f".tran 200p 480n\n"
        f".control\nset num_threads=1\nrun\n"
        f"meas tran tr1 when v(clk)={vh} rise=1 td=300n\n"
        f"meas tran tf1 when v(clk)={vh} fall=1 td=tr1\n"
        f"meas tran tr4 when v(clk)={vh} rise=4 td=300n\n"
        f"let ring_MHz = 3.0 / (tr4 - tr1) / 1e6\n"
        f"let ring_duty = (tf1 - tr1) / ((tr4 - tr1) / 3.0) * 100.0\n"
        f"meas tran vslow_max max v(clk_slow) from=300n to=480n\n"
        f"meas tran i_avg avg i(Vdd) from=tr1 to=tr4\n"
        f"let idd_uA = abs(i_avg) * 1e6\n"
        f"print ring_MHz ring_duty vslow_max idd_uA\n.endc\n.end\n"
    )
    v, retried = run_ngspice(deck, f"mc_ring_s{seed}_t{trim}", ["ring_MHz", "ring_duty", "vslow_max", "idd_uA"])
    assert v["vslow_max"] < 0.05, f"clk_slow not gated in ring MC seed={seed}: {v}"
    return v, retried


def sim_relax_mc(seed: int, trim: int) -> tuple[dict[str, float], bool]:
    vdd, vh, temp = 1.20, 0.60, 25
    deck = (
        f"* MC mismatch sleep_relax seed={seed} trim={trim}\n"
        f".options seed={seed} temp={temp} method=gear reltol=1e-3 rshunt=1e12\n"
        f".lib cornerMOSlv.lib mos_tt_mismatch\n"
        f".lib cornerMOShv.lib mos_tt_mismatch\n"
        f".lib cornerRES.lib res_typ_mismatch\n"
        f".lib cornerCAP.lib cap_typ_mismatch\n"
        f".include {MC_PEX_SPICE}\n"
        f"Xmac VDD GND en_ring en_relax trim0 trim1 trim2 trim3 trim4 trim5 trim6 trim7 clk clk_slow rpe_clk_analog\n"
        f"{trim_sources(trim, vdd)}"
        f"Vdd VDD GND pwl(0 0 2u {vdd})\nVen_ring en_ring GND dc 0\nVen_relax en_relax GND pwl(0 0 2u {vdd})\n"
        f".save v(clk) v(clk_slow) i(Vdd)\n"
        f".tran 10n 75u uic\n"
        f".control\nset num_threads=1\nrun\n"
        f"meas tran tr1 when v(clk_slow)={vh} rise=1 td=22u\n"
        f"meas tran tf1 when v(clk_slow)={vh} fall=1 td=tr1\n"
        f"meas tran tr3 when v(clk_slow)={vh} rise=3 td=22u\n"
        f"let relax_kHz = 2.0 / (tr3 - tr1) / 1e3\n"
        f"let relax_duty = (tf1 - tr1) / ((tr3 - tr1) / 2.0) * 100.0\n"
        f"meas tran vclk_max max v(clk) from=22u to=75u\n"
        f"meas tran i_avg avg i(Vdd) from=tr1 to=tr3\n"
        f"let idd_uA = abs(i_avg) * 1e6\n"
        f"print relax_kHz relax_duty vclk_max idd_uA\n.endc\n.end\n"
    )
    v, retried = run_ngspice(deck, f"mc_relax_s{seed}", ["relax_kHz", "relax_duty", "vclk_max", "idd_uA"])
    assert v["vclk_max"] < 0.05, f"clk not gated in relax MC seed={seed}: {v}"
    return v, retried


def main() -> None:
    patched = build_mc_netlist()
    best_trim = detect_best_trim()
    print(f"Prepared {MC_PEX_SPICE.name} ({patched} devices with mm_ok=1); best_trim={best_trim}, N={len(MC_SEEDS)}", flush=True)

    trims_tested = sorted({128, 191, 192, best_trim})
    ring_res: dict[tuple[int, int], dict[str, float]] = {}
    relax_res: dict[int, dict[str, float]] = {}
    trap_retries = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fut_to_ring = {ex.submit(sim_ring_mc, s, t): (s, t) for s in MC_SEEDS for t in trims_tested}
        futs_rel = {s: ex.submit(sim_relax_mc, s, best_trim) for s in MC_SEEDS}
        ring_done = 0
        total_ring = len(fut_to_ring)
        for fut in concurrent.futures.as_completed(fut_to_ring):
            s, t = fut_to_ring[fut]
            v, retried = fut.result()
            ring_res[(s, t)] = v
            trap_retries += int(retried)
            ring_done += 1
            if ring_done % 20 == 0 or ring_done == total_ring:
                print(f"[mc_ring] {ring_done}/{total_ring} complete", flush=True)
        for s, fut in futs_rel.items():
            v, retried = fut.result()
            relax_res[s] = v
            trap_retries += int(retried)
            rb = ring_res[(s, best_trim)]
            r128 = ring_res[(s, 128)]
            r191 = ring_res[(s, 191)]
            r192 = ring_res[(s, 192)]
            rl = relax_res[s]
            print(
                f"[mc seed={s}] boot@128={r128['ring_MHz']:.3f} MHz, "
                f"nom@{best_trim}={rb['ring_MHz']:.3f} MHz, "
                f"step(191->192)={r192['ring_MHz']-r191['ring_MHz']:+.4f} MHz, "
                f"relax={rl['relax_kHz']:.3f} kHz",
                flush=True,
            )

    rows = []
    for s in MC_SEEDS:
        r128 = ring_res[(s, 128)]
        r191 = ring_res[(s, 191)]
        r192 = ring_res[(s, 192)]
        rb = ring_res[(s, best_trim)]
        rl = relax_res[s]
        rows.append({
            "seed": str(s),
            "best_trim": str(best_trim),
            "ring_t128_MHz": f"{r128['ring_MHz']:.4f}",
            "ring_t191_MHz": f"{r191['ring_MHz']:.4f}",
            "ring_t192_MHz": f"{r192['ring_MHz']:.4f}",
            "step_191_192_MHz": f"{(r192['ring_MHz'] - r191['ring_MHz']):.4f}",
            "ring_best_MHz": f"{rb['ring_MHz']:.4f}",
            "ring_best_duty_pct": f"{rb['ring_duty']:.2f}",
            "ring_best_idd_uA": f"{rb['idd_uA']:.3f}",
            "relax_kHz": f"{rl['relax_kHz']:.3f}",
            "relax_duty_pct": f"{rl['relax_duty']:.2f}",
            "relax_idd_uA": f"{rl['idd_uA']:.3f}",
        })

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = RESULTS_DIR / "clk_macro_mc.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def summarize(label: str, vals: list[float], unit: str) -> None:
        mu = statistics.mean(vals)
        sd = statistics.stdev(vals)
        print(f"  {label:<24s}: mean={mu:8.4f} {unit}, sigma={sd:7.4f} {unit} ({100*sd/mu:.2f}%), min={min(vals):8.4f}, max={max(vals):8.4f}")
        assert sd > 0.0, f"Mismatch produced zero spread for {label}"

    print("\n=== Monte Carlo Mismatch Summary (N=40, tt 1.20 V 25 C) ===")
    summarize("Ring @ trim=128 (boot)", [ring_res[(s, 128)]["ring_MHz"] for s in MC_SEEDS], "MHz")
    summarize(f"Ring @ trim={best_trim} (nom)", [ring_res[(s, best_trim)]["ring_MHz"] for s in MC_SEEDS], "MHz")
    summarize("Carry step 191->192", [ring_res[(s, 192)]["ring_MHz"] - ring_res[(s, 191)]["ring_MHz"] for s in MC_SEEDS], "MHz")
    summarize("Relax (sleep_relax)", [relax_res[s]["relax_kHz"] for s in MC_SEEDS], "kHz")
    mono = sum(1 for s in MC_SEEDS if ring_res[(s, 192)]["ring_MHz"] > ring_res[(s, 191)]["ring_MHz"])
    print(f"  Monotonic 191->192 steps: {mono}/{len(MC_SEEDS)}")
    print(f"  Trap fallback retries   : {trap_retries}/200")
    print(f"  Wrote {out_csv}")


if __name__ == "__main__":
    main()
