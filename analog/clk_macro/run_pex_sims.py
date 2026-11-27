#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Run post-layout Magic hierarchical PEX ngspice verification across all modes, PVT corners, and trim sweep."""

import concurrent.futures
import csv
import os
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALOG_DIR = HERE.parent
RESULTS_DIR = ANALOG_DIR / "results"
BUILD_PEX = HERE / "build" / "pex"
PEX_SPICE = BUILD_PEX / "rpe_clk_analog_pex.spice"

PDK_ROOT = os.environ.get(
    "PDK_ROOT",
    "/home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008",
)
PDK = os.environ.get("PDK", "ihp-sg13cmos5l")

CORNERS = [
    ("tt", "mos_tt", "res_typ", "cap_typ", 1.20, 25),
    ("ss", "mos_ss", "res_wcs", "cap_wcs", 1.08, 125),
    ("ff", "mos_ff", "res_bcs", "cap_bcs", 1.32, -40),
]

MAX_WORKERS = min(10, max(1, int((os.cpu_count() or 4) * 0.75)))

DEFAULT_NGSPICE = "/nix/store/mclawsglbgvysxshnl8rx09d1k7ld8bn-ngspice-45/bin/ngspice"
NGSPICE_BIN = DEFAULT_NGSPICE if Path(DEFAULT_NGSPICE).exists() else (shutil.which("ngspice") or DEFAULT_NGSPICE)


def run_ngspice(deck_text: str, tag: str) -> str:
    BUILD_PEX.mkdir(parents=True, exist_ok=True)
    deck_path = BUILD_PEX / f"{tag}.sp"
    deck_path.write_text(deck_text)
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["PDK_ROOT"] = PDK_ROOT
    env["PDK"] = PDK
    res = subprocess.run([NGSPICE_BIN, "-b", str(deck_path)], cwd=ANALOG_DIR, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ngspice failed for {tag}:\n{res.stdout[-1200:]}\n{res.stderr[-1200:]}")
    return res.stdout


def parse_vals(out: str, names: list[str]) -> dict[str, float]:
    vals = {}
    for n in names:
        m = re.search(rf"^\s*{re.escape(n)}\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out, re.MULTILINE | re.IGNORECASE)
        if not m:
            raise ValueError(f"Could not parse '{n}' from ngspice output:\n{out[-1200:]}")
        vals[n] = float(m.group(1))
    return vals


def trim_sources(trim: int, vdd: float) -> str:
    return "\n".join(f"Vtrim{i} trim{i} GND dc {vdd if ((trim >> i) & 1) else 0.0}" for i in range(8)) + "\n"


def sim_mode(cname: str, mlib: str, rlib: str, clib: str, vdd: float, temp: int, mode: str, trim: int) -> dict[str, str]:
    vh = 0.5 * vdd
    rsh = "1e14" if mode == "standby" else "1e12"
    hdr = (
        f"* PEX {mode} {cname} trim={trim}\n"
        f".options temp={temp} method=gear reltol=1e-3 rshunt={rsh}\n"
        f".lib cornerMOSlv.lib {mlib}\n"
        f".lib cornerMOShv.lib {mlib}\n"
        f".lib cornerRES.lib {rlib}\n"
        f".lib cornerCAP.lib {clib}\n"
        f".include {PEX_SPICE}\n"
        f"Xmac VDD GND en_ring en_relax trim0 trim1 trim2 trim3 trim4 trim5 trim6 trim7 clk clk_slow rpe_clk_analog\n"
        f"{trim_sources(trim, vdd)}"
    )

    if mode == "standby":
        deck = (
            hdr
            + f"Vdd VDD GND dc {vdd}\nVen_ring en_ring GND dc 0\nVen_relax en_relax GND dc 0\n"
            + ".op\n.control\nset num_threads=1\nrun\n"
            + "let idd_nA = abs(i(Vdd)) * 1e9\n"
            + "let vclk_max = v(clk)\nlet vslow_max = v(clk_slow)\n"
            + "print idd_nA vclk_max vslow_max\n.endc\n.end\n"
        )
        out = run_ngspice(deck, f"pex_{mode}_{cname}_t{trim}")
        v = parse_vals(out, ["idd_nA", "vclk_max", "vslow_max"])
        return {
            "mode": mode, "corner": cname, "vdd_V": f"{vdd:.2f}", "temp_C": str(temp), "trim": str(trim),
            "ring_MHz": "0.0000", "ring_duty_pct": "N/A", "relax_kHz": "0.000", "relax_duty_pct": "N/A",
            "idd_uA": f"{v['idd_nA']/1e3:.6f}", "idd_standby_nA": f"{v['idd_nA']:.4f}",
        }

    if mode == "ring_only":
        deck = (
            hdr
            + f"Vdd VDD GND dc {vdd}\nVen_ring en_ring GND dc {vdd}\nVen_relax en_relax GND dc 0\n"
            + ".save v(clk) v(clk_slow) i(Vdd)\n"
            + ".tran 200p 700n\n"
            + ".control\nset num_threads=1\nrun\n"
            + f"meas tran tr1 when v(clk)={vh} rise=1 td=300n\n"
            + f"meas tran tf1 when v(clk)={vh} fall=1 td=tr1\n"
            + f"meas tran tr4 when v(clk)={vh} rise=4 td=300n\n"
            + "let ring_MHz = 3.0 / (tr4 - tr1) / 1e6\n"
            + "let ring_duty = (tf1 - tr1) / ((tr4 - tr1) / 3.0) * 100.0\n"
            + "meas tran vslow_max max v(clk_slow) from=300n to=700n\n"
            + "meas tran i_avg avg i(Vdd) from=tr1 to=tr4\n"
            + "let idd_uA = abs(i_avg) * 1e6\n"
            + "print ring_MHz ring_duty vslow_max idd_uA\n.endc\n.end\n"
        )
        out = run_ngspice(deck, f"pex_{mode}_{cname}_t{trim}")
        v = parse_vals(out, ["ring_MHz", "ring_duty", "vslow_max", "idd_uA"])
        assert v["vslow_max"] < 0.05, f"clk_slow not gated in ring_only: {v}"
        return {
            "mode": mode, "corner": cname, "vdd_V": f"{vdd:.2f}", "temp_C": str(temp), "trim": str(trim),
            "ring_MHz": f"{v['ring_MHz']:.4f}", "ring_duty_pct": f"{v['ring_duty']:.2f}",
            "relax_kHz": "0.000", "relax_duty_pct": "N/A", "idd_uA": f"{v['idd_uA']:.3f}", "idd_standby_nA": "N/A",
        }

    if mode == "sleep_relax":
        deck = (
            hdr
            + f"Vdd VDD GND pwl(0 0 2u {vdd})\nVen_ring en_ring GND dc 0\nVen_relax en_relax GND pwl(0 0 2u {vdd})\n"
            + ".save v(clk) v(clk_slow) i(Vdd)\n"
            + ".tran 10n 75u uic\n"
            + ".control\nset num_threads=1\nrun\n"
            + f"meas tran tr1 when v(clk_slow)={vh} rise=1 td=22u\n"
            + f"meas tran tf1 when v(clk_slow)={vh} fall=1 td=tr1\n"
            + f"meas tran tr3 when v(clk_slow)={vh} rise=3 td=22u\n"
            + "let relax_kHz = 2.0 / (tr3 - tr1) / 1e3\n"
            + "let relax_duty = (tf1 - tr1) / ((tr3 - tr1) / 2.0) * 100.0\n"
            + "meas tran vclk_max max v(clk) from=22u to=75u\n"
            + "meas tran i_avg avg i(Vdd) from=tr1 to=tr3\n"
            + "let idd_uA = abs(i_avg) * 1e6\n"
            + "print relax_kHz relax_duty vclk_max idd_uA\n.endc\n.end\n"
        )
        out = run_ngspice(deck, f"pex_{mode}_{cname}_t{trim}")
        v = parse_vals(out, ["relax_kHz", "relax_duty", "vclk_max", "idd_uA"])
        assert v["vclk_max"] < 0.05, f"clk not gated in sleep_relax: {v}"
        return {
            "mode": mode, "corner": cname, "vdd_V": f"{vdd:.2f}", "temp_C": str(temp), "trim": str(trim),
            "ring_MHz": "0.0000", "ring_duty_pct": "N/A",
            "relax_kHz": f"{v['relax_kHz']:.3f}", "relax_duty_pct": f"{v['relax_duty']:.2f}",
            "idd_uA": f"{v['idd_uA']:.3f}", "idd_standby_nA": "N/A",
        }

    # both_active: settle relax_core cleanly, wake en_ring at 14u, measure simultaneous operation (15u..42u)
    deck = (
        hdr
        + f"Vdd VDD GND pwl(0 0 2u {vdd})\nVen_ring en_ring GND pwl(0 0 14u 0 14.2u {vdd})\nVen_relax en_relax GND pwl(0 0 2u {vdd})\n"
        + ".save v(clk) v(clk_slow) i(Vdd)\n"
        + ".tran 1n 42u uic\n"
        + ".control\nset num_threads=1\nrun\n"
        + f"meas tran ts_r1 when v(clk_slow)={vh} rise=1 td=15u\n"
        + f"meas tran ts_f1 when v(clk_slow)={vh} fall=1 td=ts_r1\n"
        + f"meas tran ts_r2 when v(clk_slow)={vh} rise=2 td=15u\n"
        + "let relax_kHz = 1.0 / (ts_r2 - ts_r1) / 1e3\n"
        + "let relax_duty = (ts_f1 - ts_r1) / (ts_r2 - ts_r1) * 100.0\n"
        + f"meas tran tf_r1 when v(clk)={vh} rise=1 td=18u\n"
        + f"meas tran tf_f1 when v(clk)={vh} fall=1 td=tf_r1\n"
        + f"meas tran tf_r21 when v(clk)={vh} rise=21 td=18u\n"
        + "let ring_MHz = 20.0 / (tf_r21 - tf_r1) / 1e6\n"
        + "let ring_duty = (tf_f1 - tf_r1) / ((tf_r21 - tf_r1) / 20.0) * 100.0\n"
        + "meas tran i_avg avg i(Vdd) from=ts_r1 to=ts_r2\n"
        + "let idd_uA = abs(i_avg) * 1e6\n"
        + "print ring_MHz ring_duty relax_kHz relax_duty idd_uA\n.endc\n.end\n"
    )
    out = run_ngspice(deck, f"pex_{mode}_{cname}_t{trim}")
    v = parse_vals(out, ["ring_MHz", "ring_duty", "relax_kHz", "relax_duty", "idd_uA"])
    return {
        "mode": mode, "corner": cname, "vdd_V": f"{vdd:.2f}", "temp_C": str(temp), "trim": str(trim),
        "ring_MHz": f"{v['ring_MHz']:.4f}", "ring_duty_pct": f"{v['ring_duty']:.2f}",
        "relax_kHz": f"{v['relax_kHz']:.3f}", "relax_duty_pct": f"{v['relax_duty']:.2f}",
        "idd_uA": f"{v['idd_uA']:.3f}", "idd_standby_nA": "N/A",
    }


def main() -> None:
    if not PEX_SPICE.exists():
        raise FileNotFoundError(f"Run extract_pex.py first: {PEX_SPICE}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fast tt trim sweep FIRST to locate exact post-layout 60.0 MHz trim code + ss/ff bounds
    tt_args = CORNERS[0]
    sweep_codes = [0, 32, 64, 96, 128, 144, 160, 192, 224, 255]
    sweep_rows: dict[int, dict[str, str]] = {}
    corner_extras: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs_tt = [(tc, ex.submit(sim_mode, *tt_args, "ring_only", tc)) for tc in sweep_codes]
        futs_c = [(cargs[0], tc, ex.submit(sim_mode, *cargs, "ring_only", tc)) for cargs in CORNERS[1:] for tc in (0, 128, 255)]
        for tc, fut in futs_tt:
            r = fut.result()
            sweep_rows[tc] = r
            print(f"[pex_sweep] tt trim={tc:3d}: ring={r['ring_MHz']} MHz, I={r['idd_uA']} uA", flush=True)
        for cname, tc, fut in futs_c:
            r = fut.result()
            corner_extras.append(r)
            print(f"[pex_bnd]   {cname} trim={tc:3d}: ring={r['ring_MHz']} MHz, I={r['idd_uA']} uA", flush=True)

    # Refine +/-3 around crossing for exact post-layout tt 60.0 MHz trim code
    pts = sorted((tc, float(r["ring_MHz"])) for tc, r in sweep_rows.items())
    est_trim = 128
    for (t0, f0), (t1, f1) in zip(pts, pts[1:]):
        if f0 <= 60.0 <= f1 and f1 > f0:
            est_trim = round(t0 + (60.0 - f0) * (t1 - t0) / (f1 - f0))
            break
    refine_codes = [c for c in range(max(0, est_trim - 3), min(255, est_trim + 4)) if c not in sweep_rows]
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for tc, fut in [(tc, ex.submit(sim_mode, *tt_args, "ring_only", tc)) for tc in refine_codes]:
            r = fut.result()
            sweep_rows[tc] = r
            print(f"[pex_refine] tt trim={tc:3d}: ring={r['ring_MHz']} MHz, I={r['idd_uA']} uA", flush=True)

    best_trim = min(sweep_rows.keys(), key=lambda t: abs(float(sweep_rows[t]["ring_MHz"]) - 60.0))
    print(f"==> Post-layout tt 60 MHz best_trim = {best_trim} ({sweep_rows[best_trim]['ring_MHz']} MHz)", flush=True)

    # 2. All 15 Mode x Corner checks using boot default (128) & PEX-recentered (best_trim)
    jobs = []
    for cname, mlib, rlib, clib, vdd, temp in CORNERS:
        for mode, trim in [
            ("standby", 128),
            ("ring_only", 128),
            ("ring_only", best_trim),
            ("sleep_relax", best_trim),
            ("both_active", best_trim),
        ]:
            jobs.append((cname, mlib, rlib, clib, vdd, temp, mode, trim))

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [(j, ex.submit(sim_mode, *j)) for j in jobs]
        for _, fut in futs:
            res = fut.result()
            rows.append(res)
            print(
                f"[pex] {res['mode']:12s} {res['corner']} trim={res['trim']:>3s}: "
                f"ring={res['ring_MHz']} MHz, relax={res['relax_kHz']} kHz, I={res['idd_uA']} uA",
                flush=True,
            )

    with open(RESULTS_DIR / "clk_macro_pex.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Add best_trim rows for ss & ff as corner_trim tags + save full sweep
    for r in rows:
        if r["mode"] == "ring_only" and int(r["trim"]) == best_trim:
            corner_extras.append(dict(r, corner=f"{r['corner']}_nom60"))
    for cargs in CORNERS:
        r_max = next((r for r in corner_extras if r["corner"] == cargs[0] and int(r["trim"]) == 255), sweep_rows[255])
        corner_extras.append(dict(r_max, corner=f"{cargs[0]}_max"))

    all_trim_rows = [sweep_rows[k] for k in sorted(sweep_rows.keys())] + corner_extras
    with open(RESULTS_DIR / "clk_macro_pex_trim.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_trim_rows[0].keys()))
        w.writeheader()
        w.writerows(all_trim_rows)

    print("Wrote clk_macro_pex.csv and clk_macro_pex_trim.csv to", RESULTS_DIR)


if __name__ == "__main__":
    main()
