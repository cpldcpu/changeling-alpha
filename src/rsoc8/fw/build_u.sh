#!/bin/sh
# build_u.sh source out "defines"   builds fw/source.c with the defines into build/out.hex (core 0 image)
# example: sh fw/build_u.sh fwu_echo echo60 "-DCPB=60"
set -e
S=$1; O=$2; D=$3
avr-gcc -mmcu=attiny40 -Os -Wall -Ifw $D -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 -o build/$O.elf fw/$S.c $EXTRA
avr-objcopy -O binary build/$O.elf build/$O.bin
python3 -c "
b=open('build/$O.bin','rb').read(); b+=b'\0'*(len(b)%2)
open('build/$O.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n')
print('$O: %d bytes'%len(b))"
