#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Generate clean hierarchical xschem schematics and symbols for Ring Oscillator A (analog/osc_ring_std)."""

import sys
from pathlib import Path

ANALOG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALOG_DIR / "scripts"))

from xschem_builder import Schematic, write_block_symbol


def wire_mux_sel(sch: Schematic, mux, sel_net: str) -> None:
    """Connect mux S pin straight down to a label so incoming A0/A1 wires never cross it."""
    sx, sy = mux.pin("S")
    sch.wire((sx, sy), (sx, sy + 20), sel_net)
    sch.label(sel_net, (sx, sy + 20), flip=1)


def build_tap_chain_16(out_dir: Path) -> dict[str, tuple[float, float]]:
    sym_pins = write_block_symbol(
        out_dir / "tap_chain_16.sym",
        block_name="tap_chain_16",
        left_pins=[("in", "in"), ("s3", "in"), ("s2", "in"), ("s1", "in"), ("s0", "in")],
        right_pins=[("out_chain", "out"), ("out_mux", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=200,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "in", "s3", "s2", "s1", "s0", "out_chain", "out_mux"],
    )

    sch = Schematic()
    sch.text("16-Tap Standard-Cell Delay Slice (higher s[3:0] -> shorter delay)", 250, -310, scale=0.35)
    sch.title(0, 1280)

    y_row0 = -200
    y_row1 = 0
    dly_pitch = 220

    sch.pin("iopin", "VDD", (-140, -100))
    sch.pin("iopin", "VSS", (-140, -60))
    sch.pin("ipin", "in", (-140, y_row0))
    for i, sname in enumerate(["s3", "s2", "s1", "s0"]):
        sch.pin("ipin", sname, (-140, 100 + i * 40))

    # Delay chain arranged in 2 rows of 8 with generous pitch so model names never collide
    prev_pt = (-140, y_row0)
    for i in range(16):
        row = i // 8
        col = i % 8
        cx = 40 + col * dly_pitch
        cy = y_row0 if row == 0 else y_row1
        cell = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_dlygate4sd1_1.sym",
            cx, cy, name=f"XDLY{i}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        cur_net = "in" if i == 0 else f"t{i}"
        if i == 8:
            # Wrap neatly from end of row 0 around to start of row 1
            y_mid = (y_row0 + y_row1) // 2
            x_right = prev_pt[0] + 60
            x_left = -40
            sch.wire(prev_pt, (x_right, y_row0), cur_net)
            sch.wire((x_right, y_row0), (x_right, y_mid), cur_net)
            sch.wire((x_right, y_mid), (x_left, y_mid), cur_net)
            sch.wire((x_left, y_mid), (x_left, y_row1), cur_net)
            sch.wire((x_left, y_row1), cell.pin("A"), cur_net)
        else:
            sch.wire(prev_pt, cell.pin("A"), cur_net)

        if i < 15:
            next_net = f"t{i+1}"
            if i == 7:
                end_pt = (cx + 160, cy)
                tap_x = cx + 150
            else:
                end_pt = (cx + dly_pitch - 40, cy)
                tap_x = cx + 110
            sch.wire(cell.pin("X"), end_pt, next_net)
            sch.wire((tap_x, cy), (tap_x, cy - 60), next_net)
            sch.label(next_net, (tap_x, cy - 60), flip=1)
            prev_pt = end_pt
        else:
            out_pt = (cx + 120, cy)
            sch.wire(cell.pin("X"), out_pt, "out_chain")
            sch.pin("opin", "out_chain", out_pt)

    # Level 0: 8 mux2_1 controlled by s0 (reversed order: s=15 picks in [tap 0], s=0 picks t15)
    l0_outs = []
    for k in range(8):
        idx_a0 = 15 - (2 * k)
        idx_a1 = 15 - (2 * k + 1)
        na0 = "in" if idx_a0 == 0 else f"t{idx_a0}"
        na1 = "in" if idx_a1 == 0 else f"t{idx_a1}"
        mx = 200
        my = 160 + k * 140
        m = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym",
            mx, my, name=f"XM0_{k}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        sch.wire((mx - 80, my - 20), m.pin("A0"), na0)
        sch.label(na0, (mx - 80, my - 20))
        sch.wire((mx - 80, my + 20), m.pin("A1"), na1)
        sch.label(na1, (mx - 80, my + 20))
        wire_mux_sel(sch, m, "s0")
        out_net = f"m0_{k}"
        sch.wire(m.pin("X"), (mx + 60, my), out_net)
        l0_outs.append(((mx + 60, my), out_net))

    # Level 1: 4 mux2_1 controlled by s1 (jog at mx-80 so wires clear S pin at mx-40)
    l1_outs = []
    for k in range(4):
        mx = 540
        my = 230 + k * 280
        m = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym",
            mx, my, name=f"XM1_{k}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        p0, n0 = l0_outs[2 * k]
        p1, n1 = l0_outs[2 * k + 1]
        a0, a1 = m.pin("A0"), m.pin("A1")
        sch.route_hv(p0, (a0[0] - 40, a0[1]), n0)
        sch.wire((a0[0] - 40, a0[1]), a0, n0)
        sch.route_hv(p1, (a1[0] - 20, a1[1]), n1)
        sch.wire((a1[0] - 20, a1[1]), a1, n1)
        wire_mux_sel(sch, m, "s1")
        out_net = f"m1_{k}"
        sch.wire(m.pin("X"), (mx + 60, my), out_net)
        l1_outs.append(((mx + 60, my), out_net))

    # Level 2: 2 mux2_1 controlled by s2
    l2_outs = []
    for k in range(2):
        mx = 880
        my = 370 + k * 560
        m = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym",
            mx, my, name=f"XM2_{k}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        p0, n0 = l1_outs[2 * k]
        p1, n1 = l1_outs[2 * k + 1]
        a0, a1 = m.pin("A0"), m.pin("A1")
        sch.route_hv(p0, (a0[0] - 40, a0[1]), n0)
        sch.wire((a0[0] - 40, a0[1]), a0, n0)
        sch.route_hv(p1, (a1[0] - 20, a1[1]), n1)
        sch.wire((a1[0] - 20, a1[1]), a1, n1)
        wire_mux_sel(sch, m, "s2")
        out_net = f"m2_{k}"
        sch.wire(m.pin("X"), (mx + 60, my), out_net)
        l2_outs.append(((mx + 60, my), out_net))

    # Level 3: final 2:1 mux controlled by s3 -> out_mux
    mx, my = 1220, 650
    mf = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym",
        mx, my, name="XM3_0", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    a0, a1 = mf.pin("A0"), mf.pin("A1")
    sch.route_hv(l2_outs[0][0], (a0[0] - 40, a0[1]), l2_outs[0][1])
    sch.wire((a0[0] - 40, a0[1]), a0, l2_outs[0][1])
    sch.route_hv(l2_outs[1][0], (a1[0] - 20, a1[1]), l2_outs[1][1])
    sch.wire((a1[0] - 20, a1[1]), a1, l2_outs[1][1])
    wire_mux_sel(sch, mf, "s3")
    sch.wire(mf.pin("X"), (mx + 80, my), "out_mux")
    sch.pin("opin", "out_mux", (mx + 80, my))

    sch.write(out_dir / "tap_chain_16.sch")
    return sym_pins


def build_osc_ring_std() -> None:
    out_dir = ANALOG_DIR / "osc_ring_std"
    out_dir.mkdir(parents=True, exist_ok=True)

    tap_pins = build_tap_chain_16(out_dir)

    trim_pins = [(f"trim{i}", "in") for i in range(7, -1, -1)]
    sym_pins = write_block_symbol(
        out_dir / "osc_ring_std.sym",
        block_name="osc_ring_std",
        left_pins=[("en", "in")] + trim_pins,
        right_pins=[("clk", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=200,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en"] + [f"trim{i}" for i in range(7, -1, -1)] + ["clk"],
    )

    sch = Schematic()
    sch.text("Ring Oscillator A (60 MHz Standard-Cell Tap-Selected Delay Line)", 0, -340, scale=0.35)
    sch.title(0, 1080)

    sch.pin("iopin", "VDD", (-220, -260))
    sch.pin("iopin", "VSS", (-220, -220))
    sch.pin("ipin", "en", (-220, 20))
    for idx, b in enumerate(range(7, -1, -1)):
        sch.pin("ipin", f"trim{b}", (-220, 100 + idx * 40))

    # 1. Loop NAND2 + Output Buffer (clk=0 when en=0)
    xnand = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_nand2_2.sym", 0, 0,
        name="XNAND", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    sch.in_label("loop_fb", xnand.pin("A"), dx=40)
    sch.in_label("en", xnand.pin("B"), dx=40)

    xout_inv = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_inv_2.sym", 220, -140,
        name="XOUT_INV", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    xout_buf = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_buf_4.sym", 360, -140,
        name="XOUT_BUF", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    sch.wire(xout_inv.pin("Y"), xout_buf.pin("A"), "clk_pre")
    sch.wire(xout_buf.pin("X"), (460, -140), "clk")
    sch.pin("opin", "clk", (460, -140))

    # 2. Fixed delay chain: 8 x sg13cmos5l_dlygate4sd3_1 (pitch 220 so model names never collide)
    prev_pt = xnand.pin("Y")
    prev_net = "n_nand"
    for i in range(8):
        dx = 220 + i * 220
        d = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_dlygate4sd3_1.sym", dx, 0,
            name=f"XFIX{i}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        sch.wire(prev_pt, d.pin("A"), prev_net)
        if i == 0:
            # Wire n_nand directly from XNAND->XFIX0 link up to XOUT_INV.A
            sch.route_vh((120, 0), xout_inv.pin("A"), "n_nand")
            sch.label("n_nand", (120, -70), flip=0)
        prev_net = f"fix_{i}" if i < 7 else "fix_out"
        prev_pt = (dx + 60, 0)
        sch.wire(d.pin("X"), prev_pt, prev_net)

    # 3. Fine half-tap interpolation on trim0
    xf_slow = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_dlygate4sd1_1.sym", 1980, -60,
        name="XFINE_SLOW", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    xf_fast = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_buf_1.sym", 1980, 60,
        name="XFINE_FAST", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    xm_fine = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym", 2200, 0,
        name="XMUX_FINE", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    sch.route_vh(prev_pt, xf_slow.pin("A"), "fix_out")
    sch.route_vh(prev_pt, xf_fast.pin("A"), "fix_out")
    sch.wire((1880, -60), (1880, -85), "fix_out")
    sch.label("fix_out", (1880, -85), flip=0)
    a0, a1 = xm_fine.pin("A0"), xm_fine.pin("A1")
    sch.route_hv(xf_slow.pin("X"), (a0[0] - 20, a0[1]), "fine_slow")
    sch.wire((a0[0] - 20, a0[1]), a0, "fine_slow")
    sch.route_hv(xf_fast.pin("X"), (a1[0] - 20, a1[1]), "fine_fast")
    sch.wire((a1[0] - 20, a1[1]), a1, "fine_fast")
    wire_mux_sel(sch, xm_fine, "trim0")
    sch.out_label("chain_0", xm_fine.pin("X"), dx=40)

    # 4. 8 cascaded tap_chain_16 slices (slice 7 at chain_0 [fastest], slice 0 at end [slowest])
    slice_insts = []
    for idx, sl in enumerate(range(7, -1, -1)):
        sx = 260 + (idx % 4) * 560
        sy = 300 + (idx // 4) * 400
        xs = sch.add(
            "osc_ring_std/tap_chain_16.sym", sx, sy,
            custom_pins=tap_pins, name=f"XSLICE{sl}",
        )
        slice_insts.append((idx, sl, sx, sy, xs))
        in_net = "chain_0" if idx == 0 else f"chain_{idx}"
        out_net = f"chain_{idx+1}" if idx < 7 else "chain_end"
        mux_net = f"smux_{sl}"

        sch.wire((xs.pin("VDD")[0], xs.pin("VDD")[1] - 20), xs.pin("VDD"), "VDD")
        sch.label("VDD", (xs.pin("VDD")[0], xs.pin("VDD")[1] - 20))
        sch.wire(xs.pin("VSS"), (xs.pin("VSS")[0], xs.pin("VSS")[1] + 20), "VSS")
        sch.label("VSS", (xs.pin("VSS")[0], xs.pin("VSS")[1] + 20))

        if idx == 0:
            sch.in_label(in_net, xs.pin("in"), dx=40)
        for b, pname in [(4, "s3"), (3, "s2"), (2, "s1"), (1, "s0")]:
            sch.in_label(f"trim{b}", xs.pin(pname), dx=40)

        if idx == 7:
            sch.out_label(out_net, xs.pin("out_chain"), dx=40)
            oc = xs.pin("out_chain")
            nc_pt = (oc[0] + 20, oc[1] - 20)
            sch.wire((oc[0] + 20, oc[1]), nc_pt, out_net)
            sch.add("devices/noconn.sym", nc_pt[0], nc_pt[1], name="nc_end")
        sch.out_label(mux_net, xs.pin("out_mux"), dx=40)

    # Wire consecutive tap_chain_16 slices directly (out_chain -> next slice in)
    for idx in range(7):
        _, _, sx, sy, xs = slice_insts[idx]
        _, _, _, _, xs_next = slice_insts[idx + 1]
        out_net = f"chain_{idx+1}"
        out_pt = xs.pin("out_chain")
        in_pt = xs_next.pin("in")
        if idx != 3:
            mid_x = sx + 220
            sch.wire(out_pt, (mid_x, out_pt[1]), out_net)
            sch.wire((mid_x, out_pt[1]), (mid_x, in_pt[1]), out_net)
            sch.wire((mid_x, in_pt[1]), in_pt, out_net)
            sch.wire((mid_x + 60, in_pt[1]), (mid_x + 60, in_pt[1] - 20), out_net)
            sch.label(out_net, (mid_x + 60, in_pt[1] - 20), flip=1)
        else:
            # Clean row-wrap bus between row 0 (XSLICE4) and row 1 (XSLICE3)
            y_wrap = 500
            sch.wire(out_pt, (out_pt[0] + 20, out_pt[1]), out_net)
            sch.wire((out_pt[0] + 20, out_pt[1]), (out_pt[0] + 20, y_wrap), out_net)
            sch.wire((out_pt[0] + 20, y_wrap), (in_pt[0] - 40, y_wrap), out_net)
            sch.wire((in_pt[0] - 40, y_wrap), (in_pt[0] - 40, in_pt[1]), out_net)
            sch.wire((in_pt[0] - 40, in_pt[1]), in_pt, out_net)
            sch.wire((1100, y_wrap), (1100, y_wrap - 20), out_net)
            sch.label(out_net, (1100, y_wrap - 20), flip=1)

    # 5. Final 8:1 mux tree controlled by trim[7:5] -> loop_fb
    s0_nets = []
    for k in range(4):
        mx, my = 2500, 220 + k * 140
        m = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym", mx, my,
            name=f"XFM0_{k}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        sch.in_label(f"smux_{2*k}", m.pin("A0"), dx=40)
        sch.in_label(f"smux_{2*k+1}", m.pin("A1"), dx=40)
        wire_mux_sel(sch, m, "trim5")
        onet = f"fm0_{k}"
        sch.wire(m.pin("X"), (mx + 60, my), onet)
        s0_nets.append(((mx + 60, my), onet))

    s1_nets = []
    for k in range(2):
        mx, my = 2780, 290 + k * 280
        m = sch.add(
            "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym", mx, my,
            name=f"XFM1_{k}", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
        )
        a0, a1 = m.pin("A0"), m.pin("A1")
        sch.route_hv(s0_nets[2 * k][0], (a0[0] - 40, a0[1]), s0_nets[2 * k][1])
        sch.wire((a0[0] - 40, a0[1]), a0, s0_nets[2 * k][1])
        sch.route_hv(s0_nets[2 * k + 1][0], (a1[0] - 20, a1[1]), s0_nets[2 * k + 1][1])
        sch.wire((a1[0] - 20, a1[1]), a1, s0_nets[2 * k + 1][1])
        wire_mux_sel(sch, m, "trim6")
        onet = f"fm1_{k}"
        sch.wire(m.pin("X"), (mx + 60, my), onet)
        s1_nets.append(((mx + 60, my), onet))

    mx, my = 3060, 430
    mtop = sch.add(
        "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym", mx, my,
        name="XFM2_0", VDD="VDD", VSS="VSS", prefix="sg13cmos5l_",
    )
    a0, a1 = mtop.pin("A0"), mtop.pin("A1")
    sch.route_hv(s1_nets[0][0], (a0[0] - 40, a0[1]), s1_nets[0][1])
    sch.wire((a0[0] - 40, a0[1]), a0, s1_nets[0][1])
    sch.route_hv(s1_nets[1][0], (a1[0] - 20, a1[1]), s1_nets[1][1])
    sch.wire((a1[0] - 20, a1[1]), a1, s1_nets[1][1])
    wire_mux_sel(sch, mtop, "trim7")
    sch.out_label("loop_fb", mtop.pin("X"), dx=40)

    sch.write(out_dir / "osc_ring_std.sch")

    # 6. Testbench: tb_osc_ring_std.sch
    tb = Schematic()
    tb.text("Testbench: Ring Oscillator A (60 MHz Stdcell Macro)", 100, -420, scale=0.35)
    tb.title(0, 520)

    xosc = tb.add("osc_ring_std/osc_ring_std.sym", 280, 0, custom_pins=sym_pins, name="XOSC")

    vdd_src = tb.add("devices/vsource.sym", -320, -140, name="Vdd", value="1.2")
    tb.wire(vdd_src.pin("m"), (-320, -80), "GND")
    tb.add("devices/gnd.sym", -320, -80, name="g1", lab="GND")
    tb.wire(vdd_src.pin("p"), (-320, -200), "VDD")
    tb.label("VDD", (-320, -200))

    ven_src = tb.add("devices/vsource.sym", -180, -140, name="Ven", value="1.2")
    tb.wire(ven_src.pin("m"), (-180, -80), "GND")
    tb.add("devices/gnd.sym", -180, -80, name="g2", lab="GND")
    tb.wire(ven_src.pin("p"), (-180, -200), "en")
    tb.label("en", (-180, -200))

    for i in range(8):
        vx = -360 + i * 120
        vy = 340
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
        tb.in_label(pname, xosc.pin(pname), dx=40)

    cload = tb.add("devices/capa.sym", 560, 80, name="Cload", value="50f", m="1")
    tb.out_label("clk", xosc.pin("clk"), dx=40)
    tb.route_vh((xosc.pin("clk")[0] + 20, xosc.pin("clk")[1]), cload.pin("p"), "clk")
    tb.wire(cload.pin("m"), (560, 140), "GND")
    tb.add("devices/gnd.sym", 560, 140, name="g_cload", lab="GND")

    tb.add(
        "devices/code_shown.sym", -360, -350,
        name="SPICE_MODELS",
        only_toplevel="true",
        value=".options temp=25\n.lib cornerMOSlv.lib mos_tt\n.include sg13cmos5l_stdcell.spice\n",
    )

    tb.write(out_dir / "tb_osc_ring_std.sch")
    print("Generated analog/osc_ring_std/{tap_chain_16,osc_ring_std,tb_osc_ring_std}")


if __name__ == "__main__":
    build_osc_ring_std()
