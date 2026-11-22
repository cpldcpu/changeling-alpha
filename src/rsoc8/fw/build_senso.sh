#!/bin/sh
# USB-to-I2C sensor bridge on the 15 MHz oscillator (two cores): build/fwsenso_c0.hex, build/fwsenso_c1.hex
# Core 1 image is built first: it holds the descriptor packets and the oscillator start; core 0 takes the
# addresses of the packets from it (link symbols).
# EXTRA0 / EXTRA1: further compiler options for core 0 / core 1 (for example -DOSC_PROBE, -DHOLD=24); OUT: name prefix
set -e
mkdir -p build; python3 fw/gen_usb_desc.py fw build > /dev/null
O=${OUT:-fwsenso}
mk() { avr-gcc -mmcu=attiny40 -Os -Wall -Ifw -DOSC -DUSB_CPB=10 -DSENSOR $5 -Wl,--defsym=__RODATA_PM_OFFSET__=$2 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 $3 -o build/$1.elf $4
  avr-objcopy -O binary build/$1.elf build/$1.bin
  python3 -c "b=open('build/$1.bin','rb').read(); b+=b'\0'*(len(b)%2); open('build/$1.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n'); print('$1:', len(b), 'bytes')"; }
mk ${O}_c1 0x4800 "-Wl,--section-start=.data=0x800440" fw/fwsens_c1.c "$EXTRA1"
SYM=""
for n in usb_pk_device usb_pk_config usb_pk_config9 usb_pk_report usb_pk_zero usb_pk_status usb_pk_val; do
  a=$(avr-nm build/${O}_c1.elf | awk -v n=$n '$3==n {print $1}')
  [ -n "$a" ] || { echo "symbol $n missing in core 1 image"; exit 1; }
  SYM="$SYM -Wl,--defsym=$n=0x$a"
done
mk ${O}_c0 0x4000 "$SYM" "fw/fwusb.c fw/usb_stack.S" "$EXTRA0"
