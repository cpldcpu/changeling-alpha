#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Run fast parallel ngspice sweeps for Ring Oscillator B (analog/osc_ring_cc)."""

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

DEFAULT_NGSPICE = "/nix/store/mclawsglbgvysxshnl8rx09d1k7ld8bn-ngspice-45/bin/ngspice"
NGSPICE_BIN = DEFAULT_NGSPICE if Path(DEFAULT_NGSPICE).exists() else (shutil.which("ngspice") or DEFAULT_NGSPICE)
MAX_WORKERS = min(6, max(1, (os.cpu_count() or 4) // 2))


def load_base_netlist() -> str:
    sp = (BUILD_DIR / "tb_osc_ring_cc.spice").read_text()
    lines = []
    for line in sp.splitlines():
        s = line.strip()
        if s.lower() == ".end" or s.startswith((".options temp", ".lib corner", "Vdd ", "Ven ", "Vtrim")):
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
    # Start VDD and en at DC operating point so bias settles immediately, kick ring with .ic on n4
    lines = [
        f"Vdd VDD GND dc {vdd}",
        f"Ven en GND dc {vdd}",
    ]
    for b in range(8):
        v = vdd if ((trim >> b) & 1) else 0.0
        lines.append(f"Vtrim{b} trim{b} GND dc {v}")
    return "\n".join(lines) + "\n"


def measure_point(base: str, mlib: str, rlib: str, clib: str, vdd: float, temp: int, trim: int, tag: str) -> dict[str, float]:
    vh = 0.5 * vdd
    t_stop = "420n" if trim < 64 else "250n"
    deck = (
        base
        + trim_sources(trim, vdd)
        + f".options temp={temp} reltol=5e-3 abstol=1e-10 vntol=1e-4 trtol=7\n"
        + f".lib cornerMOSlv.lib {mlib}\n"
        + f".lib cornerRES.lib {rlib}\n"
        + f".lib cornerCAP.lib {clib}\n"
        + ".ic v(XOSC.XCCO.n4)=0\n"
        + ".save v(clk) v(XOSC.ictrl) i(Vdd)\n"
        + f".tran 100p {t_stop}\n"
        + ".control\nrun\n"
        + f"meas tran t_r1 when v(clk)={vh} rise=1 td=80n\n"
        + f"meas tran t_f1 when v(clk)={vh} fall=1 td=t_r1\n"
        + f"meas tran t_r5 when v(clk)={vh} rise=5 td=80n\n"
        + "let freq = 4.0 / (t_r5 - t_r1)\n"
        + "let period = (t_r5 - t_r1) / 4.0\n"
        + "let duty = (t_f1 - t_r1) / period\n"
        + "meas tran i_avg avg i(Vdd) from=t_r1 to=t_r5\n"
        + "let idd_uA = abs(i_avg) * 1e6\n"
        + "meas tran vctrl_n find v(XOSC.ictrl) at=150n\n"
        + "print freq duty idd_uA vctrl_n\n"
        + ".endc\n.end\n"
    )
    out = run_ngspice(deck, tag)
    return parse_vals(out, ["freq", "duty", "idd_uA", "vctrl_n"])


def sim_trim_sweep(base: str) -> dict[str, int]:
    coarse = [0, 32, 64, 96, 128, 160, 192, 224, 255]
    pts_by_corner: dict[str, dict[int, dict[str, float]]] = {c[0]: {} for c in CORNERS}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for cname, mlib, rlib, clib, vdd, temp in CORNERS:
            for tr in coarse:
                fut = ex.submit(measure_point, base, mlib, rlib, clib, vdd, temp, tr, f"ring_cc_{cname}_t{tr}")
                futs[fut] = (cname, tr)
        for fut in concurrent.futures.as_completed(futs):
            cname, tr = futs[fut]
            v = fut.result()
            pts_by_corner[cname][tr] = v
            print(f"[ring_cc] {cname} trim={tr:3d}: {v['freq']/1e6:.2f} MHz, duty={v['duty']*100:.1f}%, I={v['idd_uA']:.1f} uA")

    bounds = {c[0]: [0, 255] for c in CORNERS}
    for _ in range(4):
        mids = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            for cname, mlib, rlib, clib, vdd, temp in CORNERS:
                lo, hi = bounds[cname]
                mid = (lo + hi) // 2
                if mid not in pts_by_corner[cname]:
                    mids[ex.submit(measure_point, base, mlib, rlib, clib, vdd, temp, mid, f"ring_cc_{cname}_t{mid}")] = (cname, mid)
            for fut in concurrent.futures.as_completed(mids):
                cname, mid = mids[fut]
                pts_by_corner[cname][mid] = fut.result()
                print(f"[ring_cc] {cname} trim={mid:3d}: {pts_by_corner[cname][mid]['freq']/1e6:.2f} MHz")
        for cname, *_ in CORNERS:
            lo, hi = bounds[cname]
            mid = (lo + hi) // 2
            if pts_by_corner[cname][mid]["freq"] < 60e6:
                bounds[cname][0] = mid + 1
            else:
                bounds[cname][1] = mid - 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for cname, mlib, rlib, clib, vdd, temp in CORNERS:
            center = max(1, min(254, (bounds[cname][0] + bounds[cname][1]) // 2))
            for tr in (center - 1, center, center + 1):
                if tr not in pts_by_corner[cname]:
                    futs[ex.submit(measure_point, base, mlib, rlib, clib, vdd, temp, tr, f"ring_cc_{cname}_t{tr}")] = (cname, tr)
        for fut in concurrent.futures.as_completed(futs):
            cname, tr = futs[fut]
            pts_by_corner[cname][tr] = fut.result()
            print(f"[ring_cc] {cname} trim={tr:3d}: {pts_by_corner[cname][tr]['freq']/1e6:.2f} MHz")

    rows = []
    best_60_trim: dict[str, int] = {}
    for cname, mlib, rlib, clib, vdd, temp in CORNERS:
        pts = pts_by_corner[cname]
        best_60_trim[cname] = min(pts.keys(), key=lambda t: abs(pts[t]["freq"] - 60e6))
        for tr in sorted(pts.keys()):
            v = pts[tr]
            rows.append({
                "corner": cname,
                "vdd_V": f"{vdd:.2f}",
                "temp_C": str(temp),
                "trim": str(tr),
                "freq_MHz": f"{v['freq'] / 1e6:.4f}",
                "duty_pct": f"{v['duty'] * 100:.2f}",
                "idd_uA": f"{v['idd_uA']:.2f}",
                "vctrl_n_V": f"{v['vctrl_n']:.4f}",
            })

    with open(RESULTS_DIR / "osc_ring_cc_trim.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return best_60_trim


def sim_vdd_temp(base: str, tt_trim: int) -> None:
    tasks = []
    for vdd in [1.08, 1.14, 1.20, 1.26, 1.32]:
        tasks.append(("vdd", vdd, 25, f"ring_cc_vdd_{vdd:.2f}"))
    for temp in [-40, 0, 25, 75, 125]:
        tasks.append(("temp", 1.20, temp, f"ring_cc_temp_{temp}"))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(measure_point, base, "mos_tt", "res_typ", "cap_typ", vdd, temp, tt_trim, tag): (sw, vdd, temp) for sw, vdd, temp, tag in tasks}
        for fut in concurrent.futures.as_completed(futs):
            results[futs[fut]] = fut.result()

    rows = []
    for sw, vdd, temp, _ in tasks:
        v = results[(sw, vdd, temp)]
        rows.append({
            "sweep": sw,
            "corner": "tt",
            "trim": str(tt_trim),
            "vdd_V": f"{vdd:.2f}",
            "temp_C": str(temp),
            "freq_MHz": f"{v['freq'] / 1e6:.4f}",
            "duty_pct": f"{v['duty'] * 100:.2f}",
            "idd_uA": f"{v['idd_uA']:.2f}",
        })
    with open(RESULTS_DIR / "osc_ring_cc_vdd_temp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_supply_step(base: str, tt_trim: int) -> None:
    # Full cold startup from 0V + 50mV VDD step at 12us (single run)
    vdd0, vdd1 = 1.20, 1.25
    src = [
        f"Vdd VDD GND pwl(0 0 1u {vdd0} 12u {vdd0} 12.01u {vdd1})",
        f"Ven en GND pwl(0 0 1u {vdd0} 12u {vdd0} 12.01u {vdd1})",
    ]
    for b in range(8):
        v = vdd0 if ((tt_trim >> b) & 1) else 0.0
        src.append(f"Vtrim{b} trim{b} GND dc {v}")
    deck = (
        base
        + "\n".join(src) + "\n"
        + ".options temp=25 reltol=5e-3 abstol=1e-10 vntol=1e-4 trtol=7\n"
        + ".lib cornerMOSlv.lib mos_tt\n"
        + ".lib cornerRES.lib res_typ\n"
        + ".lib cornerCAP.lib cap_typ\n"
        + ".save v(clk) v(XOSC.ictrl)\n"
        + ".tran 100p 15u uic\n"
        + ".control\nrun\n"
        + "meas tran tb1 when v(clk)=0.6 rise=1 td=10u\n"
        + "meas tran tb5 when v(clk)=0.6 rise=5 td=10u\n"
        + "meas tran ti1 when v(clk)=0.625 rise=1 td=12.1u\n"
        + "meas tran ti5 when v(clk)=0.625 rise=5 td=12.1u\n"
        + "meas tran ts1 when v(clk)=0.625 rise=1 td=14u\n"
        + "meas tran ts5 when v(clk)=0.625 rise=5 td=14u\n"
        + "let f_before = 4.0 / (tb5 - tb1)\n"
        + "let f_immed  = 4.0 / (ti5 - ti1)\n"
        + "let f_settled = 4.0 / (ts5 - ts1)\n"
        + "print f_before f_immed f_settled\n"
        + ".endc\n.end\n"
    )
    out = run_ngspice(deck, "ring_cc_vdd_step")
    v = parse_vals(out, ["f_before", "f_immed", "f_settled"])
    with open(RESULTS_DIR / "osc_ring_cc_supply_step.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["trim", "vdd_before_V", "vdd_after_V", "f_before_MHz", "f_immed_MHz", "f_settled_MHz"])
        w.writeheader()
        w.writerow({
            "trim": str(tt_trim),
            "vdd_before_V": "1.20",
            "vdd_after_V": "1.25",
            "f_before_MHz": f"{v['f_before']/1e6:.4f}",
            "f_immed_MHz": f"{v['f_immed']/1e6:.4f}",
            "f_settled_MHz": f"{v['f_settled']/1e6:.4f}",
        })


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base = load_base_netlist()
    best = sim_trim_sweep(base)
    sim_vdd_temp(base, best["tt"])
    sim_supply_step(base, best["tt"])
    print("Wrote osc_ring_cc CSVs to", RESULTS_DIR)


if __name__ == "__main__":
    main()
