v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {Testbench: Ring Oscillator A (60 MHz Stdcell Macro)} 100 -420 0 0 0.35 0.35 {layer=3}
N -320 -110 -320 -80 {lab=GND}
N -320 -170 -320 -200 {lab=VDD}
N -180 -110 -180 -80 {lab=GND}
N -180 -170 -180 -200 {lab=en}
N -360 370 -360 380 {lab=GND}
N -360 310 -360 300 {lab=trim0}
N -240 370 -240 380 {lab=GND}
N -240 310 -240 300 {lab=trim1}
N -120 370 -120 380 {lab=GND}
N -120 310 -120 300 {lab=trim2}
N 0 370 0 380 {lab=GND}
N 0 310 0 300 {lab=trim3}
N 120 370 120 380 {lab=GND}
N 120 310 120 300 {lab=trim4}
N 240 370 240 380 {lab=GND}
N 240 310 240 300 {lab=trim5}
N 360 370 360 380 {lab=GND}
N 360 310 360 300 {lab=trim6}
N 480 370 480 380 {lab=GND}
N 480 310 480 300 {lab=trim7}
N 280 -220 280 -240 {lab=VDD}
N 280 220 280 240 {lab=GND}
N 120 -160 160 -160 {}
N 120 -120 160 -120 {}
N 120 -80 160 -80 {}
N 120 -40 160 -40 {}
N 120 0 160 0 {}
N 120 40 160 40 {}
N 120 80 160 80 {}
N 120 120 160 120 {}
N 120 160 160 160 {}
N 400 0 440 0 {}
N 420 0 420 50 {lab=clk}
N 420 50 560 50 {lab=clk}
N 560 110 560 140 {lab=GND}
C {devices/title.sym} 0 520 0 0 {name=title1
author=changeling-alpha}
C {osc_ring_std/osc_ring_std.sym} 280 0 0 0 {name=XOSC}
C {devices/vsource.sym} -320 -140 0 0 {name=Vdd
value=1.2}
C {devices/gnd.sym} -320 -80 0 0 {name=g1
lab=GND}
C {devices/lab_pin.sym} -320 -200 0 0 {name=l1
lab=VDD}
C {devices/vsource.sym} -180 -140 0 0 {name=Ven
value=1.2}
C {devices/gnd.sym} -180 -80 0 0 {name=g2
lab=GND}
C {devices/lab_pin.sym} -180 -200 0 0 {name=l2
lab=en}
C {devices/vsource.sym} -360 340 0 0 {name=Vtrim0
value=0}
C {devices/gnd.sym} -360 380 0 0 {name=gt0
lab=GND}
C {devices/lab_pin.sym} -360 300 0 0 {name=l3
lab=trim0}
C {devices/vsource.sym} -240 340 0 0 {name=Vtrim1
value=0}
C {devices/gnd.sym} -240 380 0 0 {name=gt1
lab=GND}
C {devices/lab_pin.sym} -240 300 0 0 {name=l4
lab=trim1}
C {devices/vsource.sym} -120 340 0 0 {name=Vtrim2
value=0}
C {devices/gnd.sym} -120 380 0 0 {name=gt2
lab=GND}
C {devices/lab_pin.sym} -120 300 0 0 {name=l5
lab=trim2}
C {devices/vsource.sym} 0 340 0 0 {name=Vtrim3
value=0}
C {devices/gnd.sym} 0 380 0 0 {name=gt3
lab=GND}
C {devices/lab_pin.sym} 0 300 0 0 {name=l6
lab=trim3}
C {devices/vsource.sym} 120 340 0 0 {name=Vtrim4
value=0}
C {devices/gnd.sym} 120 380 0 0 {name=gt4
lab=GND}
C {devices/lab_pin.sym} 120 300 0 0 {name=l7
lab=trim4}
C {devices/vsource.sym} 240 340 0 0 {name=Vtrim5
value=0}
C {devices/gnd.sym} 240 380 0 0 {name=gt5
lab=GND}
C {devices/lab_pin.sym} 240 300 0 0 {name=l8
lab=trim5}
C {devices/vsource.sym} 360 340 0 0 {name=Vtrim6
value=0}
C {devices/gnd.sym} 360 380 0 0 {name=gt6
lab=GND}
C {devices/lab_pin.sym} 360 300 0 0 {name=l9
lab=trim6}
C {devices/vsource.sym} 480 340 0 0 {name=Vtrim7
value=1.2}
C {devices/gnd.sym} 480 380 0 0 {name=gt7
lab=GND}
C {devices/lab_pin.sym} 480 300 0 0 {name=l10
lab=trim7}
C {devices/lab_pin.sym} 280 -240 0 0 {name=l11
lab=VDD}
C {devices/gnd.sym} 280 240 0 0 {name=g_vss
lab=GND}
C {devices/lab_pin.sym} 120 -160 0 0 {name=l12
lab=en}
C {devices/lab_pin.sym} 120 -120 0 0 {name=l13
lab=trim7}
C {devices/lab_pin.sym} 120 -80 0 0 {name=l14
lab=trim6}
C {devices/lab_pin.sym} 120 -40 0 0 {name=l15
lab=trim5}
C {devices/lab_pin.sym} 120 0 0 0 {name=l16
lab=trim4}
C {devices/lab_pin.sym} 120 40 0 0 {name=l17
lab=trim3}
C {devices/lab_pin.sym} 120 80 0 0 {name=l18
lab=trim2}
C {devices/lab_pin.sym} 120 120 0 0 {name=l19
lab=trim1}
C {devices/lab_pin.sym} 120 160 0 0 {name=l20
lab=trim0}
C {devices/capa.sym} 560 80 0 0 {name=Cload
value=50f
m=1}
C {devices/lab_pin.sym} 440 0 0 1 {name=l21
lab=clk}
C {devices/gnd.sym} 560 140 0 0 {name=g_cload
lab=GND}
C {devices/code_shown.sym} -360 -350 0 0 {name=SPICE_MODELS
only_toplevel=true
value=".options temp=25
.lib cornerMOSlv.lib mos_tt
.include sg13cmos5l_stdcell.spice
"}
