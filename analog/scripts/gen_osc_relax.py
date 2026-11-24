#!/usr/bin/env python3
"""Generate clean hierarchical xschem schematics and symbols for the 100 kHz Relaxation Oscillator (analog/osc_relax)."""

import sys
from pathlib import Path

ANALOG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALOG_DIR / "scripts"))

from xschem_builder import Schematic, read_sym_pins, write_block_symbol


def build_comp(out_dir: Path) -> dict[str, tuple[float, float]]:
    sym_pins = write_block_symbol(
        out_dir / "comp.sym",
        block_name="comp",
        left_pins=[("inp", "in"), ("inn", "in"), ("en", "in"), ("vpbias", "in")],
        right_pins=[("out", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=180,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en", "vpbias", "inp", "inn", "out"],
    )

    sch = Schematic()
    sch.text("Low-Power PMOS-Input Continuous-Time Comparator (~1 uA total, out = inp > inn)", 0, -340, scale=0.35)
    sch.title(40, 380)

    sch.pin("iopin", "VDD", (-120, -280))
    sch.pin("iopin", "VSS", (-120, 280))
    sch.wire((-120, -280), (1200, -280), "VDD")
    sch.wire((-120, 280), (1200, 280), "VSS")

    sch.pin("ipin", "en", (-120, -160))
    sch.pin("ipin", "vpbias", (-120, -80))
    sch.pin("ipin", "inp", (-120, 40))
    sch.pin("ipin", "inn", (-120, 120))
    sch.wire((-120, -160), (-60, -160), "en")
    sch.label("en", (-60, -160), flip=1)

    # Stage 1: PMOS tail (vpbias) + PMOS diff pair + NMOS active mirror load
    mp_tail = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 290, -180, name="MP_TAIL", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos")
    mp_in1 = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 200, -40, flip=1, name="MP_INP", w="2.0u", l="1.0u", ng="1", m="2", model="sg13_lv_pmos")
    mp_in2 = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 420, -40, name="MP_INN", w="2.0u", l="1.0u", ng="1", m="2", model="sg13_lv_pmos")
    mn_l1 = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 200, 140, flip=1, name="MN_L1", w="0.5u", l="2.0u", ng="1", m="1", model="sg13_lv_nmos")
    mn_l2 = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 420, 140, name="MN_L2", w="0.5u", l="2.0u", ng="1", m="1", model="sg13_lv_nmos")

    # Tail connections (B == S == VDD)
    sch.wire(mp_tail.pin("S"), (310, -280), "VDD")
    sch.wire(mp_tail.pin("B"), mp_tail.pin("S"), "VDD")
    sch.in_label("vpbias", mp_tail.pin("G"), dx=40)
    sch.wire(mp_tail.pin("D"), (310, -120), "ntail")
    sch.wire((180, -120), (440, -120), "ntail")
    sch.wire((180, -120), mp_in1.pin("S"), "ntail")
    sch.wire((440, -120), mp_in2.pin("S"), "ntail")

    # Bulks of input pair (B == VDD != S): route cleanly outward past device text and up to VDD rail
    sch.wire(mp_in1.pin("B"), (175, -40), "VDD")
    sch.wire((175, -40), (175, -85), "VDD")
    sch.route_hv((175, -85), (60, -280), "VDD")
    sch.wire(mp_in2.pin("B"), (445, -40), "VDD")
    sch.wire((445, -40), (445, -85), "VDD")
    sch.route_hv((445, -85), (560, -280), "VDD")

    # Input gates (outward into the center gap so labels never overlap device text)
    sch.out_label("inp", mp_in1.pin("G"), dx=30)
    sch.in_label("inn", mp_in2.pin("G"), dx=30)

    # Diff pair drains -> NMOS loads (B == S == VSS)
    sch.wire(mp_in1.pin("D"), mn_l1.pin("D"), "n_mir")
    sch.wire(mp_in2.pin("D"), mn_l2.pin("D"), "n_stg1")
    sch.wire(mn_l1.pin("S"), (180, 280), "VSS")
    sch.wire(mn_l2.pin("S"), (440, 280), "VSS")
    sch.wire(mn_l1.pin("B"), mn_l1.pin("S"), "VSS")
    sch.wire(mn_l2.pin("B"), mn_l2.pin("S"), "VSS")

    # Diode strap MN_L1 -> MN_L2
    sch.wire((180, 60), (310, 60), "n_mir")
    sch.wire((310, 60), (310, 140), "n_mir")
    sch.wire(mn_l1.pin("G"), mn_l2.pin("G"), "n_mir")

    # Stage 2: CS gain stage (MN_G2 driven by n_stg1, MP_G2 current load from vpbias)
    mp_g2 = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 700, -140, name="MP_G2", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos")
    mn_g2 = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 700, 140, name="MN_G2", w="1.0u", l="1.0u", ng="1", m="1", model="sg13_lv_nmos")
    sch.wire(mp_g2.pin("S"), (720, -280), "VDD")
    sch.wire(mp_g2.pin("B"), mp_g2.pin("S"), "VDD")
    sch.in_label("vpbias", mp_g2.pin("G"), dx=40)

    sch.wire(mn_g2.pin("S"), (720, 280), "VSS")
    sch.wire(mn_g2.pin("B"), mn_g2.pin("S"), "VSS")
    sch.route_hv((440, 40), mn_g2.pin("G"), "n_stg1")
    sch.wire(mp_g2.pin("D"), mn_g2.pin("D"), "n_stg2")

    # Pull n_stg2 high when en=0 so comparator output stays cleanly 0
    mp_off = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 940, -140, name="MP_OFF", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_pmos")
    sch.wire(mp_off.pin("S"), (960, -280), "VDD")
    sch.wire(mp_off.pin("B"), mp_off.pin("S"), "VDD")
    sch.in_label("en", mp_off.pin("G"), dx=40)
    sch.route_vh(mp_off.pin("D"), (720, 0), "n_stg2")

    # Stage 3: Output inverter -> out
    xinv_out = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", 1080, 0, name="XINV_OUT", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.wire((720, 0), xinv_out.pin("A"), "n_stg2")
    sch.wire(xinv_out.pin("Y"), (1200, 0), "out")
    sch.pin("opin", "out", (1200, 0))

    sch.write(out_dir / "comp.sch")
    return sym_pins


def build_osc_relax_variant(
    out_dir: Path,
    name: str,
    cap_type: str,  # "cmomf" or "moscap"
    M: int,
    cap_params: dict,
    bias_pins: dict[str, tuple[float, float]],
    comp_pins: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    sym_pins = write_block_symbol(
        out_dir / f"{name}.sym",
        block_name=name,
        left_pins=[("en", "in")],
        right_pins=[("clk_slow", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=180,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en", "clk_slow"],
    )

    sch = Schematic()
    sch.text(f"100 kHz Relaxation Oscillator ({name}: cap={cap_type}, M={M})", 0, -380, scale=0.35)
    sch.title(400, 1020)

    sch.pin("iopin", "VDD", (-160, -320))
    sch.pin("iopin", "VSS", (-160, 920))
    sch.wire((-160, -320), (2140, -320), "VDD")
    sch.wire((-160, 920), (2140, 920), "VSS")
    sch.pin("ipin", "en", (-160, 0))

    # Enable inverter -> enb
    xinv_en = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", -40, 0, name="XINV_EN", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.wire((-160, 0), xinv_en.pin("A"), "en")
    sch.out_label("enb", xinv_en.pin("Y"), dx=40)

    # Bias cell
    xb = sch.add("bias/bias.sym", 160, -140, custom_pins=bias_pins, name="XBIAS")
    sch.wire(xb.pin("VDD"), (xb.pin("VDD")[0], -320), "VDD")
    sch.wire(xb.pin("VSS"), (xb.pin("VSS")[0], xb.pin("VSS")[1] + 40), "VSS")
    sch.label("VSS", (xb.pin("VSS")[0], xb.pin("VSS")[1] + 40))
    sch.route_vh((-120, 0), xb.pin("en"), "en")
    sch.out_label("vnbias", xb.pin("vnbias"), dx=40)
    sch.add("devices/noconn.sym", xb.pin("ibias_out")[0], xb.pin("ibias_out")[1], name="nc_ibias")

    # ---- Threshold reference: I_ref (~0.5 uA) into 4 series rppd (~840 kOhm -> vth ~ 0.42 V) ----
    mp_ref = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 500, -220, name="MP_REF", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos")
    sch.wire(mp_ref.pin("S"), (520, -320), "VDD")
    sch.wire(mp_ref.pin("B"), mp_ref.pin("S"), "VDD")
    p_vpb = xb.pin("vpbias")
    sch.wire(p_vpb, (370, p_vpb[1]), "vpbias")
    sch.wire((370, p_vpb[1]), (370, mp_ref.pin("G")[1]), "vpbias")
    sch.wire((370, mp_ref.pin("G")[1]), mp_ref.pin("G"), "vpbias")
    sch.wire((370, mp_ref.pin("G")[1]), (370, mp_ref.pin("G")[1] - 25), "vpbias")
    sch.label("vpbias", (370, mp_ref.pin("G")[1] - 25), flip=1)
    sch.wire(mp_ref.pin("D"), (520, -140), "vth")
    sch.label("vth", (520, -140))

    prev_r = (520, -140)
    prev_n = "vth"
    for k in range(4):
        ry = -60 + k * 100
        rr = sch.add("sg13cmos5l_pr/rppd.sym", 520, ry, name=f"R_TH{k}", w="0.5e-6", l="40.0e-6", b="9", m="1", model="rppd", body="VSS", value="209k")
        sch.wire(prev_r, rr.pin("P"), prev_n)
        nxt = f"rth_{k}" if k < 3 else "VSS"
        prev_r = rr.pin("M")
        prev_n = nxt
    sch.wire(prev_r, (520, 920), "VSS")

    # ---- 1:M Current Mirror for charging currents I_chg = I_ref / M (~50 nA for M=10, ~500 nA for M=1) ----
    # Sink 0.5 uA via MN_M from diode-connected MP_M_IN (W=0.5u, L=4.0u, m=M) -> vp_chg
    mn_m = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 780, 120, name="MN_MIR", w="0.3u", l="4.0u", ng="1", m="1", model="sg13_lv_nmos")
    mp_m_in = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 780, -220, name="MP_CHG_IN", w="0.5u", l="4.0u", ng="1", m=str(M), model="sg13_lv_pmos")
    sch.in_label("vnbias", mn_m.pin("G"), dx=40)
    sch.wire(mn_m.pin("S"), (800, 920), "VSS")
    sch.wire(mn_m.pin("B"), mn_m.pin("S"), "VSS")
    sch.wire(mp_m_in.pin("S"), (800, -320), "VDD")
    sch.wire(mp_m_in.pin("B"), mp_m_in.pin("S"), "VDD")
    sch.wire(mp_m_in.pin("D"), mn_m.pin("D"), "vp_chg")
    sch.route_hv((800, -140), (720, -220), "vp_chg")
    sch.wire((720, -220), mp_m_in.pin("G"), "vp_chg")
    sch.wire((720, -220), (690, -220), "vp_chg")
    sch.label("vp_chg", (690, -220), flip=0)

    # ---- Ping-pong branches A and B ----
    for idx, (side, bx, reset_net) in enumerate([("A", 1020, "q"), ("B", 1380, "qb")]):
        vcap_net = f"vcap_{side.lower()}"
        mp_chg = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", bx, -220, name=f"MP_CHG_{side}", w="0.5u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos")
        # Low-leakage HV NMOS discharge switch (longer L=0.5u)
        mn_dis = sch.add("sg13cmos5l_pr/sg13_hv_nmos.sym", bx, 20, name=f"MN_DIS_{side}", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_hv_nmos")

        sch.wire(mp_chg.pin("S"), (bx + 20, -320), "VDD")
        sch.wire(mp_chg.pin("B"), mp_chg.pin("S"), "VDD")
        sch.in_label("vp_chg", mp_chg.pin("G"), dx=40)
        sch.wire(mp_chg.pin("D"), mn_dis.pin("D"), vcap_net)
        sch.label(vcap_net, (bx + 20, -100))

        sch.wire(mn_dis.pin("S"), (bx + 20, 120), "VSS")
        sch.label("VSS", (bx + 20, 120))
        sch.wire(mn_dis.pin("B"), mn_dis.pin("S"), "VSS")
        # Discharge active when reset_net is HIGH OR en is LOW -> gate via dis_A / dis_B NOR/OR
        sch.in_label(f"dis_{side.lower()}", mn_dis.pin("G"), dx=40)

        # Timing capacitor (either cap_cmomf or thick-oxide sg13_svaricap)
        if cap_type == "cmomf":
            cap = sch.add(
                "sg13cmos5l_pr/cap_cmomf.sym", bx + 140, 180,
                name=f"C_{side}", w=cap_params["w"], l=cap_params["l"], mmin="1", mmax="4", m=cap_params["m"],
            )
            sch.route_hv((bx + 20, -100), cap.pin("c0"), vcap_net)
            sch.wire(cap.pin("c1"), (bx + 140, 260), "VSS")
            sch.label("VSS", (bx + 140, 260))
        else:
            # Thick-oxide accumulation-mode MOSCAP: G1 & G2 tied to vcap_net, NW & body tied to VSS
            cap = sch.add(
                "sg13cmos5l_pr/sg13_svaricap.sym", bx + 180, 180,
                name=f"C_{side}", model="sg13_hv_svaricap", w=cap_params["w"], l=cap_params["l"], Nx=cap_params["Nx"], body="VSS",
            )
            sch.wire(cap.pin("NW"), (bx + 180, 110), "VSS")
            sch.label("VSS", (bx + 180, 110), flip=1)
            sch.route_hv((bx + 20, -100), (bx + 120, 180), vcap_net)
            sch.wire((bx + 120, 180), cap.pin("G2"), vcap_net)
            sch.out_label(vcap_net, cap.pin("G1"), dx=40)

        # Comparator for this cap (well separated horizontally & vertically from C_B and each other)
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

    # ---- Cross-coupled NOR SR latch + disable clamp -> q, qb, dis_a, dis_b, clk_slow ----
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

    # Symmetry-breaking init clamp: while en=0 (enb=1), pull qb=0 so q=1 deterministically on startup
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

    # Deadlock-breaker: if cmp_a & cmp_b are ever both HIGH (power-up with en=VDD), discharge vcap_a to snap latch
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

    sch.write(out_dir / f"{name}.sch")
    return sym_pins


def build_osc_relax() -> None:
    out_dir = ANALOG_DIR / "osc_relax"
    out_dir.mkdir(parents=True, exist_ok=True)

    bias_pins = read_sym_pins(ANALOG_DIR / "bias" / "bias.sym")
    comp_pins = build_comp(out_dir)

    # Variant 1 (default): cap_cmomf (~550 fF: 20.6u x 20.6u = 547 fF), M=10
    sym_cmom = build_osc_relax_variant(
        out_dir, "osc_relax", "cmomf", M=10,
        cap_params={"w": "20.6e-6", "l": "20.6e-6", "m": "1"},
        bias_pins=bias_pins, comp_pins=comp_pins,
    )

    # Variant 2: thick-oxide accumulation-mode MOSCAP (sg13_hv_svaricap ~550 fF), M=10
    # Wait: smoke test showed w=4u, l=0.5u, Nx=1 -> 8.72 fF. With w=8u, l=0.8u, Nx=10 -> ~279 fF?
    # Let's instantiate w=9.0u, l=0.8u, Nx=10 (or let run_sims calibrate exact area / cap density too!)
    sym_moscap = build_osc_relax_variant(
        out_dir, "osc_relax_moscap", "moscap", M=10,
        cap_params={"w": "9.74e-6", "l": "0.8e-6", "Nx": "9"},
        bias_pins=bias_pins, comp_pins=comp_pins,
    )

    # Testbench tb_osc_relax.sch (uses osc_relax by default; run_sims also evaluates variants & options)
    tb = Schematic()
    tb.text("Testbench: 100 kHz Relaxation Oscillator (analog/osc_relax)", 0, -240, scale=0.35)
    tb.title(0, 460)

    xosc = tb.add("osc_relax/osc_relax.sym", 260, 0, custom_pins=sym_cmom, name="XOSC")

    vdd_src = tb.add("devices/vsource.sym", -120, -80, name="Vdd", value="1.2")
    tb.wire(vdd_src.pin("m"), (-120, -20), "GND")
    tb.add("devices/gnd.sym", -120, -20, name="g1", lab="GND")
    tb.wire(vdd_src.pin("p"), (-120, -140), "VDD")
    tb.label("VDD", (-120, -140))

    ven_src = tb.add("devices/vsource.sym", -20, 60, name="Ven", value="1.2")
    tb.wire(ven_src.pin("m"), (-20, 120), "GND")
    tb.add("devices/gnd.sym", -20, 120, name="g2", lab="GND")
    tb.route_vh(ven_src.pin("p"), (120, 0), "en")
    tb.in_label("en", xosc.pin("en"), dx=20)

    tb.wire(xosc.pin("VDD"), (xosc.pin("VDD")[0], xosc.pin("VDD")[1] - 40), "VDD")
    tb.label("VDD", (xosc.pin("VDD")[0], xosc.pin("VDD")[1] - 40))
    tb.wire(xosc.pin("VSS"), (xosc.pin("VSS")[0], xosc.pin("VSS")[1] + 40), "GND")
    tb.add("devices/gnd.sym", xosc.pin("VSS")[0], xosc.pin("VSS")[1] + 40, name="g3", lab="GND")

    cload = tb.add("devices/capa.sym", 540, 40, name="Cload", value="50f", m="1")
    tb.out_label("clk_slow", xosc.pin("clk_slow"), dx=20)
    tb.route_hv((400, 0), cload.pin("p"), "clk_slow")
    tb.wire(cload.pin("m"), (540, 100), "GND")
    tb.add("devices/gnd.sym", 540, 100, name="g4", lab="GND")

    tb.add(
        "devices/code_shown.sym", -120, 200,
        name="SPICE_MODELS",
        only_toplevel="true",
        value=".options temp=25\n.lib cornerMOSlv.lib mos_tt\n.lib cornerMOShv.lib mos_tt\n.lib cornerRES.lib res_typ\n.lib cornerCAP.lib cap_typ\n.include sg13cmos5l_stdcell.spice\n",
    )
    tb.write(out_dir / "tb_osc_relax.sch")

    # Separate testbench tb_osc_relax_moscap.sch so moscap schematic is also directly netlistable & inspectable
    tb2 = Schematic()
    tb2.text("Testbench: 100 kHz Relaxation Oscillator (Thick-Oxide MOSCAP Variant)", 0, -240, scale=0.35)
    tb2.title(0, 460)
    xosc2 = tb2.add("osc_relax/osc_relax_moscap.sym", 260, 0, custom_pins=sym_moscap, name="XOSC")
    vdd2 = tb2.add("devices/vsource.sym", -120, -80, name="Vdd", value="1.2")
    tb2.wire(vdd2.pin("m"), (-120, -20), "GND")
    tb2.add("devices/gnd.sym", -120, -20, name="g1", lab="GND")
    tb2.wire(vdd2.pin("p"), (-120, -140), "VDD")
    tb2.label("VDD", (-120, -140))
    ven2 = tb2.add("devices/vsource.sym", -20, 60, name="Ven", value="1.2")
    tb2.wire(ven2.pin("m"), (-20, 120), "GND")
    tb2.add("devices/gnd.sym", -20, 120, name="g2", lab="GND")
    tb2.route_vh(ven2.pin("p"), (120, 0), "en")
    tb2.in_label("en", xosc2.pin("en"), dx=20)
    tb2.wire(xosc2.pin("VDD"), (xosc2.pin("VDD")[0], xosc2.pin("VDD")[1] - 40), "VDD")
    tb2.label("VDD", (xosc2.pin("VDD")[0], xosc2.pin("VDD")[1] - 40))
    tb2.wire(xosc2.pin("VSS"), (xosc2.pin("VSS")[0], xosc2.pin("VSS")[1] + 40), "GND")
    tb2.add("devices/gnd.sym", xosc2.pin("VSS")[0], xosc2.pin("VSS")[1] + 40, name="g3", lab="GND")
    cl2 = tb2.add("devices/capa.sym", 540, 40, name="Cload", value="50f", m="1")
    tb2.out_label("clk_slow", xosc2.pin("clk_slow"), dx=20)
    tb2.route_hv((400, 0), cl2.pin("p"), "clk_slow")
    tb2.wire(cl2.pin("m"), (540, 100), "GND")
    tb2.add("devices/gnd.sym", 540, 100, name="g4", lab="GND")
    tb2.add(
        "devices/code_shown.sym", -120, 200,
        name="SPICE_MODELS",
        only_toplevel="true",
        value=".options temp=25\n.lib cornerMOSlv.lib mos_tt\n.lib cornerMOShv.lib mos_tt\n.lib cornerRES.lib res_typ\n.lib cornerCAP.lib cap_typ\n.include sg13cmos5l_stdcell.spice\n",
    )
    tb2.write(out_dir / "tb_osc_relax_moscap.sch")
    print("Generated analog/osc_relax/{comp,osc_relax,osc_relax_moscap,tb_osc_relax,tb_osc_relax_moscap}")


if __name__ == "__main__":
    build_osc_relax()
