#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# OSCDEF="-DOSC_PROBE" OUT=fwusbop sh fw/build_usbo.sh builds a variant with markers for the testbench (fast I/O 0x1C)
# USB HID device on the internal oscillator (15 MHz, 10 clock cycles per bit): build/${OUT:-fwusbo}.hex
set -e
FW=$(dirname "$0")
mkdir -p build; python3 "$FW/gen_usb_desc.py" "$FW" build > /dev/null
avr-gcc -mmcu=attiny40 -Os -Wall -I"$FW" -DOSC -DUSB_CPB=10 $OSCDEF -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 -o build/${OUT:-fwusbo}.elf "$FW/fwusb.c" "$FW/usb_stack.S"
avr-objcopy -O binary build/${OUT:-fwusbo}.elf build/${OUT:-fwusbo}.bin
OUTN=${OUT:-fwusbo} python3 -c "import os;o=os.environ['OUTN'];b=open('build/'+o+'.bin','rb').read(); b+=b'\0'*(len(b)%2); open('build/${OUT:-fwusbo}.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n'); print('fwusbo:', len(b), 'bytes')"
