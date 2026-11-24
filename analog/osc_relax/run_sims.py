#!/usr/bin/env python3
"""Run fast parallel ngspice simulations for the Relaxation Oscillator (analog/osc_relax)."""

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
    ("tt", "mos_tt", "res_typ", "cap_typ", 1.20, 25),
    ("ss", "mos_ss", "res_wcs", "cap_wcs", 1.08, 125),
    ("ff", "mos_ff", "res_bcs", "cap_bcs", 1.32, -40),
]


def resolve_ngspice() -> str:
    res = subprocess.run(
        ["nix", "shell", "nixpkgs#ngspice", "--command", "which", "ngspice"],
        capture_output=True, text=True, check=True,
    )
    return res.stdout.strip()


NGSPICE_BIN = resolve_ngspice()
MAX_WORKERS = min(6, max(1, (os.cpu_count() or 4) // 2))


def load_netlist(fname: str) -> str:
    sp = (BUILD_DIR / fname).read_text()
    lines = []
    for line in sp.splitlines():
        s = line.strip()
        if s.lower() == ".end" or s.startswith((".options temp", ".lib corner", "Vdd ", "Ven ")):
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


def measure_relax(base: str, mlib: str, rlib: str, clib: str, vdd: float, temp: int, tag: str, cold_start: bool = False) -> dict[str, float]:
    vh = 0.5 * vdd
    if cold_start:
        vdd_line = f"Vdd VDD GND pwl(0 0 2u {vdd})\nVen en GND pwl(0 0 2u {vdd})\n"
        uic = "uic"
        td = "25u"
        tstop = "120u"
    else:
        vdd_line = f"Vdd VDD GND dc {vdd}\nVen en GND dc {vdd}\n"
        uic = ""
        td = "20u"
        tstop = "90u"

    deck = (
        base
        + vdd_line
        + f".options temp={temp} method=gear reltol=1e-3 abstol=1e-11 vntol=1e-4\n"
        + f".lib cornerMOSlv.lib {mlib}\n"
        + f".lib cornerMOShv.lib {mlib}\n"
        + f".lib cornerRES.lib {rlib}\n"
        + f".lib cornerCAP.lib {clib}\n"
        + ("" if cold_start else ".ic v(XOSC.vcap_a)=0 v(XOSC.vcap_b)=0 v(XOSC.q)=0\n")
        + ".save v(clk_slow) v(XOSC.vth) v(XOSC.vcap_a) i(Vdd)\n"
        + f".tran 50n {tstop} {uic}\n"
        + ".control\nrun\n"
        + f"meas tran t_r1 when v(clk_slow)={vh} rise=1 td={td}\n"
        + f"meas tran t_f1 when v(clk_slow)={vh} fall=1 td=t_r1\n"
        + f"meas tran t_r4 when v(clk_slow)={vh} rise=4 td={td}\n"
        + "let freq = 3.0 / (t_r4 - t_r1)\n"
        + "let period = (t_r4 - t_r1) / 3.0\n"
        + "let duty = (t_f1 - t_r1) / period\n"
        + "meas tran i_avg avg i(Vdd) from=t_r1 to=t_r4\n"
        + "let idd_uA = abs(i_avg) * 1e6\n"
        + "meas tran vth_V avg v(XOSC.vth) from=t_r1 to=t_r4\n"
        + "print freq duty idd_uA vth_V\n"
        + ".endc\n.end\n"
    )
    out = run_ngspice(deck, tag)
    return parse_vals(out, ["freq", "duty", "idd_uA", "vth_V"])


def sim_corners(base: str) -> None:
    tasks = []
    for cname, mlib, rlib, clib, vdd, temp in CORNERS:
        tasks.append((cname, mlib, rlib, clib, vdd, temp, False, f"relax_{cname}"))
        tasks.append((cname, mlib, rlib, clib, vdd, temp, True, f"relax_{cname}_cold"))

    res = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(measure_relax, base, mlib, rlib, clib, vdd, temp, tag, cold): (cname, cold)
                for cname, mlib, rlib, clib, vdd, temp, cold, tag in tasks}
        for fut in concurrent.futures.as_completed(futs):
            cname, cold = futs[fut]
            res[(cname, cold)] = fut.result()
            print(f"[relax] {cname} cold={cold}: {res[(cname, cold)]['freq']/1e3:.2f} kHz, duty={res[(cname, cold)]['duty']*100:.1f}%, I={res[(cname, cold)]['idd_uA']:.2f} uA")

    rows = []
    for cname, mlib, rlib, clib, vdd, temp in CORNERS:
        v = res[(cname, False)]
        vc = res[(cname, True)]
        rows.append({
            "corner": cname,
            "vdd_V": f"{vdd:.2f}",
            "temp_C": str(temp),
            "freq_kHz": f"{v['freq']/1e3:.3f}",
            "duty_pct": f"{v['duty']*100:.2f}",
            "vth_V": f"{v['vth_V']:.4f}",
            "idd_uA": f"{v['idd_uA']:.3f}",
            "cold_start_freq_kHz": f"{vc['freq']/1e3:.3f}",
        })
    with open(RESULTS_DIR / "osc_relax_corners.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_leakage_at_125c() -> tuple[float, float]:
    """Explicitly measure 125 C switch + cap off-leakage vs charging current."""
    deck = (
        ".options temp=125\n"
        ".lib cornerMOSlv.lib mos_ss\n"
        ".lib cornerMOShv.lib mos_ss\n"
        ".lib cornerCAP.lib cap_wcs\n"
        "Vdd vdd 0 1.08\n"
        "Vcap_a cap_a 0 0.42\n"
        "Xsw cap_a 0 0 0 sg13_hv_nmos w=0.5u l=0.5u ng=1 m=1\n"
        "Vcap_b cap_b 0 0.42\n"
        "Xsv cap_b 0 cap_b 0 sg13_hv_svaricap w=9.0u l=0.8u Nx=10\n"
        ".op\n.control\nrun\n"
        "let i_sw_nA = abs(i(Vcap_a)) * 1e9\n"
        "let i_sv_nA = abs(i(Vcap_b)) * 1e9\n"
        "print i_sw_nA i_sv_nA\n"
        ".endc\n.end\n"
    )
    out = run_ngspice(deck, "relax_leak_125c")
    v = parse_vals(out, ["i_sw_nA", "i_sv_nA"])
    return v["i_sw_nA"], v["i_sv_nA"]


def sim_vdd_temp(base: str) -> None:
    tasks = []
    for vdd in [1.08, 1.14, 1.20, 1.26, 1.32]:
        tasks.append(("vdd", vdd, 25, f"relax_vdd_{vdd:.2f}"))
    for temp in [-40, 0, 25, 75, 125]:
        tasks.append(("temp", 1.20, temp, f"relax_temp_{temp}"))

    res = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(measure_relax, base, "mos_tt", "res_typ", "cap_typ", vdd, temp, tag, False): (sw, vdd, temp)
                for sw, vdd, temp, tag in tasks}
        for fut in concurrent.futures.as_completed(futs):
            res[futs[fut]] = fut.result()

    i_sw_nA, i_sv_nA = sim_leakage_at_125c()
    rows = []
    for sw, vdd, temp, _ in tasks:
        v = res[(sw, vdd, temp)]
        rows.append({
            "sweep": sw,
            "corner": "tt",
            "vdd_V": f"{vdd:.2f}",
            "temp_C": str(temp),
            "freq_kHz": f"{v['freq']/1e3:.3f}",
            "duty_pct": f"{v['duty']*100:.2f}",
            "vth_V": f"{v['vth_V']:.4f}",
            "idd_uA": f"{v['idd_uA']:.3f}",
            "sw_leak_125C_nA": f"{i_sw_nA:.4f}",
            "moscap_leak_125C_nA": f"{i_sv_nA:.4f}",
        })
    with open(RESULTS_DIR / "osc_relax_vdd_temp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def make_m1_netlist(base_m10: str, cap_kind: str) -> str:
    """Adjust M=10 netlist parameters cleanly to test M=1 option at the same ~100 kHz target."""
    # With M=1: I_chg = I_ref (~0.5 uA), so C needs to be 10x larger (~5.5 pF) for ~100 kHz.
    s = base_m10
    s = re.sub(r"(XMP_CHG_IN\b[^\n]*\bm=)10\b", r"\g<1>1", s)
    if cap_kind == "cmomf":
        s = re.sub(r"(XC_[AB]\b[^\n]*\bm=)1\b", r"\g<1>10", s)
    else:
        s = re.sub(r"(XC_[AB]\b[^\n]*\bNx=)10\b", r"\g<1>100", s)
    return s


def sim_options(base_cmom: str, base_moscap: str) -> None:
    i_sw_nA, i_sv_nA = sim_leakage_at_125c()
    variants = [
        ("cmomf_M10", base_cmom, 10, "~50 nA", f"{i_sw_nA:.3f} nA", "~2730 um2 (1800 R + 930 C)"),
        ("cmomf_M1", make_m1_netlist(base_cmom, "cmomf"), 1, "~500 nA", f"{i_sw_nA:.3f} nA", "~11100 um2 (1800 R + 9300 C)"),
        ("hv_moscap_M10", base_moscap, 10, "~50 nA", f"{i_sw_nA + i_sv_nA:.3f} nA", "~2050 um2 (1800 R + 250 C)"),
        ("hv_moscap_M1", make_m1_netlist(base_moscap, "moscap"), 1, "~500 nA", f"{i_sw_nA + i_sv_nA:.3f} nA", "~4300 um2 (1800 R + 2500 C)"),
    ]

    rows = []
    for vname, net, mval, ichg_nom, leak_str, area_est in variants:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            f_tt = ex.submit(measure_relax, net, "mos_tt", "res_typ", "cap_typ", 1.20, 25, f"opt_{vname}_tt")
            f_v1 = ex.submit(measure_relax, net, "mos_tt", "res_typ", "cap_typ", 1.08, 25, f"opt_{vname}_v108")
            f_v2 = ex.submit(measure_relax, net, "mos_tt", "res_typ", "cap_typ", 1.32, 25, f"opt_{vname}_v132")
            f_t1 = ex.submit(measure_relax, net, "mos_tt", "res_typ", "cap_typ", 1.20, -40, f"opt_{vname}_t_40")
            f_t2 = ex.submit(measure_relax, net, "mos_tt", "res_typ", "cap_typ", 1.20, 125, f"opt_{vname}_t125")
            v_tt = f_tt.result()
            v_v1 = f_v1.result()
            v_v2 = f_v2.result()
            v_t1 = f_t1.result()
            v_t2 = f_t2.result()

        vdd_pct_per_v = ((v_v2["freq"] - v_v1["freq"]) / v_tt["freq"]) * 100.0 / 0.24
        temp_pct = ((v_t2["freq"] - v_t1["freq"]) / v_tt["freq"]) * 100.0
        print(f"[opt] {vname}: {v_tt['freq']/1e3:.2f} kHz, vdd_sens={vdd_pct_per_v:+.2f} %/V, temp_span={temp_pct:+.2f}%")
        rows.append({
            "option": vname,
            "M": str(mval),
            "ichg_nom": ichg_nom,
            "freq_tt_kHz": f"{v_tt['freq']/1e3:.3f}",
            "vdd_sens_pct_per_V": f"{vdd_pct_per_v:+.2f}",
            "temp_drift_-40_to_125C_pct": f"{temp_pct:+.2f}",
            "leak_125C": leak_str,
            "est_passive_area": area_est,
        })

    with open(RESULTS_DIR / "osc_relax_options.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base_cmom = load_netlist("tb_osc_relax.spice")
    base_moscap = load_netlist("tb_osc_relax_moscap.spice")
    sim_corners(base_cmom)
    sim_vdd_temp(base_cmom)
    sim_options(base_cmom, base_moscap)
    print("Wrote osc_relax CSVs to", RESULTS_DIR)


if __name__ == "__main__":
    main()
