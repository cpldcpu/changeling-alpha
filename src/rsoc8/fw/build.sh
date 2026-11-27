#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# build.sh name [core]   builds fw/name.c into build/name.hex (16-bit words, one per line)
# EXTRA="fw/file.S ..." adds further source files
set -e
N=$1; C=${2:-0}
# Core 1: code memory at 0x4800 in the data space; its variables start at 0x0440, above its stack
# (0x043F downwards), so that they do not overlap the variables of core 0, which start at 0x0040.
OFF=0x4000; DATA=""
[ "$C" = 1 ] && OFF=0x4800 && DATA="-Wl,--section-start=.data=0x800440"
avr-gcc -mmcu=attiny40 -Os -Wall -Ifw -Wl,--defsym=__RODATA_PM_OFFSET__=$OFF -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 $DATA -o build/$N.elf fw/$N.c $EXTRA
avr-objcopy -O binary build/$N.elf build/$N.bin
python3 -c "
import sys
b=open('build/$N.bin','rb').read(); b+=b'\0'*(len(b)%2)
open('build/$N.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n')
print('$N: %d bytes'%len(b))"
