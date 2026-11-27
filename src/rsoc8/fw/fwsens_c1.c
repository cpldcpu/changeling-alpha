/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* USB-to-I2C sensor bridge, image of core 1: I2C master in firmware, started by the interrupt pin
   of the sensor (active low, level). Pins: 4 SDA, 5 SCL, 6 interrupt. */
#include "sens.h"
#include "rpe_core1.h"
#if defined(OSC) || defined(DESC_C1)
/* The descriptor packets are in this code memory; core 0 reads them from here (build_sens.sh, build_senso.sh). */
#define USB_DESC_STORAGE __attribute__((used))
#include "usb_desc.h"
#endif
#ifdef OSC
/* Whole chip on the 15 MHz oscillator. This image also holds what core 0 has no room for: the start of
   the oscillator (coarse trim, loop) and the descriptor packets, which core 0 reads from code memory 1. */
#define OSC_WITH_START
#define OSC_WITH_TRACK
#include "oscusb.h"
#endif
#ifdef OSC
#define HOLD 64                      /* 15 MHz: 98 kHz at the fastest bit (HOLD 60 gave 103 kHz) */
#else
#define HOLD 60                      /* half of an SCL period (two holds per bit) in clock cycles, before the code time: 387 kHz at 60 MHz */
#endif
#ifdef OSC
/* Lock tracking of the oscillator: core 0 leaves the capture time of every keep-alive signal and sets SW0.
   It is handled in the idle wait and in every hold of the I2C master, so a read does not interrupt it
   (an I2C clock phase that lasts a little longer is allowed). */
static void trk(void)
{
    if (IFRH & (1 << IFRH_SW0)) { IFRH &= ~(1 << IFRH_SW0); osc_track(S_CAP); }
}
#else
#define trk()
#endif
static void hold(void) { delay_after(HOLD); trk(); wait_for(EV_DLY); }
static void start(void) { DDR &= ~PIN_SDA; hold(); DDR &= ~PIN_SCL; hold(); DDR |= PIN_SDA; hold(); DDR |= PIN_SCL; }
static void stop(void)  { DDR |= PIN_SDA; hold(); DDR &= ~PIN_SCL; hold(); DDR &= ~PIN_SDA; hold(); }
static uint8_t bit(uint8_t out)     /* out = 1 releases SDA; returns SDA while SCL is high */
{
    uint8_t v;
    if (out) DDR &= ~PIN_SDA; else DDR |= PIN_SDA;
    hold(); DDR &= ~PIN_SCL; hold();
    v = (PINR & PIN_SDA) ? 1 : 0;
    DDR |= PIN_SCL;
    return v;
}
static uint8_t wr(uint8_t b) { uint8_t i; for (i = 0; i < 8; i++) { bit(b & 0x80); b <<= 1; } return bit(1); }
static uint8_t rd(uint8_t nack) { uint8_t i, b = 0; for (i = 0; i < 8; i++) b = (uint8_t)(b << 1) | bit(1); bit(nack); return b; }

static uint16_t crc16(uint16_t v, uint8_t b)
{
    uint8_t k;
    v ^= b;
    for (k = 0; k < 8; k++) v = (v & 1) ? (v >> 1) ^ 0xA001 : v >> 1;
    return v;
}

int main(void)
{
    uint8_t drops, i, w, err, t, *p; uint16_t v;
    /* report for GET_REPORT before the first sample: eight zero bytes (the same CRC-16 as the loop below) */
    for (i = 0; i < 16; i++) S_CUR[i] = 0;
    S_CUR[0] = 11; S_CUR[1] = 0x4B; S_CUR[12] = 3; S_CUR[13] = 0xC3;
    v = 0xFFFF;
    for (i = 0; i < 8; i++) v = crc16(v, 0);
    v = ~v; S_CUR[10] = (uint8_t)v; S_CUR[11] = (uint8_t)(v >> 8);
#ifdef OSC
    osc_start();                                            /* core 0 waits for S_OSC */
    S_OSC = 1;
#endif
    PORT &= ~(PIN_SDA | PIN_SCL);                           /* open drain through the direction register */
    PCMSK = PIN_INT;
    for (;;) {
        IFRL = EV_PC;
#ifdef OSC
        trk();
        if (PINR & PIN_INT) wait_for(EV_PC | EV_SW0);
        trk();
#else
        if (PINR & PIN_INT) wait_for(EV_PC);                /* level: read again while the pin is low */
#endif
        if (PINR & PIN_INT) continue;
        t = S_FRAME;
        /* a buffer that is neither with core 0 nor holds the newest complete report */
        lock_take(0);
        w = 0; while (w + 1 == S_ARMED || w + 1 == S_RDY) w++;
        lock_release(0);
        p = S_BUF(w);
        err = 0;
        start();
        if (wr(SENS_ADDR << 1) || wr(SENS_REG)) err = 0x80;
        else {
            start();                                        /* repeated start */
            if (wr((SENS_ADDR << 1) | 1)) err = 0x80;
            else for (i = 0; i < 6; i++) p[1 + i] = rd(i == 5);
        }
        stop();
        if (err) { for (i = 0; i < 6; i++) p[1 + i] = 0; hold(); hold(); }
        p[7] = t;
        v = 0xFFFF;
        for (i = 1; i <= 7; i++) v = crc16(v, p[i]);
        /* The newest complete report stays available to core 0 during the read. If it is still there
           now, it is replaced, and its drop count plus one goes into the new report. */
        lock_take(0);
        drops = 0;
        if (S_RDY) { drops = S_BUF(S_RDY - 1)[8] & 0x7F; if (drops < 127) drops++; }
        p[8] = err | drops;
        v = ~crc16(v, p[8]); p[9] = (uint8_t)v; p[10] = (uint8_t)(v >> 8);
        S_RDY = w + 1;
        lock_release(0);
#ifndef FLT_CUR
        for (i = 1; i < 11; i++) S_CUR[1 + i] = p[i];       /* the report is also the current one for GET_REPORT */
#endif
    }
}
