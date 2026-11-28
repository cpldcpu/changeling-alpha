#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# SPI and I2C against independent testbench models (tb/spi_slave_model.v, tb/spi_master_model.v, tb/i2c_slave_model.v,
# tb/i2c_master_model.v; firmware fw/fw15_spim.c, fw16_spis.c, fw17_i2cm.c, fw18_i2cs.c, fw19_arb.c, fw/i2cm.h).
# Usage: tests/spii2c.sh [part ...]   parts: spim spis i2cm i2cs arb fault (default: all). One simulation at a time.
# Every line starts with ok, FAIL (expected result missing) or info (a measurement, no expectation).
cd "$(dirname "$0")/.."
mkdir -p build
RTLDIR=../src/rsoc8/rtl
RTL=${RTL:-"$RTLDIR/rcore8d.v $RTLDIR/rdual.v $RTLDIR/rlinecells.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"}
SIM=${SIM:-build/tb_sys.vvp}
[ -n "$NOCOMPILE" ] || iverilog -g2005 -DSIM -DFUNCTIONAL -o $SIM tb/tb_sys.v $RTL || exit 1
PARTS=${*:-"spim spis i2cm i2cs arb fault"}
NBAD=0; NOK=0
B() { sh tests/spii2c_build.sh "$@" > /dev/null 2>&1 || { echo "FAIL build $*"; exit 1; }; }
# run label want image plusargs...   want = pass or fail; pass = the model prints PASS, no FAIL line, exit code 0
run() {
    L=$1; W=$2; H=$3; shift 3
    timeout 120 vvp -n $SIM +hex=build/$H.hex "$@" > build/spii2c_last.txt 2>&1
    if grep -q -E "(SPISLV|SPIMST|I2CS|I2CM) PASS" build/spii2c_last.txt && ! grep -q -E "FAIL" build/spii2c_last.txt && grep -q "^EXIT 0 " build/spii2c_last.txt; then R=pass; else R=fail; fi
    INFO=$(grep -E "(SPISLV|SPIMST|I2CS|I2CM) (PASS|FAIL)" build/spii2c_last.txt | tr '\n' ' ' | cut -c1-${W2:-230})
    if [ "$R" = "$W" ]; then NOK=$((NOK+1)); echo "ok   $L ($W): $INFO"; else NBAD=$((NBAD+1)); echo "FAIL $L (wanted $W, got $R): $INFO $(grep -E 'EXIT|TIMEOUT' build/spii2c_last.txt | head -1)"; fi
}
# info label image plusargs... : print the summary lines
info() { L=$1; H=$2; shift 2; timeout 120 vvp -n $SIM +hex=build/$H.hex "$@" > build/spii2c_last.txt 2>&1; echo "info $L: $(grep -E '(SPISLV|SPIMST|I2CS|I2CM) (PASS|FAIL)|EXIT|TIMEOUT' build/spii2c_last.txt | tr '\n' ' ' | cut -c1-${W2:-230})"; }
# works label image plusargs... : prints 1 if the run passes
works() { H=$1; shift; timeout 120 vvp -n $SIM +hex=build/$H.hex "$@" > build/spii2c_last.txt 2>&1
    if grep -q -E "(SPISLV|SPIMST|I2CS|I2CM) PASS" build/spii2c_last.txt && ! grep -q "FAIL" build/spii2c_last.txt && grep -q "^EXIT 0 " build/spii2c_last.txt; then return 0; else return 1; fi; }
has() { echo $PARTS | grep -q -w $1; }

# ====================================================================================== SPI, chip is master (slave model)
if has spim; then
echo "== SPI master of the chip against the slave model (+spislv): pins 0 MOSI, 1 SCK, 2 MISO, 3 CS"
for m in 0 1 2 3; do for nb in 1 32; do
    B fw15_spim spim_$m$nb -DMODE=$m -DHB=8 -DNB=$nb
    run "mode $m, 16 cycles per bit, $nb byte(s) x 3, core divider 1" pass spim_$m$nb +spislv +spislv_mode=$m +spislv_xfers=3 +spislv_gapfree +maxcyc=100000
done; done
echo "-- highest SCK rate: smallest bit time (clock cycles per bit = 2 x half bit HB) with correct data from an ideal slave (MISO changes in the cycle of the SCK edge)"
for m in 0 1 2 3; do
    last=; for hb in 8 7 6 5 4 3 2 1; do
        B fw15_spim spim_r -DMODE=$m -DHB=$hb -DNB=1
        if works spim_r +spislv +spislv_mode=$m +spislv_xfers=3 +maxcyc=100000; then last=$hb; else break; fi
    done
    echo "info mode $m: fastest bit time with correct data from the ideal slave = $((2*last)) clock cycles per bit (half bit $last)"
done
echo "-- slave with MISO delay: MISO delay after the shifting edge that is still sampled correctly, per half bit HB (mode 0)"
for hb in 8 6 5 4; do
    B fw15_spim spim_d -DMODE=0 -DHB=$hb -DNB=1; last=-1
    for d in 0 1 2 3 4 5 6; do if works spim_d +spislv +spislv_mode=0 +spislv_xfers=3 +spislv_dly=$d +maxcyc=100000; then last=$d; else break; fi; done
    echo "info half bit $hb ($((2*hb)) cycles per bit): MISO delay up to $last cycles works (limit = HB - 4)"
done
echo "-- gap-free transfers of 32 bytes at core dividers 1, 2, 4 (the model counts pauses between bytes): smallest bit time without pauses, and smallest with correct data and without pauses"
for c in 1 2 4; do for m in 0 3; do
    nogap=; both=
    for hb in 8 7 6 5 4 3 2 1; do
        B fw15_spim spim_g -DMODE=$m -DHB=$hb -DNB=32
        timeout 120 vvp -n $SIM +hex=build/spim_g.hex +spislv +spislv_mode=$m +spislv_xfers=3 +cdiv=$c +maxcyc=200000 > build/spii2c_last.txt 2>&1
        P=$(grep "SPISLV mode" build/spii2c_last.txt | sed 's/.*pauses \([0-9]*\) .*/\1/' | sort -n | tail -1)
        if [ "$P" = "0" ]; then nogap=$((2*hb)); else break; fi
    done
    for hb in 8 7 6 5 4 3 2 1; do
        B fw15_spim spim_g -DMODE=$m -DHB=$hb -DNB=32
        if works spim_g +spislv +spislv_mode=$m +spislv_xfers=3 +spislv_gapfree +cdiv=$c +maxcyc=200000; then both=$((2*hb)); else break; fi
    done
    echo "info core divider $c, mode $m, 32 bytes: no pause down to ${nogap:-none} cycles per bit; no pause and correct data down to ${both:-none} cycles per bit"
done; done
echo "-- 1 byte and 32 bytes at core divider 2 and 4, 16 cycles per bit"
for c in 2 4; do for nb in 1 32; do B fw15_spim spim_c -DMODE=3 -DHB=8 -DNB=$nb; run "mode 3, $nb byte(s), core divider $c" pass spim_c +spislv +spislv_mode=3 +spislv_xfers=3 +spislv_gapfree +cdiv=$c +maxcyc=200000; done; done
echo "-- chip select handling: time from CS low to the first edge, and from the last edge to CS high, with no delay in the firmware (CSDLY = CSHOLD = 0)"
for m in 0 1 2 3; do B fw15_spim spim_cs -DMODE=$m -DHB=8 -DNB=1 -DCSDLY=0 -DCSHOLD=0; info "mode $m CS timing (firmware does not wait)" spim_cs +spislv +spislv_mode=$m +spislv_xfers=3 +maxcyc=100000; done
echo "-- the model checks: setup of MOSI (the required setup is 5 cycles, the half bit is 4: must fail), wrong mode in the model (must fail)"
B fw15_spim spim_f1 -DMODE=0 -DHB=4 -DNB=2
run "setup of MOSI 4 cycles, required 5" fail spim_f1 +spislv +spislv_mode=0 +spislv_setup=5 +maxcyc=100000
B fw15_spim spim_f2 -DMODE=0 -DHB=8 -DNB=2
run "chip sends mode 0, model expects mode 1" fail spim_f2 +spislv +spislv_mode=1 +maxcyc=100000
run "chip sends mode 0, model expects mode 2 (SCK idle level)" fail spim_f2 +spislv +spislv_mode=2 +maxcyc=100000
B fw15_spim spim_f3 -DMODE=0 -DHB=4 -DNB=32
run "32 bytes at 8 cycles per bit, core divider 4: pauses between bytes (gap-free required)" fail spim_f3 +spislv +spislv_mode=0 +spislv_xfers=3 +spislv_gapfree +cdiv=4 +maxcyc=200000
fi

# ====================================================================================== SPI, chip is slave (master model)
if has spis; then
echo "== SPI slave of the chip against the master model (+spimst, pin 4 = ready needs +pd=10)"
for m in 0 1 2 3; do
    B fw16_spis spis_$m -DMODE=$m -DNB=4
    run "mode $m, 16 cycles per bit, 4 bytes x 3, CS to first edge 40" pass spis_$m +spimst +spimst_mode=$m +spimst_hp=8 +spimst_n=4 +pd=10 +maxcyc=60000
done
for m in 0 3; do
    B fw16_spis spis_$m -DMODE=$m -DNB=32
    run "mode $m, 16 cycles per bit, 32 bytes x 3, continuous clock" pass spis_$m +spimst +spimst_mode=$m +spimst_hp=8 +spimst_n=32 +pd=10 +maxcyc=200000
    run "mode $m, 16 cycles per bit, 32 bytes x 3, core divider 2" pass spis_$m +spimst +spimst_mode=$m +spimst_hp=8 +spimst_n=32 +pd=10 +cdiv=2 +maxcyc=200000
done
echo "-- highest SCK rate at which the slave returns correct data (half period hp in cycles; model samples MISO at the edge, setup >= 1 cycle)"
for m in 0 1 2 3; do
    B fw16_spis spis_$m -DMODE=$m -DNB=4; last=
    for hp in 8 7 6 5 4 3; do
        if works spis_$m +spimst +spimst_mode=$m +spimst_hp=$hp +spimst_n=4 +pd=10 +maxcyc=60000; then last=$((2*hp)); else break; fi
    done
    echo "info mode $m: fastest bit time with correct MISO data = ${last:-none} cycles per bit"
    B fw16_spis spis_$m -DMODE=$m -DNB=8; lastrx=
    for hp in 4 3 2 1; do
        timeout 120 vvp -n $SIM +hex=build/spis_$m.hex +spimst +spimst_mode=$m +spimst_hp=$hp +spimst_n=8 +spimst_idle=1500 +pd=10 +maxcyc=60000 > build/spii2c_last.txt 2>&1
        if grep -q "^EXIT 0 " build/spii2c_last.txt; then lastrx=$((2*hp)); else break; fi
    done
    echo "info mode $m: MOSI data received correctly by the firmware (8 bytes, no pause, core divider 1) down to ${lastrx:-none} cycles per bit"
done
echo "-- the same at core divider 2 and 4 (MOSI direction, 8 bytes without pause)"
for c in 2 4; do for m in 0; do
    B fw16_spis spis_$m -DMODE=$m -DNB=8; lastrx=
    for hp in 8 6 5 4 3 2 1; do
        timeout 120 vvp -n $SIM +hex=build/spis_$m.hex +spimst +spimst_mode=$m +spimst_hp=$hp +spimst_n=8 +spimst_idle=1500 +pd=10 +cdiv=$c +maxcyc=60000 > build/spii2c_last.txt 2>&1
        if grep -q "^EXIT 0 " build/spii2c_last.txt; then lastrx=$((2*hp)); else break; fi
    done
    echo "info core divider $c, mode $m: MOSI data received correctly by the firmware down to ${lastrx:-none} cycles per bit"
done; done
echo "-- time from CS low to the first clock edge: smallest value with correct data (hp = 8)"
for m in 0 1 2 3; do
    B fw16_spis spis_$m -DMODE=$m -DNB=4; last=
    for cs in 14 10 8 7 6 5 4 3 2 1; do
        if works spis_$m +spimst +spimst_mode=$m +spimst_hp=8 +spimst_n=4 +spimst_cs=$cs +pd=10 +maxcyc=60000; then last=$cs; else break; fi
    done
    echo "info mode $m: first clock edge $last cycles after CS low is the smallest that works"
done
echo "-- MISO released when CS is high: the model checks uio_oe[2] every cycle; release time"
info "release of MISO after CS high (mode 0)" spis_0 +spimst +spimst_mode=0 +spimst_hp=8 +spimst_n=4 +pd=10 +maxcyc=60000
echo "-- late transmit byte (underrun): byte 2 written LATE cycles after the buffer became empty (16 cycles per bit, byte time 128)"
for d in 60 100 108 110 120 140 200; do
    B fw16_spis spis_late -DMODE=0 -DNB=4 -DNX=1 -DLATEB=2 -DLATE=$d
    info "LATE=$d" spis_late +spimst +spimst_mode=0 +spimst_hp=8 +spimst_n=4 +spimst_xfers=1 +pd=10 +spimst_v +maxcyc=20000
    grep -E "SPIMST byte 2" build/spii2c_last.txt | sed 's/^/        /'
done
B fw16_spis spis_ls -DMODE=0 -DNB=4 -DNX=1 -DLATEB=2 -DLATE=140 -DSHOWSTAT
info "LT0STAT just before the late write (0x60 = shifting, 0x40 = ran empty; exit code is the status)" spis_ls +spimst +spimst_mode=0 +spimst_hp=8 +spimst_n=4 +spimst_xfers=1 +pd=10 +maxcyc=20000
echo "-- transfer aborted by the master after 5 bits (CS high), then a complete one"
for m in 0 1; do
    B fw16_spis spis_ab -DMODE=$m -DNB=4 -DABORT1
    run "mode $m, abort after 5 bits, cells set up again for each transfer" pass spis_ab +spimst +spimst_mode=$m +spimst_hp=8 +spimst_n=4 +spimst_abort=5 +pd=10 +maxcyc=60000
    B fw16_spis spis_ab -DMODE=$m -DNB=4 -DABORT1 -DNOREINIT
    run "mode $m, abort after 5 bits, cells NOT set up again: the stale byte in the transmit buffer is sent first (wanted fail)" fail spis_ab +spimst +spimst_mode=$m +spimst_hp=8 +spimst_n=4 +spimst_abort=5 +pd=10 +maxcyc=60000
done
echo "-- the model checks (must fail)"
B fw16_spis spis_f1 -DMODE=0 -DNB=4
run "chip slave mode 0, master model mode 3 (mode 1 and 2 are not all detected, see report)" fail spis_f1 +spimst +spimst_mode=3 +spimst_hp=8 +spimst_n=4 +pd=10 +maxcyc=60000
run "hp 5: MISO changes in the cycle of the sampling edge" fail spis_f1 +spimst +spimst_mode=0 +spimst_hp=5 +spimst_n=4 +pd=10 +maxcyc=60000
run "master model sends 5 bytes, firmware expects 4" fail spis_f1 +spimst +spimst_mode=0 +spimst_hp=8 +spimst_n=5 +pd=10 +maxcyc=60000
fi

# ====================================================================================== I2C, chip is master (slave model with stretching)
if has i2cm; then
echo "== I2C master in firmware (fw/i2cm.h) against the slave model (+i2cs), pins 4 SDA, 5 SCL"
B fw17_i2cm im0 -DSCEN=0
run "write 3, read 4, write 1 + repeated start + read 2; no stretching" pass im0 +i2cs +maxcyc=200000
for a in "+i2cs_str=400 +i2cs_strp=20 +i2cs_seed=1" "+i2cs_str=400 +i2cs_strp=20 +i2cs_seed=7" "+i2cs_str=400 +i2cs_strp=50 +i2cs_seed=11" "+i2cs_str=1500 +i2cs_strp=8 +i2cs_seed=3" "+i2cs_strack=200" "+i2cs_strack=1000"; do
    run "same, slave stretches: $a" pass im0 +i2cs $a +maxcyc=800000
done
B fw17_i2cm im1 -DSCEN=1;  run "the slave does not acknowledge the address: I2C_NACK, stop, bus idle" pass im1 +i2cs +i2cs_noack +maxcyc=100000
B fw17_i2cm im5 -DSCEN=5;  run "the slave does not acknowledge data byte 1: I2C_NACK on that byte" pass im5 +i2cs +i2cs_nackdata=1 +maxcyc=100000
B fw17_i2cm im2 -DSCEN=2;  run "SDA stuck low for 5 clock pulses: I2C_BUSY, recovery with nine pulses, then a write works" pass im2 +i2cs +i2cs_stuck=5 +maxcyc=200000
run "SDA stuck low for 8 clock pulses (the slave is in the last bit of a byte)" pass im2 +i2cs +i2cs_stuck=8 +maxcyc=200000
run "SDA stuck low for 9 clock pulses" pass im2 +i2cs +i2cs_stuck=9 +maxcyc=200000
B fw17_i2cm im3 -DSCEN=3;  run "SDA stuck low for ever: recovery fails, I2C_BUSY reported, no line held, no hang" pass im3 +i2cs +i2cs_stuck=999 +maxcyc=100000
B fw17_i2cm im4 -DSCEN=4;  run "SCL stuck low for ever: I2C_TMO reported, no hang" pass im4 +i2cs +i2cs_sclstuck +maxcyc=100000
B fw17_i2cm im0 -DSCEN=0
run "slave stretches longer than the time-out (5000 > 3000 cycles): the master must report I2C_TMO (exit code 21)" fail im0 +i2cs +i2cs_str=5000 +i2cs_strp=2 +i2cs_seed=3 +maxcyc=200000
echo "-- fault insertion: the master of fw12_c1.c (SCL not read back, -DI2C_NOSTRETCH), data written changed (-DI2C_W_XOR=1)"
B fw17_i2cm im_f1 -DSCEN=0 -DI2C_NOSTRETCH
run "no read-back of SCL, no stretching (must still pass)" pass im_f1 +i2cs +maxcyc=200000
run "no read-back of SCL, slave stretches 200 cycles after every acknowledge" fail im_f1 +i2cs +i2cs_strack=200 +maxcyc=200000
run "no read-back of SCL, random stretching up to 400 cycles" fail im_f1 +i2cs +i2cs_str=400 +i2cs_strp=20 +i2cs_seed=1 +maxcyc=200000
B fw17_i2cm im_f2 -DSCEN=0 -DI2C_W_XOR=1
run "the master writes wrong data" fail im_f2 +i2cs +maxcyc=200000
fi

# ====================================================================================== I2C, chip is slave (master model)
if has i2cs; then
echo "== I2C slave with line cells (fw18_i2cs.c) against the master model (+i2cm), pins 4 SDA, 5 SCL, 6 DONE"
B fw18_i2cs is0
for p in 600 150; do
    W2=330 run "all transfers, SCL period $p cycles, core divider 1" pass is0 +i2cm +i2cm_per=$p +maxcyc=300000
    grep "chip as slave" build/spii2c_last.txt | sed 's/I2CM chip as slave: /        /'
done
run "all transfers, 400 kHz (150 cycles), core divider 2" pass is0 +i2cm +i2cm_per=150 +cdiv=2 +maxcyc=300000
grep "chip as slave" build/spii2c_last.txt | sed 's/I2CM chip as slave: /        /'
echo "-- fastest SCL period (cycles, low 52 % / high 48 %) at which the transfers still pass, per core divider and kind of transfer"
for c in 1 2 4; do
    for kind in "write:+i2cm_seq=3" "read1:+i2cm_seq=4 +i2cm_nrd=1" "read3:+i2cm_seq=4 +i2cm_nrd=3" "restart:+i2cm_seq=8"; do
        K=${kind%%:*}; A=${kind#*:}; last=
        for p in 600 300 200 150 120 100 90 80 70 64 60 56 52 48 44 40 36 32 28 24 20 16; do
            if works is0 +i2cm +i2cm_per=$p +cdiv=$c $A +maxcyc=120000; then last=$p; else break; fi
        done
        echo "info core divider $c, $K: passes down to SCL period $last cycles ($([ -n "$last" ] && echo $((60000 / last))) kHz if the clock is 60 MHz; 100 kHz = 600 cycles)"
    done
done
echo "-- margin of the acknowledge: delay added by firmware (SLOWACK, 4 core cycles per unit, 1 unit = about 8 cycles) at 400 kHz, core divider 1"
for n in 0 3 6 8 9 10; do B fw18_i2cs is_s -DSLOWACK=$n; info "SLOWACK=$n" is_s +i2cm +i2cm_per=150 +i2cm_seq=3 +maxcyc=40000; grep "chip as slave" build/spii2c_last.txt | sed 's/I2CM chip as slave: /        /' | cut -c1-220; done
echo "-- the slave does not stretch SCL by itself (no register for it); firmware stretch (STRETCH, SCL held low through the direction register)"
for n in 10 100; do B fw18_i2cs is_st -DSTRETCH=$n; run "firmware stretch of about $((n*8)) cycles before every acknowledge, 400 kHz" pass is_st +i2cm +i2cm_per=150 +i2cm_seq=3 +maxcyc=60000; grep "chip as slave" build/spii2c_last.txt | sed 's/I2CM chip as slave: /        /' | cut -c1-260; done
B fw18_i2cs is_st2 -DSTRETCH=10
echo "-- late data of a read (first byte written LATEDATA units late): SDA of the first bit comes after the rising edge of SCL"
for n in 0 4 8 12; do B fw18_i2cs is_ld -DLATEDATA=$n; info "LATEDATA=$n, 400 kHz" is_ld +i2cm +i2cm_per=150 +i2cm_seq=4 +i2cm_nrd=1 +maxcyc=30000; done
echo "-- I2C slave with the bus condition detector and the start at the shift edge (fw20_i2cs9.c: LCX_BCD, LCX_ESTR)"
B fw20_i2cs9 is9
for p in 600 150; do
    W2=330 run "fw20, all transfers, SCL period $p cycles, core divider 1" pass is9 +i2cm +i2cm_per=$p +maxcyc=300000
    grep "chip as slave" build/spii2c_last.txt | sed 's/I2CM chip as slave: /        /'
done
run "fw20, all transfers, 400 kHz (150 cycles), core divider 2" pass is9 +i2cm +i2cm_per=150 +cdiv=2 +maxcyc=300000
for c in 1 2 4; do
    for kind in "write:+i2cm_seq=3" "read1:+i2cm_seq=4 +i2cm_nrd=1" "read3:+i2cm_seq=4 +i2cm_nrd=3" "restart:+i2cm_seq=8"; do
        K=${kind%%:*}; A=${kind#*:}; last=
        for p in 600 300 200 150 120 100 90 80 70 64 60 56 52 48 44 40 36 32 28 24 20 16; do
            if works is9 +i2cm +i2cm_per=$p +cdiv=$c $A +maxcyc=120000; then last=$p; else break; fi
        done
        echo "info fw20, core divider $c, $K: passes down to SCL period $last cycles"
    done
done
echo "-- late data of a read, fw20: the first byte may be written until the falling edge of the acknowledge clock"
for n in 0 4 8 12 16 20; do B fw20_i2cs9 is9_ld -DLATEDATA=$n; info "fw20 LATEDATA=$n, 400 kHz" is9_ld +i2cm +i2cm_per=150 +i2cm_seq=4 +i2cm_nrd=1 +maxcyc=30000; done
B fw20_i2cs9 is9_f1 -DNOBCD; run "fw20 fault: detector off, no start found" fail is9_f1 +i2cm +i2cm_per=150 +maxcyc=100000
B fw20_i2cs9 is9_f2 -DNOESTR; info "fw20 with ESTR = 0 (the byte goes out at the write, while SCL is low or high)" is9_f2 +i2cm +i2cm_per=150 +maxcyc=100000
echo "-- fault insertion (must fail)"
run "the model addresses 0x53, the chip answers to 0x52" fail is0 +i2cm +i2cm_addr=53 +maxcyc=100000
B fw18_i2cs is_f -DSLOWACK=12
run "acknowledge 100 cycles late at 400 kHz" fail is_f +i2cm +i2cm_per=150 +i2cm_seq=3 +maxcyc=40000
run "core divider 4, 400 kHz: the slave is too slow" fail is0 +i2cm +i2cm_per=150 +cdiv=4 +maxcyc=40000
fi

# ====================================================================================== two masters
if has arb; then
echo "== two masters: the chip (firmware master, address 0x52, GO on pin 6) and the master model start together; slave model at both addresses"
B fw19_arb a_win -DEXPECT=0
B fw19_arb a_lose -DEXPECT=4
for c in 1 2 4; do for d in 0 3 8 20 60; do
    run "core divider $c, model starts $d cycles after GO, model address 0x53: the chip must win (and finish the write)" pass a_win +i2cm +i2cm_arb +i2cm_per=200 +i2cm_arbd=$d +i2cm_arbaddr=53 +i2cs +i2cs_addr=52 +i2cs_addr2=53 +cdiv=$c +maxcyc=120000
    run "core divider $c, model starts $d cycles after GO, model address 0x51: the chip must lose and release the bus" pass a_lose +i2cm +i2cm_arb +i2cm_per=200 +i2cm_arbd=$d +i2cm_arbaddr=51 +i2cs +i2cs_addr=52 +i2cs_addr2=51 +cdiv=$c +maxcyc=120000
done; done
echo "-- arbitration in the data phase (same address 0x52, first data byte 0x3C against 0x3D and 0x34)"
B fw19_arb a_d0 -DEXPECT=0; B fw19_arb a_d4 -DEXPECT=4
run "model sends 0x3D: the chip wins" pass a_d0 +i2cm +i2cm_arb +i2cm_per=200 +i2cm_arbd=3 +i2cm_arbaddr=52 +i2cm_arbxor=01 +i2cs +i2cs_addr=52 +i2cs_nochk +maxcyc=120000
run "model sends 0x34: the chip loses" pass a_d4 +i2cm +i2cm_arb +i2cm_per=200 +i2cm_arbd=3 +i2cm_arbaddr=52 +i2cm_arbxor=08 +i2cs +i2cs_addr=52 +i2cs_nochk +maxcyc=120000
echo "-- fault insertion (must fail)"
B fw19_arb a_nochk -DEXPECT=4 -DI2C_NOARB
run "no arbitration check in the firmware, the chip should lose" fail a_nochk +i2cm +i2cm_arb +i2cm_per=200 +i2cm_arbd=3 +i2cm_arbaddr=51 +i2cs +i2cs_addr=52 +i2cs_addr2=51 +maxcyc=120000
run "the chip wins but the test expects it to lose" fail a_lose +i2cm +i2cm_arb +i2cm_per=200 +i2cm_arbd=3 +i2cm_arbaddr=53 +i2cs +i2cs_addr=52 +i2cs_addr2=53 +maxcyc=120000
fi

# ====================================================================================== faults inserted into temporary copies of rtl/rlinecells.v (rtl/ is not changed)
if has fault; then
echo "== fault insertion in temporary RTL copies (build/rtlf): the SPI slave tests must fail"
mkdir -p build/rtlf
RT="$RTLDIR/rcore8d.v $RTLDIR/rdual.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"
sed '/assign o_drive/s/cs_ok & //' $RTLDIR/rlinecells.v > build/rtlf/a.v
sed '/wire t1_adv/s/ & ~(CPHA & tfirst)//' $RTLDIR/rlinecells.v > build/rtlf/b.v
cmp -s $RTLDIR/rlinecells.v build/rtlf/a.v && { echo "FAIL fault a not applied"; NBAD=$((NBAD+1)); }
cmp -s $RTLDIR/rlinecells.v build/rtlf/b.v && { echo "FAIL fault b not applied"; NBAD=$((NBAD+1)); }
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_fa.vvp tb/tb_sys.v build/rtlf/a.v $RT || exit 1
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_fb.vvp tb/tb_sys.v build/rtlf/b.v $RT || exit 1
B fw16_spis spis_0 -DMODE=0 -DNB=4; B fw16_spis spis_1 -DMODE=1 -DNB=4
SIM=build/tb_fa.vvp run "o_drive without cs_ok (MISO driven while CS is high)" fail spis_0 +spimst +spimst_mode=0 +spimst_hp=8 +spimst_n=4 +pd=10 +maxcyc=60000
SIM=build/tb_fb.vvp run "slave mode 1: first-bit advance of CPHA removed" fail spis_1 +spimst +spimst_mode=1 +spimst_hp=8 +spimst_n=4 +pd=10 +maxcyc=60000
SIM=build/tb_fb.vvp run "same copy, mode 0 (unaffected, must pass)" pass spis_0 +spimst +spimst_mode=0 +spimst_hp=8 +spimst_n=4 +pd=10 +maxcyc=60000
fi
echo "result: $NOK ok, $NBAD FAIL"
[ $NBAD = 0 ]
