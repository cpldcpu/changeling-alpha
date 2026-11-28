#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Ping endpoint (fweth) against the independent Ethernet model (tb/eth_model.v). Run from anywhere; about 25 minutes.
cd "$(dirname "$0")/.."
mkdir -p build
RTLDIR=../src/rsoc8/rtl
FW=../src/rsoc8/fw
RTL=${RTL:-"$RTLDIR/rcore8d.v $RTLDIR/rdual.v $RTLDIR/rlinecells.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"}
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_sys.vvp tb/tb_sys.v $RTL || exit 1
EXTRA=$FW/fweth_io.S sh $FW/build.sh fweth
mk() { avr-gcc -mmcu=attiny40 -Os -I$FW $2 -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 -o build/$1.elf $FW/fweth.c $FW/fweth_io.S
  avr-objcopy -O binary build/$1.elf build/$1.bin
  python3 -c "b=open('build/$1.bin','rb').read(); b+=b'\\0'*(len(b)%2); open('build/$1.hex','w').write('\\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\\n')"; }
r() { printf "%s: " "$1"; shift; vvp -n build/tb_sys.vvp "$@" 2>&1 | grep -E 'ETHM (PASS|FAIL)|TIMEOUT|EXIT' | head -1; }
r "ARP, pings, frames to ignore, divider 1 (answer delay of the largest frame is in the summary line)" +hex=build/fweth.hex +ethm=1 +maxcyc=40000000
r "the same, core divider 2" +hex=build/fweth.hex +ethm=1 +cdiv=2 +ethboot=15000 +maxcyc=60000000
r "largest frame (1916 bytes + FCS) and one byte more" +hex=build/fweth.hex +ethm=2 +maxcyc=60000000
for c in 1 2 3 4; do r "short test, core divider $c (4 fails: the receive loop needs 14 core cycles per byte)" +hex=build/fweth.hex +ethm=4 +cdiv=$c +ethboot=30000 +maxcyc=8000000; done
r "link pulses before and behind frames" +hex=build/fweth.hex +ethm=3 +maxcyc=3000000
r "periodic link pulses every 997 cycles" +hex=build/fweth.hex +ethm=1 +ethshort +ethnlp=997 +maxcyc=8000000
echo "-- fault insertion, each must FAIL"
for f in 1 2 3 4 5; do mk fw15_f$f -DFAULT=$f; r "FAULT=$f" +hex=build/fw15_f$f.hex +ethm=1 +ethshort +maxcyc=8000000; done
r "link pulses inside the frames (model fault)" +hex=build/fweth.hex +ethm=1 +ethshort +ethnlp=997 +ethnlpforce +maxcyc=8000000
mk fw15_t1 -DTDM=1; r "TD- on pin 2, differential idle pulse (must FAIL: both outputs high in idle)" +hex=build/fw15_t1.hex +ethm=5 +ethdiff +maxcyc=100000
echo "-- clock duty cycle: tolerance by bisection, about 10 minutes per duty value"
python3 tests/eth_sweep.py build/tb_sys.vvp build/fweth.hex 50 45 55 40 60
