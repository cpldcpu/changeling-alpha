#!/usr/bin/env python3
"""Run fast foundry-calibrated active-loop sweeps + full-netlist golden cross-check for Ring Oscillator A."""

import concurrent.futures
import csv
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALOG_DIR = HERE.parent
RESULTS_DIR = ANALOG_DIR / "results"
BUILD_DIR = HERE / "build"

CORNERS = [
    ("tt", "mos_tt", 1.20, 25),
    ("ss", "mos_ss", 1.08, 125),
    ("ff", "mos_ff", 1.32, -40),
]

MAX_WORKERS = min(12, max(1, int((os.cpu_count() or 4) * 0.75)))


def resolve_ngspice() -> str:
    res = subprocess.run(
        ["nix", "shell", "nixpkgs#ngspice", "--command", "which", "ngspice"],
        capture_output=True, text=True, check=True,
    )
    return res.stdout.strip()


NGSPICE_BIN = resolve_ngspice()


def run_ngspice(deck_text: str, tag: str, omp_threads: int = 1) -> str:
    deck_path = BUILD_DIR / f"{tag}.sp"
    deck_path.write_text(deck_text)
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(omp_threads)
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


def build_active_loop_deck(trim: int, mlib: str, vdd: float, temp: int, step_from: int | None = None) -> str:
    """Electrically equivalent active-loop SPICE deck matching osc_ring_std.sch cells & Liberty-calibrated mux2_1 pin cap (2.83 fF)."""
    n_taps = 127 - (trim >> 1)
    fine_bit = trim & 1

    lines = [
        f"* Active-loop equivalent of osc_ring_std (trim={trim}, n_taps={n_taps}, fine={fine_bit})",
        f".options temp={temp} klu method=trap reltol=1e-3 abstol=1e-11 vntol=1e-5 trtol=2",
        f".lib cornerMOSlv.lib {mlib}",
        ".include sg13cmos5l_stdcell.spice",
        f"Vdd VDD GND dc {vdd}",
        f"Ven en GND pwl(0 0 1n 0 1.2n {vdd})",
        f"Vtrim0 trim0 GND dc {vdd if fine_bit else 0.0}",
        "Cload clk GND 50f",
        "XNAND n_nand loop_fb en VDD GND sg13cmos5l_nand2_2",
        "XOUT_INV net_o n_nand VDD GND sg13cmos5l_inv_2",
        "XOUT_BUF clk net_o VDD GND sg13cmos5l_buf_4",
    ]
    prev = "n_nand"
    for i in range(8):
        nxt = f"fix_{i}" if i < 7 else "fix_out"
        lines.append(f"XFIX{i} {nxt} {prev} VDD GND sg13cmos5l_dlygate4sd3_1")
        prev = nxt

    lines.extend([
        "XFINE_SLOW fine_slow fix_out VDD GND sg13cmos5l_dlygate4sd1_1",
        "XFINE_FAST fine_fast fix_out VDD GND sg13cmos5l_buf_1",
        "XMUX_FINE t_0 fine_slow fine_fast trim0 VDD GND sg13cmos5l_mux2_1",
    ])

    for k in range(n_taps):
        lines.append(f"XDLY_{k} t_{k+1} t_{k} VDD GND sg13cmos5l_dlygate4sd1_1")
        lines.append(f"Cmtap_{k} t_{k} GND 2.83f")

    if step_from is not None:
        n_from = 127 - (step_from >> 1)
        n_max = max(n_taps, n_from)
        for k in range(n_taps, n_max):
            lines.append(f"XDLY_{k} t_{k+1} t_{k} VDD GND sg13cmos5l_dlygate4sd1_1")
            lines.append(f"Cmtap_{k} t_{k} GND 2.83f")
        if n_max < 127:
            lines.append(f"XDLY_TAIL t_tail t_{n_max} VDD GND sg13cmos5l_dlygate4sd1_1")
        lines.append(f"Vstep sel_step GND pwl(0 0 50n 0 50.1n {vdd})")
        lines.append(f"XMUX_L0 mx_0 t_{n_from} t_{n_taps} sel_step VDD GND sg13cmos5l_mux2_1")
    else:
        if n_taps < 127:
            lines.append(f"XDLY_TAIL t_tail t_{n_taps} VDD GND sg13cmos5l_dlygate4sd1_1")
        lines.append(f"XMUX_L0 mx_0 t_{n_taps} GND GND VDD GND sg13cmos5l_mux2_1")

    for lvl in range(1, 7):
        in_n = f"mx_{lvl-1}"
        out_n = f"mx_{lvl}" if lvl < 6 else "loop_fb"
        lines.append(f"XMUX_L{lvl} {out_n} {in_n} GND GND VDD GND sg13cmos5l_mux2_1")

    return "\n".join(lines) + "\n"


def measure_point(mlib: str, vdd: float, temp: int, trim: int, tag: str) -> dict[str, float]:
    vh = 0.5 * vdd
    n_taps = 127 - (trim >> 1)
    if mlib == "mos_ss":
        scale = 2.0
    elif mlib == "mos_ff":
        scale = 0.78
    elif temp >= 75:
        scale = 1.25
    elif vdd <= 1.14:
        scale = 1.15
    else:
        scale = 1.05
    t_per_est = (7.8 + 0.23 * n_taps) * scale
    t_stop = f"{max(25, int(2.3 * t_per_est + 8))}n"

    deck = (
        build_active_loop_deck(trim, mlib, vdd, temp)
        + ".save v(clk) i(Vdd)\n"
        + f".tran 100p {t_stop}\n"
        + ".control\nset num_threads=1\nrun\n"
        + f"meas tran t_f1 when v(clk)={vh} fall=1 td=3n\n"
        + f"meas tran t_r1 when v(clk)={vh} rise=1 td=t_f1\n"
        + f"meas tran t_f2 when v(clk)={vh} fall=2 td=3n\n"
        + "let period = t_f2 - t_f1\n"
        + "let freq = 1.0 / period\n"
        + "let duty = (t_f2 - t_r1) / period\n"
        + "meas tran i_avg avg i(Vdd) from=t_f1 to=t_f2\n"
        + "let idd_mA = abs(i_avg) * 1e3\n"
        + "print freq duty idd_mA\n"
        + ".endc\n.end\n"
    )
    out = run_ngspice(deck, tag, omp_threads=1)
    return parse_vals(out, ["freq", "duty", "idd_mA"])


def sim_trim_sweep() -> tuple[dict[str, int], dict[str, dict[int, dict[str, float]]]]:
    coarse = [0, 64, 128, 192, 255]
    pts_by_corner: dict[str, dict[int, dict[str, float]]] = {c[0]: {} for c in CORNERS}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for cname, mlib, vdd, temp in CORNERS:
            for tr in coarse:
                fut = ex.submit(measure_point, mlib, vdd, temp, tr, f"ring_std_{cname}_t{tr}")
                futs[fut] = (cname, tr)
        for fut in concurrent.futures.as_completed(futs):
            cname, tr = futs[fut]
            v = fut.result()
            pts_by_corner[cname][tr] = v
            print(f"[ring_std] {cname} trim={tr:3d}: {v['freq']/1e6:.2f} MHz, duty={v['duty']*100:.1f}%, I={v['idd_mA']:.3f} mA", flush=True)

    bounds = {c[0]: [0, 255] for c in CORNERS}
    for _ in range(4):
        mids = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            for cname, mlib, vdd, temp in CORNERS:
                lo, hi = bounds[cname]
                mid = (lo + hi) // 2
                if mid not in pts_by_corner[cname]:
                    mids[ex.submit(measure_point, mlib, vdd, temp, mid, f"ring_std_{cname}_t{mid}")] = (cname, mid)
            for fut in concurrent.futures.as_completed(mids):
                cname, mid = mids[fut]
                pts_by_corner[cname][mid] = fut.result()
                print(f"[ring_std] {cname} trim={mid:3d}: {pts_by_corner[cname][mid]['freq']/1e6:.2f} MHz", flush=True)
        for cname, *_ in CORNERS:
            lo, hi = bounds[cname]
            mid = (lo + hi) // 2
            if pts_by_corner[cname][mid]["freq"] < 60e6:
                bounds[cname][0] = mid + 1
            else:
                bounds[cname][1] = mid - 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for cname, mlib, vdd, temp in CORNERS:
            center = max(1, min(254, (bounds[cname][0] + bounds[cname][1]) // 2))
            for tr in (center - 1, center, center + 1):
                if tr not in pts_by_corner[cname]:
                    futs[ex.submit(measure_point, mlib, vdd, temp, tr, f"ring_std_{cname}_t{tr}")] = (cname, tr)
        for fut in concurrent.futures.as_completed(futs):
            cname, tr = futs[fut]
            pts_by_corner[cname][tr] = fut.result()
            print(f"[ring_std] {cname} trim={tr:3d}: {pts_by_corner[cname][tr]['freq']/1e6:.2f} MHz", flush=True)

    rows = []
    best_60_trim: dict[str, int] = {}
    for cname, mlib, vdd, temp in CORNERS:
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
                "idd_mA": f"{v['idd_mA']:.4f}",
            })

    with open(RESULTS_DIR / "osc_ring_std_trim.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return best_60_trim, pts_by_corner


def sim_vdd_temp(tt_trim: int) -> None:
    tasks = []
    for vdd in [1.08, 1.14, 1.20, 1.26, 1.32]:
        tasks.append(("vdd", vdd, 25, f"ring_std_vdd_{vdd:.2f}"))
    for temp in [-40, 0, 25, 75, 125]:
        tasks.append(("temp", 1.20, temp, f"ring_std_temp_{temp}"))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(measure_point, "mos_tt", vdd, temp, tt_trim, tag): (sw, vdd, temp) for sw, vdd, temp, tag in tasks}
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
            "idd_mA": f"{v['idd_mA']:.4f}",
        })
    with open(RESULTS_DIR / "osc_ring_std_vdd_temp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_tap_step(tt_trim: int) -> None:
    cases = [
        (tt_trim, min(255, tt_trim + 1), "lsb_step"),
        (127, 128, "msb_boundary"),
    ]

    def run_case(t_from: int, t_to: int, label: str) -> dict[str, str]:
        vdd, vh = 1.20, 0.6
        if (t_from >> 1) == (t_to >> 1):
            deck = build_active_loop_deck(t_from, "mos_tt", vdd, 25)
            deck = deck.replace(f"Vtrim0 trim0 GND dc {vdd if (t_from & 1) else 0.0}",
                                f"Vtrim0 trim0 GND pwl(0 {vdd if (t_from & 1) else 0.0} 50n {vdd if (t_from & 1) else 0.0} 50.1n {vdd if (t_to & 1) else 0.0})")
        else:
            deck = build_active_loop_deck(t_to, "mos_tt", vdd, 25, step_from=t_from)
            if (t_from & 1) != (t_to & 1):
                deck = deck.replace(f"Vtrim0 trim0 GND dc {vdd if (t_to & 1) else 0.0}",
                                    f"Vtrim0 trim0 GND pwl(0 {vdd if (t_from & 1) else 0.0} 50n {vdd if (t_from & 1) else 0.0} 50.1n {vdd if (t_to & 1) else 0.0})")
        deck += (
            ".save v(clk)\n"
            ".tran 100p 115n\n"
            ".control\nset num_threads=1\nrun\n"
            f"meas tran tb_r1 when v(clk)={vh} rise=1 td=3n\n"
            f"meas tran tb_r2 when v(clk)={vh} rise=2 td=3n\n"
            f"meas tran ta_r1 when v(clk)={vh} rise=1 td=55n\n"
            f"meas tran ta_r2 when v(clk)={vh} rise=2 td=55n\n"
            "let f_before = 1.0 / (tb_r2 - tb_r1)\n"
            "let f_after  = 1.0 / (ta_r2 - ta_r1)\n"
            f"meas tran t_step_r1 when v(clk)={vh} rise=1 td=48n\n"
            f"meas tran t_step_f1 when v(clk)={vh} fall=1 td=t_step_r1\n"
            f"meas tran t_step_r2 when v(clk)={vh} rise=2 td=48n\n"
            "let trans_period_ns = (t_step_r2 - t_step_r1) * 1e9\n"
            "let trans_hi_ns = (t_step_f1 - t_step_r1) * 1e9\n"
            "print f_before f_after trans_period_ns trans_hi_ns\n"
            ".endc\n.end\n"
        )
        out = run_ngspice(deck, f"ring_std_step_{label}", omp_threads=1)
        v = parse_vals(out, ["f_before", "f_after", "trans_period_ns", "trans_hi_ns"])
        return {
            "case": label,
            "trim_from": str(t_from),
            "trim_to": str(t_to),
            "f_before_MHz": f"{v['f_before'] / 1e6:.4f}",
            "f_after_MHz": f"{v['f_after'] / 1e6:.4f}",
            "trans_period_ns": f"{v['trans_period_ns']:.3f}",
            "trans_hi_ns": f"{v['trans_hi_ns']:.3f}",
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        rows = list(ex.map(lambda args: run_case(*args), cases))
    with open(RESULTS_DIR / "osc_ring_std_tap_step.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_golden_check(active_tt_255: dict[str, float]) -> None:
    """Run full unmodified xschem netlist tb_osc_ring_std.spice at tt, trim=255 (<= 25% CPU) and compare."""
    sp = (BUILD_DIR / "tb_osc_ring_std.spice").read_text()
    lines = []
    for line in sp.splitlines():
        s = line.strip()
        if s.lower() == ".end" or s.startswith((".options temp", ".lib cornerMOSlv", "Vdd ", "Ven ", "Vtrim")):
            continue
        lines.append(line)
    base = "\n".join(lines) + "\n"
    trim = 255
    vdd = 1.20
    srcs = [f"Vdd VDD GND dc {vdd}", f"Ven en GND pwl(0 0 1n 0 1.2n {vdd})"]
    for b in range(8):
        srcs.append(f"Vtrim{b} trim{b} GND dc {vdd if ((trim >> b) & 1) else 0.0}")
    deck = (
        base
        + "\n".join(srcs) + "\n"
        + ".options temp=25 klu method=trap reltol=1e-3 abstol=1e-11 vntol=1e-5 trtol=2\n"
        + ".lib cornerMOSlv.lib mos_tt\n"
        + ".save v(clk)\n"
        + ".tran 200p 40n\n"
        + ".control\nset num_threads=8\nrun\n"
        + "meas tran t_r1 when v(clk)=0.6 rise=1 td=10n\n"
        + "meas tran t_f1 when v(clk)=0.6 fall=1 td=t_r1\n"
        + "meas tran t_r3 when v(clk)=0.6 rise=3 td=10n\n"
        + "let freq = 2.0 / (t_r3 - t_r1)\n"
        + "let period = (t_r3 - t_r1) / 2.0\n"
        + "let duty = (t_f1 - t_r1) / period\n"
        + "print freq duty\n"
        + ".endc\n.end\n"
    )
    out = run_ngspice(deck, "ring_std_golden_tt_255", omp_threads=8)
    g = parse_vals(out, ["freq", "duty"])
    diff_pct = (g["freq"] - active_tt_255["freq"]) / g["freq"] * 100.0
    print(f"[golden] full={g['freq']/1e6:.3f} MHz vs active={active_tt_255['freq']/1e6:.3f} MHz (diff={diff_pct:+.2f}%)", flush=True)
    with open(RESULTS_DIR / "osc_ring_std_golden_check.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["corner", "trim", "full_netlist_MHz", "active_loop_MHz", "diff_pct", "full_duty_pct", "active_duty_pct"])
        w.writeheader()
        w.writerow({
            "corner": "tt",
            "trim": "255",
            "full_netlist_MHz": f"{g['freq']/1e6:.4f}",
            "active_loop_MHz": f"{active_tt_255['freq']/1e6:.4f}",
            "diff_pct": f"{diff_pct:+.3f}",
            "full_duty_pct": f"{g['duty']*100:.2f}",
            "active_duty_pct": f"{active_tt_255['duty']*100:.2f}",
        })


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    best, pts = sim_trim_sweep()
    sim_vdd_temp(best["tt"])
    sim_tap_step(best["tt"])
    sim_golden_check(pts["tt"][255])
    print("Wrote osc_ring_std CSVs to", RESULTS_DIR)


if __name__ == "__main__":
    main()
