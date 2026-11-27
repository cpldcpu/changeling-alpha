/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Shared between the two images of the USB-to-I2C sensor bridge.
   Core 0: USB low-speed HID device (fwusb.c built with -DSENSOR).
   Core 1: I2C master (fwsens_c1.c). It waits for the interrupt pin of the sensor, reads a sample
   and leaves a complete report packet for core 0.
   Hand-over: three packet buffers (one with core 0, one with the newest report, one being written). RDY names the buffer with the newest complete report, ARMED the
   buffer that core 0 has given to the USB routine. Both are changed only while lock 0 is held. */
#ifndef SENS_H
#define SENS_H
#include "rpe.h"
#define S_RDY    (*(volatile uint8_t *)0x0700)     /* 0 none, 1 to 3: buffer number + 1 */
#define S_ARMED  (*(volatile uint8_t *)0x0701)
#define S_FRAME  (*(volatile uint8_t *)0x0702)     /* frames since the bus reset, counted by core 0 */
#define S_OSC    (*(volatile uint8_t *)0x0703)     /* 1: core 1 has started the oscillator and switched the loop on (-DOSC) */
#define S_CAP    (*(volatile uint16_t *)0x0704)    /* timer capture of the last keep-alive signal (-DOSC); SW0 is set when it is new */
#define S_CUR    ((uint8_t *)0x0750)               /* newest report for GET_REPORT: length 11, identifier DATA1, 8 bytes, CRC-16, then the empty DATA0 packet; written by core 1 */
#define S_BUF(i) ((uint8_t *)(0x0710 + 16 * (i)))  /* packet: identifier, 8 report bytes, CRC-16 */
/* report: bytes 0-5 sample, byte 6 frame count at the interrupt, byte 7 status:
   bit 7 sensor did not acknowledge, bits 6-0 samples dropped since the last report (stops at 127) */
#define SENS_ADDR 0x29
#define SENS_REG  0x01
#define PIN_SDA 0x10
#define PIN_SCL 0x20
#define PIN_INT 0x40
#endif
