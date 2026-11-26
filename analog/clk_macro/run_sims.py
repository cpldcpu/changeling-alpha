#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Verify unified clock macro (rpe_clk_analog) across all operating modes and corners, and export report waveforms."""

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
BUILD_DIR = HERE / "build"

CORNERS = [
    ("tt", "mos_tt", "res_typ", "cap_typ", 1.20, 25),
    ("ss", "mos_ss", "res_wcs", "cap_wcs", 1.08, 125),
    ("ff", "mos_ff", "res_bcs", "cap_bcs", 1.32, -40),
]

MAX_WORKERS = min(10, max(1, int((os.cpu_count() or 4) * 0.75)))
DEFAULT_NGSPICE = "/nix/store/mclawsglbgvysxshnl8rx09d1k7ld8bn-ngspice-45/bin/ngspice"
NGSPICE_BIN = DEFAULT_NGSPICE if Path(DEFAULT_NGSPICE).exists() else (shutil.which("ngspice") or DEFAULT_NGSPICE)


def load_netlist() -> str:
    sp = (BUILD_DIR / "tb_rpe_clk_analog.spice").read_text()
    lines = []
    for line in sp.splitlines():
        s = line.strip()
        if s.lower() == ".end" or s.startswith((".options temp", ".lib corner", "Vdd ", "Ven_ring ", "Ven_relax ", "Vtrim")):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def run_ngspice(deck_text: str, tag: str) -> str:
    deck_path = BUILD_DIR / f"{tag}.sp"
    deck_path.write_text(deck_text)
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env.setdefault("PDK_ROOT", "/home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008")
    env.setdefault("PDK", "ihp-sg13cmos5l")
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


def sim_mode(base: str, cname: str, mlib: str, rlib: str, clib: str, vdd: float, temp: int, mode: str, trim: int) -> dict[str, str]:
    vh = 0.5 * vdd
    hdr = (
        f"* Unified macro {mode} {cname} trim={trim}\n"
        f"{base}"
        f".options temp={temp} method=gear reltol=1e-3\n"
        f".lib cornerMOSlv.lib {mlib}\n"
        f".lib cornerMOShv.lib {mlib}\n"
        f".lib cornerRES.lib {rlib}\n"
        f".lib cornerCAP.lib {clib}\n"
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
        out = run_ngspice(deck, f"mac_{mode}_{cname}_t{trim}")
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
            + ".tran 200p 1.2u\n"
            + ".control\nset num_threads=1\nrun\n"
            + f"meas tran tr1 when v(clk)={vh} rise=1 td=400n\n"
            + f"meas tran tf1 when v(clk)={vh} fall=1 td=tr1\n"
            + f"meas tran tr4 when v(clk)={vh} rise=4 td=400n\n"
            + "let ring_MHz = 3.0 / (tr4 - tr1) / 1e6\n"
            + "let ring_duty = (tf1 - tr1) / ((tr4 - tr1) / 3.0) * 100.0\n"
            + "meas tran vslow_max max v(clk_slow) from=400n to=1.2u\n"
            + "meas tran i_avg avg i(Vdd) from=tr1 to=tr4\n"
            + "let idd_uA = abs(i_avg) * 1e6\n"
            + "print ring_MHz ring_duty vslow_max idd_uA\n.endc\n.end\n"
        )
        out = run_ngspice(deck, f"mac_{mode}_{cname}_t{trim}")
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
            + f"meas tran tr1 when v(clk_slow)={vh} rise=1 td=25u\n"
            + f"meas tran tf1 when v(clk_slow)={vh} fall=1 td=tr1\n"
            + f"meas tran tr3 when v(clk_slow)={vh} rise=3 td=25u\n"
            + "let relax_kHz = 2.0 / (tr3 - tr1) / 1e3\n"
            + "let relax_duty = (tf1 - tr1) / ((tr3 - tr1) / 2.0) * 100.0\n"
            + "meas tran vclk_max max v(clk) from=25u to=75u\n"
            + "meas tran i_avg avg i(Vdd) from=tr1 to=tr3\n"
            + "let idd_uA = abs(i_avg) * 1e6\n"
            + "print relax_kHz relax_duty vclk_max idd_uA\n.endc\n.end\n"
        )
        out = run_ngspice(deck, f"mac_{mode}_{cname}_t{trim}")
        v = parse_vals(out, ["relax_kHz", "relax_duty", "vclk_max", "idd_uA"])
        assert v["vclk_max"] < 0.05, f"clk not gated in sleep_relax: {v}"
        return {
            "mode": mode, "corner": cname, "vdd_V": f"{vdd:.2f}", "temp_C": str(temp), "trim": str(trim),
            "ring_MHz": "0.0000", "ring_duty_pct": "N/A",
            "relax_kHz": f"{v['relax_kHz']:.3f}", "relax_duty_pct": f"{v['relax_duty']:.2f}",
            "idd_uA": f"{v['idd_uA']:.3f}", "idd_standby_nA": "N/A",
        }

    # both_active: settle relax_core cleanly, wake en_ring at 16u, measure simultaneous operation (17u..44u)
    deck = (
        hdr
        + f"Vdd VDD GND pwl(0 0 2u {vdd})\nVen_ring en_ring GND pwl(0 0 16u 0 16.2u {vdd})\nVen_relax en_relax GND pwl(0 0 2u {vdd})\n"
        + ".save v(clk) v(clk_slow) i(Vdd)\n"
        + ".tran 5n 44u uic\n"
        + ".control\nset num_threads=1\nrun\n"
        + f"meas tran ts_r1 when v(clk_slow)={vh} rise=1 td=17u\n"
        + f"meas tran ts_f1 when v(clk_slow)={vh} fall=1 td=ts_r1\n"
        + f"meas tran ts_r2 when v(clk_slow)={vh} rise=2 td=17u\n"
        + "let relax_kHz = 1.0 / (ts_r2 - ts_r1) / 1e3\n"
        + "let relax_duty = (ts_f1 - ts_r1) / (ts_r2 - ts_r1) * 100.0\n"
        + f"meas tran tf_r1 when v(clk)={vh} rise=1 td=20u\n"
        + f"meas tran tf_f1 when v(clk)={vh} fall=1 td=tf_r1\n"
        + f"meas tran tf_r6 when v(clk)={vh} rise=6 td=20u\n"
        + "let ring_MHz = 5.0 / (tf_r6 - tf_r1) / 1e6\n"
        + "let ring_duty = (tf_f1 - tf_r1) / ((tf_r6 - tf_r1) / 5.0) * 100.0\n"
        + "meas tran i_avg avg i(Vdd) from=ts_r1 to=ts_r2\n"
        + "let idd_uA = abs(i_avg) * 1e6\n"
        + "print ring_MHz ring_duty relax_kHz relax_duty idd_uA\n.endc\n.end\n"
    )
    out = run_ngspice(deck, f"mac_{mode}_{cname}_t{trim}")
    v = parse_vals(out, ["ring_MHz", "ring_duty", "relax_kHz", "relax_duty", "idd_uA"])
    return {
        "mode": mode, "corner": cname, "vdd_V": f"{vdd:.2f}", "temp_C": str(temp), "trim": str(trim),
        "ring_MHz": f"{v['ring_MHz']:.4f}", "ring_duty_pct": f"{v['ring_duty']:.2f}",
        "relax_kHz": f"{v['relax_kHz']:.3f}", "relax_duty_pct": f"{v['relax_duty']:.2f}",
        "idd_uA": f"{v['idd_uA']:.3f}", "idd_standby_nA": "N/A",
    }


def export_waveforms(base: str, nom_trim: int = 155) -> None:
    """Export clean sleep_relax (cold-start + cap ramp) and ring_only (nom_trim + vctrl) waveforms for report figures."""
    vdd = 1.20
    # 1) Sleep-mode relaxation cold-start & ramp waveforms (0..45 us)
    wr_path = BUILD_DIR / "wf_relax.txt"
    deck_rel = (
        f"* Waveform relax_core cold-start & oscillation\n{base}"
        f".options temp=25 method=gear reltol=5e-4\n"
        f".lib cornerMOSlv.lib mos_tt\n.lib cornerMOShv.lib mos_tt\n.lib cornerRES.lib res_typ\n.lib cornerCAP.lib cap_typ\n"
        f"{trim_sources(nom_trim, vdd)}"
        f"Vdd VDD GND pwl(0 0 2u {vdd})\nVen_ring en_ring GND dc 0\nVen_relax en_relax GND pwl(0 0 2u {vdd})\n"
        ".save v(clk_slow) v(xmac.xrelax.vcap_a) v(xmac.xrelax.vcap_b) v(xmac.xrelax.vth) v(en_relax)\n"
        ".tran 5n 45u uic\n"
        f".control\nset num_threads=1\nrun\nwrdata {wr_path} v(clk_slow) v(xmac.xrelax.vcap_a) v(xmac.xrelax.vcap_b) v(xmac.xrelax.vth) v(en_relax)\n.endc\n.end\n"
    )
    run_ngspice(deck_rel, "wf_relax")

    # 2) Ring-mode fast waveform (300..600 ns)
    wrg_path = BUILD_DIR / "wf_ring.txt"
    deck_ring = (
        f"* Waveform cco_core oscillation\n{base}"
        f".options temp=25 method=gear reltol=5e-4\n"
        f".lib cornerMOSlv.lib mos_tt\n.lib cornerMOShv.lib mos_tt\n.lib cornerRES.lib res_typ\n.lib cornerCAP.lib cap_typ\n"
        f"{trim_sources(nom_trim, vdd)}"
        f"Vdd VDD GND dc {vdd}\nVen_ring en_ring GND dc {vdd}\nVen_relax en_relax GND dc 0\n"
        ".save v(clk) v(xmac.xcco.n0) v(xmac.xcco.n2)\n"
        ".tran 25p 600n\n"
        f".control\nset num_threads=1\nrun\nwrdata {wrg_path} v(clk) v(xmac.xcco.n0) v(xmac.xcco.n2)\n.endc\n.end\n"
    )
    run_ngspice(deck_ring, "wf_ring")

    # Parse ngspice wrdata format cleanly into CSVs for matplotlib
    for src, dst, cols in [
        (wr_path, RESULTS_DIR / "clk_macro_wf_relax.csv", ["t_s", "clk_slow_V", "vcap_a_V", "vcap_b_V", "vth_V", "en_relax_V"]),
        (wrg_path, RESULTS_DIR / "clk_macro_wf_ring.csv", ["t_s", "clk_V", "n0_V", "n2_V"]),
    ]:
        rows_out = []
        ncols = len(cols) - 1
        for line in src.read_text().splitlines():
            parts = line.split()
            if not parts:
                continue
            vals = [float(parts[0])] + [float(parts[2 * k + 1]) for k in range(ncols)]
            rows_out.append(vals)
        with open(dst, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows_out)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base = load_netlist()
    nom_trim = 155
    jobs = []
    for cname, mlib, rlib, clib, vdd, temp in CORNERS:
        for mode, trim in [
            ("standby", 128),
            ("ring_only", 128),
            ("ring_only", nom_trim),
            ("sleep_relax", nom_trim),
            ("both_active", nom_trim),
        ]:
            jobs.append((cname, mlib, rlib, clib, vdd, temp, mode, trim))

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [(j, ex.submit(sim_mode, base, *j)) for j in jobs]
        for j, fut in futs:
            res = fut.result()
            rows.append(res)
            print(f"[clk_macro] {res['mode']:12s} {res['corner']} trim={res['trim']:>3s}: ring={res['ring_MHz']} MHz, relax={res['relax_kHz']} kHz, I={res['idd_uA']} uA", flush=True)

    with open(RESULTS_DIR / "clk_macro_modes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    export_waveforms(base, nom_trim)
    print("Wrote clk_macro_modes.csv and waveform CSVs to", RESULTS_DIR)


if __name__ == "__main__":
    main()
