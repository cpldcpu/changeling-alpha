v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {Testbench: Self-Biased Reference (analog/bias)} 0 -240 0 0 0.35 0.35 {layer=3}
N -120 -50 -120 -20 {lab=GND}
N -120 -110 -120 -140 {lab=VDD}
N 0 110 0 140 {lab=GND}
N 0 50 120 50 {lab=en}
N 120 50 120 0 {lab=en}
N 120 0 160 0 {lab=en}
N 100 0 120 0 {}
N 280 -100 280 -140 {lab=VDD}
N 280 100 280 140 {lab=GND}
N 400 -40 440 -40 {}
N 400 0 440 0 {}
N 400 40 420 40 {}
N 420 40 420 90 {lab=ibias_out}
N 420 90 540 90 {lab=ibias_out}
N 540 150 540 180 {lab=GND}
C {devices/title.sym} 0 340 0 0 {name=title1
author=changeling-alpha}
C {bias/bias.sym} 280 0 0 0 {name=XBIAS}
C {devices/vsource.sym} -120 -80 0 0 {name=Vdd
value=1.2}
C {devices/vsource.sym} 0 80 0 0 {name=Ven
value=1.2}
C {devices/vsource.sym} 540 120 0 0 {name=Vload
value=0.6}
C {devices/gnd.sym} -120 -20 0 0 {name=g1
lab=GND}
C {devices/lab_pin.sym} -120 -140 0 0 {name=l1
lab=VDD}
C {devices/gnd.sym} 0 140 0 0 {name=g2
lab=GND}
C {devices/lab_pin.sym} 100 0 0 0 {name=l2
lab=en}
C {devices/lab_pin.sym} 280 -140 0 0 {name=l3
lab=VDD}
C {devices/gnd.sym} 280 140 0 0 {name=g3
lab=GND}
C {devices/lab_pin.sym} 440 -40 0 1 {name=l4
lab=vpbias}
C {devices/lab_pin.sym} 440 0 0 1 {name=l5
lab=vnbias}
C {devices/lab_pin.sym} 420 40 0 1 {name=l6
lab=ibias_out}
C {devices/gnd.sym} 540 180 0 0 {name=g4
lab=GND}
C {devices/code_shown.sym} -120 200 0 0 {name=SPICE_PARAM
only_toplevel=true
value=".options temp=25
.lib cornerMOSlv.lib mos_tt
.lib cornerRES.lib res_typ
"}
