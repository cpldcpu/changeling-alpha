#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Generate clean xschem schematics and symbol for the self-biased current reference (analog/bias)."""

import sys
from pathlib import Path

ANALOG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALOG_DIR / "scripts"))

from xschem_builder import Schematic, write_block_symbol


def build_bias() -> None:
    out_dir = ANALOG_DIR / "bias"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Symbol: bias.sym
    sym_pins = write_block_symbol(
        out_dir / "bias.sym",
        block_name="bias",
        left_pins=[("en", "in")],
        right_pins=[("vpbias", "out"), ("vnbias", "out"), ("ibias_out", "out")],
        top_pins=[("VDD", "inout")],
        bottom_pins=[("VSS", "inout")],
        width=180,
        pin_pitch=40,
        spice_order=["VDD", "VSS", "en", "vpbias", "vnbias", "ibias_out"],
    )

    # 2. Core schematic: bias.sch
    sch = Schematic()
    sch.text("Self-Biased Beta-Multiplier Reference (0.5 uA nominal, 1.2 V CMOS)", 0, -340, scale=0.35)
    sch.title(0, 380)

    # Power & GND rails (VDD at y=-280, VSS at y=280)
    sch.pin("iopin", "VDD", (0, -280))
    sch.pin("iopin", "VSS", (0, 280))
    sch.wire((0, -280), (1740, -280), "VDD")
    sch.wire((0, 280), (1740, 280), "VSS")

    # ---- Enable inverter: en -> enb ----
    sch.pin("ipin", "en", (-40, 0))
    sch.wire((-40, 0), (40, 0), "en")
    mp_en = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 100, -80,
        name="MEN_P", w="0.5u", l="0.5u", ng="1", m="1", model="sg13_lv_pmos",
    )
    mn_en = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 100, 80,
        name="MEN_N", w="0.25u", l="0.5u", ng="1", m="1", model="sg13_lv_nmos",
    )
    sch.wire((40, -80), (40, 80), "en")
    sch.wire((40, -80), mp_en.pin("G"), "en")
    sch.wire((40, 80), mn_en.pin("G"), "en")
    sch.wire(mp_en.pin("S"), (120, -280), "VDD")
    sch.wire(mp_en.pin("B"), mp_en.pin("S"))
    sch.wire(mn_en.pin("S"), (120, 280), "VSS")
    sch.wire(mn_en.pin("B"), mn_en.pin("S"))
    sch.wire(mp_en.pin("D"), mn_en.pin("D"), "enb")

    # ---- Start-up circuit (< 100 nA steady-state, unconditional startup, gated by en) ----
    msu_en = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 380, -200,
        name="MSU_EN", w="0.3u", l="1.0u", ng="1", m="1", model="sg13_lv_pmos",
    )
    msu_p1 = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 380, -100,
        name="MSU_P1", w="0.15u", l="10u", ng="1", m="1", model="sg13_lv_pmos",
    )
    msu_p2 = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 380, 0,
        name="MSU_P2", w="0.15u", l="10u", ng="1", m="1", model="sg13_lv_pmos",
    )
    msu_n = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 380, 120,
        name="MSU_N", w="4.0u", l="0.5u", ng="1", m="1", model="sg13_lv_nmos",
    )
    sch.wire(msu_en.pin("S"), (400, -280), "VDD")
    sch.wire(msu_en.pin("B"), msu_en.pin("S"))
    # Route MSU_P1 and MSU_P2 bulk pins cleanly around parameter text to a vertical VDD rail at x=520
    sch.wire((520, -280), (520, -40), "VDD")
    for mdev, by in [(msu_p1, -100), (msu_p2, 0)]:
        bx, _ = mdev.pin("B")
        sch.wire((bx, by), (bx + 10, by), "VDD")
        sch.wire((bx + 10, by), (bx + 10, by - 40), "VDD")
        sch.wire((bx + 10, by - 40), (520, by - 40), "VDD")
    sch.wire((120, 0), (260, 0), "enb")
    sch.wire((260, 0), (260, -200), "enb")
    sch.wire((260, -200), msu_en.pin("G"), "enb")
    sch.label("enb", (260, -200), flip=0)
    sch.in_label("VSS", msu_p1.pin("G"), dx=40)
    sch.in_label("VSS", msu_p2.pin("G"), dx=40)
    sch.wire(msu_en.pin("D"), msu_p1.pin("S"), "su_s0")
    sch.wire(msu_p1.pin("D"), msu_p2.pin("S"), "su_s1")
    sch.wire(msu_p2.pin("D"), msu_n.pin("D"), "su_mid")
    sch.in_label("vnbias", msu_n.pin("G"), dx=40)
    sch.wire(msu_n.pin("S"), (400, 280), "VSS")
    sch.wire(msu_n.pin("B"), msu_n.pin("S"))

    # Injection NMOS: pulls vpbias down while vnbias == 0 and en == 1
    msu_inj = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 660, 120,
        name="MSU_INJ", w="0.5u", l="1.0u", ng="1", m="1", model="sg13_lv_nmos",
    )
    sch.wire((400, 60), (600, 60), "su_mid")
    sch.route_vh((600, 60), msu_inj.pin("G"), "su_mid")
    sch.wire(msu_inj.pin("S"), (680, 280), "VSS")
    sch.wire(msu_inj.pin("B"), msu_inj.pin("S"))
    sch.wire(msu_inj.pin("D"), (680, 40), "vpbias")
    sch.wire((680, 40), (740, 40), "vpbias")
    sch.wire((740, 40), (740, -40), "vpbias")
    sch.wire((740, -40), (1180, -40), "vpbias")

    # ---- Beta-multiplier core ----
    # High-ro L=4u PMOS mirror + moderate-inversion L=4u NMOS (vnbias ~ 0.45-0.55V) + K=4 + R_BIAS ~ 220 kOhm
    mp1 = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 940, -120, flip=1,
        name="MP1", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos",
    )
    mn1 = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 940, 80, flip=1,
        name="MN1", w="0.3u", l="4.0u", ng="1", m="1", model="sg13_lv_nmos",
    )
    mp2 = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 1240, -120,
        name="MP2", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos",
    )
    mn2 = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 1240, 40,
        name="MN2", w="0.3u", l="4.0u", ng="1", m="4", model="sg13_lv_nmos",
    )
    rbias = sch.add(
        "sg13cmos5l_pr/rppd.sym", 1260, 180,
        name="R_BIAS", w="0.5e-6", l="20.0e-6", b="19", m="1", model="rppd", body="VSS", value="108k",
    )

    sch.wire(mp1.pin("S"), (920, -280), "VDD")
    sch.wire(mp1.pin("B"), mp1.pin("S"))
    sch.wire(mn1.pin("S"), (920, 280), "VSS")
    sch.wire(mn1.pin("B"), mn1.pin("S"))

    sch.wire(mp2.pin("S"), (1260, -280), "VDD")
    sch.wire(mp2.pin("B"), mp2.pin("S"))
    # Route MN2 bulk cleanly around parameter text to clear space below MN2
    mn2_bx, mn2_by = mn2.pin("B")
    sch.wire((mn2_bx, mn2_by), (mn2_bx + 10, mn2_by), "VSS")
    sch.wire((mn2_bx + 10, mn2_by), (mn2_bx + 10, 100), "VSS")
    sch.out_label("VSS", (mn2_bx + 10, 100), dx=110)

    sch.wire(mp1.pin("D"), mn1.pin("D"), "vnbias")
    sch.wire((920, 0), (980, 0), "vnbias")
    sch.route_vh((980, 0), mn1.pin("G"), "vnbias")
    sch.wire((980, 40), mn2.pin("G"), "vnbias")

    sch.wire(mp2.pin("D"), mn2.pin("D"), "vpbias")
    sch.wire((1180, -40), (1260, -40), "vpbias")
    sch.wire((1140, -40), (1140, -60), "vpbias")
    sch.label("vpbias", (1140, -60), flip=0)
    sch.route_vh((1180, -40), mp2.pin("G"), "vpbias")
    sch.wire((1180, -120), mp1.pin("G"), "vpbias")

    sch.wire(mn2.pin("S"), rbias.pin("P"), "n_res")
    sch.wire(rbias.pin("M"), (1260, 280), "VSS")

    # ---- Enable shutdown devices on vpbias and vnbias ----
    mp_off = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 1040, -200,
        name="MP_OFF", w="1.0u", l="0.5u", ng="1", m="1", model="sg13_lv_pmos",
    )
    sch.wire(mp_off.pin("S"), (1060, -280), "VDD")
    sch.wire(mp_off.pin("B"), mp_off.pin("S"))
    sch.in_label("en", mp_off.pin("G"), dx=30)
    sch.wire(mp_off.pin("D"), (1060, -120), "vpbias")

    mn_off = sch.add(
        "sg13cmos5l_pr/sg13_lv_nmos.sym", 1040, 200,
        name="MN_OFF", w="1.0u", l="0.5u", ng="1", m="1", model="sg13_lv_nmos",
    )
    sch.wire(mn_off.pin("S"), (1060, 280), "VSS")
    sch.wire(mn_off.pin("B"), mn_off.pin("S"))
    sch.in_label("enb", mn_off.pin("G"), dx=30)
    sch.wire(mn_off.pin("D"), (1060, 40), "vnbias")

    # ---- Output mirror branch -> ibias_out & output pins ----
    mp_out = sch.add(
        "sg13cmos5l_pr/sg13_lv_pmos.sym", 1540, -120,
        name="MP_OUT", w="1.0u", l="4.0u", ng="1", m="1", model="sg13_lv_pmos",
    )
    sch.wire(mp_out.pin("S"), (1560, -280), "VDD")
    sch.wire(mp_out.pin("B"), mp_out.pin("S"))

    sch.wire((1260, -40), (1480, -40), "vpbias")
    sch.wire((1480, -40), (1480, -120), "vpbias")
    sch.wire((1480, -120), mp_out.pin("G"), "vpbias")
    sch.wire((1480, -40), (1740, -40), "vpbias")
    sch.pin("opin", "vpbias", (1740, -40))

    sch.wire((980, 0), (1740, 0), "vnbias")
    sch.wire((1380, 0), (1380, -20), "vnbias")
    sch.label("vnbias", (1380, -20), flip=1)
    sch.pin("opin", "vnbias", (1740, 0))

    sch.route_vh(mp_out.pin("D"), (1740, 40), "ibias_out")
    sch.pin("opin", "ibias_out", (1740, 40))

    sch.write(out_dir / "bias.sch")

    # 3. Testbench schematic: tb_bias.sch
    tb = Schematic()
    tb.text("Testbench: Self-Biased Reference (analog/bias)", 0, -240, scale=0.35)
    tb.title(0, 340)

    xb = tb.add("bias/bias.sym", 280, 0, custom_pins=sym_pins, name="XBIAS")

    vdd_src = tb.add("devices/vsource.sym", -120, -80, name="Vdd", value="1.2")
    ven_src = tb.add("devices/vsource.sym", 0, 80, name="Ven", value="1.2")
    vload = tb.add("devices/vsource.sym", 540, 120, name="Vload", value="0.6")

    tb.wire(vdd_src.pin("m"), (-120, -20), "GND")
    tb.add("devices/gnd.sym", -120, -20, name="g1", lab="GND")
    tb.wire(vdd_src.pin("p"), (-120, -140), "VDD")
    tb.label("VDD", (-120, -140))

    tb.wire(ven_src.pin("m"), (0, 140), "GND")
    tb.add("devices/gnd.sym", 0, 140, name="g2", lab="GND")
    tb.route_hv(ven_src.pin("p"), (120, 0), "en")
    tb.wire((120, 0), xb.pin("en"), "en")
    tb.in_label("en", (120, 0), dx=20)

    tb.wire(xb.pin("VDD"), (xb.pin("VDD")[0], xb.pin("VDD")[1] - 40), "VDD")
    tb.label("VDD", (xb.pin("VDD")[0], xb.pin("VDD")[1] - 40))
    tb.wire(xb.pin("VSS"), (xb.pin("VSS")[0], xb.pin("VSS")[1] + 40), "GND")
    tb.add("devices/gnd.sym", xb.pin("VSS")[0], xb.pin("VSS")[1] + 40, name="g3", lab="GND")

    tb.out_label("vpbias", xb.pin("vpbias"), dx=40)
    tb.out_label("vnbias", xb.pin("vnbias"), dx=40)

    tb.out_label("ibias_out", xb.pin("ibias_out"), dx=20)
    tb.route_vh((xb.pin("ibias_out")[0] + 20, xb.pin("ibias_out")[1]), vload.pin("p"), "ibias_out")
    tb.wire(vload.pin("m"), (540, 180), "GND")
    tb.add("devices/gnd.sym", 540, 180, name="g4", lab="GND")

    tb.add(
        "devices/code_shown.sym", -120, 200,
        name="SPICE_PARAM",
        only_toplevel="true",
        value=".options temp=25\n.lib cornerMOSlv.lib mos_tt\n.lib cornerRES.lib res_typ\n",
    )

    tb.write(out_dir / "tb_bias.sch")
    print("Generated analog/bias/{bias.sym,bias.sch,tb_bias.sch}")


if __name__ == "__main__":
    build_bias()
