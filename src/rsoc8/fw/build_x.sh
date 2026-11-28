#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# build_x.sh source out core "defines"   builds fw/source.c with the defines into build/out.hex (core 0 or core 1 image)
# example: sh fw/build_x.sh fwx_c0 x_echo 0 "-DROLE_ECHO -DTWO"
set -e
FW=$(dirname "$0")
mkdir -p build
S=$1; O=$2; C=${3:-0}; D=$4
OFF=0x4000; DATA=""
[ "$C" = 1 ] && OFF=0x4800 && DATA="-Wl,--section-start=.data=0x800440"
avr-gcc -mmcu=attiny40 -Os -Wall -I"$FW" $D -Wl,--defsym=__RODATA_PM_OFFSET__=$OFF -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 $DATA -o build/$O.elf "$FW/$S.c" $EXTRA
avr-objcopy -O binary build/$O.elf build/$O.bin
python3 -c "
b=open('build/$O.bin','rb').read(); b+=b'\0'*(len(b)%2)
open('build/$O.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n')
print('$O: %d bytes'%len(b))"
