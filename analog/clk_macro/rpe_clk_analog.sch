v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {Unified Clock Macro (rpe_clk_analog = shared bias + osc_ring_cc + relax_core)} 0 -400 0 0 0.35 0.35 {layer=3}
N -360 -240 -260 -240 {lab=en_ring}
N -360 -200 -260 -200 {lab=en_relax}
N -140 -220 -80 -220 {lab=en_bias_b}
N 300 -320 300 -340 {lab=VDD}
N 300 -120 300 -100 {lab=VSS}
N 0 -220 180 -220 {lab=en_bias}
N 80 -220 80 -245 {lab=en_bias}
N 300 -20 300 0 {lab=VDD}
N 300 480 300 500 {lab=VSS}
N 840 20 840 40 {lab=VDD}
N 840 200 840 220 {lab=VSS}
N 840 -340 840 -320 {lab=VDD}
N 840 -120 840 -100 {lab=VSS}
N 420 -260 560 -260 {lab=vpbias}
N 560 -260 560 -220 {lab=vpbias}
N 560 -220 720 -220 {lab=vpbias}
N 500 -260 500 -280 {lab=vpbias}
N 420 -220 500 -220 {lab=vnbias}
N 500 -220 500 -180 {lab=vnbias}
N 500 -180 720 -180 {lab=vnbias}
N 600 -180 600 -160 {lab=vnbias}
N 460 -220 460 -70 {lab=vnbias}
N 460 -70 40 -70 {lab=vnbias}
N 40 -70 40 100 {lab=vnbias}
N 40 100 180 100 {lab=vnbias}
N 150 60 180 60 {}
N 150 420 180 420 {}
N 150 380 180 380 {}
N 150 340 180 340 {}
N 150 300 180 300 {}
N 150 260 180 260 {}
N 150 220 180 220 {}
N 150 180 180 180 {}
N 150 140 180 140 {}
N 420 240 560 240 {lab=ictrl}
N 560 240 560 140 {lab=ictrl}
N 560 140 720 140 {lab=ictrl}
N 560 240 560 260 {lab=ictrl}
N 690 100 720 100 {}
N 960 120 1060 120 {lab=clk}
N 690 -260 720 -260 {}
N 960 -220 1060 -220 {lab=clk_slow}
C {devices/title.sym} 200 620 0 0 {name=title1
author=changeling-alpha}
C {devices/iopin.sym} -360 -340 0 0 {name=p1
lab=VDD}
C {devices/iopin.sym} -360 520 0 0 {name=p2
lab=VSS}
C {devices/ipin.sym} -360 -240 0 0 {name=p3
lab=en_ring}
C {devices/ipin.sym} -360 -200 0 0 {name=p4
lab=en_relax}
C {devices/ipin.sym} -360 60 0 0 {name=p5
lab=trim7}
C {devices/ipin.sym} -360 100 0 0 {name=p6
lab=trim6}
C {devices/ipin.sym} -360 140 0 0 {name=p7
lab=trim5}
C {devices/ipin.sym} -360 180 0 0 {name=p8
lab=trim4}
C {devices/ipin.sym} -360 220 0 0 {name=p9
lab=trim3}
C {devices/ipin.sym} -360 260 0 0 {name=p10
lab=trim2}
C {devices/ipin.sym} -360 300 0 0 {name=p11
lab=trim1}
C {devices/ipin.sym} -360 340 0 0 {name=p12
lab=trim0}
C {sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym} -200 -220 0 0 {name=XEN_NOR
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym} -40 -220 0 0 {name=XEN_OR
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {bias/bias.sym} 300 -220 0 0 {name=XBIAS}
C {devices/lab_pin.sym} 300 -340 0 0 {name=l13
lab=VDD}
C {devices/lab_pin.sym} 300 -100 0 0 {name=l14
lab=VSS}
C {devices/lab_pin.sym} 80 -245 0 1 {name=l15
lab=en_bias}
C {devices/noconn.sym} 420 -180 0 0 {name=nc_ibias}
C {osc_ring_cc/idac_8b.sym} 300 240 0 0 {name=XIDAC}
C {osc_ring_cc/cco_core.sym} 840 120 0 0 {name=XCCO}
C {clk_macro/relax_core.sym} 840 -220 0 0 {name=XRELAX}
C {devices/lab_pin.sym} 300 -20 0 0 {name=l16
lab=VDD}
C {devices/lab_pin.sym} 300 500 0 0 {name=l17
lab=VSS}
C {devices/lab_pin.sym} 840 20 0 0 {name=l18
lab=VDD}
C {devices/lab_pin.sym} 840 220 0 0 {name=l19
lab=VSS}
C {devices/lab_pin.sym} 840 -340 0 0 {name=l20
lab=VDD}
C {devices/lab_pin.sym} 840 -100 0 0 {name=l21
lab=VSS}
C {devices/lab_pin.sym} 500 -280 0 1 {name=l22
lab=vpbias}
C {devices/lab_pin.sym} 600 -160 0 1 {name=l23
lab=vnbias}
C {devices/lab_pin.sym} 150 60 0 0 {name=l24
lab=en_ring}
C {devices/lab_pin.sym} 150 420 0 0 {name=l25
lab=trim0}
C {devices/lab_pin.sym} 150 380 0 0 {name=l26
lab=trim1}
C {devices/lab_pin.sym} 150 340 0 0 {name=l27
lab=trim2}
C {devices/lab_pin.sym} 150 300 0 0 {name=l28
lab=trim3}
C {devices/lab_pin.sym} 150 260 0 0 {name=l29
lab=trim4}
C {devices/lab_pin.sym} 150 220 0 0 {name=l30
lab=trim5}
C {devices/lab_pin.sym} 150 180 0 0 {name=l31
lab=trim6}
C {devices/lab_pin.sym} 150 140 0 0 {name=l32
lab=trim7}
C {devices/lab_pin.sym} 560 260 0 1 {name=l33
lab=ictrl}
C {devices/lab_pin.sym} 690 100 0 0 {name=l34
lab=en_ring}
C {devices/opin.sym} 1060 120 0 0 {name=p35
lab=clk}
C {devices/lab_pin.sym} 690 -260 0 0 {name=l36
lab=en_relax}
C {devices/opin.sym} 1060 -220 0 0 {name=p37
lab=clk_slow}
