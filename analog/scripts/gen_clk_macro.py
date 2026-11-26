#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Generate unified analog clock macro schematics & symbols (analog/clk_macro): rpe_clk_analog = bias + osc_ring_cc + relax_core (SVaricap M=10)."""

import sys
from pathlib import Path

ANALOG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALOG_DIR / "scripts"))

from xschem_builder import Schematic, read_sym_pins, write_block_symbol


def build_relax_core(out_dir: Path, comp_pins: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    sym_pins = write_block_symbol(
        out_dir / "relax_core.sym",
        block_name="relax_core",
        left_pins=[("en", "in"), ("vpbias", "in"), ("vnbias", "in")],
        right_pins=[("clk_slow", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=200,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en", "vpbias", "vnbias", "clk_slow"],
    )

    sch = Schematic()
    sch.text("100 kHz Relaxation Core (SVaricap W=9.74u, L=0.8u, Nx=8; M=10; external bias)", 0, -380, scale=0.35)
    sch.title(400, 1020)

    sch.pin("iopin", "VDD", (-160, -320))
    sch.pin("iopin", "VSS", (-160, 920))
    sch.wire((-160, -320), (2140, -320), "VDD")
    sch.wire((-160, 920), (2140, 920), "VSS")

    sch.pin("ipin", "en", (-160, 0))
    sch.pin("ipin", "vpbias", (-160, -140))
    sch.pin("ipin", "vnbias", (-160, 140))
    sch.wire((-160, -140), (-120, -140), "vpbias")
    sch.wire((-160, 140), (-120, 140), "vnbias")

    # Enable inverter -> enb
    xinv_en = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", -40, 0, name="XINV_EN", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.wire((-160, 0), xinv_en.pin("A"), "en")
    sch.out_label("enb", xinv_en.pin("Y"), dx=40)

    # Threshold reference: I_ref (~0.5 uA) into 4 series rppd (b=9, w=0.5u, l=40u -> ~836 kOhm -> vth ~ 0.42 V)
    mp_ref = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 460, -220, name="MP_REF", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos")
    sch.wire(mp_ref.pin("S"), (480, -320), "VDD")
    sch.wire(mp_ref.pin("B"), mp_ref.pin("S"), "VDD")
    sch.wire((-120, -140), (380, -140), "vpbias")
    sch.route_vh((380, -140), mp_ref.pin("G"), "vpbias")
    sch.wire((340, -140), (340, -165), "vpbias")
    sch.label("vpbias", (340, -165), flip=1)
    sch.wire(mp_ref.pin("D"), (480, -140), "vth")
    sch.label("vth", (480, -140))

    prev_r = (480, -140)
    prev_n = "vth"
    for k in range(4):
        ry = -60 + k * 100
        rr = sch.add("sg13cmos5l_pr/rppd.sym", 480, ry, name=f"R_TH{k}", w="0.5e-6", l="40.0e-6", b="9", m="1", model="rppd", body="VSS", value="209k")
        sch.wire(prev_r, rr.pin("P"), prev_n)
        nxt = f"rth_{k}" if k < 3 else "VSS"
        prev_r = rr.pin("M")
        prev_n = nxt
    sch.wire(prev_r, (480, 920), "VSS")

    # 1:10 Current mirror for charging current (~50 nA)
    mn_m = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 760, 120, name="MN_MIR", w="0.3u", l="4.0u", ng="1", m="1", model="sg13_lv_nmos")
    mp_m_in = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 760, -220, name="MP_CHG_IN", w="0.5u", l="4.0u", ng="1", m="10", model="sg13_lv_pmos")
    sch.in_label("vnbias", mn_m.pin("G"), dx=40)
    sch.wire(mn_m.pin("S"), (780, 920), "VSS")
    sch.wire(mn_m.pin("B"), mn_m.pin("S"), "VSS")
    sch.wire(mp_m_in.pin("S"), (780, -320), "VDD")
    sch.wire(mp_m_in.pin("B"), mp_m_in.pin("S"), "VDD")
    sch.wire(mp_m_in.pin("D"), mn_m.pin("D"), "vp_chg")
    sch.route_hv((780, -140), (700, -220), "vp_chg")
    sch.wire((700, -220), mp_m_in.pin("G"), "vp_chg")
    sch.wire((700, -220), (670, -220), "vp_chg")
    sch.label("vp_chg", (670, -220), flip=0)

    # Ping-pong branches A and B with foundry-legal SVaricap (W=9.74u, L=0.8u, Nx=8 PEX-centered)
    for idx, (side, bx) in enumerate([("A", 1020), ("B", 1380)]):
        vcap_net = f"vcap_{side.lower()}"
        mp_chg = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", bx, -220, name=f"MP_CHG_{side}", w="0.5u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos")
        mn_dis = sch.add("sg13cmos5l_pr/sg13_hv_nmos.sym", bx, 20, name=f"MN_DIS_{side}", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_hv_nmos")

        sch.wire(mp_chg.pin("S"), (bx + 20, -320), "VDD")
        sch.wire(mp_chg.pin("B"), mp_chg.pin("S"), "VDD")
        sch.in_label("vp_chg", mp_chg.pin("G"), dx=40)
        sch.wire(mp_chg.pin("D"), mn_dis.pin("D"), vcap_net)
        sch.label(vcap_net, (bx + 20, -100))

        sch.wire(mn_dis.pin("S"), (bx + 20, 120), "VSS")
        sch.label("VSS", (bx + 20, 120))
        sch.wire(mn_dis.pin("B"), mn_dis.pin("S"), "VSS")
        sch.in_label(f"dis_{side.lower()}", mn_dis.pin("G"), dx=40)

        cap = sch.add(
            "sg13cmos5l_pr/sg13_svaricap.sym", bx + 180, 180,
            name=f"C_{side}", model="sg13_hv_svaricap", w="9.74e-6", l="0.8e-6", Nx="8", body="VSS",
        )
        sch.wire(cap.pin("NW"), (bx + 180, 110), "VSS")
        sch.label("VSS", (bx + 180, 110), flip=1)
        sch.route_hv((bx + 20, -100), (bx + 120, 180), vcap_net)
        sch.wire((bx + 120, 180), cap.pin("G2"), vcap_net)
        sch.out_label(vcap_net, cap.pin("G1"), dx=40)

        xc = sch.add("osc_relax/comp.sym", 1960, -140 if idx == 0 else 180, custom_pins=comp_pins, name=f"XCOMP_{side}")
        if idx == 0:
            sch.wire(xc.pin("VDD"), (xc.pin("VDD")[0], -320), "VDD")
        else:
            sch.wire((xc.pin("VDD")[0], xc.pin("VDD")[1] - 20), xc.pin("VDD"), "VDD")
            sch.label("VDD", (xc.pin("VDD")[0], xc.pin("VDD")[1] - 20))
        sch.wire(xc.pin("VSS"), (xc.pin("VSS")[0], xc.pin("VSS")[1] + 20), "VSS")
        sch.label("VSS", (xc.pin("VSS")[0], xc.pin("VSS")[1] + 20))
        for p, lab in [("inp", vcap_net), ("inn", "vth"), ("en", "en"), ("vpbias", "vpbias")]:
            sch.in_label(lab, xc.pin(p), dx=40)
        sch.out_label(f"cmp_{side.lower()}", xc.pin("out"), dx=40)

    # Cross-coupled SR latch
    xnor_q = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym", 1680, 460, name="XSR_Q", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    xnor_qb = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym", 1680, 600, name="XSR_QB", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.in_label("cmp_b", xnor_q.pin("A"), dx=60)
    sch.in_label("cmp_a", xnor_qb.pin("A"), dx=60)

    # Cross-couple q (XSR_Q.Y -> XSR_QB.B) and qb (XSR_QB.Y -> XSR_Q.B)
    sch.wire(xnor_q.pin("Y"), (1760, 460), "q")
    sch.wire((1760, 460), (1760, 515), "q")
    sch.wire((1760, 515), (1590, 515), "q")
    sch.wire((1590, 515), (1590, xnor_qb.pin("B")[1]), "q")
    sch.wire((1590, xnor_qb.pin("B")[1]), xnor_qb.pin("B"), "q")
    sch.wire((1760, 460), (1800, 460), "q")
    sch.label("q", (1800, 460), flip=1)

    sch.wire(xnor_qb.pin("Y"), (1780, 600), "qb")
    sch.wire((1780, 600), (1780, 545), "qb")
    sch.wire((1780, 545), (1600, 545), "qb")
    sch.wire((1600, 545), (1600, xnor_q.pin("B")[1]), "qb")
    sch.wire((1600, xnor_q.pin("B")[1]), xnor_q.pin("B"), "qb")

    mn_init = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 1960, 600, name="MN_INIT", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_nmos")
    sch.in_label("enb", mn_init.pin("G"), dx=40)
    sch.wire((1780, 600), (1820, 600), "qb")
    sch.wire((1820, 600), (1820, 530), "qb")
    sch.wire((1820, 530), (1980, 530), "qb")
    sch.wire((1980, 530), mn_init.pin("D"), "qb")
    sch.wire((1860, 530), (1860, 510), "qb")
    sch.label("qb", (1860, 510), flip=1)
    sch.wire(mn_init.pin("S"), (1980, 670), "VSS")
    sch.label("VSS", (1980, 670), flip=1)
    sch.wire(mn_init.pin("B"), mn_init.pin("S"), "VSS")

    for tag, qnet, y0 in [("A", "q", 460), ("B", "qb", 600)]:
        gnor = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym", 1020, y0, name=f"XDIS_N_{tag}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
        ginv = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", 1220, y0, name=f"XDIS_I_{tag}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
        sch.in_label(qnet, gnor.pin("A"), dx=40)
        sch.in_label("enb", gnor.pin("B"), dx=40)
        sch.wire(gnor.pin("Y"), ginv.pin("A"), f"disn_{tag.lower()}")
        sch.out_label(f"dis_{tag.lower()}", ginv.pin("Y"), dx=40)

    # Deadlock-breaker
    xn_both = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nand2_2.sym", 1020, 760, name="XBOTH_NAND", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    xi_both = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", 1220, 760, name="XBOTH_INV", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    mn_unstick = sch.add("sg13cmos5l_pr/sg13_hv_nmos.sym", 1420, 760, name="MN_UNSTICK", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_hv_nmos")
    sch.in_label("cmp_a", xn_both.pin("A"), dx=40)
    sch.in_label("cmp_b", xn_both.pin("B"), dx=40)
    sch.wire(xn_both.pin("Y"), xi_both.pin("A"), "both_n")
    sch.wire(xi_both.pin("Y"), mn_unstick.pin("G"), "both_hi")
    sch.wire(mn_unstick.pin("D"), (1440, 680), "vcap_a")
    sch.label("vcap_a", (1440, 680), flip=1)
    sch.wire(mn_unstick.pin("S"), (1440, 920), "VSS")
    sch.wire(mn_unstick.pin("B"), mn_unstick.pin("S"), "VSS")

    xout_nor = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym", 1680, 760, name="XOUT_NOR", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    xout_buf = sch.add("sg13cmos5l_stdcells/sg13cmos5l_buf_2.sym", 1880, 760, name="XOUT_BUF", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.in_label("qb", xout_nor.pin("A"), dx=40)
    sch.in_label("enb", xout_nor.pin("B"), dx=40)
    sch.wire(xout_nor.pin("Y"), xout_buf.pin("A"), "clk_pre")
    sch.wire(xout_buf.pin("X"), (2040, 760), "clk_slow")
    sch.pin("opin", "clk_slow", (2040, 760))

    sch.write(out_dir / "relax_core.sch")
    return sym_pins


def build_clk_macro() -> None:
    out_dir = ANALOG_DIR / "clk_macro"
    out_dir.mkdir(parents=True, exist_ok=True)

    bias_pins = read_sym_pins(ANALOG_DIR / "bias" / "bias.sym")
    idac_pins = read_sym_pins(ANALOG_DIR / "osc_ring_cc" / "idac_8b.sym")
    cco_pins = read_sym_pins(ANALOG_DIR / "osc_ring_cc" / "cco_core.sym")
    comp_pins = read_sym_pins(ANALOG_DIR / "osc_relax" / "comp.sym")

    relax_pins = build_relax_core(out_dir, comp_pins)

    trim_pins = [(f"trim{i}", "in") for i in range(7, -1, -1)]
    macro_pins = write_block_symbol(
        out_dir / "rpe_clk_analog.sym",
        block_name="rpe_clk_analog",
        left_pins=[("en_ring", "in"), ("en_relax", "in")] + trim_pins,
        right_pins=[("clk", "out"), ("clk_slow", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=220,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en_ring", "en_relax"] + [f"trim{i}" for i in range(7, -1, -1)] + ["clk", "clk_slow"],
    )

    sch = Schematic()
    sch.text("Unified Clock Macro (rpe_clk_analog = shared bias + osc_ring_cc + relax_core)", 0, -400, scale=0.35)
    sch.title(200, 620)

    # Rails & external ports
    sch.pin("iopin", "VDD", (-360, -340))
    sch.pin("iopin", "VSS", (-360, 520))
    sch.pin("ipin", "en_ring", (-360, -240))
    sch.pin("ipin", "en_relax", (-360, -200))
    for i, b in enumerate(range(7, -1, -1)):
        sch.pin("ipin", f"trim{b}", (-360, 60 + i * 40))

    # Shared bias enable: en_bias = en_ring | en_relax
    x_nor = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym", -200, -220, name="XEN_NOR", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    x_inv = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", -40, -220, name="XEN_OR", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.wire((-360, -240), x_nor.pin("A"), "en_ring")
    sch.wire((-360, -200), x_nor.pin("B"), "en_relax")
    sch.wire(x_nor.pin("Y"), x_inv.pin("A"), "en_bias_b")

    # Shared Bias
    xb = sch.add("bias/bias.sym", 300, -220, custom_pins=bias_pins, name="XBIAS")
    sch.wire(xb.pin("VDD"), (xb.pin("VDD")[0], xb.pin("VDD")[1] - 20), "VDD")
    sch.label("VDD", (xb.pin("VDD")[0], xb.pin("VDD")[1] - 20))
    sch.wire(xb.pin("VSS"), (xb.pin("VSS")[0], xb.pin("VSS")[1] + 20), "VSS")
    sch.label("VSS", (xb.pin("VSS")[0], xb.pin("VSS")[1] + 20))
    sch.wire(x_inv.pin("Y"), xb.pin("en"), "en_bias")
    sch.wire((80, -220), (80, -245), "en_bias")
    sch.label("en_bias", (80, -245), flip=1)
    sch.add("devices/noconn.sym", xb.pin("ibias_out")[0], xb.pin("ibias_out")[1], name="nc_ibias")

    # Ring Oscillator B (IDAC + CCO) and Relax core
    xdac = sch.add("osc_ring_cc/idac_8b.sym", 300, 240, custom_pins=idac_pins, name="XIDAC")
    xcco = sch.add("osc_ring_cc/cco_core.sym", 840, 120, custom_pins=cco_pins, name="XCCO")
    xrel = sch.add("clk_macro/relax_core.sym", 840, -220, custom_pins=relax_pins, name="XRELAX")

    for inst in (xdac, xcco, xrel):
        pv = inst.pin("VDD")
        sch.wire((pv[0], pv[1] - 20), pv, "VDD")
        sch.label("VDD", (pv[0], pv[1] - 20))
        pg = inst.pin("VSS")
        sch.wire(pg, (pg[0], pg[1] + 20), "VSS")
        sch.label("VSS", (pg[0], pg[1] + 20))

    # Bias -> Relax core (vpbias, vnbias) & IDAC (vnbias) via clean orthogonal routing
    p_vp_b, p_vp_r = xb.pin("vpbias"), xrel.pin("vpbias")
    sch.wire(p_vp_b, (560, p_vp_b[1]), "vpbias")
    sch.wire((560, p_vp_b[1]), (560, p_vp_r[1]), "vpbias")
    sch.wire((560, p_vp_r[1]), p_vp_r, "vpbias")
    sch.wire((500, p_vp_b[1]), (500, p_vp_b[1] - 20), "vpbias")
    sch.label("vpbias", (500, p_vp_b[1] - 20), flip=1)

    p_vn_b, p_vn_r, p_vn_d = xb.pin("vnbias"), xrel.pin("vnbias"), xdac.pin("vnbias")
    sch.wire(p_vn_b, (500, p_vn_b[1]), "vnbias")
    sch.wire((500, p_vn_b[1]), (500, p_vn_r[1]), "vnbias")
    sch.wire((500, p_vn_r[1]), p_vn_r, "vnbias")
    sch.wire((600, p_vn_r[1]), (600, p_vn_r[1] + 20), "vnbias")
    sch.label("vnbias", (600, p_vn_r[1] + 20), flip=1)

    sch.wire((460, p_vn_b[1]), (460, -70), "vnbias")
    sch.wire((460, -70), (40, -70), "vnbias")
    sch.wire((40, -70), (40, p_vn_d[1]), "vnbias")
    sch.wire((40, p_vn_d[1]), p_vn_d, "vnbias")

    # IDAC connections
    sch.in_label("en_ring", xdac.pin("en"), dx=30)
    for b in range(8):
        sch.in_label(f"trim{b}", xdac.pin(f"trim{b}"), dx=30)

    # IDAC -> CCO (ictrl)
    p_ic_d, p_ic_c = xdac.pin("ictrl"), xcco.pin("ictrl")
    sch.wire(p_ic_d, (560, p_ic_d[1]), "ictrl")
    sch.wire((560, p_ic_d[1]), (560, p_ic_c[1]), "ictrl")
    sch.wire((560, p_ic_c[1]), p_ic_c, "ictrl")
    sch.wire((560, p_ic_d[1]), (560, p_ic_d[1] + 20), "ictrl")
    sch.label("ictrl", (560, p_ic_d[1] + 20), flip=1)

    # CCO connections
    sch.in_label("en_ring", xcco.pin("en"), dx=30)
    sch.wire(xcco.pin("clk"), (xcco.pin("clk")[0] + 100, xcco.pin("clk")[1]), "clk")
    sch.pin("opin", "clk", (xcco.pin("clk")[0] + 100, xcco.pin("clk")[1]))

    # Relax core connections
    sch.in_label("en_relax", xrel.pin("en"), dx=30)
    sch.wire(xrel.pin("clk_slow"), (xrel.pin("clk_slow")[0] + 100, xrel.pin("clk_slow")[1]), "clk_slow")
    sch.pin("opin", "clk_slow", (xrel.pin("clk_slow")[0] + 100, xrel.pin("clk_slow")[1]))

    sch.write(out_dir / "rpe_clk_analog.sch")

    # Testbench tb_rpe_clk_analog.sch
    tb = Schematic()
    tb.text("Testbench: Unified Custom Analog Clock Macro (rpe_clk_analog)", 0, -400, scale=0.35)
    tb.title(0, 500)

    xmac = tb.add("clk_macro/rpe_clk_analog.sym", 280, 0, custom_pins=macro_pins, name="XMAC")

    for vx, name, net, val in [
        (-280, "Vdd", "VDD", "1.2"),
        (-160, "Ven_ring", "en_ring", "1.2"),
        (-40, "Ven_relax", "en_relax", "1.2"),
    ]:
        vs = tb.add("devices/vsource.sym", vx, -100, name=name, value=val)
        tb.wire(vs.pin("m"), (vx, -40), "GND")
        tb.add("devices/gnd.sym", vx, -40, name=f"g_{name}", lab="GND")
        tb.wire(vs.pin("p"), (vx, -160), net)
        tb.label(net, (vx, -160))

    for i in range(8):
        vx = -260 + i * 120
        vy = 340
        val = "1.2" if i in (0, 1, 2, 4, 7) else "0"  # 0x97 = 151
        vs = tb.add("devices/vsource.sym", vx, vy, name=f"Vtrim{i}", value=val)
        tb.wire(vs.pin("m"), (vx, vy + 40), "GND")
        tb.add("devices/gnd.sym", vx, vy + 40, name=f"gt{i}", lab="GND")
        tb.wire(vs.pin("p"), (vx, vy - 40), f"trim{i}")
        tb.label(f"trim{i}", (vx, vy - 40))

    tb.wire(xmac.pin("VDD"), (xmac.pin("VDD")[0], xmac.pin("VDD")[1] - 20), "VDD")
    tb.label("VDD", (xmac.pin("VDD")[0], xmac.pin("VDD")[1] - 20))
    tb.wire(xmac.pin("VSS"), (xmac.pin("VSS")[0], xmac.pin("VSS")[1] + 20), "GND")
    tb.add("devices/gnd.sym", xmac.pin("VSS")[0], xmac.pin("VSS")[1] + 20, name="g_vss", lab="GND")

    for pname in ["en_ring", "en_relax"] + [f"trim{i}" for i in range(7, -1, -1)]:
        p = xmac.pin(pname)
        tb.wire((p[0] - 40, p[1]), p, pname)
        tb.label(pname, (p[0] - 40, p[1]))

    for cname, cy, net in [("Cload_ring", -20, "clk"), ("Cload_relax", 100, "clk_slow")]:
        p = xmac.pin(net)
        cl = tb.add("devices/capa.sym", 580, cy, name=cname, value="50f", m="1")
        tb.out_label(net, p, dx=40)
        tb.route_vh((p[0] + 40, p[1]), cl.pin("p"), net)
        tb.wire(cl.pin("m"), (580, cy + 60), "GND")
        tb.add("devices/gnd.sym", 580, cy + 60, name=f"g_{cname}", lab="GND")

    tb.add(
        "devices/code_shown.sym", -280, -350,
        name="SPICE_MODELS",
        only_toplevel="true",
        value=".options temp=25\n.lib cornerMOSlv.lib mos_tt\n.lib cornerMOShv.lib mos_tt\n.lib cornerRES.lib res_typ\n.lib cornerCAP.lib cap_typ\n.include sg13cmos5l_stdcell.spice\n",
    )
    tb.write(out_dir / "tb_rpe_clk_analog.sch")
    print("Generated analog/clk_macro/{relax_core,rpe_clk_analog,tb_rpe_clk_analog}")


if __name__ == "__main__":
    build_clk_macro()
