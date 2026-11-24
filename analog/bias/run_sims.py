#!/usr/bin/env python3
"""Run ngspice corner, VDD sweep, temperature sweep, and startup sims for analog/bias."""

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
    ("tt", "mos_tt", "res_typ", 1.20, 25),
    ("ss", "mos_ss", "res_wcs", 1.08, 125),
    ("ff", "mos_ff", "res_bcs", 1.32, -40),
]


def load_base_netlist() -> str:
    sp = (BUILD_DIR / "tb_bias.spice").read_text()
    lines = []
    for line in sp.splitlines():
        s = line.strip()
        if s.lower() == ".end" or s.startswith((".options temp", ".lib cornerMOSlv", ".lib cornerRES", "Vdd ", "Ven ")):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def run_ngspice(deck_text: str, tag: str) -> str:
    deck_path = BUILD_DIR / f"{tag}.sp"
    deck_path.write_text(deck_text)
    env = os.environ.copy()
    env.setdefault("PDK_ROOT", "/home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008")
    env.setdefault("PDK", "ihp-sg13cmos5l")
    cmd = ["nix", "shell", "nixpkgs#ngspice", "--command", "ngspice", "-b", str(deck_path)]
    res = subprocess.run(cmd, cwd=ANALOG_DIR, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ngspice failed for {tag}:\n{res.stdout}\n{res.stderr}")
    return res.stdout


def parse_vals(out: str, names: list[str]) -> dict[str, float]:
    vals = {}
    for n in names:
        m = re.search(rf"^\s*{re.escape(n)}\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out, re.MULTILINE | re.IGNORECASE)
        if not m:
            raise ValueError(f"Could not parse '{n}' from ngspice output:\n{out[-1200:]}")
        vals[n] = float(m.group(1))
    return vals


def sim_corners(base: str) -> None:
    rows = []
    for cname, mlib, rlib, vdd, temp in CORNERS:
        deck_on = (
            base
            + f"Vdd VDD GND dc {vdd}\n"
            + f"Ven en GND dc {vdd}\n"
            + f".options temp={temp}\n"
            + f".lib cornerMOSlv.lib {mlib}\n"
            + f".lib cornerRES.lib {rlib}\n"
            + ".op\n.control\nrun\n"
            + "let i_ref = abs(i(Vload))\n"
            + "let i_tot = abs(i(Vdd))\n"
            + "print i_ref i_tot v(vpbias) v(vnbias)\n"
            + ".endc\n.end\n"
        )
        out_on = run_ngspice(deck_on, f"bias_{cname}_on")
        von = parse_vals(out_on, ["i_ref", "i_tot", "v(vpbias)", "v(vnbias)"])

        deck_off = (
            base
            + f"Vdd VDD GND dc {vdd}\n"
            + "Ven en GND dc 0\n"
            + f".options temp={temp}\n"
            + f".lib cornerMOSlv.lib {mlib}\n"
            + f".lib cornerRES.lib {rlib}\n"
            + ".op\n.control\nrun\n"
            + "let i_off = abs(i(Vdd))\n"
            + "let i_ref_off = abs(i(Vload))\n"
            + "print i_off i_ref_off\n"
            + ".endc\n.end\n"
        )
        out_off = run_ngspice(deck_off, f"bias_{cname}_off")
        voff = parse_vals(out_off, ["i_off", "i_ref_off"])

        rows.append({
            "corner": cname,
            "vdd_V": f"{vdd:.2f}",
            "temp_C": str(temp),
            "i_ref_uA": f"{von['i_ref'] * 1e6:.4f}",
            "i_tot_uA": f"{von['i_tot'] * 1e6:.4f}",
            "vpbias_V": f"{von['v(vpbias)']:.4f}",
            "vnbias_V": f"{von['v(vnbias)']:.4f}",
            "i_standby_nA": f"{voff['i_off'] * 1e9:.4f}",
            "i_ref_off_nA": f"{voff['i_ref_off'] * 1e9:.4f}",
        })

    with open(RESULTS_DIR / "bias_corners.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_vdd_sweep(base: str) -> None:
    rows = []
    vdds = [1.00, 1.04, 1.08, 1.12, 1.16, 1.20, 1.24, 1.28, 1.32, 1.36, 1.40]
    for cname, mlib, rlib, _, temp in CORNERS:
        for vdd in vdds:
            deck = (
                base
                + f"Vdd VDD GND dc {vdd}\n"
                + f"Ven en GND dc {vdd}\n"
                + f".options temp={temp}\n"
                + f".lib cornerMOSlv.lib {mlib}\n"
                + f".lib cornerRES.lib {rlib}\n"
                + ".op\n.control\nrun\n"
                + "let i_ref = abs(i(Vload))\n"
                + "let i_tot = abs(i(Vdd))\n"
                + "print i_ref i_tot v(vpbias) v(vnbias)\n"
                + ".endc\n.end\n"
            )
            out = run_ngspice(deck, f"bias_vdd_{cname}_{vdd:.2f}")
            v = parse_vals(out, ["i_ref", "i_tot", "v(vpbias)", "v(vnbias)"])
            rows.append({
                "corner": cname,
                "temp_C": str(temp),
                "vdd_V": f"{vdd:.2f}",
                "i_ref_uA": f"{v['i_ref'] * 1e6:.4f}",
                "i_tot_uA": f"{v['i_tot'] * 1e6:.4f}",
                "vpbias_V": f"{v['v(vpbias)']:.4f}",
                "vnbias_V": f"{v['v(vnbias)']:.4f}",
            })
    with open(RESULTS_DIR / "bias_vdd_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_temp_sweep(base: str) -> None:
    rows = []
    for cname, mlib, rlib, vdd, _ in CORNERS:
        for temp in [-40, -10, 25, 55, 85, 125]:
            deck = (
                base
                + f"Vdd VDD GND dc {vdd}\n"
                + f"Ven en GND dc {vdd}\n"
                + f".options temp={temp}\n"
                + f".lib cornerMOSlv.lib {mlib}\n"
                + f".lib cornerRES.lib {rlib}\n"
                + ".op\n.control\nrun\n"
                + "let i_ref = abs(i(Vload))\n"
                + "let i_tot = abs(i(Vdd))\n"
                + "print i_ref i_tot v(vpbias) v(vnbias)\n"
                + ".endc\n.end\n"
            )
            out = run_ngspice(deck, f"bias_temp_{cname}_{temp}")
            v = parse_vals(out, ["i_ref", "i_tot", "v(vpbias)", "v(vnbias)"])
            rows.append({
                "corner": cname,
                "vdd_V": f"{vdd:.2f}",
                "temp_C": str(temp),
                "i_ref_uA": f"{v['i_ref'] * 1e6:.4f}",
                "i_tot_uA": f"{v['i_tot'] * 1e6:.4f}",
                "vpbias_V": f"{v['v(vpbias)']:.4f}",
                "vnbias_V": f"{v['v(vnbias)']:.4f}",
            })
    with open(RESULTS_DIR / "bias_temp_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def sim_startup(base: str) -> None:
    rows = []
    for cname, mlib, rlib, vdd, temp in CORNERS:
        lines = []
        for line in base.splitlines():
            if line.startswith("Vload "):
                lines.append("Vload ibias_out GND pwl(0 0 10u 0.6)")
            else:
                lines.append(line)
        deck = (
            "\n".join(lines)
            + f"\nVdd VDD GND pwl(0 0 10u {vdd})\n"
            + f"Ven en GND pwl(0 0 10u {vdd})\n"
            + f".options temp={temp}\n"
            + f".lib cornerMOSlv.lib {mlib}\n"
            + f".lib cornerRES.lib {rlib}\n"
            + ".tran 100n 100u uic\n"
            + ".control\nrun\n"
            + "let i_out = abs(i(Vload))\n"
            + "meas tran i_final find i_out at=99u\n"
            + "let i_tgt = 0.95 * i_final\n"
            + "meas tran t_settle when i_out=i_tgt rise=1 td=1u\n"
            + "meas tran vp_final find v(vpbias) at=99u\n"
            + "meas tran vn_final find v(vnbias) at=99u\n"
            + "print i_final t_settle vp_final vn_final\n"
            + ".endc\n.end\n"
        )
        out = run_ngspice(deck, f"bias_startup_{cname}")
        v = parse_vals(out, ["i_final", "t_settle", "vp_final", "vn_final"])
        rows.append({
            "corner": cname,
            "vdd_V": f"{vdd:.2f}",
            "temp_C": str(temp),
            "i_final_uA": f"{v['i_final'] * 1e6:.4f}",
            "t_settle_us": f"{v['t_settle'] * 1e6:.3f}",
            "vp_final_V": f"{v['vp_final']:.4f}",
            "vn_final_V": f"{v['vn_final']:.4f}",
        })
    with open(RESULTS_DIR / "bias_startup.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base = load_base_netlist()
    sim_corners(base)
    sim_vdd_sweep(base)
    sim_temp_sweep(base)
    sim_startup(base)
    print("Wrote bias CSVs to", RESULTS_DIR)


if __name__ == "__main__":
    main()
