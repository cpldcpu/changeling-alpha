v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {Testbench: 100 kHz Relaxation Oscillator (analog/osc_relax)} 0 -240 0 0 0.35 0.35 {layer=3}
N -120 -50 -120 -20 {lab=GND}
N -120 -110 -120 -140 {lab=VDD}
N -20 90 -20 120 {lab=GND}
N -20 30 -20 0 {lab=en}
N -20 0 120 0 {lab=en}
N 120 0 140 0 {}
N 260 -60 260 -100 {lab=VDD}
N 260 60 260 100 {lab=GND}
N 380 0 400 0 {}
N 400 0 540 0 {lab=clk_slow}
N 540 0 540 10 {lab=clk_slow}
N 540 70 540 100 {lab=GND}
C {devices/title.sym} 0 460 0 0 {name=title1
author=changeling-alpha}
C {osc_relax/osc_relax.sym} 260 0 0 0 {name=XOSC}
C {devices/vsource.sym} -120 -80 0 0 {name=Vdd
value=1.2}
C {devices/gnd.sym} -120 -20 0 0 {name=g1
lab=GND}
C {devices/lab_pin.sym} -120 -140 0 0 {name=l1
lab=VDD}
C {devices/vsource.sym} -20 60 0 0 {name=Ven
value=1.2}
C {devices/gnd.sym} -20 120 0 0 {name=g2
lab=GND}
C {devices/lab_pin.sym} 120 0 0 0 {name=l2
lab=en}
C {devices/lab_pin.sym} 260 -100 0 0 {name=l3
lab=VDD}
C {devices/gnd.sym} 260 100 0 0 {name=g3
lab=GND}
C {devices/capa.sym} 540 40 0 0 {name=Cload
value=50f
m=1}
C {devices/lab_pin.sym} 400 0 0 1 {name=l4
lab=clk_slow}
C {devices/gnd.sym} 540 100 0 0 {name=g4
lab=GND}
C {devices/code_shown.sym} -120 200 0 0 {name=SPICE_MODELS
only_toplevel=true
value=".options temp=25
.lib cornerMOSlv.lib mos_tt
.lib cornerMOShv.lib mos_tt
.lib cornerRES.lib res_typ
.lib cornerCAP.lib cap_typ
.include sg13cmos5l_stdcell.spice
"}
