#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Firmware tests on the system testbench. Needs: iverilog, avr-gcc with avr-libc, python3.
cd "$(dirname "$0")/.."
mkdir -p build
RTL=${RTL:-"rtl/rcore8d.v rtl/rdual.v rtl/rlinecells.v rtl/rlcports.v rtl/revents.v rtl/rtimers.v rtl/rclock.v rtl/rhost.v rtl/rpe_top.v rtl/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"}
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_sys.vvp tb/tb_sys.v $RTL || exit 1
for f in fw1 fw3 fw6 fw7 fw8 fwh; do sh fw/build.sh $f > /dev/null 2>&1; done
sh fw/build.sh fw2_c0 0 > /dev/null 2>&1; sh fw/build.sh fw2_c1 1 > /dev/null 2>&1
echo "fw1 (one core: UART through line cells, time base, pin change interrupt, flags): $(vvp -n build/tb_sys.vvp +hex=build/fw1.hex 2>/dev/null | grep -E 'EXIT|TIMEOUT')"
echo "fw2 (two cores: UART between the cores, shared memory, flags, lock):            $(vvp -n build/tb_sys.vvp +hex0=build/fw2_c0.hex +hex1=build/fw2_c1.hex 2>/dev/null | grep -E 'EXIT|TIMEOUT')"
echo "fw3 (10BASE-T frame at 6 clock cycles per bit, both-edge sampling):              $(vvp -n build/tb_sys.vvp +hex=build/fw3.hex 2>/dev/null | grep -E 'EXIT|TIMEOUT')"
sh fw/build.sh fw5_c0 0 > /dev/null 2>&1; sh fw/build.sh fw5_c1 1 > /dev/null 2>&1
bf4() { avr-gcc -mmcu=attiny40 -Os -Wall -Ifw -DLCA_VAL=$2 -DLCB_VAL=$3 -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -o build/$1.elf fw/fw4.c
        avr-objcopy -O binary build/$1.elf build/$1.bin
        python3 -c "b=open('build/$1.bin','rb').read(); b+=b'\\0'*(len(b)%2); open('build/$1.hex','w').write('\\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\\n')"; }
bf4 fw4_60 9 24; bf4 fw4_30 4 12
r() { vvp -n build/tb_sys.vvp "$@" 2>/dev/null | grep -E 'EXIT|TIMEOUT|PWM|HOST' | tr '\n' ' '; echo; }
printf "fw6 (timer compare and capture, PWM, CRC from software and from line cells):    "; r +hex=build/fw6.hex
printf "fw7 (clocking: dividers, measurement against a reference pin, window, outputs):   "; r +hex=build/fw7.hex +ref=1250000
printf "fw8 (program protection: write enables, limit, lock):                            "; r +hex=build/fw8.hex
printf "fw1 loaded through the host link:                                                "; r +hex=build/fw1.hex +spiload
printf "fw2 (two images) loaded through the host link:                                   "; r +hex0=build/fw2_c0.hex +hex1=build/fw2_c1.hex +spiload
BRK=$(( 0x$(avr-nm build/fwh.elf | awk '$3=="tick"{print $1}') / 2 ))
printf "host link: status, mailbox, halt, memory and register access, step, inject, break: "; r +hex=build/fwh.hex +htest=1 +brk=$BRK +maxcyc=3000000
printf "the same with the core clock enabled every third cycle:                          "; r +hex=build/fwh.hex +htest=1 +brk=$BRK +maxcyc=3000000 +cdiv=3
printf "the same with the core clock enabled every second cycle (reset value):           "; r +hex=build/fwh.hex +htest=1 +brk=$BRK +maxcyc=3000000 +cdiv=2
echo "-- cores at half the clock rate (+cdiv=2), peripherals at the full rate"
printf "fw1: "; r +hex=build/fw1.hex +cdiv=2
printf "fw2: "; r +hex0=build/fw2_c0.hex +hex1=build/fw2_c1.hex +cdiv=2
printf "fw6: "; r +hex=build/fw6.hex +cdiv=2
printf "fw3 (expected to fail with 110: one core cannot serve both directions):  "; r +hex=build/fw3.hex +cdiv=2
printf "fw5 (10BASE-T, one core sends, the other receives):                      "; r +hex0=build/fw5_c0.hex +hex1=build/fw5_c1.hex +cdiv=2
printf "fw4 (10BASE-T receive from a generator, 6 clock cycles per bit):         "; r +hex=build/fw4_60.hex +eth=60000 +ethstart=15000000 +cdiv=2
echo "-- 10BASE-T receive at 3 clock cycles per bit (whole chip at 30 MHz), bit time of the sender -5 %, 0, +5 %"
for e in 28500 30000 31500; do printf "fw4, bit time $e ps: "; r +hex=build/fw4_30.hex +eth=$e +ethstart=15000000; done
python3 tests/tim_test.py 0 100
# USB HID device against the host model (enumeration, faults, reports); about 3 minutes per run
python3 fw/gen_usb_desc.py fw build > /dev/null; EXTRA=fw/usb_stack.S sh fw/build.sh fwusb 0 > /dev/null 2>&1; sh fw/build_sens.sh > /dev/null 2>&1
u() { vvp -n build/tb_sys.vvp "$@" 2>&1 | grep -E "USB PASS|USB errors|FAIL|SENSOR:" | cut -c1-150 | tr '\n' ' '; }
printf "fwusb (USB HID device, enumeration by the host model), divider 1 and 4:  "; u +hex=build/fwusb.hex +usbhost +maxcyc=9000000; u +hex=build/fwusb.hex +usbhost +cdiv=4 +maxcyc=9000000; echo
printf "fwsens (I2C sensor with interrupt line to USB reports), divider 1:       "; u +hex0=build/fwsens_c0.hex +hex1=build/fwsens_c1.hex +usbhost +sensor +maxcyc=14000000; echo
printf "fwsens, short enumeration, divider 2 and 4:                              "; u +hex0=build/fwsens_c0.hex +hex1=build/fwsens_c1.hex +usbhost +sensor +quick +cdiv=2 +maxcyc=14000000; u +hex0=build/fwsens_c0.hex +hex1=build/fwsens_c1.hex +usbhost +sensor +quick +cdiv=4 +maxcyc=14000000; echo
printf "fwusb, HID class requests (GET/SET_REPORT with OUT data stage, GET_CONFIGURATION, GET_IDLE, protocol) and endpoint 0 robustness, short enumeration: "; u +hex=build/fwusb.hex +usbhost +quick +feat +ep0 +maxcyc=20000000; echo
printf "fwsens, the same checks (GET_REPORT returns the report of core 1): "; u +hex0=build/fwsens_c0.hex +hex1=build/fwsens_c1.hex +usbhost +sensor +quick +feat +ep0 +maxcyc=20000000; echo
iverilog -g2005 -o build/tb_sync.vvp tb/tb_sync.v rtl/rlcports.v rtl/rlinecells.v && vvp -n build/tb_sync.vvp | grep -E "PASS|errors"
iverilog -g2005 -o build/tb_clk.vvp tb/tb_clk.v rtl/rclock.v rtl/rlinecells.v && printf "clocking block, two unrelated clocks: " && vvp -n build/tb_clk.vvp | grep -E "PASS|FAIL|errors|shortest" | tr "\n" " "; echo
# protocol firmware with both ends of the link on the chip
for f in fw11 fw12; do sh fw/build.sh ${f}_c0 0 > /dev/null 2>&1; sh fw/build.sh ${f}_c1 1 > /dev/null 2>&1; done
EXTRA=fw/usb_dev.S sh fw/build.sh fw13_c0 0 > /dev/null 2>&1; sh fw/build.sh fw13_c1 1 > /dev/null 2>&1
sh fw/build.sh fw10 > /dev/null 2>&1
printf "fw10 (WS2812 controller, LED with forwarding, second LED):           "; r +hex=build/fw10.hex +maxcyc=40000
printf "fw11 (SPI master and slave, modes 0 and 1), core divider 1 and 2:    "; r +hex0=build/fw11_c0.hex +hex1=build/fw11_c1.hex +maxcyc=80000 | tr '\n' ' '; r +hex0=build/fw11_c0.hex +hex1=build/fw11_c1.hex +maxcyc=80000 +cdiv=2
printf "fw12 (I2C firmware master, slave with line cells), divider 1 and 2:  "; r +hex0=build/fw12_c0.hex +hex1=build/fw12_c1.hex +short=4657 +maxcyc=300000 | tr '\n' ' '; r +hex0=build/fw12_c0.hex +hex1=build/fw12_c1.hex +short=4657 +maxcyc=300000 +cdiv=2
printf "fw13 (USB low-speed host and device), divider 1 and 3:               "; r +hex0=build/fw13_c0.hex +hex1=build/fw13_c1.hex +short=0213 +pd=05 +maxcyc=120000 | tr '\n' ' '; r +hex0=build/fw13_c0.hex +hex1=build/fw13_c1.hex +short=0213 +pd=05 +maxcyc=120000 +cdiv=3
mk13b() { avr-gcc -mmcu=attiny40 -Os -Ifw -DBADTOKEN -Wl,--defsym=__RODATA_PM_OFFSET__=$2 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 $3 -o build/$1.elf $4 2>/dev/null; avr-objcopy -O binary build/$1.elf build/$1.bin
  python3 -c "b=open('build/$1.bin','rb').read(); b+=b'\\0'*(len(b)%2); open('build/$1.hex','w').write('\\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\\n')"; }
mk13b fw13b_c0 0x4000 "" "fw/fw13_c0.c fw/usb_dev.S"; mk13b fw13b_c1 0x4800 "-Wl,--section-start=.data=0x800440" fw/fw13_c1.c
printf "fw13 with a wrong CRC5 in the IN token: the device must not answer:  "; r +hex0=build/fw13b_c0.hex +hex1=build/fw13b_c1.hex +short=0213 +pd=05 +maxcyc=120000
sh fw/build.sh fw14 > /dev/null 2>&1; cp build/fw14.hex build/fw14_good.hex
avr-gcc -mmcu=attiny40 -Os -Ifw -DBAD -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 -o build/fw14_bad.elf fw/fw14.c 2>/dev/null
avr-objcopy -O binary build/fw14_bad.elf build/fw14_bad.bin
python3 -c "b=open('build/fw14_bad.bin','rb').read(); b+=b'\\0'*(len(b)%2); open('build/fw14_bad.hex','w').write('\\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\\n')"
printf "fw14 (10BASE-T frame check with the CRC unit), good frame, then a wrong bit: "; r +hex=build/fw14_good.hex +eth=60000 +ethfcs +ethstart=15000000 +maxcyc=60000 | tr '\n' ' '; r +hex=build/fw14_bad.hex +eth=60000 +ethfcs +ethbad=7 +ethstart=15000000 +maxcyc=60000
# oscillator: the same top level with the oscillator model in place of the stub
sh fw/build.sh fw9 > /dev/null 2>&1
iverilog -g2005 -DSIM -DFUNCTIONAL -DOSCMODEL -o build/tb_sys_osc.vvp tb/tb_sys.v tb/osc_model.v $(echo $RTL | sed 's# rtl/rpe_osc_stub.v##') || exit 1
printf "fw9 (switch to the oscillator, trim loop, clock output), strap low:  "; vvp -n build/tb_sys_osc.vvp +hex=build/fw9.hex +ref=5000000 +maxcyc=400000 2>/dev/null | grep -E 'EXIT|TIMEOUT|PINS' | tr '\n' ' '; echo
printf "fw9, strap high, host link at 1 MHz:                                 "; vvp -n build/tb_sys_osc.vvp +hex=build/fw9.hex +ref=5000000 +maxcyc=400000 +strap +spihalf=500 2>/dev/null | grep -E 'EXIT|TIMEOUT|PINS' | tr '\n' ' '; echo
sh fw/build_usbo.sh > /dev/null 2>&1
printf "fwusbo (USB HID device on the oscillator, trimmed by the keep-alive signal), start -15 %% and +12 %%: "; for e in 0.85 1.12; do vvp -n build/tb_sys_osc.vvp +hex=build/fwusbo.hex +usbhost +oscusb +oscerr=$e +maxcyc=4000000 2>&1 | grep -E "USB PASS|USB errors|FAIL" | cut -c1-120 | tr '\n' ' '; done; echo
sh fw/build_senso.sh > /dev/null 2>&1
printf "fwsenso (two-core sensor bridge on the oscillator, 1 ms frames, HID class requests, endpoint 0): "; vvp -n build/tb_sys_osc.vvp +hex0=build/fwsenso_c0.hex +hex1=build/fwsenso_c1.hex +usbhost +sensor +oscusb +feat +ep0 +maxcyc=25000000 2>&1 | grep -E "USB PASS|USB errors|FAIL|SENSOR:" | cut -c1-120 | tr '\n' ' '; echo
