#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Generate publication-grade vector PDF plots from verified analog/results/*.csv and crop schematic PDFs."""
from __future__ import annotations
import csv
import re
import subprocess
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ANALOG_DIR = Path(__file__).resolve().parents[1]
RES_DIR = ANALOG_DIR / "results"
SCH_PDF_DIR = RES_DIR / "pdf"
FIG_DIR = Path(__file__).resolve().parent / "figures"

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 8.5,
    "axes.titlesize": 9.5,
    "axes.titleweight": "bold",
    "axes.labelsize": 8.5,
    "legend.fontsize": 7.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "axes.grid": True,
    "grid.alpha": 0.30,
    "grid.linestyle": "--",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

C_COL = {"tt": "#1f77b4", "ss": "#d62728", "ff": "#2ca02c"}
C_LBL = {"tt": "tt (1.20 V, 25 °C)", "ss": "ss (1.08 V, 125 °C)", "ff": "ff (1.32 V, -40 °C)"}


def read_csv(name: str) -> list[dict]:
    with open(RES_DIR / name, newline="") as f:
        return list(csv.DictReader(f))


def plot_bias_pvt() -> None:
    vdd_rows = read_csv("bias_vdd_sweep.csv")
    tmp_rows = read_csv("bias_temp_sweep.csv")
    cor_rows = read_csv("bias_corners.csv")
    stu_rows = read_csv("bias_startup.csv")

    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.2))

    ax = axes[0]
    for c in ("tt", "ss", "ff"):
        sub = [r for r in vdd_rows if r["corner"] == c]
        x = [float(r["vdd_V"]) for r in sub]
        y = [float(r["i_ref_uA"]) for r in sub]
        ax.plot(x, y, marker="o", ms=3.2, lw=1.6, color=C_COL[c], label=f"{c} ({sub[0]['temp_C']} °C)")
    ax.axvspan(1.08, 1.32, color="#eeeeee", zorder=0, label="±10% VDD")
    ax.set_title("(a) $I_{\\mathrm{ref}}$ Supply Line Regulation")
    ax.set_xlabel("$V_{DD}$ (V)")
    ax.set_ylabel("$I_{\\mathrm{ref}}$ (µA)")
    ax.legend(frameon=True, fontsize=6.8)

    ax = axes[1]
    for c in ("tt", "ss", "ff"):
        sub = [r for r in tmp_rows if r["corner"] == c]
        x = [float(r["temp_C"]) for r in sub]
        y = [float(r["i_ref_uA"]) for r in sub]
        ax.plot(x, y, marker="s", ms=3.4, lw=1.6, color=C_COL[c], label=f"{c} ({sub[0]['vdd_V']} V)")
    ax.set_title("(b) $I_{\\mathrm{ref}}$ Temperature Dependence (PTAT)")
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("$I_{\\mathrm{ref}}$ (µA)")
    ax.legend(frameon=True, fontsize=6.8)

    ax = axes[2]
    corners = ["tt", "ss", "ff"]
    iref = [float(next(r["i_ref_uA"] for r in cor_rows if r["corner"] == c)) for c in corners]
    itot = [float(next(r["i_tot_uA"] for r in cor_rows if r["corner"] == c)) for c in corners]
    tset = [float(next(r["t_settle_us"] for r in stu_rows if r["corner"] == c)) for c in corners]
    x = np.arange(3)
    w = 0.34
    b1 = ax.bar(x - w/2, iref, w, color="#1f77b4", label="$I_{\\mathrm{ref}}$ (µA)")
    b2 = ax.bar(x + w/2, itot, w, color="#ff7f0e", label="$I_{\\mathrm{tot}}$ (µA)")
    ax.set_xticks(x, [f"{c}\n($t_{{set}}$={ts:.2f} µs)" for c, ts in zip(corners, tset)])
    ax.set_ylabel("Current (µA)")
    ax.set_ylim(0, 2.55)
    ax.set_title("(c) Corner Current & Startup Summary")
    for b in list(b1) + list(b2):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.04, f"{b.get_height():.2f}", ha="center", va="bottom", fontsize=6.8)
    ax.legend(frameon=True, fontsize=6.8)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_bias_pvt.pdf")
    plt.close(fig)


def plot_ring_trim() -> None:
    r_a = read_csv("osc_ring_std_trim.csv")
    r_b = read_csv("osc_ring_cc_trim.csv")
    r_pex_t = read_csv("clk_macro_pex_trim.csv")

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.6), sharey=True)
    for ax, rows, title in [
        (axes[0], r_a, "(a) Ring A — Standard-Cell Starved (Unregulated)"),
        (axes[1], r_b, "(b) Ring B — CMOM Current-Controlled Ring (Selected)"),
    ]:
        for c in ("ff", "tt", "ss"):
            sub = sorted([r for r in rows if r["corner"] == c], key=lambda r: int(r["trim"]))
            x = [int(r["trim"]) for r in sub]
            y = [float(r["freq_MHz"]) for r in sub]
            ax.plot(x, y, marker="o", ms=3.0, lw=1.7, color=C_COL[c], label=C_LBL[c])
        ax.axhline(60.0, color="#333333", ls="--", lw=1.0, label="60 MHz target")
        ax.axvline(128, color="#7f7f7f", ls=":", lw=1.1, label="Safe boot trim=128")
        ax.set_xlabel("8-bit DAC Trim Code (0–255)")
        ax.set_title(title)
        ax.set_xlim(-5, 260)
        ax.set_ylim(0, 235)
        ax.legend(frameon=True, fontsize=7.0, loc="upper left")

    axes[0].set_ylabel("Oscillation Frequency (MHz)")
    axes[0].annotate("ff @ trim=128:\n61.28 MHz (>60!)", xy=(128, 61.3), xytext=(142, 130),
                     fontsize=7.2, color="#d62728", arrowprops=dict(arrowstyle="->", color="#d62728", lw=0.8))

    tt_near = min([r for r in r_b if r["corner"] == "tt"], key=lambda r: abs(float(r["freq_MHz"]) - 60.0))
    sch_38_t = int(tt_near["trim"])
    sch_38_f = float(tt_near["freq_MHz"])
    sch_128_f = next(float(r["freq_MHz"]) for r in r_b if r["corner"] == "tt" and int(r["trim"]) == 128)
    pex_ff_128 = next(float(r["ring_MHz"]) for r in r_pex_t if r["corner"] == "ff" and int(r["trim"]) == 128)
    pex_tt_nom = min([r for r in r_pex_t if r["corner"] == "tt"], key=lambda r: abs(float(r["ring_MHz"]) - 60.0))
    pex_tt_max = next(float(r["ring_MHz"]) for r in r_pex_t if r["corner"] == "tt" and int(r["trim"]) == 255)
    axes[1].annotate(
        f"Pre-emphasized for PEX:\n"
        f"Sch @{sch_38_t}: {sch_38_f:.2f} | @128: {sch_128_f:.2f} MHz\n"
        f"PEX ff@128: {pex_ff_128:.2f} MHz (<=60)\n"
        f"PEX tt@{pex_tt_nom['trim']}: {float(pex_tt_nom['ring_MHz']):.2f} MHz (max {pex_tt_max:.2f})",
        xy=(sch_38_t, sch_38_f), xytext=(82, 12), fontsize=7.0, color="#111111",
        bbox=dict(boxstyle="round,pad=0.25", fc="#f5f5f5", ec="#888888"),
        arrowprops=dict(arrowstyle="->", color="#111111", lw=0.8),
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_ring_trim.pdf")
    plt.close(fig)


def plot_ring_sensitivity() -> None:
    vt_a = read_csv("osc_ring_std_vdd_temp.csv")
    vt_b = read_csv("osc_ring_cc_vdd_temp.csv")
    step_b = read_csv("osc_ring_cc_supply_step.csv")[0]

    def _metrics(rows: list[dict]) -> tuple[int, float, float]:
        trim_v = int(rows[0]["trim"])
        vsub = sorted([r for r in rows if r["sweep"] == "vdd"], key=lambda r: float(r["vdd_V"]))
        tsub = sorted([r for r in rows if r["sweep"] == "temp"], key=lambda r: float(r["temp_C"]))
        fnom = next(float(r["freq_MHz"]) for r in vsub if abs(float(r["vdd_V"]) - 1.20) < 1e-3)
        vslope = (float(vsub[-1]["freq_MHz"]) - float(vsub[0]["freq_MHz"])) / (
            fnom * (float(vsub[-1]["vdd_V"]) - float(vsub[0]["vdd_V"]))
        ) * 100.0
        tdrift = (float(tsub[-1]["freq_MHz"]) - float(tsub[0]["freq_MHz"])) / fnom * 100.0
        return trim_v, vslope, tdrift

    ta, vsa, tda = _metrics(vt_a)
    tb, vsb, tdb = _metrics(vt_b)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.4))

    ax = axes[0]
    for rows, lbl, col, mk in [
        (vt_a, f"Ring A (std, trim={ta}): {vsa:+.1f} %/V", "#d62728", "s"),
        (vt_b, f"Ring B (CC, trim={tb}): {vsb:+.1f} %/V", "#1f77b4", "o"),
    ]:
        sub = [r for r in rows if r["sweep"] == "vdd"]
        x = [float(r["vdd_V"]) for r in sub]
        y = [float(r["freq_MHz"]) for r in sub]
        ax.plot(x, y, marker=mk, ms=4.0, lw=1.8, color=col, label=lbl)
    ax.axhline(60.0, color="#444444", ls="--", lw=0.9)
    ax.set_title("(a) Frequency vs. Supply Voltage ($T=25$ °C, tt)")
    ax.set_xlabel("$V_{DD}$ (V)")
    ax.set_ylabel("Frequency (MHz)")
    ax.text(1.16, 50.0,
            f"VDD step 1.20→1.25 V:\n{float(step_b['f_before_MHz']):.2f} → {float(step_b['f_immed_MHz']):.2f} → {float(step_b['f_settled_MHz']):.2f} MHz",
            fontsize=6.8, bbox=dict(boxstyle="round,pad=0.22", fc="#eef6ff", ec="#1f77b4", lw=0.6))
    ax.legend(frameon=True, fontsize=7.2, loc="upper left")

    ax = axes[1]
    for rows, lbl, col, mk in [
        (vt_a, f"Ring A (std, trim={ta}): {tda:+.1f}%", "#d62728", "s"),
        (vt_b, f"Ring B (CC, trim={tb}): {tdb:+.1f}%", "#1f77b4", "o"),
    ]:
        sub = [r for r in rows if r["sweep"] == "temp"]
        x = [float(r["temp_C"]) for r in sub]
        y = [float(r["freq_MHz"]) for r in sub]
        ax.plot(x, y, marker=mk, ms=4.0, lw=1.8, color=col, label=lbl)
    ax.axhline(60.0, color="#444444", ls="--", lw=0.9)
    ax.set_title("(b) Frequency vs. Temperature ($V_{DD}=1.20$ V, tt)")
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Frequency (MHz)")
    ax.legend(frameon=True, fontsize=7.2, loc="upper left")

    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_ring_sensitivity.pdf")
    plt.close(fig)


def plot_relax_options() -> None:
    opts = read_csv("osc_relax_options.csv")
    vt = read_csv("osc_relax_vdd_temp.csv")

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.4))

    ax = axes[0]
    names = [r["option"] for r in opts]
    areas = [float(re.search(r"~(\d+)", r["est_passive_area"]).group(1)) for r in opts]
    vdd_s = [float(r["vdd_sens_pct_per_V"].replace("+", "")) for r in opts]
    colors = ["#90caf9", "#b0bec5", "#1565c0", "#a5d6a7"]
    x = np.arange(len(names))
    bars = ax.bar(x, areas, color=colors, edgecolor="#222222", lw=0.8)
    bars[2].set_hatch("//")
    ax.set_xticks(x, ["cmomf\nM=10", "cmomf\nM=1", "hv_moscap\nM=10 (Sel)", "hv_moscap\nM=1"], fontsize=7.5)
    ax.set_ylabel("Estimated Passive Area (µm²)")
    ax.set_ylim(0, 12800)
    ax.set_title("(a) Relax Topology Area vs. Supply Sensitivity")
    for b, a, s in zip(bars, areas, vdd_s):
        ax.text(b.get_x() + b.get_width()/2, a + 220, f"~{a:.0f} µm²\n(+{s:.2f} %/V)", ha="center", va="bottom", fontsize=6.8)

    ax = axes[1]
    vdd_sub = [r for r in vt if r["sweep"] == "vdd"]
    tmp_sub = [r for r in vt if r["sweep"] == "temp"]
    ax2 = ax.twiny()
    l1, = ax.plot([float(r["vdd_V"]) for r in vdd_sub], [float(r["freq_kHz"]) for r in vdd_sub],
                  "o-", lw=1.7, color="#1f77b4", label="vs. VDD (25 °C)")
    l2, = ax2.plot([float(r["temp_C"]) for r in tmp_sub], [float(r["freq_kHz"]) for r in tmp_sub],
                   "s--", lw=1.7, color="#d62728", label="vs. Temp (1.20 V)")
    ax.set_xlabel("$V_{DD}$ (V)", color="#1f77b4")
    ax2.set_xlabel("Temperature (°C)", color="#d62728")
    ax.set_ylabel("Frequency (kHz)")
    ax.set_ylim(104, 116)
    ax.set_title("(b) Relax Frequency Stability (tt)", pad=18)
    ax.legend([l1, l2], [l1.get_label(), l2.get_label()], loc="lower left", fontsize=7.2, frameon=True)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_relax_options.pdf")
    plt.close(fig)


def plot_macro_waveforms() -> None:
    wf_ring = np.genfromtxt(RES_DIR / "clk_macro_wf_ring.csv", delimiter=",", names=True)
    wf_rel = np.genfromtxt(RES_DIR / "clk_macro_wf_relax.csv", delimiter=",", names=True)

    sch_modes = read_csv("clk_macro_modes.csv")
    ring_row = next(r for r in sch_modes if r["mode"] == "ring_only" and r["corner"] == "tt" and int(r["trim"]) != 128)
    rel_row = next(r for r in sch_modes if r["mode"] == "sleep_relax" and r["corner"] == "tt")
    nom_trim = int(ring_row["trim"])
    f_ring = float(ring_row["ring_MHz"])
    f_rel = float(rel_row["relax_kHz"])

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.5))

    ax = axes[0]
    t_us = wf_ring["t_s"] * 1e6
    # Show zoomed steady-state 60 ns window near end of ring simulation (internal CCO nodes n0, n2 + clk)
    t_max = float(t_us.max())
    mask = (t_us >= max(0.0, t_max - 0.06)) & (t_us <= t_max)
    ax.plot(t_us[mask], wf_ring["n0_V"][mask], lw=1.1, ls="--", color="#ff7f0e", label="CCO stage $n_0$ (V)")
    ax.plot(t_us[mask], wf_ring["n2_V"][mask], lw=1.1, ls=":", color="#2ca02c", label="CCO stage $n_2$ (V)")
    ax.plot(t_us[mask], wf_ring["clk_V"][mask], lw=1.3, color="#1f77b4", label="clk output (V)")
    ax.set_title(f"(a) Ring Mode Steady-State (Sch tt, trim={nom_trim}, {f_ring:.1f} MHz)")
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Voltage (V)")
    ax.set_ylim(-0.08, 1.48)
    ax.legend(loc="upper right", ncol=3, frameon=True, fontsize=6.6)

    ax = axes[1]
    tr_us = wf_rel["t_s"] * 1e6
    mr = (tr_us >= 20.0) & (tr_us <= 44.0)
    ax.plot(tr_us[mr], wf_rel["vcap_a_V"][mr], lw=1.2, color="#ff7f0e", label="$v_{\\mathrm{cap,A}}$ (V)")
    ax.plot(tr_us[mr], wf_rel["vcap_b_V"][mr], lw=1.2, color="#9467bd", label="$v_{\\mathrm{cap,B}}$ (V)")
    ax.plot(tr_us[mr], wf_rel["vth_V"][mr], lw=1.3, ls="--", color="#333333", label="$V_{\\mathrm{th}}$ (V)")
    ax.plot(tr_us[mr], wf_rel["clk_slow_V"][mr], lw=1.1, color="#1f77b4", alpha=0.85, label="clk_slow (V)")
    ax.set_title(f"(b) Dual-Slope Relax Mode (Sch tt, $f_{{\\mathrm{{slow}}}}={f_rel:.1f}$ kHz)")
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Voltage (V)")
    ax.set_ylim(-0.08, 1.48)
    ax.legend(loc="upper right", ncol=2, frameon=True, fontsize=6.6)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_macro_waveforms.pdf")
    plt.close(fig)


def plot_pex_comparison() -> None:
    """Plot Schematic vs. True Hierarchical Magic PEX (ring trim curve & PVT corner matrix)."""
    sch_modes = read_csv("clk_macro_modes.csv")
    sch_trim = [r for r in read_csv("osc_ring_cc_trim.csv") if r["corner"] == "tt"]
    pex_modes = read_csv("clk_macro_pex.csv")
    pex_trim_all = read_csv("clk_macro_pex_trim.csv")
    pex_trim_tt = sorted([r for r in pex_trim_all if r["corner"] == "tt"], key=lambda r: int(r["trim"]))
    best_trim = max(int(r["trim"]) for r in pex_modes if r["mode"] == "ring_only" and r["corner"] == "tt")

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 3.2))

    # (a) Ring B trim curve: Schematic vs Hierarchical Magic PEX (tt)
    ax = axes[0]
    tx_s = [int(r["trim"]) for r in sorted(sch_trim, key=lambda r: int(r["trim"]))]
    fy_s = [float(r["freq_MHz"]) for r in sorted(sch_trim, key=lambda r: int(r["trim"]))]
    tx_p = [int(r["trim"]) for r in pex_trim_tt]
    fy_p = [float(r["ring_MHz"]) for r in pex_trim_tt]
    ax.plot(tx_s, fy_s, "o-", ms=3.2, lw=1.7, color="#1f77b4", label="Schematic (tt, 1.20 V, 25 °C)")
    ax.plot(tx_p, fy_p, "s-", ms=3.4, lw=1.8, color="#d62728", label="Magic PEX Hier. (tt, 1.20 V, 25 °C)")
    ax.axhline(60.0, color="#333333", ls="--", lw=1.0, label="60 MHz SoC Target")
    ax.axvline(best_trim, color="#7f7f7f", ls=":", lw=1.0)
    all_sch_trim = read_csv("osc_ring_cc_trim.csv")

    def _sch_ring_at(corner: str, trim_val: int) -> float:
        hits = [r for r in sch_modes if r["mode"] == "ring_only" and r["corner"] == corner and int(r["trim"]) == trim_val]
        if hits:
            return float(hits[0]["ring_MHz"])
        pts = sorted([(int(r["trim"]), float(r["freq_MHz"])) for r in all_sch_trim if r["corner"] == corner])
        return float(np.interp(trim_val, [p[0] for p in pts], [p[1] for p in pts]))

    f_p_best = next(float(r["ring_MHz"]) for r in pex_trim_tt if int(r["trim"]) == best_trim)
    f_p_128 = next(float(r["ring_MHz"]) for r in pex_trim_tt if int(r["trim"]) == 128)
    f_p_255 = next(float(r["ring_MHz"]) for r in pex_trim_tt if int(r["trim"]) == 255)
    f_s_best = _sch_ring_at("tt", best_trim)
    ax.annotate(f"Sch @{best_trim}: {f_s_best:.2f} MHz", xy=(best_trim, f_s_best), xytext=(22, 168),
                fontsize=7.0, color="#1f77b4", arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=0.8))
    ax.annotate(f"PEX @{best_trim}: {f_p_best:.2f} MHz\nPEX @128: {f_p_128:.2f} MHz\nPEX @255: {f_p_255:.2f} MHz",
                xy=(best_trim, f_p_best), xytext=(148, 8),
                fontsize=6.9, color="#d62728",
                bbox=dict(boxstyle="round,pad=0.22", fc="#fff5f5", ec="#d62728", lw=0.6),
                arrowprops=dict(arrowstyle="->", color="#d62728", lw=0.8))
    ax.set_title("(a) Ring B Frequency vs. Trim: Schematic vs. PEX (tt)")
    ax.set_xlabel("8-bit DAC Trim Code (0–255)")
    ax.set_ylabel("Frequency (MHz)")
    ax.set_xlim(-5, 265)
    ax.set_ylim(0, 212)
    ax.legend(frameon=True, fontsize=6.8, loc="upper left")

    # (b) Corner comparison for Ring (MHz, left) & Relax (kHz, right)
    ax1 = axes[1]
    ax2 = ax1.twinx()
    ax2.spines["top"].set_visible(False)
    corners = ["tt", "ss", "ff"]
    ring_sch = [_sch_ring_at(c, best_trim) for c in corners]
    ring_pex = [float(next(r["ring_MHz"] for r in pex_modes if r["mode"] == "ring_only" and r["corner"] == c and int(r["trim"]) == best_trim)) for c in corners]
    rel_sch = [float(next(r["relax_kHz"] for r in sch_modes if r["mode"] == "sleep_relax" and r["corner"] == c)) for c in corners]
    rel_pex = [float(next(r["relax_kHz"] for r in pex_modes if r["mode"] == "sleep_relax" and r["corner"] == c)) for c in corners]

    xr = np.arange(3)
    xl = np.arange(3) + 3.6
    bw = 0.34
    b1 = ax1.bar(xr - bw/2, ring_sch, bw, color="#1f77b4", label="Schematic")
    b2 = ax1.bar(xr + bw/2, ring_pex, bw, color="#d62728", label="Magic PEX")
    b3 = ax2.bar(xl - bw/2, rel_sch, bw, color="#1f77b4", alpha=0.82)
    b4 = ax2.bar(xl + bw/2, rel_pex, bw, color="#d62728", alpha=0.82)
    ax1.axvline(2.8, color="#888888", ls="--", lw=0.9)
    ax1.set_xticks(list(xr) + list(xl), [f"Ring\n{c}" for c in corners] + [f"Relax\n{c}" for c in corners], fontsize=7.2)
    ax1.set_ylabel(f"Ring Frequency @ trim={best_trim} (MHz)", color="#154c79")
    ax2.set_ylabel("Relax Frequency (kHz)", color="#8d4e00")
    ax1.set_ylim(0, 205)
    ax2.set_ylim(0, 205)
    ax1.set_title("(b) PVT Corners: Schematic vs. Hierarchical PEX")
    for b in list(b1) + list(b2):
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 2.2, f"{b.get_height():.1f}", ha="center", va="bottom", fontsize=6.4)
    for b in list(b3) + list(b4):
        ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 2.2, f"{b.get_height():.1f}", ha="center", va="bottom", fontsize=6.4)
    ax1.legend(loc="upper right", frameon=True, fontsize=7.0)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_pex_comparison.pdf")
    plt.close(fig)


def plot_mc_mismatch() -> None:
    """Plot 40-seed post-layout Magic PEX Monte Carlo mismatch distributions."""
    mc_rows = read_csv("clk_macro_mc.csv")
    best_trim = int(mc_rows[0]["best_trim"])
    f128 = np.array([float(r["ring_t128_MHz"]) for r in mc_rows])
    fbest = np.array([float(r["ring_best_MHz"]) for r in mc_rows])
    dstep = np.array([float(r["step_191_192_MHz"]) for r in mc_rows])
    frel = np.array([float(r["relax_kHz"]) for r in mc_rows])

    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.15))

    ax = axes[0]
    ax.hist(f128, bins=10, color="#ff7f0e", alpha=0.78, edgecolor="#222222", lw=0.6,
            label=f"Boot @128: {f128.mean():.2f}±{f128.std(ddof=1):.2f} MHz")
    ax.hist(fbest, bins=10, color="#1f77b4", alpha=0.78, edgecolor="#222222", lw=0.6,
            label=f"Nom @{best_trim}: {fbest.mean():.2f}±{fbest.std(ddof=1):.2f} MHz")
    ax.axvline(60.0, color="#d62728", ls="--", lw=1.1, label="60.0 MHz SoC Target")
    ax.set_title("(a) Ring Frequency Mismatch (PEX tt)")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Samples (out of 40)")
    ax.legend(frameon=True, fontsize=6.4, loc="upper center")

    ax = axes[1]
    ax.hist(dstep, bins=10, color="#2ca02c", alpha=0.82, edgecolor="#222222", lw=0.6)
    ax.axvline(0.0, color="#d62728", ls="--", lw=1.0, label="Monotonicity limit (0)")
    ax.axvline(dstep.mean(), color="#111111", ls=":", lw=1.1,
               label=f"$\\mu={dstep.mean():+.3f}$, $\\sigma={dstep.std(ddof=1):.3f}$ MHz")
    mono = int(np.sum(dstep > 0.0))
    ax.set_title(f"(b) IDAC Carry Step 191→192 ({mono}/{len(dstep)} Mono.)")
    ax.set_xlabel("$\\Delta f_{191\\to 192}$ (MHz)")
    ax.set_ylabel("Samples (out of 40)")
    ax.legend(frameon=True, fontsize=6.5, loc="upper left")

    ax = axes[2]
    ax.hist(frel, bins=10, color="#9467bd", alpha=0.82, edgecolor="#222222", lw=0.6)
    ax.axvline(frel.mean(), color="#111111", ls=":", lw=1.1,
               label=f"$\\mu={frel.mean():.2f}$, $\\sigma={frel.std(ddof=1):.2f}$ kHz")
    ax.set_title("(c) Relax Frequency Mismatch (sleep_relax)")
    ax.set_xlabel("Frequency (kHz)")
    ax.set_ylabel("Samples (out of 40)")
    ax.legend(frameon=True, fontsize=6.5, loc="upper right")

    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_mc_mismatch.pdf")
    plt.close(fig)


def crop_schematics() -> None:
    """Copy & tightly crop xschem schematic PDFs into report/figures/sch_*.pdf via Ghostscript."""
    names = ["bias", "idac_8b", "cco_core", "comp", "relax_core", "rpe_clk_analog"]
    for nm in names:
        src = SCH_PDF_DIR / f"{nm}.pdf"
        dst = FIG_DIR / f"sch_{nm}.pdf"
        bb_res = subprocess.run(
            ["gs", "-sDEVICE=bbox", "-dNOPAUSE", "-dBATCH", "-q", str(src)],
            capture_output=True, text=True, check=True,
        )
        m = re.search(r"%%BoundingBox:\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", bb_res.stderr)
        if m:
            x1, y1, x2, y2 = [float(v) for v in m.groups()]
            pad = 6.0
            cx1, cy1, cx2, cy2 = x1 - pad, y1 - pad, x2 + pad, y2 + pad
            w_pt, h_pt = max(10.0, cx2 - cx1), max(10.0, cy2 - cy1)
            subprocess.run(
                [
                    "gs", "-dNOPAUSE", "-dBATCH", "-q", "-sDEVICE=pdfwrite",
                    f"-dDEVICEWIDTHPOINTS={w_pt:.2f}", f"-dDEVICEHEIGHTPOINTS={h_pt:.2f}",
                    "-dFIXEDMEDIA", "-o", str(dst),
                    "-c", f"<< /PageOffset [{-cx1:.2f} {-cy1:.2f}] >> setpagedevice",
                    "-f", str(src),
                ],
                check=True,
            )
        else:
            dst.write_bytes(src.read_bytes())
    print(f"Cropped {len(names)} schematic PDFs to {FIG_DIR}")


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plot_bias_pvt()
    plot_ring_trim()
    plot_ring_sensitivity()
    plot_relax_options()
    plot_macro_waveforms()
    plot_pex_comparison()
    plot_mc_mismatch()
    crop_schematics()
    print("Generated all 7 vector plots and cropped schematic PDFs.")


if __name__ == "__main__":
    main()
