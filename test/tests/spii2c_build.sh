#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# builds one image: spii2c_build.sh <source name without .c> <output name> [defines...]  (core 0, one image)
cd "$(dirname "$0")/.."
FW=../src/rsoc8/fw
mkdir -p build
N=$1; O=$2; shift 2
avr-gcc -mmcu=attiny40 -Os -Wall -I"$FW" "$@" -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 -o build/$O.elf "$FW/$N.c" $EXTRA || exit 1
avr-objcopy -O binary build/$O.elf build/$O.bin
python3 -c "
b=open('build/$O.bin','rb').read(); b+=b'\0'*(len(b)%2)
open('build/$O.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n')
print('$O: %d bytes'%len(b))"
