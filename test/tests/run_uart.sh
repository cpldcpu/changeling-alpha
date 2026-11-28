#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# UART against the independent model (tb/uart_model.v), mailbox bridge, UART to WS2812 bridge (tb/ws2812_model.v).
# usage: sh tests/run_uart.sh [limits]    (about 8 minutes; "limits" adds the fine sweeps that find the tolerance limits)
# Every line ends with PASS or FAIL. "expected FAIL" marks a test that shows a known weakness or a deliberate fault
# and passes only if the failure is detected.
cd "$(dirname "$0")/.."
mkdir -p build
RTLDIR=../src/rsoc8/rtl
FW=../src/rsoc8/fw
RTL="$RTLDIR/rcore8d.v $RTLDIR/rdual.v $RTLDIR/rlinecells.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_sys.vvp tb/tb_sys.v $RTL || exit 1
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_sys_old.vvp tb/tb_sys.v $(echo $RTL | sed "s#$RTLDIR/rhost.v#tb/old/rhost_before_032.v#") || exit 1      # host link before the fix of the mailbox read
B() { sh $FW/build_u.sh "$@" > /dev/null 2>&1 || echo "BUILD FAILED $2"; }
NFAIL=0; MODE=$1
# t <label> <expected: PASS|FAIL> <simulator image> <options...>
t() {
    label=$1; exp=$2; img=$3; shift 3
    if [ -n "$ONLY" ] && ! echo "$label" | grep -q -E "$ONLY"; then return; fi        # ONLY=<regex>: run only matching tests
    out=$(vvp -n build/$img.vvp "$@" 2>&1)
    if ! echo "$out" | grep -q -E "UART TEST|EXIT|TIMEOUT"; then out=$(vvp -n build/$img.vvp "$@" 2>&1); fi     # simulation killed from outside: once more
    if echo "$out" | grep -q "UART TEST PASS"; then got=PASS; elif echo "$out" | grep -q -E "UART TEST FAIL|EXIT|TIMEOUT"; then got=FAIL; else got=NORESULT; fi
    if [ "$got" = "$exp" ]; then r=PASS; else r=FAIL; NFAIL=$((NFAIL+1)); fi
    extra=$(echo "$out" | grep -E "$GREP" | cut -c1-170 | tr '\n' '|')
    printf "%-62s %s (expected %s, got %s) %s\n" "$label" "$r" "$exp" "$got" "$extra"
}
GREP="^$"
echo "== A: echo against the UART model"
for c in 60 521; do B fwu_echo echo$c "-DCPB=$c"; done
GREP="sweep mode [0-9]: last|chip transmitter"
t "A1 sweep -8..+8 %, CPB 60 (1 Mbaud), 3 modes, +-3 % must pass" PASS tb_sys +hex=build/echo60.hex +uart +uscen=1 +ucpb=60 +maxcyc=2000000
GREP="sweep mode [0-9]: last|chip transmitter"
t "A2 offsets -7, 0, +7 %, CPB 521 (115200), clock error of the model" PASS tb_sys +hex=build/echo521.hex +uart +uscen=1 +ucpb=521 +unb=4 +umodes=4 +uomin=-70 +uomax=70 +uostep=70 +maxcyc=3000000
t "A2b offsets -3,0,+3 % at CPB 521, 4 characters, all modes" PASS tb_sys +hex=build/echo521.hex +uart +uscen=1 +ucpb=521 +unb=4 +uomin=-30 +uomax=30 +uostep=30 +maxcyc=3000000
GREP="sweep mode 2 \(both\) offset"
for c in 8 5 4 3 2; do B fwu_echo echo$c "-DCPB=$c"; done
for c in 8 5; do t "A3 fast rate CPB $c: +-3 % must pass" PASS tb_sys +hex=build/echo$c.hex +uart +uscen=1 +ucpb=$c +unb=6 +umodes=4 +uomin=-30 +uomax=30 +uostep=30 +maxcyc=500000; done
for c in 4 3 2; do t "A3 fast rate CPB $c: offset 0 only" PASS tb_sys +hex=build/echo$c.hex +uart +uscen=1 +ucpb=$c +unb=6 +umodes=4 +uomin=0 +uomax=0 +uostep=10 +maxcyc=500000; done
B fwu_echo echo1 "-DCPB=1"
t "A3 CPB 1: does not work (expected FAIL)" FAIL tb_sys +hex=build/echo1.hex +uart +uscen=1 +ucpb=1 +unb=6 +umodes=4 +uomin=0 +uomax=0 +uostep=10 +maxcyc=500000
GREP="back-to"
for o in 0 -3 3; do t "A4 16 characters back to back, 1 stop bit, CPB 60, model offset $o %" PASS tb_sys +hex=build/echo60.hex +uart +uscen=2 +ucpb=60 +unb=16 +uoff=$o +maxcyc=500000; done
t "A4 16 characters back to back, CPB 521, offset -3 %" PASS tb_sys +hex=build/echo521.hex +uart +uscen=2 +ucpb=521 +unb=16 +uoff=-3 +maxcyc=500000
t "A4 192 characters back to back, CPB 60, -3 %: overrun (expected FAIL)" FAIL tb_sys +hex=build/echo60.hex +uart +uscen=2 +ucpb=60 +unb=192 +uoff=-3 +maxcyc=1500000
GREP="back-to"
t "A4 16 characters back to back, 2 stop bits from the model" PASS tb_sys +hex=build/echo60.hex +uart +uscen=6 +ucpb=60 +unstop=2 +maxcyc=500000
GREP="framing|after a framing"
t "A5 framing errors reported with '!', next character received" PASS tb_sys +hex=build/echo60.hex +uart +uscen=3 +ucpb=60 +maxcyc=500000
B fwu_echo echo60_nr "-DCPB=60 -DNORESYNC"
t "A5 same without restart of the receiver (expected FAIL: extra 0xFF)" FAIL tb_sys +hex=build/echo60_nr.hex +uart +uscen=3 +ucpb=60 +maxcyc=500000
GREP="glitch"
B fwu_echo echo60_sc "-DCPB=60 -DSTARTCHK"
t "A6 glitch 0.3 bit: without start bit check (documented weakness)" PASS tb_sys +hex=build/echo60.hex +uart +uscen=4 +ucpb=60 +maxcyc=500000
t "A6 glitch 0.3 bit: with start bit check by receive cell 1" PASS tb_sys +hex=build/echo60_sc.hex +uart +uscen=4 +ustartchk +ucpb=60 +maxcyc=500000
GREP="parity"
B fwu_echo echo60_pe "-DCPB=60 -DPARCHK=1"; B fwu_echo echo60_po "-DCPB=60 -DPARCHK=2"
t "A7 7 data bits + even parity (frame passes unchanged, firmware checks)" PASS tb_sys +hex=build/echo60_pe.hex +uart +uscen=5 +ucpb=60 +und=7 +upar=1 +upchk +maxcyc=500000
t "A7 7 data bits + odd parity" PASS tb_sys +hex=build/echo60_po.hex +uart +uscen=5 +ucpb=60 +und=7 +upar=2 +upchk +maxcyc=500000
t "A7 fault: firmware checks odd, model sends even (expected FAIL)" FAIL tb_sys +hex=build/echo60_po.hex +uart +uscen=5 +ucpb=60 +und=7 +upar=1 +upchk +maxcyc=500000
GREP="overrun|after the overrun|burst"
# additional frame bit of the cells (register LCX): parity generated and checked by the cells, ninth data bit
B fwu_par par60_e "-DCPB=60 -DPAR=2"; B fwu_par par60_o "-DCPB=60 -DPAR=1"; B fwu_par par60_n "-DCPB=60 -DNINE"; B fwu_par par8_e "-DCPB=8 -DPAR=2"
t "A10 8 data bits + even parity by the cells, wrong parity marked" PASS tb_sys +hex=build/par60_e.hex +uart +uscen=9 +ucpb=60 +und=8 +upar=1 +maxcyc=500000
t "A10 8 data bits + odd parity by the cells" PASS tb_sys +hex=build/par60_o.hex +uart +uscen=9 +ucpb=60 +und=8 +upar=2 +maxcyc=500000
t "A10 even parity, 8 cycles per bit" PASS tb_sys +hex=build/par8_e.hex +uart +uscen=9 +ucpb=8 +und=8 +upar=1 +maxcyc=200000
GREP="back-to"
for o in 0 -3 3; do t "A10 even parity, 16 characters back to back, model offset $o %" PASS tb_sys +hex=build/par60_e.hex +uart +uscen=2 +ucpb=60 +unb=16 +und=8 +upar=1 +uoff=$o +maxcyc=500000; done
GREP="parity"
t "A10 ninth data bit passed through by firmware (model: even parity, two wrong)" PASS tb_sys +hex=build/par60_n.hex +uart +uscen=5 +ucpb=60 +und=8 +upar=1 +maxcyc=500000
t "A10 fault: cells odd, model even (expected FAIL)" FAIL tb_sys +hex=build/par60_o.hex +uart +uscen=9 +ucpb=60 +und=8 +upar=1 +maxcyc=500000
t "A10 fault: firmware without the additional bit (echo60), model with parity (expected FAIL)" FAIL tb_sys +hex=build/echo60.hex +uart +uscen=9 +ucpb=60 +und=8 +upar=1 +maxcyc=500000
B fwu_par par60_2s "-DCPB=60 -DTWOSTOP"
GREP="back-to"
t "A11 transmit with two stop bits (ninth bit = 1), 16 characters back to back, model checks two stop bits" PASS tb_sys +hex=build/par60_2s.hex +uart +uscen=2 +ucpb=60 +unb=16 +urnstop=2 +maxcyc=500000
t "A11 fault: firmware with one stop bit, model checks two (expected FAIL)" FAIL tb_sys +hex=build/echo60.hex +uart +uscen=2 +ucpb=60 +unb=16 +urnstop=2 +maxcyc=500000
B fwu_echo echo60_st "-DCPB=60 -DSTALL=12000"
t "A8 overrun: firmware stalls, 8 characters back to back" PASS tb_sys +hex=build/echo60_st.hex +uart +uscen=7 +ucpb=60 +maxcyc=800000
B fwu_echo echo8 "-DCPB=8"; B fwu_echo echo10 "-DCPB=10"
t "A8 slow firmware (+cdiv=4), CPB 8, burst of 24: lost characters marked" PASS tb_sys +hex=build/echo8.hex +cdiv=4 +uart +uscen=8 +ucpb=8 +unb=24 +maxcyc=800000
t "A8 +cdiv=4, CPB 10, burst of 48: nothing lost" PASS tb_sys +hex=build/echo10.hex +cdiv=4 +uart +uscen=8 +ucpb=10 +unb=48 +maxcyc=800000
B fwu_echo echo60_b "-DCPB=60 -DBUSY=40"
t "A8 1 Mbaud, +cdiv=4, firmware with delay loop, burst of 24" PASS tb_sys +hex=build/echo60_b.hex +cdiv=4 +uart +uscen=8 +ucpb=60 +unb=24 +maxcyc=800000
t "A8 1 Mbaud, +cdiv=4, normal firmware, 16 back to back" PASS tb_sys +hex=build/echo60.hex +cdiv=4 +uart +uscen=2 +ucpb=60 +unb=16 +maxcyc=800000
B fwu_echo echo64 "-DCPB=64"
GREP="sweep mode 2 \(both\) offset"
t "A9 fault: firmware at CPB 64, model at 60 (expected FAIL)" FAIL tb_sys +hex=build/echo64.hex +uart +uscen=1 +ucpb=60 +unb=6 +umodes=4 +uomin=0 +uomax=0 +uostep=10 +maxcyc=500000

echo "== B: mailbox bridge"
B fwu_mbx mbx60 "-DCPB=60"; B fwu_mbx mbx60f "-DCPB=60 -DFAULT"; B fwu_mbx mbx16 "-DCPB=16"; B fwu_mbx mbx20 "-DCPB=20"; B fwu_mbx mbx28 "-DCPB=28"; B fwu_mbx mbx30 "-DCPB=30"
GREP="MAILBOX|spacing"
t "B1 host to UART, 32 bytes, CPB 60" PASS tb_sys +hex=build/mbx60.hex +uart +uscen=10 +ucpb=60 +unb=32 +maxcyc=1500000
t "B1 fault in the firmware (expected FAIL)" FAIL tb_sys +hex=build/mbx60f.hex +uart +uscen=10 +ucpb=60 +unb=8 +maxcyc=500000
t "B2 UART to host, 16 bytes back to back, CPB 60" PASS tb_sys +hex=build/mbx60.hex +uart +uscen=11 +ucpb=60 +unb=16 +maxcyc=1500000
t "B2 UART to host, 32 bytes, CPB 60, host clock 53 ns: loss (expected FAIL)" FAIL tb_sys +hex=build/mbx60.hex +uart +uscen=11 +ucpb=60 +unb=32 +spihalf=53 +maxcyc=1500000
t "B2 UART to host, 32 bytes, CPB 60, host clock 40 ns" PASS tb_sys +hex=build/mbx60.hex +uart +uscen=11 +ucpb=60 +unb=32 +spihalf=40 +maxcyc=1500000
t "B2 single-command mailbox read, host link before the fix (expected FAIL: race)" FAIL tb_sys_old +hex=build/mbx60.hex +uart +uscen=11 +ucpb=60 +unb=32 +spihalf=40 +umbsingle +maxcyc=1500000
t "B2 single-command mailbox read, CPB 60" PASS tb_sys +hex=build/mbx60.hex +uart +uscen=11 +ucpb=60 +unb=32 +spihalf=40 +umbsingle +maxcyc=1500000
t "B2 single-command read, CPB 28, host clock 40 ns" PASS tb_sys +hex=build/mbx28.hex +uart +uscen=11 +ucpb=28 +unb=48 +spihalf=40 +umbsingle +maxcyc=1500000
t "B2 single-command read, CPB 30, host clock 53 ns: loss (expected FAIL)" FAIL tb_sys +hex=build/mbx30.hex +uart +uscen=11 +ucpb=30 +unb=48 +spihalf=53 +umbsingle +maxcyc=1500000
B fwu_mbx mbx80 "-DCPB=80"
t "B3 both directions at the same time, 32 bytes, CPB 80, 40 ns" PASS tb_sys +hex=build/mbx80.hex +uart +uscen=12 +ucpb=80 +unb=32 +spihalf=40 +maxcyc=2500000
t "B3 both directions, CPB 60: host loses a byte (expected FAIL)" FAIL tb_sys +hex=build/mbx60.hex +uart +uscen=12 +ucpb=60 +unb=32 +spihalf=40 +maxcyc=2500000
t "B4 overflow host to firmware: second byte refused, first kept" PASS tb_sys +hex=build/mbx60.hex +uart +uscen=13 +ucpb=60 +maxcyc=800000
t "B5 overflow firmware to host: first three bytes arrive, overrun" PASS tb_sys +hex=build/mbx60.hex +uart +uscen=14 +ucpb=60 +unb=16 +maxcyc=1500000
t "B6 blind writes, CPB 16, host clock 40 ns (152 cycles per write)" PASS tb_sys +hex=build/mbx16.hex +uart +uscen=15 +ucpb=16 +unb=32 +spihalf=40 +maxcyc=1500000
t "B6 blind writes, CPB 20, host clock 40 ns: refused writes reported by error bit" PASS tb_sys +hex=build/mbx20.hex +uart +uscen=15 +ucpb=20 +unb=32 +spihalf=40 +maxcyc=1500000

echo "== C: UART to WS2812"
B fwu_ws ws60 "-DCPB=60"; B fwu_ws ws60s "-DCPB=60 -DSTREAM"; B fwu_ws ws521 "-DCPB=521"; B fwu_ws ws521s "-DCPB=521 -DSTREAM"
B fwu_ws ws60_f "-DCPB=60 -DT1H_CYC=60"; B fwu_ws ws60_g "-DCPB=60 -DT1H_CYC=54"
GREP="WS2812 model|WS2812 firmware|bytes per"
for o in 0 -3 3; do t "C1 collect, 1 Mbaud, 8 LEDs, UART model offset $o %" PASS tb_sys +hex=build/ws60.hex +uart +ws +uscen=20 +ucpb=60 +unb=8 +uoff=$o +maxcyc=800000; done
t "C1 collect, 1 Mbaud, 60 LEDs, -3 %" PASS tb_sys +hex=build/ws60.hex +uart +ws +uscen=20 +ucpb=60 +unb=60 +uoff=-3 +maxcyc=1500000
t "C2 collect, 115200, 4 LEDs" PASS tb_sys +hex=build/ws521.hex +uart +ws +uscen=20 +ucpb=521 +unb=4 +maxcyc=1500000
t "C2 collect, 1 Mbaud, 8 LEDs, 0.2 ms gap after each byte (slow sender)" PASS tb_sys +hex=build/ws60.hex +uart +ws +uscen=20 +ucpb=60 +unb=2 +ugap=200 +maxcyc=1500000
t "C3 stream, 1 Mbaud, 8 LEDs, 0 % and +3 %" PASS tb_sys +hex=build/ws60s.hex +uart +ws +uscen=20 +ucpb=60 +unb=8 +uoff=3 +maxcyc=800000
t "C3 stream, 1 Mbaud, 60 LEDs, -3 %: overrun (expected FAIL)" FAIL tb_sys +hex=build/ws60s.hex +uart +ws +uscen=20 +ucpb=60 +unb=60 +uoff=-3 +maxcyc=1500000
t "C3 stream, 115200, 4 LEDs: gaps above reset time (expected FAIL)" FAIL tb_sys +hex=build/ws521s.hex +uart +ws +uscen=20 +ucpb=521 +unb=4 +maxcyc=1500000
t "C4 fault: T1H 60 cycles in the firmware (expected FAIL)" FAIL tb_sys +hex=build/ws60_f.hex +uart +ws +uscen=20 +ucpb=60 +unb=2 +maxcyc=500000
t "C4 T1H 54 cycles (48 + 6, inside the tolerance of 9)" PASS tb_sys +hex=build/ws60_g.hex +uart +ws +uscen=20 +ucpb=60 +unb=2 +maxcyc=500000
t "C5 two frames, pause 2 bit times: second frame lost, reported" PASS tb_sys +hex=build/ws60.hex +uart +ws +uscen=21 +ucpb=60 +unb=4 +upause=2 +maxcyc=1500000
t "C5 two frames, pause 130 bit times: both correct" PASS tb_sys +hex=build/ws60.hex +uart +ws +uscen=21 +ucpb=60 +unb=4 +upause=130 +maxcyc=1500000

if [ "$MODE" = "limits" ]; then
  echo "== fine sweeps (limits)"
  GREP="sweep mode [0-9] \("
  for r in "-62 -48 2" "48 62 2"; do set -- $r; t "limits CPB 60, offsets $1..$2 tenths of a percent" PASS tb_sys +hex=build/echo60.hex +uart +uscen=1 +ucpb=60 +maxcyc=2000000 +uomin=$1 +uomax=$2 +uostep=$3; done
fi
echo "failures of expectation: $NFAIL"
