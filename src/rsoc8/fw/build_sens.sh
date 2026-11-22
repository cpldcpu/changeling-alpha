#!/bin/sh
# builds the two images of the USB-to-I2C sensor bridge: build/fwsens_c0.hex, build/fwsens_c1.hex
# The core 1 image is built first: it holds the descriptor packets (-DDESC_C1), which core 0 reads from code memory 1
# (link symbols taken from the core 1 image); without this, core 0 with the HID class requests does not fit into 2048 bytes.
set -e
mkdir -p build; python3 fw/gen_usb_desc.py fw build > /dev/null
mk() { avr-gcc -mmcu=attiny40 -Os -Wall -Ifw $5 -Wl,--defsym=__RODATA_PM_OFFSET__=$2 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 $3 -o build/$1.elf $4
  avr-objcopy -O binary build/$1.elf build/$1.bin
  python3 -c "b=open('build/$1.bin','rb').read(); b+=b'\0'*(len(b)%2); open('build/$1.hex','w').write('\n'.join('%04x'%(b[i]|b[i+1]<<8) for i in range(0,len(b),2))+'\n'); print('$1:', len(b), 'bytes')"; }
mk fwsens_c1 0x4800 "-Wl,--section-start=.data=0x800440" fw/fwsens_c1.c "-DDESC_C1 $EXTRA1"
SYM=""
for n in usb_pk_device usb_pk_config usb_pk_config9 usb_pk_report usb_pk_zero usb_pk_status usb_pk_val; do
  a=$(avr-nm build/fwsens_c1.elf | awk -v n=$n '$3==n {print $1}')
  [ -n "$a" ] || { echo "symbol $n missing in core 1 image"; exit 1; }
  SYM="$SYM -Wl,--defsym=$n=0x$a"
done
mk fwsens_c0 0x4000 "$SYM" "fw/fwusb.c fw/usb_stack.S" "-DSENSOR -DDESC_C1 $EXTRA0"
