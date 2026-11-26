#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Custom compacted layout builders for bias_lay, idac_8b_lay, and cco_core_lay in IHP SG13CMOS5L."""

from __future__ import annotations
from typing import Dict, List, Tuple
import pya as db

from lay_core import (
    L_M1, L_M2, L_M3, L_M4, L_NWELL,
    BoxU, FetPins, LayoutBuilder, STDCELL_H, std_pin_pad,
)
from lay_router import NetRouter


def build_bias_lay(lb: LayoutBuilder) -> Tuple[db.Cell, Dict[str, Tuple[float, float, int]]]:
    """Build compacted bias_lay subblock matching analog/bias/bias.sch."""
    cell = lb.ly.create_cell("bias_lay")

    # R_BIAS at left: (2.2, 2.4) -> bbox ~(2.0..15.82, 1.69..23.73)
    rp, rm, _ = lb.place_rppd(cell, 2.2, 2.4, w_um=0.5, l_um=20.0, bends=19)

    # NMOS row at y = 3.2 with gate_side="top"
    f_mn1 = lb.place_fet_array(cell, "nmos", 16.8, 3.2, 0.3, 4.0, m_count=1, cols=1, gate_side="top")
    f_mn2 = lb.place_fet_array(cell, "nmos", 22.2, 3.2, 0.3, 4.0, m_count=4, cols=1, dy_um=1.00, gate_side="top")
    f_mno = lb.place_fet_array(cell, "nmos", 27.8, 3.2, 1.0, 0.5, m_count=1, cols=1, gate_side="top")
    f_men_n = lb.place_fet_array(cell, "nmos", 30.0, 3.2, 0.25, 0.5, m_count=1, cols=1, gate_side="top")
    f_msu_n = lb.place_fet_array(cell, "nmos", 32.2, 3.2, 4.0, 0.5, m_count=1, cols=1, gate_side="top")
    f_msu_inj = lb.place_fet_array(cell, "nmos", 34.5, 3.2, 0.5, 1.0, m_count=1, cols=1, gate_side="top")

    # PMOS lower row y = 14.8, upper startup long-L PMOS row y = 20.8
    f_mp1 = lb.place_fet_array(cell, "pmos", 16.8, 14.8, 1.0, 4.0, m_count=1, cols=1, gate_side="bot")
    f_mp2 = lb.place_fet_array(cell, "pmos", 22.6, 14.8, 1.0, 4.0, m_count=1, cols=1, gate_side="bot")
    f_mpout = lb.place_fet_array(cell, "pmos", 28.4, 14.8, 1.0, 4.0, m_count=1, cols=1, gate_side="bot")
    f_mpo = lb.place_fet_array(cell, "pmos", 34.2, 14.8, 1.0, 0.5, m_count=1, cols=1, gate_side="bot")
    f_men_p = lb.place_fet_array(cell, "pmos", 36.5, 14.8, 0.5, 0.5, m_count=1, cols=1, gate_side="bot")
    f_msu_en = lb.place_fet_array(cell, "pmos", 38.8, 14.8, 0.3, 1.0, m_count=1, cols=1, gate_side="bot")
    f_msu_p1 = lb.place_fet_array(cell, "pmos", 16.8, 20.8, 0.15, 10.0, m_count=1, cols=1, gate_side="bot")
    f_msu_p2 = lb.place_fet_array(cell, "pmos", 29.2, 20.8, 0.15, 10.0, m_count=1, cols=1, gate_side="bot")

    # Shared NWell over all bias PMOS + top ntap1 row tied to VDD
    x_bias_end = 41.6
    lb.rect(cell, L_NWELL, 16.0, 13.8, 41.5, 25.0)
    vdd_y = 23.8
    vss_y = 0.6
    lb.rect(cell, L_M1, 16.0, vdd_y - 0.40, 41.5, vdd_y + 0.40)
    lb.rect(cell, L_M2, 0.6, vdd_y - 0.35, x_bias_end, vdd_y + 0.35)
    for tx in (17.5, 23.5, 29.5, 35.5, 40.2):
        tm = lb.place_tap(cell, "ntap1", tx, vdd_y - 0.39)
        lb.via_stack(cell, tm.cx, tm.cy, 1, 2)

    lb.rect(cell, L_M1, 0.6, vss_y - 0.40, 41.5, vss_y + 0.40)
    lb.rect(cell, L_M2, 0.6, vss_y - 0.35, x_bias_end, vss_y + 0.35)
    for px in (1.5, 9.0, 16.5, 24.0, 31.5, 39.0):
        pm = lb.place_tap(cell, "ptap1", px, vss_y - 0.39)
        lb.via_stack(cell, pm.cx, pm.cy, 1, 2)
    # Extra ptaps above R_BIAS wired in M1 down left gutter (x=1.0) to vss_y
    lb.wire(cell, L_M1, [(1.0, vss_y), (1.0, 24.8), (14.5, 24.8)], w=0.30)
    for px in (2.5, 14.0):
        lb.place_tap(cell, "ptap1", px, 24.41)

    rt = NetRouter(lb, cell, m2_y0=8.6, m2_pitch=0.64, m3_pitch=0.64, pack=True)

    lb.wire(cell, L_M1, [(rm.cx, rm.cy), (rm.cx, vss_y)], w=0.22)
    for fn in (f_mn1, f_mno, f_men_n, f_msu_n, f_msu_inj):
        sx = fn.S.cx
        lb.wire(cell, L_M1, [(sx, fn.S.y2 - 0.1), (sx, vss_y)], w=0.22)
    rt.connect([(f_msu_p1.G.cx, f_msu_p1.G.cy, 1), (f_msu_p2.G.cx, f_msu_p2.G.cy, 1), (18.0, vss_y, 2)])

    rt.connect([(f.S.cx, f.S.cy, 1) for f in (f_mp1, f_mp2, f_mpout, f_mpo, f_men_p, f_msu_en)] + [(18.0, vdd_y, 2)], y_track=17.6)

    rt.connect([(rp.cx, rp.cy, 1), (f_mn2.S.cx, f_mn2.S.y1 + 0.2, 1)])
    y_vpb = rt.connect(
        [
            (f_mn2.D.cx, f_mn2.D.cy, 1),
            (f_msu_inj.D.cx, f_msu_inj.D.cy, 1),
            (f_mp2.D.cx, f_mp2.D.cy, 1),
            (f_mpo.D.cx, f_mpo.D.cy, 1),
            (f_mp1.G.cx, f_mp1.G.cy, 1),
            (f_mp2.G.cx, f_mp2.G.cy, 1),
            (f_mpout.G.cx, f_mpout.G.cy, 1),
        ],
        extend_to_x=[x_bias_end],
    )
    y_vnb = rt.connect(
        [
            (f_mn1.D.cx, f_mn1.D.cy, 1),
            (f_mn1.G.cx, f_mn1.G.cy, 1),
            (f_mn2.G.cx, f_mn2.G.cy, 1),
            (f_mno.D.cx, f_mno.D.cy, 1),
            (f_msu_n.G.cx, f_msu_n.G.cy, 1),
            (f_mp1.D.cx, f_mp1.D.cy, 1),
        ],
        extend_to_x=[x_bias_end],
    )
    y_en = rt.connect(
        [(f_men_n.G.cx, f_men_n.G.cy, 1), (f_men_p.G.cx, f_men_p.G.cy, 1), (f_mpo.G.cx, f_mpo.G.cy, 1)],
        extend_to_x=[x_bias_end],
    )
    rt.connect([(f_men_n.D.cx, f_men_n.D.cy, 1), (f_men_p.D.cx, f_men_p.D.cy, 1), (f_mno.G.cx, f_mno.G.cy, 1), (f_msu_en.G.cx, f_msu_en.G.cy, 1)])
    rt.connect([(f_msu_en.D.cx, f_msu_en.D.cy, 1), (f_msu_p1.S.cx, f_msu_p1.S.cy, 1)], y_track=18.3)
    rt.connect([(f_msu_p1.D.cx, f_msu_p1.D.cy, 1), (f_msu_p2.S.cx, f_msu_p2.S.cy, 1)], y_track=19.0)
    rt.connect([(f_msu_p2.D.cx, f_msu_p2.D.cy, 1), (f_msu_n.D.cx, f_msu_n.D.cy, 1), (f_msu_inj.G.cx, f_msu_inj.G.cy, 1)])
    y_iout = rt.connect([(f_mpout.D.cx, f_mpout.D.cy, 1)], extend_to_x=[x_bias_end])

    pins = {
        "VDD": (0.8, vdd_y, 2),
        "VSS": (0.8, vss_y, 2),
        "en": (x_bias_end, y_en, 2),
        "vpbias": (x_bias_end, y_vpb, 2),
        "vnbias": (x_bias_end, y_vnb, 2),
        "ibias_out": (x_bias_end, y_iout, 2),
    }
    return cell, pins


def build_idac_8b_lay(lb: LayoutBuilder) -> Tuple[db.Cell, Dict[str, Tuple[float, float, int]]]:
    """Build compacted 5-column 2-row-stdcell idac_8b_lay subblock matching analog/osc_ring_cc/idac_8b.sch."""
    cell = lb.ly.create_cell("idac_8b_lay")

    # 1. Two rows of 9 stdcells with dedicated open bridge channel between Row 0 (y=1.8) and Row 1 (y=14.0)
    row0_specs = [
        ("XINV_EN", "sg13cmos5l_inv_1"),
        ("XINV_B0", "sg13cmos5l_inv_1"), ("XINV_B1", "sg13cmos5l_inv_1"),
        ("XINV_B2", "sg13cmos5l_inv_1"), ("XINV_B3", "sg13cmos5l_inv_1"),
        ("XINV_B4", "sg13cmos5l_inv_1"), ("XINV_A", "sg13cmos5l_inv_1"),
        ("XN_AB", "sg13cmos5l_nand2_2"), ("XI_AB", "sg13cmos5l_inv_1"),
    ]
    row1_specs = [
        ("XN_ABC", "sg13cmos5l_nand2_2"), ("XN_BC", "sg13cmos5l_nand2_2"),
        ("XI_BC", "sg13cmos5l_inv_1"), ("XNO_T2", "sg13cmos5l_nor2_1"),
        ("XNO_BORC", "sg13cmos5l_nor2_1"), ("XI_BORC", "sg13cmos5l_inv_1"),
        ("XN_T4", "sg13cmos5l_nand2_2"), ("XNO_T1", "sg13cmos5l_nor2_1"),
        ("XNO_T0", "sg13cmos5l_nor2_1"),
    ]
    y_std0, y_std1 = 1.8, 14.0
    std_pins: Dict[str, Dict[str, Tuple[float, float, int]]] = {}
    row0_insts = {nm for nm, _ in row0_specs}
    row_max_x = 0.0
    for y_s, specs, x0, gap in [(y_std0, row0_specs, 2.4, 3.00), (y_std1, row1_specs, 2.4, 2.55)]:
        x_cur = x0
        for iname, cname in specs:
            w, pdict = lb.place_stdcell(cell, cname, x_cur, y_s)
            std_pins[iname] = lb.escape_stdcell_pins(cell, cname, x_cur, pdict, gut=0.48)
            x_cur += w + gap
        row_max_x = max(row_max_x, x_cur)

    # 2. 5-column PMOS array width determines block right edge (~45.6 um)
    col_x0 = 8.6
    col_dx = 5.65
    x_arr_end = round(max(45.6, col_x0 + 5 * col_dx + 3.0, row_max_x + 1.5), 2)

    lb.bridge_stdcell_row(cell, 0.2, x_arr_end - 0.6, y_std0)
    lb.bridge_stdcell_row(cell, 0.2, x_arr_end - 0.6, y_std1)
    for tx in range(3, int(x_arr_end - 1), 10):
        tm0 = lb.place_tap(cell, "ntap1", float(tx), y_std0 + STDCELL_H + 0.42)
        lb.wire(cell, L_M1, [(tm0.cx, tm0.cy), (tm0.cx, y_std0 + STDCELL_H)], w=0.40)
        pm0 = lb.place_tap(cell, "ptap1", float(tx), y_std0 - 1.25)
        lb.wire(cell, L_M1, [(pm0.cx, pm0.cy), (pm0.cx, y_std0)], w=0.40)
        tm1 = lb.place_tap(cell, "ntap1", float(tx), y_std1 + STDCELL_H + 0.42)
        lb.wire(cell, L_M1, [(tm1.cx, tm1.cy), (tm1.cx, y_std1 + STDCELL_H)], w=0.40)
        pm1 = lb.place_tap(cell, "ptap1", float(tx), y_std1 - 1.15)
        lb.wire(cell, L_M1, [(pm1.cx, pm1.cy), (pm1.cx, y_std1)], w=0.40)

    # 3. Single row of 13 switch PMOS (y_sw=30.0) + MN_DIV (outside NWell!)
    sw_defs = [
        ("PED", 4), ("B0", 1), ("B1", 1), ("B2", 1), ("B3", 1), ("B4", 2),
        ("T0", 4), ("T1", 4), ("T2", 4), ("T3", 4), ("T4", 4), ("T5", 4), ("T6", 4),
    ]
    y_sw = 30.0
    sw_fets: Dict[str, FetPins] = {}
    sx = 8.6
    for sname, mcnt in sw_defs:
        sw_fets[sname] = lb.place_fet_array(cell, "pmos", sx, y_sw, 1.0, 0.2, m_count=mcnt, cols=1, dy_um=1.48, gate_side="bot")
        sx += 2.65
    f_mndiv = lb.place_fet_array(cell, "nmos", 2.4, y_sw, 0.3, 4.0, m_count=1, cols=1, gate_side="top")

    # 4. Stacked 5-column current-source PMOS array above rt_drn (y_arr=45.4)
    y_arr = 45.4
    dy_u = 1.08

    ped_0 = lb.place_fet_array(cell, "pmos", col_x0 + 0 * col_dx, y_arr, 0.5, 4.0, m_count=24, cols=1, dy_um=dy_u, gate_side="bot")
    ped_1 = lb.place_fet_array(cell, "pmos", col_x0 + 1 * col_dx, y_arr, 0.5, 4.0, m_count=24, cols=1, dy_um=dy_u, gate_side="bot")
    t_fets: Dict[str, FetPins] = {}
    t_fets["T0"] = lb.place_fet_array(cell, "pmos", col_x0 + 0 * col_dx, y_arr + 26 * dy_u, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")
    t_fets["T1"] = lb.place_fet_array(cell, "pmos", col_x0 + 1 * col_dx, y_arr + 26 * dy_u, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")

    t_fets["T2"] = lb.place_fet_array(cell, "pmos", col_x0 + 2 * col_dx, y_arr, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")
    t_fets["T3"] = lb.place_fet_array(cell, "pmos", col_x0 + 2 * col_dx, y_arr + 34 * dy_u, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")

    t_fets["T4"] = lb.place_fet_array(cell, "pmos", col_x0 + 3 * col_dx, y_arr, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")
    t_fets["T5"] = lb.place_fet_array(cell, "pmos", col_x0 + 3 * col_dx, y_arr + 34 * dy_u, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")

    col4_x = col_x0 + 4 * col_dx
    b_fets: Dict[str, FetPins] = {}
    row_idx = 0
    for bname, bcnt in [("B0", 1), ("B1", 2), ("B2", 4), ("B3", 8), ("B4", 16)]:
        b_fets[bname] = lb.place_fet_array(cell, "pmos", col4_x, y_arr + row_idx * dy_u, 0.5, 4.0, m_count=bcnt, cols=1, dy_um=dy_u, gate_side="bot")
        row_idx += bcnt + 1
    row_idx += 1  # extra breathing room below T6 gate
    t_fets["T6"] = lb.place_fet_array(cell, "pmos", col4_x, y_arr + row_idx * dy_u, 0.5, 4.0, m_count=32, cols=1, dy_um=dy_u, gate_side="bot")

    # Left ref divider: MP_DAC_OFF + MP_IN
    f_mpoff = lb.place_fet_array(cell, "pmos", 2.4, y_arr, 0.5, 0.5, m_count=1, cols=1, gate_side="bot")
    f_mpin = lb.place_fet_array(cell, "pmos", 2.4, y_arr + 3.6, 1.5, 4.0, m_count=2, cols=1, dy_um=2.06, gate_side="bot")

    y_vdd_top = round(y_arr + (row_idx + 32) * dy_u + 1.2, 2)
    # L-shaped NWell (excludes f_mndiv!): rect1 over MPS + 5-col MPC, rect2 over MP_IN + MP_DAC_OFF
    lb.rect(cell, L_NWELL, 7.8, y_sw - 1.0, x_arr_end, y_vdd_top + 1.2)
    lb.rect(cell, L_NWELL, 1.5, y_arr - 1.2, 8.6, y_vdd_top + 1.2)

    lb.rect(cell, L_M1, 1.5, y_vdd_top - 0.40, x_arr_end, y_vdd_top + 0.40)
    lb.rect(cell, L_M2, -0.8, y_vdd_top - 0.35, x_arr_end, y_vdd_top + 0.35)
    for tx in range(3, int(x_arr_end), 10):
        tm = lb.place_tap(cell, "ntap1", float(tx), y_vdd_top - 0.39)
        lb.via_stack(cell, tm.cx, tm.cy, 1, 2)

    pm_div = lb.place_tap(cell, "ptap1", 2.4, y_sw - 1.7)
    lb.wire(cell, L_M1, [(f_mndiv.S.cx, f_mndiv.S.y1 + 0.15), (f_mndiv.S.cx, pm_div.cy), (pm_div.cx, pm_div.cy)], w=0.24)
    lb.via_stack(cell, pm_div.cx, pm_div.cy, 1, 2)

    # VDD sources for MPC_* columns -> continuous vertical M1 per column up to y_vdd_top
    for fp in [f_mpin, f_mpoff, ped_0, ped_1, t_fets["T2"], t_fets["T4"]]:
        lb.wire(cell, L_M1, [(fp.S.cx, fp.S.y2), (fp.S.cx, y_vdd_top)], w=0.24)
    for bf in list(b_fets.values()) + list(t_fets.values()):
        lb.wire(cell, L_M1, [(bf.S.cx, bf.S.y1), (bf.S.cx, bf.S.y2)], w=0.24)
    lb.wire(cell, L_M1, [(b_fets["B0"].S.cx, b_fets["B0"].S.y1), (t_fets["T6"].S.cx, y_vdd_top)], w=0.24)

    # Power M3 straps strictly at left (x=0.4 VSS) and right (x_vdd_m3 VDD) outside signal routing core
    shared_vx: List[Tuple[float, float, float, None]] = []
    shared_m2: List[Tuple[float, float, float, Tuple[int, int]]] = []
    x_vss_m3 = 0.4
    x_vdd_m3 = round(x_arr_end - 1.0, 2)
    shared_vx.append((x_vss_m3, y_std0 - 0.5, pm_div.cy + 0.5, None))
    shared_vx.append((x_vdd_m3, y_std0 + STDCELL_H - 0.5, y_vdd_top + 0.5, None))

    for ys in (y_std0, y_std1):
        lb.wire(cell, L_M2, [(1.2, ys + STDCELL_H), (x_arr_end - 0.6, ys + STDCELL_H)], w=0.38)
        lb.via_stack(cell, x_vdd_m3, ys + STDCELL_H, 1, 3)
        lb.wire(cell, L_M2, [(0.4, ys), (x_arr_end - 0.6, ys)], w=0.38)
        lb.via_stack(cell, 1.3, ys, 1, 2)
        lb.via_stack(cell, x_vss_m3, ys, 2, 3)
    lb.wire(cell, L_M3, [(x_vdd_m3, y_std0 + STDCELL_H), (x_vdd_m3, y_vdd_top)], w=0.40)
    lb.via_stack(cell, x_vdd_m3, y_vdd_top, 2, 3)
    lb.wire(cell, L_M3, [(x_vss_m3, y_std0), (x_vss_m3, pm_div.cy)], w=0.36)
    lb.via_stack(cell, x_vss_m3, pm_div.cy, 2, 3)
    lb.wire(cell, L_M2, [(x_vss_m3, pm_div.cy), (pm_div.cx, pm_div.cy)], w=0.30)

    rt_top = NetRouter(lb, cell, m2_y0=43.8, m2_pitch=0.66, m3_pitch=0.66, shared_vx=shared_vx, shared_m2=shared_m2, min_x=1.15)
    rt_drn = NetRouter(lb, cell, m2_y0=37.2, m2_pitch=0.66, m3_pitch=0.66, shared_vx=shared_vx, shared_m2=shared_m2, min_x=1.15, pack=True)
    rt_low = NetRouter(lb, cell, m2_y0=6.8, m2_pitch=0.66, m3_pitch=0.66, shared_vx=shared_vx, shared_m2=shared_m2, min_x=1.15, pack=False)
    rt_mid = NetRouter(lb, cell, m2_y0=19.2, m2_pitch=0.66, m3_pitch=0.66, shared_vx=shared_vx, shared_m2=shared_m2, min_x=1.15, pack=True)

    # Row 0 stays strictly inside y <= 12.2: bridge upward Row 0 pins onto staggered M2 landing pads (y=10.2..12.18)
    # while routing trim0..4 cleanly in rt_low (y=6.8..9.44)
    port_y: Dict[str, float] = {}
    for b in range(5):
        p_t = std_pins[f"XINV_B{b}"]["A"]
        rt_low.reserve_pin(p_t[0], p_t[1], 9.8)
        port_y[f"trim{b}"] = rt_low.connect([p_t], extend_to_x=[-0.8])

    # Reserve Row 1 pins + ALL upward Row 0 raw Xs so static pre-jog never collides with another Row 0 stub
    taken_m3_x: List[float] = [x_vss_m3, x_vdd_m3]
    for iname, _ in row1_specs:
        for ex, ey, ml in std_pins[iname].values():
            if ml == 3:
                rt_mid.reserve_pin(ex, ey, y_sw - 0.5)
                taken_m3_x.append(round(ex, 3))

    row0_raw_xs = []
    for iname, _ in row0_specs:
        for pn, (ex, ey, ml) in std_pins[iname].items():
            if not (iname.startswith("XINV_B") and pn == "A"):
                row0_raw_xs.append(round(ex, 3))

    row0_lifted: Dict[Tuple[str, str], Tuple[float, float, int]] = {}
    used_bridge_m2: List[Tuple[float, float, float]] = []
    up_idx = 0
    for iname, _ in row0_specs:
        for pn, (ex, ey, ml) in sorted(std_pins[iname].items()):
            if iname.startswith("XINV_B") and pn == "A":
                continue
            ex_r = round(ex, 3)
            if all(abs(ex_r - tx) >= 0.68 for tx in taken_m3_x):
                rt_mid.reserve_pin(ex_r, ey, y_sw - 0.5)
                taken_m3_x.append(ex_r)
                row0_lifted[(iname, pn)] = (ex_r, ey, 3)
            else:
                # Pick nearest clean X in [1.2..x_arr_end-1.8] clearing BOTH taken_m3_x and all Row 0 stub Xs
                forbidden_x = taken_m3_x + row0_raw_xs
                found_x = None
                for step in range(1, 1600):
                    off = ((step + 1) // 2) * 0.05
                    cx = round(ex_r + (off if step % 2 == 1 else -off), 3)
                    if 1.15 <= cx <= x_arr_end - 1.7 and all(abs(cx - tx) >= 0.67 for tx in forbidden_x):
                        found_x = cx
                        break
                assert found_x is not None, f"No Row 1 pass-through X near {ex_r}"
                xlo, xhi = min(ex_r, found_x) - 0.34, max(ex_r, found_x) + 0.34
                y_br = None
                for k_br in range(6):
                    yb = round(10.0 + ((up_idx + k_br) % 4) * 0.68, 3)
                    if all(abs(yb - uy) >= 0.50 or xhi < ux1 or xlo > ux2 for uy, ux1, ux2 in used_bridge_m2):
                        y_br = yb
                        break
                if y_br is None:
                    y_br = round(10.0 + (up_idx % 4) * 0.68, 3)
                up_idx += 1
                used_bridge_m2.append((y_br, xlo, xhi))
                lb.wire(cell, L_M3, [(ex_r, ey), (ex_r, y_br)], w=0.24)
                lb.via(cell, ex_r, y_br, 2)
                lb.wire(cell, L_M2, [(ex_r, y_br), (found_x, y_br)], w=0.24)
                lb.via(cell, found_x, y_br, 2)
                rt_mid.reserve_pin(found_x, y_br, y_sw - 0.5)
                taken_m3_x.append(found_x)
                row0_lifted[(iname, pn)] = (found_x, y_br, 3)

    # Reserve f_mndiv.D X before ictrl routes sw_fets
    rt_drn.reserve_x(round(f_mndiv.D.cx, 3), f_mndiv.D.cy, 43.8)

    # ictrl rail above switches (y = 36.1, cleanly >0.35um above sw_fets.S.y2=35.49)
    y_ictrl = 36.1
    ictrl_pins = [(sw_fets[s].D.cx, sw_fets[s].D.y1 + 0.15, 1) for s, _ in sw_defs]
    rt_drn.connect(ictrl_pins, y_track=y_ictrl, extend_to_x=[x_arr_end])

    # vpdac net: MP_IN, MP_DAC_OFF, MN_DIV, PED_0/1, B0..B4, T0..T6
    vpdac_pins = (
        [(f_mpin.D.cx, f_mpin.D.cy, 1), (f_mpin.G.cx, f_mpin.G.cy, 1), (f_mpoff.D.cx, f_mpoff.D.cy, 1), (f_mndiv.D.cx, f_mndiv.D.cy, 1)]
        + [(ped_0.G.cx, ped_0.G.cy, 1), (ped_1.G.cx, ped_1.G.cy, 1)]
        + [(b_fets[b].G.cx, b_fets[b].G.cy, 1) for b in ("B0", "B1", "B2", "B3", "B4")]
        + [(t_fets[f"T{k}"].G.cx, t_fets[f"T{k}"].G.cy, 1) for k in range(7)]
    )
    rt_top.connect(vpdac_pins, y_track=43.8)

    # MPC drains -> MPS sources (stagger S M1 tap Y across 33.8 / 34.5 / 35.2)
    rt_drn.connect([(ped_0.D.cx, ped_0.D.y1 + 0.15, 1), (ped_1.D.cx, ped_1.D.y1 + 0.15, 1), (sw_fets["PED"].S.cx, sw_fets["PED"].S.y2 - 0.15, 1)])
    for bname in ("B0", "B1", "B2", "B3", "B4"):
        bf = b_fets[bname]
        rt_drn.connect([(bf.D.cx, bf.D.cy, 1), (sw_fets[bname].S.cx, sw_fets[bname].S.y2 - 0.15, 1)])
    for k in range(7):
        tk = f"T{k}"
        sy_tap = round(sw_fets[tk].S.y2 - 0.15 - (k % 3) * 0.70, 3)
        rt_drn.connect([(t_fets[tk].D.cx, t_fets[tk].D.y1 + 0.15, 1), (sw_fets[tk].S.cx, sy_tap, 1)])
    assert rt_drn.max_used_y() < 43.2, f"idac rt_drn overflow: {rt_drn.max_used_y()}"

    def sp(inst: str, pin: str) -> Tuple[float, float, int]:
        if (inst, pin) in row0_lifted:
            return row0_lifted[(inst, pin)]
        return std_pins[inst][pin]

    def sw_g(sname: str, idx: int) -> Tuple[float, float, int]:
        g = sw_fets[sname].G
        if idx % 2 == 1:
            gy = round(g.cy - 0.66, 3)
            lb.wire(cell, L_M1, [(g.cx, g.cy), (g.cx, gy)], w=0.22)
            return (g.cx, gy, 1)
        return (g.cx, g.cy, 1)

    net_map = {
        "trim5": [sp("XN_ABC", "B"), sp("XN_BC", "B"), sp("XNO_BORC", "B")],
        "trim6": [sp("XN_AB", "B"), sp("XN_BC", "A"), sp("XNO_BORC", "A"), sp("XNO_T1", "B")],
        "trim7": [sp("XINV_A", "A"), sp("XN_AB", "A"), sp("XNO_T2", "A"), sp("XN_T4", "A"), sp("XNO_T1", "A"), sp("XNO_T0", "A")],
        "en": [sp("XINV_EN", "A")],
        "ab": [sp("XI_AB", "Y"), sp("XN_ABC", "A")],
        "bc_n": [sp("XN_BC", "Y"), sp("XI_BC", "A")],
        "bc": [sp("XI_BC", "Y"), sp("XNO_T2", "B")],
        "borc_n": [sp("XNO_BORC", "Y"), sp("XI_BORC", "A")],
        "borc": [sp("XI_BORC", "Y"), sp("XN_T4", "B"), sp("XNO_T0", "B")],
        "enb": [sp("XINV_EN", "Y"), sw_g("PED", 0)],
        "b0_b": [sp("XINV_B0", "Y"), sw_g("B0", 1)],
        "b1_b": [sp("XINV_B1", "Y"), sw_g("B1", 2)],
        "b2_b": [sp("XINV_B2", "Y"), sw_g("B2", 3)],
        "b3_b": [sp("XINV_B3", "Y"), sw_g("B3", 4)],
        "b4_b": [sp("XINV_B4", "Y"), sw_g("B4", 5)],
        "t3_b": [sp("XINV_A", "Y"), sw_g("T3", 6)],
        "t5_b": [sp("XN_AB", "Y"), sp("XI_AB", "A"), sw_g("T5", 7)],
        "t6_b": [sp("XN_ABC", "Y"), sw_g("T6", 8)],
        "t2_b": [sp("XNO_T2", "Y"), sw_g("T2", 9)],
        "t4_b": [sp("XN_T4", "Y"), sw_g("T4", 10)],
        "t1_b": [sp("XNO_T1", "Y"), sw_g("T1", 11)],
        "t0_b": [sp("XNO_T0", "Y"), sw_g("T0", 12)],
    }

    for nname, plist in net_map.items():
        if nname.startswith("trim"):
            ext = [-0.8]
        elif nname == "en":
            ext = [x_arr_end]
        else:
            ext = None
        yt = rt_mid.connect(plist, extend_to_x=ext)
        if ext:
            port_y[nname] = yt

    y_vnb = rt_mid.connect([(f_mndiv.G.cx, f_mndiv.G.cy, 1)], extend_to_x=[x_arr_end])
    # Connect MP_DAC_OFF.G via left gutter x=1.15 M3 straight down to y_en M2 trunk (drawn across 1.15..x_arr_end)
    y_en = port_y["en"]
    lb.via_stack(cell, f_mpoff.G.cx, f_mpoff.G.cy, 1, 2)
    lb.wire(cell, L_M2, [(f_mpoff.G.cx, f_mpoff.G.cy), (1.15, f_mpoff.G.cy)], w=0.24)
    lb.via_stack(cell, 1.15, f_mpoff.G.cy, 2, 3)
    lb.wire(cell, L_M3, [(1.15, f_mpoff.G.cy), (1.15, y_en)], w=0.24)
    lb.via_stack(cell, 1.15, y_en, 2, 3)
    lb.wire(cell, L_M2, [(1.15, y_en), (x_arr_end, y_en)], w=0.24)
    rt_mid.reserve_x(1.15, y_en, f_mpoff.G.cy)
    assert rt_mid.max_used_y() < y_sw - 1.5, f"idac rt_mid too high ({rt_mid.max_used_y()}) vs y_sw={y_sw}"

    pins = {
        "VDD": (-0.8, y_vdd_top, 2),
        "VSS": (x_vss_m3, y_std0, 3),
        "en": (x_arr_end, y_en, 2),
        "vnbias": (x_arr_end, y_vnb, 2),
        "ictrl": (x_arr_end, y_ictrl, 2),
    }
    for i in range(8):
        pins[f"trim{i}"] = (-0.8, port_y[f"trim{i}"], 2)
    return cell, pins


def build_cco_core_lay(lb: LayoutBuilder) -> Tuple[db.Cell, Dict[str, Tuple[float, float, int]]]:
    """Build compacted cco_core_lay subblock matching analog/osc_ring_cc/cco_core.sch."""
    cell = lb.ly.create_cell("cco_core_lay")

    y_nmos = 8.4
    y_pmos = 22.0
    # Bias mirror (left)
    f_mn_bias = lb.place_fet_array(cell, "nmos", 2.0, y_nmos, 2.0, 1.0, m_count=2, cols=1, dy_um=2.56, gate_side="top")
    f_mn_bmir = lb.place_fet_array(cell, "nmos", 4.6, y_nmos, 2.0, 1.0, m_count=2, cols=1, dy_um=2.56, gate_side="top")
    f_mn_noff = lb.place_fet_array(cell, "nmos", 7.2, y_nmos, 0.5, 0.5, m_count=1, cols=1, gate_side="top")
    f_mp_bias = lb.place_fet_array(cell, "pmos", 2.0, y_pmos, 4.0, 1.0, m_count=2, cols=1, dy_um=4.56, gate_side="bot")
    f_mp_poff = lb.place_fet_array(cell, "pmos", 5.2, y_pmos, 0.5, 0.5, m_count=1, cols=1, gate_side="bot")

    # 5 stages (k=0..4) along sx = 10.6 + k * 7.2
    y_cap = 33.8
    stgs = []
    for k in range(5):
        sx = 10.6 + k * 7.2
        mnc = lb.place_fet_array(cell, "nmos", sx, y_nmos, 2.0, 1.0, m_count=1, gate_side="top")
        mni = lb.place_fet_array(cell, "nmos", sx + 3.0, y_nmos, 0.5, 0.2, m_count=1, gate_side="top")
        mpc = lb.place_fet_array(cell, "pmos", sx, y_pmos, 4.0, 1.0, m_count=1, gate_side="bot")
        mpi = lb.place_fet_array(cell, "pmos", sx + 3.8, y_pmos, 1.0, 0.2, m_count=1, gate_side="bot")
        cplus, cminus, _ = lb.place_cmomf(cell, sx + 1.0, y_cap, size_um=2.4)
        stgs.append((mnc, mni, mpc, mpi, cplus, cminus))

    # MN_RST at far right
    f_rst = lb.place_fet_array(cell, "nmos", 47.6, y_nmos, 0.5, 0.5, m_count=1, gate_side="top")

    # Bottom 4 stdcells: XINV_EN on left (near en/mn_noff), XBUF1/2/4 on right (near stage 3 and clk out)
    y_std = 1.6
    st_pins: Dict[str, Dict[str, Tuple[float, float, int]]] = {}
    w_en, pd_en = lb.place_stdcell(cell, "sg13cmos5l_inv_1", 2.6, y_std)
    st_pins["XINV_EN"] = lb.escape_stdcell_pins(cell, "sg13cmos5l_inv_1", 2.6, pd_en, gut=0.48)
    x_cur = 28.0
    for iname, cname in [("XBUF1", "sg13cmos5l_inv_1"), ("XBUF2", "sg13cmos5l_inv_2"), ("XBUF4", "sg13cmos5l_buf_4")]:
        w, pd = lb.place_stdcell(cell, cname, x_cur, y_std)
        st_pins[iname] = lb.escape_stdcell_pins(cell, cname, x_cur, pd, gut=0.48)
        x_cur += w + 2.40
    lb.bridge_stdcell_row(cell, 0.2, round(max(46.0, x_cur + 1.0), 2), y_std)

    # NWell over all PMOS + ntap1 + VDD M1/M2
    lb.rect(cell, L_NWELL, 1.2, y_pmos - 1.0, 47.2, 32.9)
    y_vdd = 31.8
    y_vss_nmos = 6.8
    lb.rect(cell, L_M1, 1.2, y_vdd - 0.40, 49.6, y_vdd + 0.40)
    lb.rect(cell, L_M2, -0.8, y_vdd - 0.35, 49.6, y_vdd + 0.35)
    for tx in (3.0, 12.5, 22.0, 31.5, 41.0, 46.2):
        tm = lb.place_tap(cell, "ntap1", float(tx), y_vdd - 0.39)
        lb.via_stack(cell, tm.cx, tm.cy, 1, 2)

    x_vss_strap = 50.6
    x_clk_out = 51.9
    lb.rect(cell, L_M1, 1.2, y_vss_nmos - 0.40, 50.6, y_vss_nmos + 0.40)
    lb.rect(cell, L_M2, -0.8, y_vss_nmos - 0.35, 50.9, y_vss_nmos + 0.35)
    for px in (3.0, 12.5, 22.0, 31.5, 41.0, 48.5):
        pm = lb.place_tap(cell, "ptap1", float(px), y_vss_nmos - 0.39)
        lb.via_stack(cell, pm.cx, pm.cy, 1, 2)

    x_std_vdd_m3 = 0.4
    x_std_vss_m2 = 1.1
    lb.via_stack(cell, x_std_vdd_m3, y_std + STDCELL_H, 1, 3)
    lb.wire(cell, L_M3, [(x_std_vdd_m3, y_std + STDCELL_H), (x_std_vdd_m3, y_vdd)], w=0.35)
    lb.via_stack(cell, x_std_vdd_m3, y_vdd, 2, 3)

    lb.via_stack(cell, x_std_vss_m2, y_std, 1, 2)
    lb.wire(cell, L_M2, [(x_std_vss_m2, y_std), (x_std_vss_m2, y_vss_nmos)], w=0.35)

    # Top cap VSS rail above cap_cmomfs
    y_vss_top = 37.2
    lb.rect(cell, L_M2, 1.2, y_vss_top - 0.3, x_vss_strap + 0.3, y_vss_top + 0.3)
    lb.wire(cell, L_M3, [(x_vss_strap, y_vss_nmos), (x_vss_strap, y_vss_top)], w=0.40)
    lb.via_stack(cell, x_vss_strap, y_vss_nmos, 2, 3)
    lb.via_stack(cell, x_vss_strap, y_vss_top, 2, 3)
    for _, _, _, _, _, cminus in stgs:
        lb.wire(cell, L_M4, [(cminus.cx, cminus.y2 - 0.05), (cminus.cx, y_vss_top)], w=0.20)
        lb.via_stack(cell, cminus.cx, y_vss_top, 2, 4)

    for fp in [f_mp_bias, f_mp_poff] + [s[2] for s in stgs]:
        lb.wire(cell, L_M1, [(fp.S.cx, fp.S.y2 - 0.1), (fp.S.cx, y_vdd)], w=0.24)
    for fn in [f_mn_bias, f_mn_bmir, f_mn_noff, f_rst] + [s[0] for s in stgs]:
        lb.wire(cell, L_M1, [(fn.S.cx, fn.S.y1 + 0.16), (fn.S.cx, y_vss_nmos)], w=0.24)

    for mnc, mni, mpc, mpi, _, _ in stgs:
        lb.wire(cell, L_M1, [(mpc.D.cx, mpi.S.cy), (mpi.S.cx, mpi.S.cy)], w=0.22)
        lb.wire(cell, L_M1, [(mnc.D.cx, mni.S.cy), (mni.S.cx, mni.S.cy)], w=0.22)

    cap_rects = [(10.6 + k * 7.2 + 0.5, 10.6 + k * 7.2 + 3.6, 32.8, 36.6) for k in range(5)]
    rt = NetRouter(lb, cell, m2_y0=14.3, m2_pitch=0.64, m3_pitch=0.64, blocked_rects=cap_rects, min_x=1.8, pack=True)
    rt.reserve_x(x_std_vdd_m3, y_std + STDCELL_H, y_vdd)
    rt.reserve_x(x_vss_strap, y_vss_nmos, y_vss_top)
    for pmap in st_pins.values():
        for ex, ey, ml in pmap.values():
            if ml == 3:
                rt.reserve_pin(ex, ey, 13.8)

    def sp(inst: str, pn: str) -> Tuple[float, float, int]:
        return st_pins[inst][pn]

    y_en = rt.connect([sp("XINV_EN", "A"), (f_mp_poff.G.cx, f_mp_poff.G.cy, 1)], extend_to_x=[-0.8])
    lb.wire(cell, L_M1, [(f_mn_noff.G.cx, f_mn_noff.G.cy), (f_mn_noff.G.cx, 10.12)], w=0.22)
    rt.connect([sp("XINV_EN", "Y"), (f_mn_noff.G.cx, 10.12, 1), (f_rst.G.cx, f_rst.G.cy, 1)])

    # Route XBUF chain first so buffer M3 pins consume lowest tracks and clear stage pins cleanly
    rt.connect([sp("XBUF1", "Y"), sp("XBUF2", "A")])
    rt.connect([sp("XBUF2", "Y"), sp("XBUF4", "A")])
    y_clk = rt.connect([sp("XBUF4", "X")], extend_to_x=[x_clk_out])

    y_ictrl = rt.connect(
        [(f_mn_bias.D.cx, f_mn_bias.D.cy, 1), (f_mn_bias.G.cx, f_mn_bias.G.cy, 1),
         (f_mn_bmir.G.cx, f_mn_bmir.G.cy, 1), (f_mn_noff.D.cx, f_mn_noff.D.cy, 1)]
        + [(s[0].G.cx, s[0].G.cy, 1) for s in stgs],
        extend_to_x=[-0.8],
    )
    rt.connect(
        [(f_mp_bias.D.cx, f_mp_bias.D.cy, 1), (f_mp_bias.G.cx, f_mp_bias.G.cy, 1),
         (f_mn_bmir.D.cx, f_mn_bmir.D.cy, 1), (f_mp_poff.D.cx, f_mp_poff.D.cy, 1)]
        + [(s[2].G.cx, s[2].G.cy, 1) for s in stgs]
    )

    # Route stage feedback loops in non-inverting order (0, 2, 4, 1, 3) so adjacent tracks are 2 stages apart
    for k in (0, 2, 4, 1, 3):
        nxt = (k + 1) % 5
        _, mni_k, _, mpi_k, cplus_k, _ = stgs[k]
        _, mni_nx, _, mpi_nx, _, _ = stgs[nxt]
        cx_out = round(cplus_k.x1 - 0.90, 3)
        lb.wire(cell, L_M4, [(cplus_k.x1 + 0.05, cplus_k.cy), (cx_out, cplus_k.cy)], w=0.20)
        lb.via_stack(cell, cx_out, cplus_k.cy, 3, 4)
        pts: List[Tuple] = [
            (mpi_k.D.cx, mpi_k.D.cy, 1, (0.24, 0.38)),
            (mni_k.D.cx, mni_k.D.cy, 1, (0.24, 0.38)),
            (mpi_nx.G.cx, mpi_nx.G.cy, 1),
            (mni_nx.G.cx, mni_nx.G.cy, 1),
            (cx_out, cplus_k.cy, 3),
        ]
        if k == 3:
            pts.extend([(f_rst.D.cx, f_rst.D.cy, 1), sp("XBUF1", "A")])
        rt.connect(pts)

    assert rt.max_used_y() < 20.8, f"cco rt overflow: {rt.max_used_y()}"

    pins = {
        "VDD": (-0.8, y_vdd, 2),
        "VSS": (-0.8, y_vss_nmos, 2),
        "en": (-0.8, y_en, 2),
        "ictrl": (-0.8, y_ictrl, 2),
        "clk": (x_clk_out, y_clk, 2),
    }
    return cell, pins
