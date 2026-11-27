v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {100 kHz Relaxation Oscillator (osc_relax: cap=cmomf, M=10)} 0 -380 0 0 0.35 0.35 {layer=3}
N -160 -320 2140 -320 {lab=VDD}
N -160 920 2140 920 {lab=VSS}
N -160 0 -80 0 {lab=en}
N 0 0 40 0 {}
N 160 -240 160 -320 {lab=VDD}
N 160 -40 160 0 {lab=VSS}
N -120 0 -120 -140 {lab=en}
N -120 -140 40 -140 {lab=en}
N 280 -140 320 -140 {}
N 520 -250 520 -320 {lab=VDD}
N 520 -220 520 -250 {lab=VDD}
N 280 -180 370 -180 {lab=vpbias}
N 370 -180 370 -220 {lab=vpbias}
N 370 -220 480 -220 {lab=vpbias}
N 370 -220 370 -245 {lab=vpbias}
N 520 -190 520 -140 {lab=vth}
N 520 -140 520 -90 {lab=vth}
N 520 -30 520 10 {lab=rth_0}
N 520 70 520 110 {lab=rth_1}
N 520 170 520 210 {lab=rth_2}
N 520 270 520 920 {lab=VSS}
N 720 120 760 120 {}
N 800 150 800 920 {lab=VSS}
N 800 120 800 150 {lab=VSS}
N 800 -250 800 -320 {lab=VDD}
N 800 -220 800 -250 {lab=VDD}
N 800 -190 800 90 {lab=vp_chg}
N 800 -140 720 -140 {lab=vp_chg}
N 720 -140 720 -220 {lab=vp_chg}
N 720 -220 760 -220 {lab=vp_chg}
N 720 -220 690 -220 {lab=vp_chg}
N 1040 -250 1040 -320 {lab=VDD}
N 1040 -220 1040 -250 {lab=VDD}
N 960 -220 1000 -220 {}
N 1040 -190 1040 -10 {lab=vcap_a}
N 1040 50 1040 120 {lab=VSS}
N 1040 20 1040 50 {lab=VSS}
N 960 20 1000 20 {}
N 1040 -100 1160 -100 {lab=vcap_a}
N 1160 -100 1160 150 {lab=vcap_a}
N 1160 210 1160 260 {lab=VSS}
N 1960 -260 1960 -320 {lab=VDD}
N 1960 -20 1960 0 {lab=VSS}
N 1800 -200 1840 -200 {}
N 1800 -160 1840 -160 {}
N 1800 -120 1840 -120 {}
N 1800 -80 1840 -80 {}
N 2080 -140 2120 -140 {}
N 1400 -250 1400 -320 {lab=VDD}
N 1400 -220 1400 -250 {lab=VDD}
N 1320 -220 1360 -220 {}
N 1400 -190 1400 -10 {lab=vcap_b}
N 1400 50 1400 120 {lab=VSS}
N 1400 20 1400 50 {lab=VSS}
N 1320 20 1360 20 {}
N 1400 -100 1520 -100 {lab=vcap_b}
N 1520 -100 1520 150 {lab=vcap_b}
N 1520 210 1520 260 {lab=VSS}
N 1960 40 1960 60 {lab=VDD}
N 1960 300 1960 320 {lab=VSS}
N 1800 120 1840 120 {}
N 1800 160 1840 160 {}
N 1800 200 1840 200 {}
N 1800 240 1840 240 {}
N 2080 180 2120 180 {}
N 1560 440 1620 440 {}
N 1560 580 1620 580 {}
N 1740 460 1760 460 {lab=q}
N 1760 460 1760 515 {lab=q}
N 1760 515 1590 515 {lab=q}
N 1590 515 1590 620 {lab=q}
N 1590 620 1620 620 {lab=q}
N 1760 460 1800 460 {lab=q}
N 1740 600 1780 600 {lab=qb}
N 1780 600 1780 545 {lab=qb}
N 1780 545 1600 545 {lab=qb}
N 1600 545 1600 480 {lab=qb}
N 1600 480 1620 480 {lab=qb}
N 1900 600 1940 600 {}
N 1780 600 1820 600 {lab=qb}
N 1820 600 1820 530 {lab=qb}
N 1820 530 1980 530 {lab=qb}
N 1980 530 1980 570 {lab=qb}
N 1860 530 1860 510 {lab=qb}
N 1980 630 1980 670 {lab=VSS}
N 1980 600 1980 630 {lab=VSS}
N 920 440 960 440 {}
N 920 480 960 480 {}
N 1080 460 1180 460 {lab=disn_a}
N 1260 460 1300 460 {}
N 920 580 960 580 {}
N 920 620 960 620 {}
N 1080 600 1180 600 {lab=disn_b}
N 1260 600 1300 600 {}
N 920 740 960 740 {}
N 920 780 960 780 {}
N 1080 760 1180 760 {lab=both_n}
N 1260 760 1400 760 {lab=both_hi}
N 1440 730 1440 680 {lab=vcap_a}
N 1440 790 1440 920 {lab=VSS}
N 1440 760 1440 790 {lab=VSS}
N 1580 740 1620 740 {}
N 1580 780 1620 780 {}
N 1740 760 1840 760 {lab=clk_pre}
N 1920 760 2040 760 {lab=clk_slow}
C {devices/title.sym} 400 1020 0 0 {name=title1
author=changeling-alpha}
C {devices/iopin.sym} -160 -320 0 0 {name=p1
lab=VDD}
C {devices/iopin.sym} -160 920 0 0 {name=p2
lab=VSS}
C {devices/ipin.sym} -160 0 0 0 {name=p3
lab=en}
C {sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym} -40 0 0 0 {name=XINV_EN
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {devices/lab_pin.sym} 40 0 0 1 {name=l4
lab=enb}
C {bias/bias.sym} 160 -140 0 0 {name=XBIAS}
C {devices/lab_pin.sym} 160 0 0 0 {name=l5
lab=VSS}
C {devices/lab_pin.sym} 320 -140 0 1 {name=l6
lab=vnbias}
C {devices/noconn.sym} 280 -100 0 0 {name=nc_ibias}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 500 -220 0 0 {name=MP_REF
w=1.0u
l=4.0u
ng=1
m=1
model=sg13_lv_pmos}
C {devices/lab_pin.sym} 370 -245 0 1 {name=l7
lab=vpbias}
C {devices/lab_pin.sym} 520 -140 0 0 {name=l8
lab=vth}
C {sg13cmos5l_pr/rppd.sym} 520 -60 0 0 {name=R_TH0
w=0.5e-6
l=40.0e-6
b=9
m=1
model=rppd
body=VSS
value=209k}
C {sg13cmos5l_pr/rppd.sym} 520 40 0 0 {name=R_TH1
w=0.5e-6
l=40.0e-6
b=9
m=1
model=rppd
body=VSS
value=209k}
C {sg13cmos5l_pr/rppd.sym} 520 140 0 0 {name=R_TH2
w=0.5e-6
l=40.0e-6
b=9
m=1
model=rppd
body=VSS
value=209k}
C {sg13cmos5l_pr/rppd.sym} 520 240 0 0 {name=R_TH3
w=0.5e-6
l=40.0e-6
b=9
m=1
model=rppd
body=VSS
value=209k}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 780 120 0 0 {name=MN_MIR
w=0.3u
l=4.0u
ng=1
m=1
model=sg13_lv_nmos}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 780 -220 0 0 {name=MP_CHG_IN
w=0.5u
l=4.0u
ng=1
m=10
model=sg13_lv_pmos}
C {devices/lab_pin.sym} 720 120 0 0 {name=l9
lab=vnbias}
C {devices/lab_pin.sym} 690 -220 0 0 {name=l10
lab=vp_chg}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 1020 -220 0 0 {name=MP_CHG_A
w=0.5u
l=4.0u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1020 20 0 0 {name=MN_DIS_A
w=0.5u
l=0.5u
ng=1
m=1
model=sg13_hv_nmos}
C {devices/lab_pin.sym} 960 -220 0 0 {name=l11
lab=vp_chg}
C {devices/lab_pin.sym} 1040 -100 0 0 {name=l12
lab=vcap_a}
C {devices/lab_pin.sym} 1040 120 0 0 {name=l13
lab=VSS}
C {devices/lab_pin.sym} 960 20 0 0 {name=l14
lab=dis_a}
C {sg13cmos5l_pr/cap_cmomf.sym} 1160 180 0 0 {name=C_A
w=20.6e-6
l=20.6e-6
mmin=1
mmax=4
m=1}
C {devices/lab_pin.sym} 1160 260 0 0 {name=l15
lab=VSS}
C {osc_relax/comp.sym} 1960 -140 0 0 {name=XCOMP_A}
C {devices/lab_pin.sym} 1960 0 0 0 {name=l16
lab=VSS}
C {devices/lab_pin.sym} 1800 -200 0 0 {name=l17
lab=vcap_a}
C {devices/lab_pin.sym} 1800 -160 0 0 {name=l18
lab=vth}
C {devices/lab_pin.sym} 1800 -120 0 0 {name=l19
lab=en}
C {devices/lab_pin.sym} 1800 -80 0 0 {name=l20
lab=vpbias}
C {devices/lab_pin.sym} 2120 -140 0 1 {name=l21
lab=cmp_a}
C {sg13cmos5l_pr/sg13_lv_pmos.sym} 1380 -220 0 0 {name=MP_CHG_B
w=0.5u
l=4.0u
ng=1
m=1
model=sg13_lv_pmos}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1380 20 0 0 {name=MN_DIS_B
w=0.5u
l=0.5u
ng=1
m=1
model=sg13_hv_nmos}
C {devices/lab_pin.sym} 1320 -220 0 0 {name=l22
lab=vp_chg}
C {devices/lab_pin.sym} 1400 -100 0 0 {name=l23
lab=vcap_b}
C {devices/lab_pin.sym} 1400 120 0 0 {name=l24
lab=VSS}
C {devices/lab_pin.sym} 1320 20 0 0 {name=l25
lab=dis_b}
C {sg13cmos5l_pr/cap_cmomf.sym} 1520 180 0 0 {name=C_B
w=20.6e-6
l=20.6e-6
mmin=1
mmax=4
m=1}
C {devices/lab_pin.sym} 1520 260 0 0 {name=l26
lab=VSS}
C {osc_relax/comp.sym} 1960 180 0 0 {name=XCOMP_B}
C {devices/lab_pin.sym} 1960 40 0 0 {name=l27
lab=VDD}
C {devices/lab_pin.sym} 1960 320 0 0 {name=l28
lab=VSS}
C {devices/lab_pin.sym} 1800 120 0 0 {name=l29
lab=vcap_b}
C {devices/lab_pin.sym} 1800 160 0 0 {name=l30
lab=vth}
C {devices/lab_pin.sym} 1800 200 0 0 {name=l31
lab=en}
C {devices/lab_pin.sym} 1800 240 0 0 {name=l32
lab=vpbias}
C {devices/lab_pin.sym} 2120 180 0 1 {name=l33
lab=cmp_b}
C {sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym} 1680 460 0 0 {name=XSR_Q
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym} 1680 600 0 0 {name=XSR_QB
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {devices/lab_pin.sym} 1560 440 0 0 {name=l34
lab=cmp_b}
C {devices/lab_pin.sym} 1560 580 0 0 {name=l35
lab=cmp_a}
C {devices/lab_pin.sym} 1800 460 0 1 {name=l36
lab=q}
C {sg13cmos5l_pr/sg13_lv_nmos.sym} 1960 600 0 0 {name=MN_INIT
w=0.5u
l=0.5u
ng=1
m=1
model=sg13_lv_nmos}
C {devices/lab_pin.sym} 1900 600 0 0 {name=l37
lab=enb}
C {devices/lab_pin.sym} 1860 510 0 1 {name=l38
lab=qb}
C {devices/lab_pin.sym} 1980 670 0 1 {name=l39
lab=VSS}
C {sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym} 1020 460 0 0 {name=XDIS_N_A
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym} 1220 460 0 0 {name=XDIS_I_A
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {devices/lab_pin.sym} 920 440 0 0 {name=l40
lab=q}
C {devices/lab_pin.sym} 920 480 0 0 {name=l41
lab=enb}
C {devices/lab_pin.sym} 1300 460 0 1 {name=l42
lab=dis_a}
C {sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym} 1020 600 0 0 {name=XDIS_N_B
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym} 1220 600 0 0 {name=XDIS_I_B
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {devices/lab_pin.sym} 920 580 0 0 {name=l43
lab=qb}
C {devices/lab_pin.sym} 920 620 0 0 {name=l44
lab=enb}
C {devices/lab_pin.sym} 1300 600 0 1 {name=l45
lab=dis_b}
C {sg13cmos5l_stdcells/sg13cmos5l_nand2_2.sym} 1020 760 0 0 {name=XBOTH_NAND
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym} 1220 760 0 0 {name=XBOTH_INV
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1420 760 0 0 {name=MN_UNSTICK
w=0.5u
l=0.5u
ng=1
m=1
model=sg13_hv_nmos}
C {devices/lab_pin.sym} 920 740 0 0 {name=l46
lab=cmp_a}
C {devices/lab_pin.sym} 920 780 0 0 {name=l47
lab=cmp_b}
C {devices/lab_pin.sym} 1440 680 0 1 {name=l48
lab=vcap_a}
C {sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym} 1680 760 0 0 {name=XOUT_NOR
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {sg13cmos5l_stdcells/sg13cmos5l_buf_2.sym} 1880 760 0 0 {name=XOUT_BUF
VDD=VDD
VSS=VSS
prefix=sg13cmos5l_}
C {devices/lab_pin.sym} 1580 740 0 0 {name=l49
lab=qb}
C {devices/lab_pin.sym} 1580 780 0 0 {name=l50
lab=enb}
C {devices/opin.sym} 2040 760 0 0 {name=p51
lab=clk_slow}
