#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Custom compacted layout builders for comp_lay, relax_core_lay, and top-level rpe_clk_analog."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple
import pya as db

from lay_core import (
    L_M1, L_M2, L_M3, L_M4, L_NWELL, L_PRBND,
    BoxU, LayoutBuilder, STDCELL_H, std_pin_pad,
)
from lay_router import NetRouter
from blocks_bias_ring import build_bias_lay, build_cco_core_lay, build_idac_8b_lay


def build_comp_lay(lb: LayoutBuilder, name: str = "comp_lay") -> Tuple[db.Cell, Dict[str, Tuple[float, float, int]]]:
    """Build compacted continuous-time comparator cell matching analog/osc_relax/comp.sch."""
    cell = lb.ly.create_cell(name)

    # NMOS active load + Stage 2 CS NMOS at y = 8.2
    f_l1 = lb.place_fet_array(cell, "nmos", 2.0, 8.2, 0.5, 2.0, m_count=1, gate_side="top")
    f_l2 = lb.place_fet_array(cell, "nmos", 5.4, 8.2, 0.5, 2.0, m_count=1, gate_side="top")
    f_g2n = lb.place_fet_array(cell, "nmos", 8.8, 8.2, 1.0, 1.0, m_count=1, gate_side="top")

    # PMOS diff pair + tail + G2 load + off clamp inside contiguous NWell
    f_inp = lb.place_fet_array(cell, "pmos", 2.0, 16.4, 2.0, 1.0, m_count=2, cols=1, dy_um=2.56, gate_side="bot")
    f_inn = lb.place_fet_array(cell, "pmos", 5.0, 16.4, 2.0, 1.0, m_count=2, cols=1, dy_um=2.56, gate_side="bot")
    f_tail = lb.place_fet_array(cell, "pmos", 8.0, 16.8, 1.0, 4.0, m_count=1, gate_side="bot")
    f_g2p = lb.place_fet_array(cell, "pmos", 13.5, 16.8, 1.0, 4.0, m_count=1, gate_side="bot")
    f_off = lb.place_fet_array(cell, "pmos", 19.0, 16.8, 0.5, 0.5, m_count=1, gate_side="bot")

    # Output inverter stdcell at y = 1.6, x = 15.2
    y_std = 1.6
    w_inv, inv_raw = lb.place_stdcell(cell, "sg13cmos5l_inv_1", 15.2, y_std)
    inv_p = lb.escape_stdcell_pins(cell, "sg13cmos5l_inv_1", 15.2, inv_raw, gut=0.48)
    x_comp_end = 21.8
    lb.bridge_stdcell_row(cell, 0.2, x_comp_end - 0.3, y_std)

    lb.rect(cell, L_NWELL, 1.2, 15.4, x_comp_end - 0.2, 23.8)
    y_vdd, y_vss_nmos = 22.8, 6.6
    lb.rect(cell, L_M1, 1.2, y_vdd - 0.35, x_comp_end - 0.2, y_vdd + 0.35)
    lb.rect(cell, L_M2, 0.2, y_vdd - 0.35, x_comp_end, y_vdd + 0.35)
    for tx in (2.5, 11.5, 20.0):
        tm = lb.place_tap(cell, "ntap1", tx, y_vdd - 0.39)
        lb.via_stack(cell, tm.cx, tm.cy, 1, 2)

    lb.rect(cell, L_M1, 1.2, y_vss_nmos - 0.35, x_comp_end - 0.2, y_vss_nmos + 0.35)
    lb.rect(cell, L_M2, 0.2, y_vss_nmos - 0.35, x_comp_end, y_vss_nmos + 0.35)
    for px in (2.5, 11.5, 20.0):
        pm = lb.place_tap(cell, "ptap1", px, y_vss_nmos - 0.39)
        lb.via_stack(cell, pm.cx, pm.cy, 1, 2)

    x_vdd_m3 = 0.4
    x_vss_m2 = 1.1
    lb.via_stack(cell, x_vdd_m3, y_std + STDCELL_H, 1, 3)
    lb.wire(cell, L_M3, [(x_vdd_m3, y_std + STDCELL_H), (x_vdd_m3, y_vdd)], w=0.32)
    lb.via_stack(cell, x_vdd_m3, y_vdd, 2, 3)

    lb.via_stack(cell, x_vss_m2, y_std, 1, 2)
    lb.wire(cell, L_M2, [(x_vss_m2, y_std), (x_vss_m2, y_vss_nmos)], w=0.32)

    for fp in (f_tail, f_g2p, f_off):
        lb.wire(cell, L_M1, [(fp.S.cx, fp.S.y2 - 0.1), (fp.S.cx, y_vdd)], w=0.24)
    for fn in (f_l1, f_l2, f_g2n):
        lb.wire(cell, L_M1, [(fn.S.cx, fn.S.y1 + 0.16), (fn.S.cx, y_vss_nmos)], w=0.24)

    rt = NetRouter(lb, cell, m2_y0=10.6, m2_pitch=0.64, m3_pitch=0.64, min_x=1.8, pack=True)
    rt.reserve_x(x_vdd_m3, y_std + STDCELL_H - 0.5, y_vdd + 0.5)
    for ex, ey, ml in inv_p.values():
        if ml == 3:
            rt.reserve_pin(ex, ey, 16.0)

    rt.connect([(f_tail.D.cx, f_tail.D.cy, 1), (f_inp.S.cx, f_inp.S.cy, 1), (f_inn.S.cx, f_inn.S.cy, 1)])
    rt.connect([(f_inp.D.cx, f_inp.D.cy, 1), (f_l1.D.cx, f_l1.D.cy, 1), (f_l1.G.cx, f_l1.G.cy, 1), (f_l2.G.cx, f_l2.G.cy, 1)])
    rt.connect([(f_inn.D.cx, f_inn.D.cy, 1), (f_l2.D.cx, f_l2.D.cy, 1), (f_g2n.G.cx, f_g2n.G.cy, 1)])

    inv_a = inv_p["A"]
    inv_y = inv_p["Y"]
    rt.connect([(f_g2p.D.cx, f_g2p.D.cy, 1), (f_g2n.D.cx, f_g2n.D.cy, 1), (f_off.D.cx, f_off.D.cy, 1), inv_a])

    y_vpb = rt.connect([(f_tail.G.cx, f_tail.G.cy, 1), (f_g2p.G.cx, f_g2p.G.cy, 1)], extend_to_x=[0.4])
    y_en = rt.connect([(f_off.G.cx, f_off.G.cy, 1)], extend_to_x=[0.4])
    y_inp = rt.connect([(f_inp.G.cx, f_inp.G.cy, 1)], extend_to_x=[0.4])
    y_inn = rt.connect([(f_inn.G.cx, f_inn.G.cy, 1)], extend_to_x=[0.4])
    y_out = rt.connect([inv_y], extend_to_x=[x_comp_end])
    assert rt.max_used_y() < 15.8, f"comp_lay channel overflow: {rt.max_used_y()}"

    return cell, {
        "VDD": (0.4, y_vdd, 2), "VSS": (0.4, y_vss_nmos, 2),
        "vpbias": (0.4, y_vpb, 2), "en": (0.4, y_en, 2),
        "inp": (0.4, y_inp, 2), "inn": (0.4, y_inn, 2),
        "out": (x_comp_end, y_out, 2),
    }


def build_relax_core_lay(lb: LayoutBuilder) -> Tuple[db.Cell, Dict[str, Tuple[float, float, int]]]:
    """Build compacted relax_core_lay subblock matching clk_macro/relax_core.sch."""
    cell = lb.ly.create_cell("relax_core_lay")

    # 1. Left: 4 series rppd (w=0.5u, l=40.0u, b=9) at x = 1.8 + k*7.8, y = 9.0 -> y=8.34..50.26
    r_pins = []
    for k in range(4):
        rp, rm, _ = lb.place_rppd(cell, 1.8 + k * 7.8, 9.0, w_um=0.5, l_um=40.0, bends=9)
        r_pins.append((rp, rm))
    for py in (7.2, 51.4):
        lb.wire(cell, L_M2, [(1.5, py), (31.5, py)], w=0.30)
        for px in (2.4, 12.0, 21.6, 30.8):
            pm = lb.place_tap(cell, "ptap1", px, py - 0.39)
            lb.via_stack(cell, pm.cx, pm.cy, 1, 2)

    # 2. HV Zone: C_A (7.61..19.96), C_B (20.21..32.56); staggered nmosHV on right
    g1_a, g2_a, w_a, _ = lb.place_svaricap(cell, 33.4, 8.4, w_str="9.74u", l_str="0.8u", nx=8)
    g1_b, g2_b, w_b, _ = lb.place_svaricap(cell, 33.4, 21.0, w_str="9.74u", l_str="0.8u", nx=8)
    f_dis_a = lb.place_fet_array(cell, "nmosHV", 54.5, 9.0, 0.5, 0.5, m_count=1, gate_side="top")
    f_dis_b = lb.place_fet_array(cell, "nmosHV", 57.4, 14.5, 0.5, 0.5, m_count=1, gate_side="top")
    f_unstick = lb.place_fet_array(cell, "nmosHV", 60.3, 20.0, 0.5, 0.5, m_count=1, gate_side="top")
    f_mn_init = lb.place_fet_array(cell, "nmos", 42.6, 34.4, 0.5, 0.5, m_count=1, gate_side="top")

    # 3. MN_MIR + LV PMOS row
    f_mnmir = lb.place_fet_array(cell, "nmos", 33.4, 34.4, 0.3, 4.0, m_count=1, gate_side="top")
    f_mpref = lb.place_fet_array(cell, "pmos", 33.6, 39.6, 1.0, 4.0, m_count=1, gate_side="bot")
    f_mchg_in = lb.place_fet_array(cell, "pmos", 39.4, 39.6, 0.5, 4.0, m_count=10, cols=2, dy_um=1.04, dx_um=5.65, gate_side="bot")
    f_mchg_a = lb.place_fet_array(cell, "pmos", 50.8, 39.6, 0.5, 4.0, m_count=1, gate_side="bot")
    f_mchg_b = lb.place_fet_array(cell, "pmos", 56.6, 39.6, 0.5, 4.0, m_count=1, gate_side="bot")

    lb.rect(cell, L_NWELL, 33.0, 38.6, 62.2, 50.6)
    y_vdd_top = 49.6
    lb.rect(cell, L_M1, 33.0, y_vdd_top - 0.35, 62.2, y_vdd_top + 0.35)
    lb.rect(cell, L_M2, 33.0, y_vdd_top - 0.35, 62.6, y_vdd_top + 0.35)
    for tx in (34.5, 43.5, 52.5, 60.8):
        tm = lb.place_tap(cell, "ntap1", tx, y_vdd_top - 0.39)
        lb.via_stack(cell, tm.cx, tm.cy, 1, 2)
    for fp in (f_mpref, f_mchg_a, f_mchg_b):
        lb.wire(cell, L_M1, [(fp.S.cx, fp.S.y2 - 0.1), (fp.S.cx, y_vdd_top)], w=0.24)
    lb.wire(cell, L_M2, [(f_mchg_in.S.cx, f_mchg_in.S.cy), (f_mchg_in.S.cx, y_vdd_top)], w=0.30)

    # 4. Two compacted comparators on right (cx_off=68.0, CA: 1.8..25.6, CB: 26.2..50.0)
    comp_cell, cp_pins = build_comp_lay(lb, "comp_lay")
    cx_off = 68.0
    inst_ca_y, inst_cb_y = 1.8, 26.2
    cell.insert(db.CellInstArray(comp_cell.cell_index(), db.Trans(db.Trans.R0, round(cx_off * 1000), round(inst_ca_y * 1000))))
    cell.insert(db.CellInstArray(comp_cell.cell_index(), db.Trans(db.Trans.R0, round(cx_off * 1000), round(inst_cb_y * 1000))))

    comp_west_x = {"VSS": 63.40, "inn": 64.04, "en": 64.68, "vpbias": 65.32, "VDD": 67.24}
    comp_inp_x = {False: 65.96, True: 66.60}
    comp_out_x = {False: 90.80, True: 91.44}

    def cpin_esc(cy0: float, pname: str, is_b: bool = False) -> Tuple[float, float, int]:
        px, py, ml = cp_pins[pname]
        gx, gy = cx_off + px, cy0 + py
        if pname == "out":
            ex = comp_out_x[is_b]
        elif pname == "inp":
            ex = comp_inp_x[is_b]
        else:
            ex = comp_west_x[pname]
        lb.wire(cell, L_M2, [(gx, gy), (ex, gy)], w=0.24)
        return (ex, gy, ml)

    # 5. Bottom stdcell row (11 cells, gap=1.72, gut=0.48)
    dec_cells = [
        ("XINV_EN", "sg13cmos5l_inv_1"),
        ("XSR_Q", "sg13cmos5l_nor2_1"), ("XSR_QB", "sg13cmos5l_nor2_1"),
        ("XDIS_N_A", "sg13cmos5l_nor2_1"), ("XDIS_I_A", "sg13cmos5l_inv_1"),
        ("XDIS_N_B", "sg13cmos5l_nor2_1"), ("XDIS_I_B", "sg13cmos5l_inv_1"),
        ("XBOTH_NAND", "sg13cmos5l_nand2_2"), ("XBOTH_INV", "sg13cmos5l_inv_1"),
        ("XOUT_NOR", "sg13cmos5l_nor2_1"), ("XOUT_BUF", "sg13cmos5l_buf_2"),
    ]
    y_std = 1.6
    x_cur = 2.6
    dpins: Dict[str, Dict[str, Tuple[float, float, int]]] = {}
    for iname, cname in dec_cells:
        w, pd = lb.place_stdcell(cell, cname, x_cur, y_std)
        dpins[iname] = lb.escape_stdcell_pins(cell, cname, x_cur, pd, gut=0.48)
        x_cur += w + 1.72
    x_dec_end = round(x_cur + 1.0, 2)
    lb.bridge_stdcell_row(cell, 0.0, x_dec_end, y_std)
    for tx in range(3, int(x_dec_end), 12):
        tm = lb.place_tap(cell, "ntap1", float(tx), y_std + STDCELL_H + 0.42)
        lb.wire(cell, L_M1, [(tm.cx, tm.cy), (tm.cx, y_std + STDCELL_H)], w=0.40)

    y_vss = 0.6
    x_rel_end = 92.4
    lb.rect(cell, L_M1, 0.4, y_vss - 0.35, x_rel_end, y_vss + 0.35)
    lb.rect(cell, L_M2, 0.4, y_vss - 0.35, x_rel_end, y_vss + 0.35)
    lb.via_stack(cell, 1.25, y_std, 1, 2)
    lb.wire(cell, L_M2, [(1.25, y_vss), (1.25, y_std)], w=0.35)

    c_ca, c_cb = {}, {}
    for pn in ("VSS", "inn", "en", "vpbias"):
        xa, ya, _ = cpin_esc(inst_ca_y, pn, False)
        xb, yb, _ = cpin_esc(inst_cb_y, pn, True)
        assert abs(xa - xb) < 1e-4
        lb.via_stack(cell, xa, ya, 2, 3)
        lb.via_stack(cell, xb, yb, 2, 3)
        y_lo = y_vss if pn == "VSS" else ya
        lb.wire(cell, L_M3, [(xa, y_lo), (xb, yb)], w=0.24)
        if pn == "VSS":
            lb.via_stack(cell, xa, y_vss, 2, 3)
        c_cb[pn] = (xb, yb, 3)
    for is_b, pname in [(False, "inp"), (True, "inp"), (False, "out"), (True, "out")]:
        cxp, cyp, _ = cpin_esc(inst_cb_y if is_b else inst_ca_y, pname, is_b)
        lb.via_stack(cell, cxp, cyp, 2, 3)
        c_ca[(pname, is_b)] = (cxp, cyp, 3)

    # Top channel router above rppd (51.4) & comp_lay (50.2)
    rt = NetRouter(lb, cell, m2_y0=52.8, m2_pitch=0.64, m3_pitch=0.64, blocked_x=[(67.6, 90.2), (92.0, 200.0)], min_x=1.8, pack=True)

    x_ptap_vss_m3 = 1.25
    x_std_vdd_m3 = 0.25
    x_lv_vdd_m3 = 62.76
    rt.reserve_x(x_ptap_vss_m3, y_vss - 0.5, 52.0)
    rt.reserve_x(x_std_vdd_m3, y_std + STDCELL_H - 0.5, 68.0)
    rt.reserve_x(x_lv_vdd_m3, y_vdd_top - 0.5, 68.0)
    rt.reserve_x(comp_west_x["VDD"], 1.8, 68.0)
    rt.reserve_x(comp_west_x["VSS"], 0.0, 52.0)
    for pn in ("inn", "en", "vpbias"):
        rt.reserve_pin(c_cb[pn][0], c_cb[pn][1], 68.0)
    for key in c_ca:
        rt.reserve_pin(c_ca[key][0], c_ca[key][1], 68.0)
    for pmap in dpins.values():
        for ex, ey, ml in pmap.values():
            if ml == 3:
                rt.reserve_pin(ex, ey, 68.0)

    lb.wire(cell, L_M2, [(x_ptap_vss_m3, 7.2), (1.5, 7.2)], w=0.30)
    lb.wire(cell, L_M2, [(x_ptap_vss_m3, 51.4), (1.5, 51.4)], w=0.30)
    lb.via_stack(cell, x_ptap_vss_m3, 7.2, 2, 3)
    lb.via_stack(cell, x_ptap_vss_m3, 51.4, 2, 3)
    lb.via_stack(cell, x_ptap_vss_m3, y_vss, 2, 3)
    lb.wire(cell, L_M3, [(x_ptap_vss_m3, y_vss), (x_ptap_vss_m3, 51.4)], w=0.32)

    def sp(iname: str, pn: str) -> Tuple[float, float, int]:
        return dpins[iname][pn]

    def drop_s(fp):
        sy = round(fp.S.y1 - 0.9, 3)
        lb.wire(cell, L_M1, [(fp.S.cx, fp.S.y1 + 0.15), (fp.S.cx, sy)], w=0.22)
        return (fp.S.cx, sy, 1)

    rt.connect([
        (r_pins[3][1].cx, r_pins[3][1].cy, 1),
        (f_mnmir.S.cx, f_mnmir.S.cy, 1),
        drop_s(f_dis_a),
        drop_s(f_dis_b),
        drop_s(f_unstick),
        drop_s(f_mn_init),
        (w_a.cx, w_a.cy, 1),
        (w_b.cx, w_b.cy, 1),
        (10.0, y_vss, 2),
    ], y_track=y_vss)

    rt.connect([(f_mpref.D.cx, f_mpref.D.cy, 1), (r_pins[0][0].cx, r_pins[0][0].cy, 1), c_cb["inn"]])
    rt.connect([(r_pins[0][1].cx, r_pins[0][1].cy, 1), (r_pins[1][0].cx, r_pins[1][0].cy, 1)])
    rt.connect([(r_pins[1][1].cx, r_pins[1][1].cy, 1), (r_pins[2][0].cx, r_pins[2][0].cy, 1)])
    rt.connect([(r_pins[2][1].cx, r_pins[2][1].cy, 1), (r_pins[3][0].cx, r_pins[3][0].cy, 1)])

    rt.connect([
        (f_mnmir.D.cx, f_mnmir.D.cy, 1),
        (f_mchg_in.D.cx, f_mchg_in.D.cy, 2),
        (f_mchg_in.G.cx, f_mchg_in.G.cy, 2),
        (f_mchg_a.G.cx, f_mchg_a.G.cy, 1),
        (f_mchg_b.G.cx, f_mchg_b.G.cy, 1),
    ])

    # Shield vcap_a and vcap_b apart with vpbias (quiet DC net) between them
    rt.connect([
        (f_mchg_a.D.cx, f_mchg_a.D.cy, 1), (f_dis_a.D.cx, f_dis_a.D.cy, 1),
        (f_unstick.D.cx, f_unstick.D.cy, 1), (36.8, g1_a.cy, 1), (38.8, g2_a.cy, 1),
        c_ca[("inp", False)],
    ])
    y_vpb = rt.connect([(f_mpref.G.cx, f_mpref.G.cy, 1), c_cb["vpbias"]], extend_to_x=[-0.8])
    rt.connect([
        (f_mchg_b.D.cx, f_mchg_b.D.cy, 1), (f_dis_b.D.cx, f_dis_b.D.cy, 1),
        (44.8, g1_b.cy, 1), (47.13, g2_b.cy, 1),
        c_ca[("inp", True)],
    ])

    y_en = rt.connect([sp("XINV_EN", "A"), c_cb["en"]], extend_to_x=[-0.8])
    rt.connect([sp("XINV_EN", "Y"), (f_mn_init.G.cx, f_mn_init.G.cy, 1), sp("XDIS_N_A", "B"), sp("XDIS_N_B", "B"), sp("XOUT_NOR", "B")])
    rt.connect([c_ca[("out", False)], sp("XSR_QB", "A"), sp("XBOTH_NAND", "A")])
    rt.connect([c_ca[("out", True)], sp("XSR_Q", "A"), sp("XBOTH_NAND", "B")])
    rt.connect([sp("XSR_Q", "Y"), sp("XSR_QB", "B"), sp("XDIS_N_A", "A")])
    rt.connect([sp("XSR_QB", "Y"), sp("XSR_Q", "B"), (f_mn_init.D.cx, f_mn_init.D.cy, 1), sp("XDIS_N_B", "A"), sp("XOUT_NOR", "A")])
    rt.connect([sp("XDIS_N_A", "Y"), sp("XDIS_I_A", "A")])
    rt.connect([sp("XDIS_I_A", "Y"), (f_dis_a.G.cx, f_dis_a.G.cy, 1)])
    rt.connect([sp("XDIS_N_B", "Y"), sp("XDIS_I_B", "A")])
    rt.connect([sp("XDIS_I_B", "Y"), (f_dis_b.G.cx, f_dis_b.G.cy, 1)])
    rt.connect([sp("XBOTH_NAND", "Y"), sp("XBOTH_INV", "A")])
    rt.connect([sp("XBOTH_INV", "Y"), (f_unstick.G.cx, f_unstick.G.cy, 1)])
    rt.connect([sp("XOUT_NOR", "Y"), sp("XOUT_BUF", "A")])

    y_clk_slow = rt.connect([sp("XOUT_BUF", "X")], extend_to_x=[x_rel_end])
    y_vnb = rt.connect([(f_mnmir.G.cx, f_mnmir.G.cy, 1)], extend_to_x=[-0.8])

    y_vdd_fin = round(rt.max_used_y() + 1.0, 2)
    lb.rect(cell, L_M2, -0.8, y_vdd_fin - 0.35, x_rel_end, y_vdd_fin + 0.35)
    lb.wire(cell, L_M2, [(x_lv_vdd_m3, y_vdd_top), (33.0, y_vdd_top)], w=0.35)
    lb.via_stack(cell, x_lv_vdd_m3, y_vdd_top, 2, 3)
    lb.wire(cell, L_M3, [(x_lv_vdd_m3, y_vdd_top), (x_lv_vdd_m3, y_vdd_fin)], w=0.40)
    lb.via_stack(cell, x_lv_vdd_m3, y_vdd_fin, 2, 3)

    lb.via_stack(cell, x_std_vdd_m3, y_std + STDCELL_H, 1, 3)
    lb.wire(cell, L_M3, [(x_std_vdd_m3, y_std + STDCELL_H), (x_std_vdd_m3, y_vdd_fin)], w=0.35)
    lb.via_stack(cell, x_std_vdd_m3, y_vdd_fin, 2, 3)

    for cx, cy, _ in (cpin_esc(inst_ca_y, "VDD", False), cpin_esc(inst_cb_y, "VDD", True)):
        lb.via_stack(cell, cx, cy, 2, 3)
        lb.wire(cell, L_M3, [(cx, cy), (cx, y_vdd_fin)], w=0.35)
        lb.via_stack(cell, cx, y_vdd_fin, 2, 3)

    return cell, {
        "VDD": (-0.8, y_vdd_fin, 2), "VSS": (x_rel_end, y_vss, 2),
        "en": (-0.8, y_en, 2), "vpbias": (-0.8, y_vpb, 2), "vnbias": (-0.8, y_vnb, 2),
        "clk_slow": (x_rel_end, y_clk_slow, 2),
    }


def _vss_m3_underpass(lb: LayoutBuilder, cell: db.Cell, x_from: float, y_from: float, ml_from: int, x_ring: float, x_cross_hi: float) -> None:
    """Route a VSS M4 strap horizontally to x_cross_hi, jump under VDD M4 ring on M3, and land on VSS M4 ring at x_ring."""
    lb.via_stack(cell, x_from, y_from, ml_from, 4)
    lb.wire(cell, L_M4, [(x_from, y_from), (x_cross_hi, y_from)], w=0.55)
    lb.via_stack(cell, x_cross_hi, y_from, 3, 4)
    lb.wire(cell, L_M3, [(x_cross_hi, y_from), (x_ring, y_from)], w=0.55)
    lb.via_stack(cell, x_ring, y_from, 3, 4)


def build_top_macro(lb: LayoutBuilder) -> Tuple[db.Cell, BoxU, Dict[str, Tuple[BoxU, int]]]:
    """Assemble compacted 2-column rpe_clk_analog top cell with tight M4 rings and clean corridors."""
    c_bias, p_bias = build_bias_lay(lb)
    c_idac, p_idac = build_idac_8b_lay(lb)
    c_cco, p_cco = build_cco_core_lay(lb)
    c_rel, p_rel = build_relax_core_lay(lb)

    for nm, sc in [("bias_lay", c_bias), ("idac_8b_lay", c_idac), ("cco_core_lay", c_cco), ("relax_core_lay", c_rel)]:
        bb_s = sc.bbox().to_dtype(0.001)
        print(f"SUBBLOCK {nm:15s}: {bb_s.width():.3f} x {bb_s.height():.3f} um ({bb_s.width()*bb_s.height():.1f} um^2)")

    top = lb.ly.create_cell("rpe_clk_analog")

    # Compact 2-column floorplan with wide inter-block routing corridors (no dead quadrants)
    pos_idac = (10.5, 8.2)
    pos_bias = (63.5, 8.2)
    pos_cco = (112.0, 8.2)

    bb_cco = c_cco.bbox().to_dtype(0.001)
    bb_idac = c_idac.bbox().to_dtype(0.001)
    bb_rel = c_rel.bbox().to_dtype(0.001)

    y_rel = round(max(pos_cco[1] + bb_cco.top + 8.5, 56.0), 1)
    x_rel = round(pos_cco[0] + bb_cco.right - bb_rel.right, 1)
    pos_rel = (x_rel, y_rel)

    W_MAC = round(max(pos_cco[0] + bb_cco.right, pos_rel[0] + bb_rel.right) + 7.5, 1)
    H_MAC = round(max(pos_idac[1] + bb_idac.top, pos_rel[1] + bb_rel.top) + 6.5, 1)

    sub_Placements = [(c_bias, pos_bias), (c_cco, pos_cco), (c_idac, pos_idac), (c_rel, pos_rel)]
    sub_blocked: List[Tuple[float, float, float, float]] = []
    for subc, (px, py) in sub_Placements:
        top.insert(db.CellInstArray(subc.cell_index(), db.Trans(db.Trans.R0, round(px * 1000), round(py * 1000))))
        sbb = subc.bbox().to_dtype(0.001)
        sub_blocked.append((
            round(px + sbb.left - 0.6, 2),
            round(px + sbb.right + 0.6, 2),
            round(py + sbb.bottom - 0.6, 2),
            round(py + sbb.top + 0.6, 2),
        ))

    # Top-level OR gate for en_bias = en_ring | en_relax tucked cleanly above bias_lay
    y_or = 36.2
    x_or = 66.5
    w_nor, nor_raw = lb.place_stdcell(top, "sg13cmos5l_nor2_1", x_or, y_or)
    nor_p = lb.escape_stdcell_pins(top, "sg13cmos5l_nor2_1", x_or, nor_raw, gut=0.48)
    _, inv_raw = lb.place_stdcell(top, "sg13cmos5l_inv_1", x_or + w_nor + 1.72, y_or)
    inv_p = lb.escape_stdcell_pins(top, "sg13cmos5l_inv_1", x_or + w_nor + 1.72, inv_raw, gut=0.48)
    lb.bridge_stdcell_row(top, 63.5, 75.0, y_or)
    tm_or = lb.place_tap(top, "ntap1", 73.7, y_or + STDCELL_H + 0.42)
    lb.wire(top, L_M1, [(tm_or.cx, tm_or.cy), (tm_or.cx, y_or + STDCELL_H)], w=0.32)
    pm_or = lb.place_tap(top, "ptap1", 73.7, y_or - 1.25)
    lb.wire(top, L_M1, [(pm_or.cx, pm_or.cy), (pm_or.cx, y_or)], w=0.32)

    lb.rect(top, L_PRBND, 0.0, 0.0, W_MAC, H_MAC)

    def _via3_array(cx: float, cy: float, xs_off: Tuple[float, ...], ys_off: Tuple[float, ...]) -> None:
        for dx in xs_off:
            for dy in ys_off:
                lb.via(top, cx + dx, cy + dy, 3)

    # Outer VSS / inner VDD split between vertical Metal4 perimeter bars and horizontal Metal3 buses
    # so Tiny Tapeout full-height Metal4 PDN stripes never collide with horizontal Metal4 straps.
    rw = 1.4
    lb.rect(top, L_M4, 0.8, 0.8, 0.8 + rw, H_MAC - 0.8)                  # West VSS (M4)
    lb.rect(top, L_M4, W_MAC - 0.8 - rw, 0.8, W_MAC - 0.8, H_MAC - 0.8)  # East VSS (M4)
    lb.rect(top, L_M3, 0.8, 0.8, W_MAC - 0.8, 0.8 + rw)                  # Bottom VSS (M3, y=0.8..2.2)
    lb.rect(top, L_M3, 0.8, H_MAC - 0.8 - rw, W_MAC - 0.8, H_MAC - 0.8)  # Top VSS (M3, y=134.8..136.2)
    for cx_c in (1.5, W_MAC - 1.5):
        for cy_c in (1.5, H_MAC - 1.5):
            _via3_array(cx_c, cy_c, (-0.30, 0.30), (-0.30, 0.30))

    lb.rect(top, L_M4, 3.0, 3.0, 3.0 + rw, H_MAC - 3.0)                  # West VDD (M4)
    lb.rect(top, L_M4, W_MAC - 3.0 - rw, 3.0, W_MAC - 3.0, H_MAC - 3.0)  # East VDD (M4)
    lb.rect(top, L_M3, 3.0, 3.0, W_MAC - 3.0, 3.0 + rw)                  # Bottom VDD (M3, y=3.0..4.4)
    lb.rect(top, L_M3, 3.0, H_MAC - 3.0 - rw, W_MAC - 3.0, H_MAC - 3.0)  # Top VDD (M3, y=132.6..134.0)
    for cx_c in (3.7, W_MAC - 3.7):
        for cy_c in (3.7, H_MAC - 3.7):
            _via3_array(cx_c, cy_c, (-0.30, 0.30), (-0.30, 0.30))

    # Full-height Metal4 PDN stripe pins aligned to the 8x4 tile grid for origin x = 1514.880 um
    # Tile VPWR: 1537.67, 1582.63, 1627.59, 1672.55 -> local cx = 22.79, 67.75, 112.71, 157.67
    # Tile VGND: 1543.29, 1588.25, 1633.21, 1678.17 -> local cx = 28.41, 73.37, 118.33, 163.29
    PDN_W = 2.10
    VDD_STRIPE_CX = [22.79, 67.75, 112.71, 157.67]
    VSS_STRIPE_CX = [28.41, 73.37, 118.33, 163.29]
    for cx in VDD_STRIPE_CX:
        lb.rect(top, L_M4, cx - 0.5 * PDN_W, 0.0, cx + 0.5 * PDN_W, H_MAC)
        _via3_array(cx, 3.7, (-0.45, 0.0, 0.45), (-0.30, 0.30))
        _via3_array(cx, H_MAC - 3.7, (-0.45, 0.0, 0.45), (-0.30, 0.30))
    for cx in VSS_STRIPE_CX:
        lb.rect(top, L_M4, cx - 0.5 * PDN_W, 0.0, cx + 0.5 * PDN_W, H_MAC)
        _via3_array(cx, 1.5, (-0.45, 0.0, 0.45), (-0.30, 0.30))
        _via3_array(cx, H_MAC - 1.5, (-0.45, 0.0, 0.45), (-0.30, 0.30))

    def gp(pos, pdict, pname):
        x, y, ml = pdict[pname]
        return (pos[0] + x, pos[1] + y, ml)

    def esc_corridor(pos, pdict, pname, target_x: float) -> Tuple[float, float, int]:
        px, py, ml = gp(pos, pdict, pname)
        lb.wire(top, L_M2, [(px, py), (target_x, py)], w=0.24)
        return (round(target_x, 3), py, ml)

    # VDD connections to inner VDD ring / bottom & top M3 VDD buses
    vx_i, vy_i, vml_i = gp(pos_idac, p_idac, "VDD")
    lb.via_stack(top, vx_i, vy_i, vml_i, 4)
    lb.wire(top, L_M4, [(vx_i, vy_i), (3.7, vy_i)], w=0.55)

    vx_b, vy_b, vml_b = gp(pos_bias, p_bias, "VDD")
    lb.via_stack(top, vx_b, vy_b, vml_b, 4)
    lb.wire(top, L_M4, [(vx_b, vy_b), (61.2, vy_b), (61.2, 3.7)], w=0.55)
    lb.via_stack(top, 61.2, 3.7, 3, 4)

    vx_c, vy_c, vml_c = gp(pos_cco, p_cco, "VDD")
    lb.via_stack(top, vx_c, vy_c, vml_c, 4)
    lb.wire(top, L_M4, [(vx_c, vy_c), (112.71, vy_c)], w=0.55)  # directly onto M4 VDD stripe #3

    vx_r, vy_r, vml_r = gp(pos_rel, p_rel, "VDD")
    lb.via_stack(top, vx_r, vy_r, vml_r, 4)
    lb.wire(top, L_M4, [(vx_r, vy_r), (vx_r, H_MAC - 3.7)], w=0.55)
    lb.via_stack(top, vx_r, H_MAC - 3.7, 3, 4)

    # en_or VDD -> tie left to bias_lay VDD strap (x=61.2, y=3.7)
    lb.via_stack(top, 63.9, y_or + STDCELL_H, 1, 4)
    lb.wire(top, L_M4, [(63.9, y_or + STDCELL_H), (61.2, y_or + STDCELL_H), (61.2, 3.7)], w=0.45)

    # VSS connections via M2 underpasses under bottom M3 VDD bar (y=3.0..4.4), or M3 underpass at West/East M4 ring
    gx_i, gy_i, gml_i = gp(pos_idac, p_idac, "VSS")
    _vss_m3_underpass(lb, top, gx_i, gy_i, gml_i, x_ring=1.5, x_cross_hi=5.4)

    gx_b, gy_b, gml_b = gp(pos_bias, p_bias, "VSS")
    lb.via_stack(top, gx_b, gy_b, gml_b, 4)
    lb.wire(top, L_M4, [(gx_b, gy_b), (gx_b, 5.2)], w=0.55)
    lb.via_stack(top, gx_b, 5.2, 2, 4)
    lb.wire(top, L_M2, [(gx_b, 5.2), (gx_b, 1.5)], w=0.55)
    lb.via_stack(top, gx_b, 1.5, 2, 3)

    gx_c, gy_c, gml_c = gp(pos_cco, p_cco, "VSS")
    x_cco_vss = 109.8
    lb.via_stack(top, gx_c, gy_c, gml_c, 2)
    lb.wire(top, L_M2, [(gx_c, gy_c), (x_cco_vss, gy_c)], w=0.55)
    lb.via_stack(top, x_cco_vss, gy_c, 2, 4)
    lb.wire(top, L_M4, [(x_cco_vss, gy_c), (x_cco_vss, 5.2)], w=0.55)
    lb.via_stack(top, x_cco_vss, 5.2, 2, 4)
    lb.wire(top, L_M2, [(x_cco_vss, 5.2), (x_cco_vss, 1.5)], w=0.55)
    lb.via_stack(top, x_cco_vss, 1.5, 2, 3)

    # en_or VSS -> M3/M4 down along x=62.5 to M2 underpass into bottom VSS M3 bar
    lb.via_stack(top, 63.9, y_or, 1, 3)
    lb.wire(top, L_M3, [(63.9, y_or), (62.5, y_or), (62.5, 5.2)], w=0.45)
    lb.via_stack(top, 62.5, 5.2, 2, 3)
    lb.wire(top, L_M2, [(62.5, 5.2), (62.5, 1.5)], w=0.45)
    lb.via_stack(top, 62.5, 1.5, 2, 3)

    gx_r, gy_r, gml_r = gp(pos_rel, p_rel, "VSS")
    _vss_m3_underpass(lb, top, gx_r, gy_r, gml_r, x_ring=W_MAC - 1.5, x_cross_hi=W_MAC - 5.4)

    # Perimeter substrate tap ring along top & bottom VSS M3 bars (no M4 on taps -> safe under M4 VDD stripes)
    skip_xs = [gx_b, x_cco_vss, 62.5]
    for tx in range(8, int(W_MAC) - 6, 15):
        pm_t = lb.place_tap(top, "ptap1", float(tx), H_MAC - 1.9)
        lb.via_stack(top, pm_t.cx, pm_t.cy, 1, 3)
        if all(abs(float(tx) - sx) > 2.2 for sx in skip_xs):
            pm_b = lb.place_tap(top, "ptap1", float(tx), 1.1)
            lb.via_stack(top, pm_b.cx, pm_b.cy, 1, 3)

    # Inter-block signal spine in central gap above cco_core (y >= 49.0) and below relax_core
    # min_x=7.4 keeps top router strictly outside West 0..6.4 pin zone!
    rt = NetRouter(
        lb, top, m2_y0=49.0, m2_pitch=0.66, m3_pitch=0.66,
        blocked_rects=sub_blocked,
        min_x=57.4,
        pack=True,
    )
    rt.reserve_x(61.2, 3.0, 42.0)
    rt.reserve_x(62.5, 1.0, 42.0)
    rt.reserve_x(63.2, 34.5, 37.5)
    rt.reserve_x(63.9, 35.0, 42.0)
    rt.reserve_x(x_cco_vss, 1.0, 12.0)
    for pmap in (nor_p, inv_p):
        for ex, ey, ml in pmap.values():
            if ml == 3:
                rt.reserve_pin(ex, ey, 56.0)

    rt.connect([nor_p["Y"], inv_p["A"]], y_track=42.2)
    rt.connect([inv_p["Y"], esc_corridor(pos_bias, p_bias, "en", 107.0)])
    rt.connect([esc_corridor(pos_bias, p_bias, "vpbias", 107.0), esc_corridor(pos_rel, p_rel, "vpbias", 63.0)])
    rt.connect([
        esc_corridor(pos_bias, p_bias, "vnbias", 107.0),
        esc_corridor(pos_idac, p_idac, "vnbias", 57.8),
        esc_corridor(pos_rel, p_rel, "vnbias", 63.0),
    ])
    rt.connect([esc_corridor(pos_idac, p_idac, "ictrl", 58.5), esc_corridor(pos_cco, p_cco, "ictrl", 109.2)])

    pin_boxes: Dict[str, List[Tuple[BoxU, int]]] = {}
    pin_boxes["VDD"] = [
        (lb.pin_rect_label(top, 4, "VDD", cx - 0.5 * PDN_W, 0.0, cx + 0.5 * PDN_W, H_MAC), 4)
        for cx in VDD_STRIPE_CX
    ]
    pin_boxes["VSS"] = [
        (lb.pin_rect_label(top, 4, "VSS", cx - 0.5 * PDN_W, 0.0, cx + 0.5 * PDN_W, H_MAC), 4)
        for cx in VSS_STRIPE_CX
    ]

    # West M3 pins: trim0..7 exit straight West from idac_8b_lay at their own Y!
    for b in range(8):
        px, py, _ = gp(pos_idac, p_idac, f"trim{b}")
        lb.via_stack(top, 6.2, py, 2, 3)
        lb.wire(top, L_M2, [(px, py), (6.2, py)], w=0.24)
        lb.rect(top, L_M3, 0.0, py - 0.18, 6.40, py + 0.18)
        pin_boxes[f"trim{b}"] = [(lb.pin_rect_label(top, 3, f"trim{b}", 0.0, py - 0.18, 5.6, py + 0.18), 3)]

    # en_ring & en_relax enter West below idac_8b_lay -> jog along M2 under idac to x_spine -> route in spine
    lb.rect(top, L_M3, 0.0, 5.5 - 0.18, 6.40, 5.5 + 0.18)
    lb.via_stack(top, 6.2, 5.5, 2, 3)
    lb.wire(top, L_M2, [(6.2, 5.5), (59.2, 5.5)], w=0.24)
    lb.via_stack(top, 59.2, 5.5, 2, 3)
    pin_boxes["en_ring"] = [(lb.pin_rect_label(top, 3, "en_ring", 0.0, 5.5 - 0.18, 5.6, 5.5 + 0.18), 3)]
    p_en_idac = esc_corridor(pos_idac, p_idac, "en", 59.2)
    lb.wire(top, L_M3, [(59.2, 5.5), (59.2, p_en_idac[1])], w=0.24)
    rt.connect([nor_p["A"], p_en_idac, esc_corridor(pos_cco, p_cco, "en", 109.2)])

    lb.rect(top, L_M3, 0.0, 6.3 - 0.18, 6.40, 6.3 + 0.18)
    lb.via_stack(top, 6.2, 6.3, 2, 3)
    lb.wire(top, L_M2, [(6.2, 6.3), (59.9, 6.3)], w=0.24)
    pin_boxes["en_relax"] = [(lb.pin_rect_label(top, 3, "en_relax", 0.0, 6.3 - 0.18, 5.6, 6.3 + 0.18), 3)]
    rt.connect([nor_p["B"], esc_corridor(pos_rel, p_rel, "en", 63.0), (59.9, 6.3, 2)])

    assert rt.max_used_y() < pos_rel[1] - 1.2, f"top spine overflow {rt.max_used_y()} into relax_core at y={pos_rel[1]}"

    # East clock outputs on M3 flush with x=W_MAC
    for pname, pos, pdict in [("clk", pos_cco, p_cco), ("clk_slow", pos_rel, p_rel)]:
        cx_o, cy_o, ml_o = gp(pos, pdict, pname)
        lb.via_stack(top, cx_o, cy_o, ml_o, 3)
        lb.rect(top, L_M3, cx_o - 0.18, cy_o - 0.18, W_MAC, cy_o + 0.18)
        pin_boxes[pname] = [(lb.pin_rect_label(top, 3, pname, W_MAC - 5.6, cy_o - 0.18, W_MAC, cy_o + 0.18), 3)]

    return top, BoxU(0.0, 0.0, W_MAC, H_MAC), pin_boxes


def write_lef_and_verilog(out_dir: Path, bb: BoxU, pin_boxes: Dict[str, List[Tuple[BoxU, int]]]) -> None:
    m_name = {1: "Metal1", 2: "Metal2", 3: "Metal3", 4: "Metal4"}
    pin_dirs = {
        "VDD": ("INOUT", "POWER"),
        "VSS": ("INOUT", "GROUND"),
        "clk": ("OUTPUT", "SIGNAL"),
        "clk_slow": ("OUTPUT", "SIGNAL"),
    }
    lef = [
        "VERSION 5.7 ;",
        "BUSBITCHARS \"[]\" ;",
        "DIVIDERCHAR \"/\" ;",
        "MACRO rpe_clk_analog",
        "  CLASS BLOCK ;",
        "  FOREIGN rpe_clk_analog 0.000 0.000 ;",
        "  ORIGIN 0.000 0.000 ;",
        f"  SIZE {bb.w:.3f} BY {bb.h:.3f} ;",
        "  SYMMETRY X Y R90 ;",
    ]
    for pname, rects in pin_boxes.items():
        pdir, puse = pin_dirs.get(pname, ("INPUT", "SIGNAL"))
        ml = rects[0][1]
        lef.extend([
            f"  PIN {pname}",
            f"    DIRECTION {pdir} ;",
            f"    USE {puse} ;",
            "    PORT",
            f"      LAYER {m_name[ml]} ;",
        ])
        for pbox, _ in rects:
            lef.append(f"        RECT {pbox.x1:.3f} {pbox.y1:.3f} {pbox.x2:.3f} {pbox.y2:.3f} ;")
        lef.extend([
            "    END",
            f"  END {pname}",
        ])
    # Carve 0.24 um clearance openings in OBS Metal4 around the 8 power stripe pins so PDN stripes have 0 overlap errors
    m4_stripes = sorted([(pbox.x1, pbox.x2) for pname in ("VDD", "VSS") for pbox, _ in pin_boxes[pname]])
    m4_obs = []
    cur_x = 0.0
    for sx1, sx2 in m4_stripes:
        if sx1 - 0.24 > cur_x + 0.05:
            m4_obs.append((cur_x, sx1 - 0.24))
        cur_x = sx2 + 0.24
    if bb.w > cur_x + 0.05:
        m4_obs.append((cur_x, bb.w))

    lef.extend([
        "  OBS",
        "    LAYER Metal1 ;",
        f"      RECT 0.000 0.000 {bb.w:.3f} {bb.h:.3f} ;",
        "    LAYER Metal2 ;",
        f"      RECT 0.000 0.000 {bb.w:.3f} {bb.h:.3f} ;",
        "    LAYER Metal3 ;",
        f"      RECT 5.800 0.000 {bb.w - 5.8:.3f} {bb.h:.3f} ;",
        "    LAYER Metal4 ;",
    ])
    for ox1, ox2 in m4_obs:
        lef.append(f"      RECT {ox1:.3f} 0.000 {ox2:.3f} {bb.h:.3f} ;")
    lef.extend([
        "  END",
        "END rpe_clk_analog",
        "END LIBRARY",
    ])
    (out_dir / "rpe_clk_analog.lef").write_text("\n".join(lef) + "\n")

    vlog = """// Blackbox stub for unified custom analog clock macro (rpe_clk_analog)
(* blackbox *)
module rpe_clk_analog (
    inout  wire VDD,
    inout  wire VSS,
    input  wire en_ring,
    input  wire en_relax,
    input  wire trim0,
    input  wire trim1,
    input  wire trim2,
    input  wire trim3,
    input  wire trim4,
    input  wire trim5,
    input  wire trim6,
    input  wire trim7,
    output wire clk,
    output wire clk_slow
);
endmodule
"""
    (out_dir / "rpe_clk_analog.v").write_text(vlog)
