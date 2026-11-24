#!/usr/bin/env python3
"""Generate clean hierarchical xschem schematics and symbols for Ring Oscillator B (analog/osc_ring_cc)."""

import sys
from pathlib import Path

ANALOG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALOG_DIR / "scripts"))

from xschem_builder import Schematic, read_sym_pins, write_block_symbol


def build_idac_8b(out_dir: Path) -> dict[str, tuple[float, float]]:
    trim_pins = [(f"trim{i}", "in") for i in range(7, -1, -1)]
    sym_pins = write_block_symbol(
        out_dir / "idac_8b.sym",
        block_name="idac_8b",
        left_pins=[("en", "in"), ("vnbias", "in")] + trim_pins,
        right_pins=[("ictrl", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=200,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en", "vnbias"] + [f"trim{i}" for i in range(7, -1, -1)] + ["ictrl"],
    )

    sch = Schematic()
    sch.text("8-bit Segmented PMOS Current DAC (3b Therm + 5b Binary + Pedestal, I_lsb=62.5 nA)", 0, -400, scale=0.35)
    sch.title(0, 1540)

    # Rails
    sch.pin("iopin", "VDD", (-120, -340))
    sch.pin("iopin", "VSS", (-120, 1360))
    sch.wire((-120, -340), (2820, -340), "VDD")
    sch.wire((-120, 1360), (2820, 1360), "VSS")

    sch.pin("ipin", "en", (-120, -240))
    sch.pin("ipin", "vnbias", (-120, -140))
    for i, b in enumerate(range(7, -1, -1)):
        sch.pin("ipin", f"trim{b}", (-120, 40 + i * 60))

    # ---- Reference divider: vnbias (0.5 uA) -> MP_IN diode (W=1.5u, L=4u, m=2 -> 1.33x boost) ----
    # Unit current source W=0.5u, L=4u, m=1 gives 0.5 uA / 6 = 83.3 nA = I_lsb (PEX re-centered).
    mn_div = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 60, -140,
        name="MN_DIV", w="0.3u", l="4.0u", ng="1", m="1", model="sg13_lv_nmos",
    )
    mp_in = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 60, -260,
        name="MP_IN", w="1.5u", l="4.0u", ng="1", m="2", model="sg13_lv_pmos",
    )
    mp_off = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 300, -260,
        name="MP_DAC_OFF", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_pmos",
    )
    sch.wire((-120, -140), mn_div.pin("G"), "vnbias")
    sch.wire(mn_div.pin("B"), mn_div.pin("S"), "VSS")
    sch.wire(mn_div.pin("S"), (80, -90), "VSS")
    sch.label("VSS", (80, -90))

    sch.wire(mp_in.pin("S"), (80, -340), "VDD")
    sch.wire(mp_in.pin("B"), mp_in.pin("S"), "VDD")
    sch.wire(mp_in.pin("D"), mn_div.pin("D"), "vpdac")
    sch.route_hv((80, -200), (20, -260), "vpdac")
    sch.wire((20, -260), mp_in.pin("G"), "vpdac")
    sch.wire((200, -200), (200, -185), "vpdac")
    sch.label("vpdac", (200, -185), flip=1)

    sch.wire(mp_off.pin("S"), (320, -340), "VDD")
    sch.wire(mp_off.pin("B"), mp_off.pin("S"), "VDD")
    sch.in_label("en", mp_off.pin("G"), dx=40)
    sch.wire((80, -200), (320, -200), "vpdac")
    sch.wire(mp_off.pin("D"), (320, -200), "vpdac")

    # ---- Enable inverter + 3-to-7 active-low thermometer decoder + binary inverters ----
    # Outputs active-low signals: enb, t0_b..t6_b, b0_b..b4_b
    def add_inv(name: str, x: float, y: float, in_net: str, out_net: str, out_lab: bool = True) -> object:
        g = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", x, y, name=name, VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
        if in_net:
            sch.in_label(in_net, g.pin("A"), dx=40)
        if out_lab and out_net:
            sch.out_label(out_net, g.pin("Y"), dx=40)
        return g

    def add_nand2(name: str, x: float, y: float, a_net: str, b_net: str, out_net: str, out_lab: bool = True) -> object:
        g = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nand2_2.sym", x, y, name=name, VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
        if a_net:
            sch.in_label(a_net, g.pin("A"), dx=40)
        if b_net:
            sch.in_label(b_net, g.pin("B"), dx=40)
        if out_lab and out_net:
            sch.out_label(out_net, g.pin("Y"), dx=40)
        return g

    def add_nor2(name: str, x: float, y: float, a_net: str, b_net: str, out_net: str, out_lab: bool = True) -> object:
        g = sch.add("sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym", x, y, name=name, VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
        if a_net:
            sch.in_label(a_net, g.pin("A"), dx=40)
        if b_net:
            sch.in_label(b_net, g.pin("B"), dx=40)
        if out_lab and out_net:
            sch.out_label(out_net, g.pin("Y"), dx=40)
        return g

    def wire_tap(p1: tuple[float, float], p2: tuple[float, float], net: str) -> None:
        """Connect consecutive decoder gates directly and label on a short upward tap if needed."""
        sch.wire(p1, p2, net)
        mx = (p1[0] + p2[0]) * 0.5 - 10
        my = p1[1]
        sch.wire((mx, my), (mx, my - 20), net)
        sch.label(net, (mx, my - 20), flip=1)

    add_inv("XINV_EN", 60, -10, "en", "enb")
    for b in range(5):
        add_inv(f"XINV_B{b}", 60, 85 + b * 95, f"trim{b}", f"b{b}_b")

    # 3-to-7 thermometer active-low decoder for a=trim7, b=trim6, c=trim5
    y_dec = [560 + r * 95 for r in range(4)]
    x_s1, x_s2, x_s3 = 340, 580, 820

    add_inv("XINV_A", 60, y_dec[0], "trim7", "t3_b")

    g_nab = add_nand2("XN_AB", x_s1, y_dec[0], "trim7", "trim6", "t5_b", out_lab=False)
    g_iab = add_inv("XI_AB", x_s2, y_dec[0], "", "ab", out_lab=False)
    wire_tap(g_nab.pin("Y"), g_iab.pin("A"), "t5_b")
    g_nabc = add_nand2("XN_ABC", x_s3, y_dec[0], "", "trim5", "t6_b")
    sch.wire(g_iab.pin("Y"), (x_s2 + 80, y_dec[0]), "ab")
    sch.wire((x_s2 + 80, y_dec[0]), (x_s2 + 80, y_dec[0] - 20), "ab")
    sch.wire((x_s2 + 80, y_dec[0] - 20), g_nabc.pin("A"), "ab")
    sch.wire((x_s2 + 130, y_dec[0] - 20), (x_s2 + 130, y_dec[0] - 38), "ab")
    sch.label("ab", (x_s2 + 130, y_dec[0] - 38), flip=0)

    g_nbc = add_nand2("XN_BC", x_s1, y_dec[1], "trim6", "trim5", "bc_n", out_lab=False)
    g_ibc = add_inv("XI_BC", x_s2, y_dec[1], "", "bc", out_lab=False)
    wire_tap(g_nbc.pin("Y"), g_ibc.pin("A"), "bc_n")
    g_not2 = add_nor2("XNO_T2", x_s3, y_dec[1], "trim7", "", "t2_b")
    sch.wire(g_ibc.pin("Y"), (x_s2 + 80, y_dec[1]), "bc")
    sch.wire((x_s2 + 80, y_dec[1]), (x_s2 + 80, y_dec[1] + 20), "bc")
    sch.wire((x_s2 + 80, y_dec[1] + 20), g_not2.pin("B"), "bc")
    sch.wire((x_s2 + 130, y_dec[1] + 20), (x_s2 + 130, y_dec[1] + 38), "bc")
    sch.label("bc", (x_s2 + 130, y_dec[1] + 38), flip=0)

    g_noborc = add_nor2("XNO_BORC", x_s1, y_dec[2], "trim6", "trim5", "borc_n", out_lab=False)
    g_iborc = add_inv("XI_BORC", x_s2, y_dec[2], "", "borc", out_lab=False)
    wire_tap(g_noborc.pin("Y"), g_iborc.pin("A"), "borc_n")
    g_nt4 = add_nand2("XN_T4", x_s3, y_dec[2], "trim7", "", "t4_b")
    sch.wire(g_iborc.pin("Y"), (x_s2 + 80, y_dec[2]), "borc")
    sch.wire((x_s2 + 80, y_dec[2]), (x_s2 + 80, y_dec[2] + 20), "borc")
    sch.wire((x_s2 + 80, y_dec[2] + 20), g_nt4.pin("B"), "borc")
    sch.wire((x_s2 + 130, y_dec[2] + 20), (x_s2 + 130, y_dec[2] + 38), "borc")
    sch.label("borc", (x_s2 + 130, y_dec[2] + 38), flip=1)

    add_nor2("XNO_T1", x_s1, y_dec[3], "trim7", "trim6", "t1_b")
    g_not0 = add_nor2("XNO_T0", x_s3, y_dec[3], "trim7", "", "t0_b")
    sch.route_vh((x_s2 + 80, y_dec[2] + 20), g_not0.pin("B"), "borc")

    # ---- PMOS Current Array + Drain Switches -> ictrl ----
    # (name, mult_pmos, mult_sw, sw_gate_net)
    branches = [
        ("PED", 48, 4, "enb"),
        ("B0", 1, 1, "b0_b"),
        ("B1", 2, 1, "b1_b"),
        ("B2", 4, 1, "b2_b"),
        ("B3", 8, 1, "b3_b"),
        ("B4", 16, 2, "b4_b"),
        ("T0", 32, 4, "t0_b"),
        ("T1", 32, 4, "t1_b"),
        ("T2", 32, 4, "t2_b"),
        ("T3", 32, 4, "t3_b"),
        ("T4", 32, 4, "t4_b"),
        ("T5", 32, 4, "t5_b"),
        ("T6", 32, 4, "t6_b"),
    ]

    bus_y = 1240
    sch.wire((1100, bus_y), (2820, bus_y), "ictrl")
    sch.pin("opin", "ictrl", (2820, bus_y))

    for i, (bname, m_cur, m_sw, sw_net) in enumerate(branches):
        bx = 1100 + (i % 7) * 260
        row = i // 7
        if row == 1:
            # Place second row below decoder cleanly
            by_cur = 960
            by_sw = 1080
        else:
            by_cur = 80
            by_sw = 200

        mp_c = sch.add(
            "sg13cmos5l_pr/sg13_lv_pmos.sym", bx, by_cur,
            name=f"MPC_{bname}", w="0.5u", l="4.0u", ng="1", m=str(m_cur), model="sg13_lv_pmos",
        )
        mp_s = sch.add(
            "sg13cmos5l_pr/sg13_lv_pmos.sym", bx, by_sw,
            name=f"MPS_{bname}", w="1.0u", l="0.2u", ng="1", m=str(m_sw), model="sg13_lv_pmos",
        )
        # Source & bulk of current source to VDD
        sch.wire((bx + 20, by_cur - 50), mp_c.pin("S"), "VDD")
        sch.label("VDD", (bx + 20, by_cur - 50))
        sch.wire(mp_c.pin("B"), mp_c.pin("S"), "VDD")
        sch.in_label("vpdac", mp_c.pin("G"), dx=40)

        # Drain of current source -> source of switch; switch bulk to VDD clear of text
        sch.wire(mp_c.pin("D"), mp_s.pin("S"), f"d_{bname}")
        sch.wire(mp_s.pin("B"), (bx + 26, by_sw), "VDD")
        sch.wire((bx + 26, by_sw), (bx + 26, by_sw - 45), "VDD")
        sch.wire((bx + 26, by_sw - 45), (bx + 60, by_sw - 45), "VDD")
        sch.label("VDD", (bx + 60, by_sw - 45), flip=1)
        sch.in_label(sw_net, mp_s.pin("G"), dx=40)

        # Switch drain -> ictrl bus
        if row == 1:
            sch.wire(mp_s.pin("D"), (bx + 20, bus_y), "ictrl")
        else:
            sch.wire(mp_s.pin("D"), (bx + 20, by_sw + 50), "ictrl")
            sch.label("ictrl", (bx + 20, by_sw + 50))

    sch.write(out_dir / "idac_8b.sch")
    return sym_pins


def build_cco_core(out_dir: Path) -> dict[str, tuple[float, float]]:
    sym_pins = write_block_symbol(
        out_dir / "cco_core.sym",
        block_name="cco_core",
        left_pins=[("en", "in"), ("ictrl", "in")],
        right_pins=[("clk", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=180,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en", "ictrl", "clk"],
    )

    sch = Schematic()
    sch.text("5-Stage Current-Starved Ring Oscillator Core (with CMOM stage caps + output buffer)", 0, -340, scale=0.35)
    sch.title(0, 560)

    sch.pin("iopin", "VDD", (-120, -280))
    sch.pin("iopin", "VSS", (-120, 280))
    sch.wire((-120, -280), (2660, -280), "VDD")
    sch.wire((-120, 280), (2660, 280), "VSS")

    sch.pin("ipin", "en", (-120, -100))
    sch.pin("ipin", "ictrl", (-120, 120))

    # Enable inverter: en -> enb
    xinv_en = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", 0, -100, name="XINV_EN", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.wire((-120, -100), xinv_en.pin("A"), "en")
    sch.out_label("enb", xinv_en.pin("Y"), dx=40)

    # ---- Bias mirrors: ictrl -> vctrl_n -> vctrl_p ----
    mn_b = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 40, 120, name="MN_BIAS", w="2.0u", l="1.0u", ng="1", m="2", model="sg13_lv_nmos")
    sch.wire(mn_b.pin("S"), (60, 280), "VSS")
    sch.wire(mn_b.pin("B"), mn_b.pin("S"), "VSS")
    sch.wire((-120, 120), (0, 120), "ictrl")
    sch.route_vh((0, 120), mn_b.pin("D"), "ictrl")
    sch.wire((0, 120), mn_b.pin("G"), "ictrl")

    # Mirror ictrl -> MP_BIAS -> vctrl_p
    mp_b = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 240, -140, name="MP_BIAS", w="4.0u", l="1.0u", ng="1", m="2", model="sg13_lv_pmos")
    mn_bm = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 240, 120, name="MN_BMIR", w="2.0u", l="1.0u", ng="1", m="2", model="sg13_lv_nmos")
    sch.wire(mp_b.pin("S"), (260, -280), "VDD")
    sch.wire(mp_b.pin("B"), mp_b.pin("S"), "VDD")
    sch.wire(mp_b.pin("D"), mn_bm.pin("D"), "vctrl_p")
    sch.route_hv((260, -40), (180, -140), "vctrl_p")
    sch.wire((180, -140), mp_b.pin("G"), "vctrl_p")
    sch.label("vctrl_p", (180, -140))

    sch.wire(mn_bm.pin("S"), (260, 280), "VSS")
    sch.wire(mn_bm.pin("B"), mn_bm.pin("S"), "VSS")

    # Shutdown clamps on vctrl_p and ictrl (vctrl_n) when en=0
    mp_poff = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", 440, -200, name="MP_POFF", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_pmos")
    sch.wire(mp_poff.pin("S"), (460, -280), "VDD")
    sch.wire(mp_poff.pin("B"), mp_poff.pin("S"), "VDD")
    sch.in_label("en", mp_poff.pin("G"), dx=40)
    sch.wire((260, -40), (460, -40), "vctrl_p")
    sch.wire((460, -40), mp_poff.pin("D"), "vctrl_p")

    mn_noff = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 440, 200, name="MN_NOFF", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_nmos")
    sch.wire(mn_noff.pin("S"), (460, 280), "VSS")
    sch.wire(mn_noff.pin("B"), mn_noff.pin("S"), "VSS")
    sch.in_label("enb", mn_noff.pin("G"), dx=40)

    # Clean overhead ictrl bus connecting MN_BIAS -> MN_BMIR.G -> MN_NOFF.D
    sch.wire((0, 90), (0, 60), "ictrl")
    sch.wire((0, 60), (460, 60), "ictrl")
    sch.route_vh((190, 60), mn_bm.pin("G"), "ictrl")
    sch.wire((460, 60), mn_noff.pin("D"), "ictrl")
    sch.wire((320, 60), (320, 40), "ictrl")
    sch.label("ictrl", (320, 40), flip=1)

    # ---- 5 Current-Starved Inverter Stages (n0 -> n1 -> n2 -> n3 -> n4 -> n0) ----
    # Note: 5 stages, each with CMOM cap (2.4u x 2.4u ≈ 7.4 fF compact -> ~60 MHz in PEX) + starved PMOS/NMOS stack
    for k in range(5):
        sx = 680 + k * 300
        in_net = f"n{k}"
        out_net = f"n{(k + 1) % 5}"

        mp_cur = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", sx, -180, name=f"MPC_{k}", w="4.0u", l="1.0u", ng="1", m="1", model="sg13_lv_pmos")
        mp_inv = sch.add("sg13cmos5l_pr/sg13_lv_pmos.sym", sx, -60, name=f"MPI_{k}", w="1.0u", l="0.2u", ng="1", m="1", model="sg13_lv_pmos")
        mn_inv = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", sx, 60, name=f"MNI_{k}", w="0.5u", l="0.2u", ng="1", m="1", model="sg13_lv_nmos")
        mn_cur = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", sx, 180, name=f"MNC_{k}", w="2.0u", l="1.0u", ng="1", m="1", model="sg13_lv_nmos")

        # CMOM load capacitor at output node out_net (2.4e-6 x 2.4e-6 ≈ 7.41 fF -> PEX-centered)
        cap = sch.add("sg13cmos5l_pr/cap_cmomf.sym", sx + 140, 100, name=f"CC_{k}", w="2.4e-6", l="2.4e-6", mmin="1", mmax="4", m="1")

        # Rails & bulks (only short B->S where B==S; MPI/MNI bulks route clear of parameter text)
        sch.wire(mp_cur.pin("S"), (sx + 20, -280), "VDD")
        sch.wire(mp_cur.pin("B"), mp_cur.pin("S"), "VDD")
        sch.wire(mp_inv.pin("B"), (sx + 26, -60), "VDD")
        sch.wire((sx + 26, -60), (sx + 26, -100), "VDD")
        sch.wire((sx + 26, -100), (sx + 60, -100), "VDD")
        sch.label("VDD", (sx + 60, -100), flip=1)

        sch.wire(mn_cur.pin("S"), (sx + 20, 280), "VSS")
        sch.wire(mn_cur.pin("B"), mn_cur.pin("S"), "VSS")
        sch.wire(mn_inv.pin("B"), (sx + 26, 60), "VSS")
        sch.wire((sx + 26, 60), (sx + 26, 115), "VSS")
        sch.wire((sx + 26, 115), (sx + 60, 115), "VSS")
        sch.label("VSS", (sx + 60, 115), flip=1)

        # Bias gates
        sch.in_label("vctrl_p", mp_cur.pin("G"), dx=40)
        sch.in_label("ictrl", mn_cur.pin("G"), dx=40)

        # Stack connections
        sch.wire(mp_cur.pin("D"), mp_inv.pin("S"), f"ps_{k}")
        sch.wire(mn_inv.pin("S"), mn_cur.pin("D"), f"ns_{k}")

        # Inverter input
        sch.wire((sx - 60, -60), (sx - 60, 60), in_net)
        sch.wire((sx - 60, -60), mp_inv.pin("G"), in_net)
        sch.wire((sx - 60, 60), mn_inv.pin("G"), in_net)
        if k == 0:
            sch.label(in_net, (sx - 60, 0))

        # Inverter output -> out_net & cap, and direct horizontal wire to next stage
        sch.wire(mp_inv.pin("D"), mn_inv.pin("D"), out_net)
        sch.route_hv((sx + 20, 0), cap.pin("c0"), out_net)
        if k < 4:
            next_sx = 680 + (k + 1) * 300
            sch.wire((sx + 140, 0), (next_sx - 60, 0), out_net)
            sch.wire((sx + 180, 0), (sx + 180, -20), out_net)
            sch.label(out_net, (sx + 180, -20), flip=1)
        else:
            sch.wire((sx + 140, 0), (sx + 140, -15), out_net)
            sch.label(out_net, (sx + 140, -15), flip=1)
        sch.wire(cap.pin("c1"), (sx + 140, 280), "VSS")

    # Shutdown reset clamp on n4 (forces n4=0 -> clk=0 when en=0 and starts ring asymmetrically)
    mn_rst = sch.add("sg13cmos5l_pr/sg13_lv_nmos.sym", 2220, 200, name="MN_RST", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_nmos")
    sch.wire(mn_rst.pin("S"), (2240, 280), "VSS")
    sch.wire(mn_rst.pin("B"), mn_rst.pin("S"), "VSS")
    sch.in_label("enb", mn_rst.pin("G"), dx=40)

    # Output squaring & gating buffer: n4 -> inv_1 -> inv_2 -> buf_4 -> clk
    xi1 = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym", 2240, -100, name="XBUF1", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    xi2 = sch.add("sg13cmos5l_stdcells/sg13cmos5l_inv_2.sym", 2400, -100, name="XBUF2", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    xb4 = sch.add("sg13cmos5l_stdcells/sg13cmos5l_buf_4.sym", 2560, -100, name="XBUF4", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_")
    sch.in_label("n4", xi1.pin("A"), dx=40)
    sch.wire((2160, -100), (2160, 140), "n4")
    sch.route_hv((2160, 140), mn_rst.pin("D"), "n4")
    sch.wire(xi1.pin("Y"), xi2.pin("A"), "c_1")
    sch.wire(xi2.pin("Y"), xb4.pin("A"), "c_2")
    sch.wire(xb4.pin("X"), (2660, -100), "clk")
    sch.pin("opin", "clk", (2660, -100))

    sch.write(out_dir / "cco_core.sch")
    return sym_pins


def build_osc_ring_cc() -> None:
    out_dir = ANALOG_DIR / "osc_ring_cc"
    out_dir.mkdir(parents=True, exist_ok=True)

    bias_pins = read_sym_pins(ANALOG_DIR / "bias" / "bias.sym")
    idac_pins = build_idac_8b(out_dir)
    cco_pins = build_cco_core(out_dir)

    trim_pins = [(f"trim{i}", "in") for i in range(7, -1, -1)]
    sym_pins = write_block_symbol(
        out_dir / "osc_ring_cc.sym",
        block_name="osc_ring_cc",
        left_pins=[("en", "in")] + trim_pins,
        right_pins=[("clk", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=200,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en"] + [f"trim{i}" for i in range(7, -1, -1)] + ["clk"],
    )

    # Top-level osc_ring_cc.sch connecting bias + idac_8b + cco_core
    sch = Schematic()
    sch.text("Ring Oscillator B (60 MHz Current-Controlled Oscillator = bias + idac_8b + cco_core)", 0, -340, scale=0.35)
    sch.title(0, 460)

    sch.pin("iopin", "VDD", (-200, -280))
    sch.pin("iopin", "VSS", (-200, 400))
    sch.pin("ipin", "en", (-200, 0))
    for idx, b in enumerate(range(7, -1, -1)):
        sch.pin("ipin", f"trim{b}", (-200, 60 + idx * 40))

    xb = sch.add("bias/bias.sym", 0, -80, custom_pins=bias_pins, name="XBIAS")
    xdac = sch.add("osc_ring_cc/idac_8b.sym", 360, 40, custom_pins=idac_pins, name="XIDAC")
    xcco = sch.add("osc_ring_cc/cco_core.sym", 740, 0, custom_pins=cco_pins, name="XCCO")

    # Tie power & enable across all 3 sub-blocks cleanly via labels (en wired directly to XBIAS)
    for inst in (xb, xdac, xcco):
        p_vdd = inst.pin("VDD")
        sch.wire((p_vdd[0], p_vdd[1] - 20), p_vdd, "VDD")
        sch.label("VDD", (p_vdd[0], p_vdd[1] - 20))
        p_vss = inst.pin("VSS")
        sch.wire(p_vss, (p_vss[0], p_vss[1] + 20), "VSS")
        sch.label("VSS", (p_vss[0], p_vss[1] + 20))

    sch.wire((-200, 0), (-150, 0), "en")
    sch.route_vh((-150, 0), xb.pin("en"), "en")
    for inst in (xdac, xcco):
        p_en = inst.pin("en")
        sch.wire((p_en[0] - 20, p_en[1]), p_en, "en")
        sch.label("en", (p_en[0] - 20, p_en[1]))

    # Bias -> IDAC (direct orthogonal wire)
    p_vn_b = xb.pin("vnbias")
    p_vn_d = xdac.pin("vnbias")
    sch.wire(p_vn_b, (180, p_vn_b[1]), "vnbias")
    sch.wire((180, p_vn_b[1]), (180, p_vn_d[1]), "vnbias")
    sch.wire((180, p_vn_d[1]), p_vn_d, "vnbias")
    sch.wire((180, p_vn_d[1]), (180, p_vn_d[1] - 20), "vnbias")
    sch.label("vnbias", (180, p_vn_d[1] - 20), flip=1)

    # Leave unused bias outputs explicitly marked noconn directly on pins
    for unused in ("vpbias", "ibias_out"):
        p = xb.pin(unused)
        sch.add("devices/noconn.sym", p[0], p[1], name=f"nc_{unused}")

    # Trim bits -> IDAC
    for b in range(8):
        p = xdac.pin(f"trim{b}")
        sch.wire((p[0] - 20, p[1]), p, f"trim{b}")
        sch.label(f"trim{b}", (p[0] - 20, p[1]))

    # IDAC -> CCO (direct orthogonal wire with clean tap label)
    p_ic_d = xdac.pin("ictrl")
    p_ic_c = xcco.pin("ictrl")
    sch.route_hv(p_ic_d, p_ic_c, "ictrl")
    sch.wire((550, p_ic_d[1]), (550, p_ic_d[1] - 20), "ictrl")
    sch.label("ictrl", (550, p_ic_d[1] - 20), flip=1)

    # CCO -> clk
    sch.wire(xcco.pin("clk"), (xcco.pin("clk")[0] + 60, xcco.pin("clk")[1]), "clk")
    sch.pin("opin", "clk", (xcco.pin("clk")[0] + 60, xcco.pin("clk")[1]))

    sch.write(out_dir / "osc_ring_cc.sch")

    # Testbench: tb_osc_ring_cc.sch
    tb = Schematic()
    tb.text("Testbench: Ring Oscillator B (60 MHz Current-Controlled)", 0, -320, scale=0.35)
    tb.title(0, 460)

    xosc = tb.add("osc_ring_cc/osc_ring_cc.sym", 280, 0, custom_pins=sym_pins, name="XOSC")

    vdd_src = tb.add("devices/vsource.sym", -180, -140, name="Vdd", value="1.2")
    tb.wire(vdd_src.pin("m"), (-180, -80), "GND")
    tb.add("devices/gnd.sym", -180, -80, name="g1", lab="GND")
    tb.wire(vdd_src.pin("p"), (-180, -200), "VDD")
    tb.label("VDD", (-180, -200))

    ven_src = tb.add("devices/vsource.sym", -80, -140, name="Ven", value="1.2")
    tb.wire(ven_src.pin("m"), (-80, -80), "GND")
    tb.add("devices/gnd.sym", -80, -80, name="g2", lab="GND")
    tb.wire(ven_src.pin("p"), (-80, -200), "en")
    tb.label("en", (-80, -200))

    for i in range(8):
        vx = -220 + i * 120
        vy = 320
        val = "1.2" if i == 7 else "0"
        vs = tb.add("devices/vsource.sym", vx, vy, name=f"Vtrim{i}", value=val)
        tb.wire(vs.pin("m"), (vx, vy + 40), "GND")
        tb.add("devices/gnd.sym", vx, vy + 40, name=f"gt{i}", lab="GND")
        tb.wire(vs.pin("p"), (vx, vy - 40), f"trim{i}")
        tb.label(f"trim{i}", (vx, vy - 40))

    tb.wire(xosc.pin("VDD"), (xosc.pin("VDD")[0], xosc.pin("VDD")[1] - 20), "VDD")
    tb.label("VDD", (xosc.pin("VDD")[0], xosc.pin("VDD")[1] - 20))
    tb.wire(xosc.pin("VSS"), (xosc.pin("VSS")[0], xosc.pin("VSS")[1] + 20), "GND")
    tb.add("devices/gnd.sym", xosc.pin("VSS")[0], xosc.pin("VSS")[1] + 20, name="g_vss", lab="GND")

    for pname in ["en"] + [f"trim{i}" for i in range(7, -1, -1)]:
        p = xosc.pin(pname)
        tb.wire((p[0] - 40, p[1]), p, pname)
        tb.label(pname, (p[0] - 40, p[1]))

    cload = tb.add("devices/capa.sym", 540, 90, name="Cload", value="50f", m="1")
    tb.out_label("clk", xosc.pin("clk"), dx=40)
    tb.route_vh((xosc.pin("clk")[0] + 40, xosc.pin("clk")[1]), cload.pin("p"), "clk")
    tb.wire(cload.pin("m"), (540, 150), "GND")
    tb.add("devices/gnd.sym", 540, 150, name="g_cload", lab="GND")

    tb.add(
        "devices/code_shown.sym", -220, -300,
        name="SPICE_MODELS",
        only_toplevel="true",
        value=".options temp=25\n.lib cornerMOSlv.lib mos_tt\n.lib cornerRES.lib res_typ\n.lib cornerCAP.lib cap_typ\n.include sg13cmos5l_stdcell.spice\n",
    )

    tb.write(out_dir / "tb_osc_ring_cc.sch")
    print("Generated analog/osc_ring_cc/{idac_8b,cco_core,osc_ring_cc,tb_osc_ring_cc}")


if __name__ == "__main__":
    build_osc_ring_cc()
