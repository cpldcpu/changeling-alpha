v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {Self-Biased Beta-Multiplier Reference (0.5 uA nominal, 1.2 V CMOS)} 0 -340 0 0 0.35 0.35 {layer=3}
N 0 -280 1740 -280 {lab=VDD}
N 0 280 1740 280 {lab=VSS}
N -40 0 40 0 {lab=en}
N 40 -80 40 80 {lab=en}
N 40 -80 80 -80 {lab=en}
N 40 80 80 80 {lab=en}
N 120 -110 120 -280 {lab=VDD}
N 120 -80 120 -110 {}
N 120 110 120 280 {lab=VSS}
N 120 80 120 110 {}
N 120 -50 120 50 {lab=enb}
N 400 -230 400 -280 {lab=VDD}
N 400 -200 400 -230 {}
N 520 -280 520 -40 {lab=VDD}
N 400 -100 410 -100 {lab=VDD}
N 410 -100 410 -140 {lab=VDD}
N 410 -140 520 -140 {lab=VDD}
N 400 0 410 0 {lab=VDD}
N 410 0 410 -40 {lab=VDD}
N 410 -40 520 -40 {lab=VDD}
N 120 0 260 0 {lab=enb}
N 260 0 260 -200 {lab=enb}
N 260 -200 360 -200 {lab=enb}
N 320 -100 360 -100 {}
N 320 0 360 0 {}
N 400 -170 400 -130 {lab=su_s0}
N 400 -70 400 -30 {lab=su_s1}
N 400 30 400 90 {lab=su_mid}
N 320 120 360 120 {}
N 400 150 400 280 {lab=VSS}
N 400 120 400 150 {}
N 400 60 600 60 {lab=su_mid}
N 600 60 600 120 {lab=su_mid}
N 600 120 640 120 {lab=su_mid}
N 680 150 680 280 {lab=VSS}
N 680 120 680 150 {}
N 680 90 680 40 {lab=vpbias}
N 680 40 740 40 {lab=vpbias}
N 740 40 740 -40 {lab=vpbias}
N 740 -40 1180 -40 {lab=vpbias}
N 920 -150 920 -280 {lab=VDD}
N 920 -120 920 -150 {}
N 920 110 920 280 {lab=VSS}
N 920 80 920 110 {}
N 1260 -150 1260 -280 {lab=VDD}
N 1260 -120 1260 -150 {}
N 1260 40 1270 40 {lab=VSS}
N 1270 40 1270 100 {lab=VSS}
N 1270 100 1380 100 {}
N 920 -90 920 50 {lab=vnbias}
N 920 0 980 0 {lab=vnbias}
N 980 0 980 80 {lab=vnbias}
N 980 80 960 80 {lab=vnbias}
N 980 40 1220 40 {lab=vnbias}
N 1260 -90 1260 10 {lab=vpbias}
N 1180 -40 1260 -40 {lab=vpbias}
N 1140 -40 1140 -60 {lab=vpbias}
N 1180 -40 1180 -120 {lab=vpbias}
N 1180 -120 1220 -120 {lab=vpbias}
N 1180 -120 960 -120 {lab=vpbias}
N 1260 70 1260 150 {lab=n_res}
N 1260 210 1260 280 {lab=VSS}
N 1060 -230 1060 -280 {lab=VDD}
N 1060 -200 1060 -230 {}
N 990 -200 1020 -200 {}
N 1060 -170 1060 -120 {lab=vpbias}
N 1060 230 1060 280 {lab=VSS}
N 1060 200 1060 230 {}
N 990 200 1020 200 {}
N 1060 170 1060 40 {lab=vnbias}
N 1560 -150 1560 -280 {lab=VDD}
N 1560 -120 1560 -150 {}
N 1260 -40 1480 -40 {lab=vpbias}
N 1480 -40 1480 -120 {lab=vpbias}
N 1480 -120 1520 -120 {lab=vpbias}
N 1480 -40 1740 -40 {lab=vpbias}
N 980 0 1740 0 {lab=vnbias}
N 1380 0 1380 -20 {lab=vnbias}
N 1560 -90 1560 40 {lab=ibias_out}
N 1560 40 1740 40 {lab=ibias_out}
C {devices/title.sym} 0 380 0 0 {name=title1
author=changeling-alpha}
C {devices/iopin.sym} 0 -280 0 0 {name=p1
lab=VDD}
C {devices/iopin.sym} 0 280 0 0 {name=p2
lab=VSS}
C {devices/ipin.sym} -40 0 0 0 {name=p3
lab=en}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 100 -80 0 0 {name=MEN_P
w=0.5u
l=0.5u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 100 80 0 0 {name=MEN_N
w=0.25u
l=0.5u
ng=1
m=1
model=sg13_lv_nmos}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 380 -200 0 0 {name=MSU_EN
w=0.3u
l=1.0u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 380 -100 0 0 {name=MSU_P1
w=0.15u
l=10u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 380 0 0 0 {name=MSU_P2
w=0.15u
l=10u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 380 120 0 0 {name=MSU_N
w=4.0u
l=0.5u
ng=1
m=1
model=sg13_lv_nmos}
C {devices/lab_pin.sym} 260 -200 0 0 {name=l4
lab=enb}
C {devices/lab_pin.sym} 320 -100 0 0 {name=l5
lab=VSS}
C {devices/lab_pin.sym} 320 0 0 0 {name=l6
lab=VSS}
C {devices/lab_pin.sym} 320 120 0 0 {name=l7
lab=vnbias}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 660 120 0 0 {name=MSU_INJ
w=0.5u
l=1.0u
ng=1
m=1
model=sg13_lv_nmos}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 940 -120 0 1 {name=MP1
w=1.0u
l=4.0u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 940 80 0 1 {name=MN1
w=0.3u
l=4.0u
ng=1
m=1
model=sg13_lv_nmos}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 1240 -120 0 0 {name=MP2
w=1.0u
l=4.0u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 1240 40 0 0 {name=MN2
w=0.3u
l=4.0u
ng=1
m=4
model=sg13_lv_nmos}
C {sg13cmos5l_pr/rppd.sym} 1260 180 0 0 {name=R_BIAS
w=0.5e-6
l=20.0e-6
b=19
m=1
model=rppd
body=VSS
value=108k}
C {devices/lab_pin.sym} 1380 100 0 1 {name=l8
lab=VSS}
C {devices/lab_pin.sym} 1140 -60 0 0 {name=l9
lab=vpbias}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 1040 -200 0 0 {name=MP_OFF
w=1.0u
l=0.5u
ng=1
m=1
model=sg13_lv_pmos}
C {devices/lab_pin.sym} 990 -200 0 0 {name=l10
lab=en}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 1040 200 0 0 {name=MN_OFF
w=1.0u
l=0.5u
ng=1
m=1
model=sg13_lv_nmos}
C {devices/lab_pin.sym} 990 200 0 0 {name=l11
lab=enb}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 1540 -120 0 0 {name=MP_OUT
w=1.0u
l=4.0u
ng=1
m=1
model=sg13_lv_pmos}
C {devices/opin.sym} 1740 -40 0 0 {name=p12
lab=vpbias}
C {devices/lab_pin.sym} 1380 -20 0 1 {name=l13
lab=vnbias}
C {devices/opin.sym} 1740 0 0 0 {name=p14
lab=vnbias}
C {devices/opin.sym} 1740 40 0 0 {name=p15
lab=ibias_out}
