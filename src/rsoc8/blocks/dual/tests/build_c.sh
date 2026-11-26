#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# usage: build_c.sh <part>   -> build/c<part>.hex (16-bit words)
set -e
P=$1
avr-gcc -mmcu=attiny40 -Os -Wall -DPART=$P -I tests tests/ctest.c -o build/c$P.elf
avr-objcopy -O binary -j .text -j .rodata -j .data build/c$P.elf build/c$P.bin
python3 -c "
import sys
b=open('build/c$P.bin','rb').read()
if len(b)%2: b+=b'\0'
open('build/c$P.hex','w').write('\n'.join('%02x%02x'%(b[i+1],b[i]) for i in range(0,len(b),2))+'\n')
print('part $P:',len(b),'bytes')"
