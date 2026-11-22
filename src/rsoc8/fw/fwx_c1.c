/* Stress tests, image of core 1 (build with core 1). Role chosen by -D:
     ROLE_SPIM  SPI master on pair 1, pins 0 MOSI, 1 SCK, 2 MISO, 3 CS (port register); endless transfers of NB bytes without a
                pause (HB: half bit time in clock cycles, MODE, CSDLY, CSHOLD, XGAP: cycles from CS high to the next CS low)
     ROLE_I2CM  I2C master in firmware (fw/i2cm.h, pins SDA 4, SCL 5), endless sequence: write 3 bytes, read 4 bytes,
                write 1 byte + repeated start + read 2 bytes (I2C_Q: quarter period in clock cycles)
     ROLE_WSC   WS2812 controller: transmit cell 1 on pin WSP, frames of NLED LEDs (3 NLED bytes) with a gap of GAPC cycles
   Rounds are counted in the shared memory (fwx.h); errors with their first code. */
#include "fwx.h"
#ifdef ROLE_I2CM
#include "i2cm.h"
#endif
#include "rpe_core1.h"

#ifdef OCB_STAMP                                            /* core 1 also serves a timer event: compare B, period OCA_PERIOD, own time stamps */
#ifndef OCA_PERIOD
#define OCA_PERIOD 997
#endif
#ifndef OCA_TOL
#define OCA_TOL 80
#endif
static uint16_t blast_t, bn, bbad, bmax;
ISR(VEC_OCB)
{
    uint16_t t = time_now();
    if (bn) {
        int16_t dv = (int16_t)(t - blast_t - OCA_PERIOD);
        if (dv < 0) dv = -dv;
        if ((uint16_t)dv > bmax) { bmax = dv; X16(R_OCBDEV) = dv; }
        if ((uint16_t)dv > OCA_TOL) { bbad++; X16(R_OCBBAD) = bbad; }
    }
    blast_t = t; bn++; X16(R_OCBN) = bn;
}
static void ocb_init(void) { IFRL = EV_OCB; IERL = EV_OCB; sei(); }
#else
static void ocb_init(void) { }
#endif

#ifdef ROLE_HOG                                             /* bus hog: an I/O read in nearly every cycle, never waits */
#define HOG16 "in r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\t"
static void hog(void) { for (;;) __asm__ __volatile__(HOG16 HOG16 ::: "r16"); }
#endif
#ifdef ROLE_SPIM
#ifndef MODE
#define MODE 0
#endif
#ifndef HB
#define HB 8
#endif
#ifndef NB
#define NB 32
#endif
#ifndef CSDLY
#define CSDLY 8
#endif
#ifndef CSHOLD
#define CSHOLD 8
#endif
#ifndef XGAP
#define XGAP 4
#endif
#define CS_PIN 0x08
/*                                CTRL  PIN   OUT   CLK                       TIM   A  B   C  DEC   ENC   SH    MATCH RUN EVM   CS */
static uint8_t mt[15] = { 0xA0, 0x01, 0x13, 0x08, 0x04, 1, HB, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0x00 };
static const uint8_t mr[15] = { 0xC0, 0x40, 0x00, 0x00, 0x02, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x00 };
int main(void)
{
    uint8_t v, sent, got, mb, sb;
    mt[3] = 0x08 | ((MODE & 2) ? 0x04 : 0) | ((MODE & 1) ? 0x02 : 0);
    ocb_init();
    PORT |= CS_PIN; DDR |= CS_PIN;
    lc_setup(LC_T1, mt); lc_setup(LC_R1, mr);
    delay_after(200); wait_for(EV_DLY);
    for (;;) {
        PORT &= ~CS_PIN;
        if (CSDLY) { delay_after(CSDLY); wait_for(EV_DLY); }
        sent = 0; got = 0; mb = M_BYTE(0); sb = S_BYTE(0);
        LT1DATA = mb; sent = 1; mb += 29;
        while (got < NB) {
            if (sent < NB && (LT1STAT & LCS_TXE)) {
#ifdef SPIBAD                                               /* fault insertion: one wrong byte */
                LT1DATA = (sent == 5) ? mb ^ 0x10 : mb; mb += 29; sent++;
#else
                LT1DATA = mb; mb += 29; sent++;
#endif
            }
            if (LR1STAT & LCS_RXF) {
                v = LR1DATA; got++;
                if (v != sb) ERR1(10 + got);
                sb += 53;
            }
        }
        while (LT1STAT & LCS_BUSY) ;
        if (CSHOLD) { delay_after(CSHOLD); wait_for(EV_DLY); }
        PORT |= CS_PIN;
        if (LR1STAT & LCS_OVR) { ERR1(50); LR1STAT = LCS_OVR; }
        X16(R_XFERS)++;
        if (XGAP) { delay_after(XGAP); wait_for(EV_DLY); }
    }
}
#endif

#ifdef ROLE_I2CM
#ifndef ADDR
#define ADDR 0x52
#endif
static uint8_t buf[4];
static uint8_t seq(void)
{
    uint8_t i, e;
    i2c_start(); if (i2c_err) return 1;
    e = i2c_wr(ADDR << 1); if (e) { if (e == I2C_NACK) i2c_stop(); return 2 + 10 * e; }
    for (i = 0; i < 3; i++) { e = i2c_wr(I2C_W_BYTE(i)); if (e) { if (e == I2C_NACK) i2c_stop(); return 3 + 10 * e; } }
    i2c_stop();
    i2c_start(); if (i2c_err) return 4;
    e = i2c_wr((ADDR << 1) | 1); if (e) return 5 + 10 * e;
    for (i = 0; i < 4; i++) buf[i] = i2c_rd(i == 3);
    i2c_stop(); if (i2c_err) return 6;
    for (i = 0; i < 4; i++) if (buf[i] != I2C_R_BYTE(i)) return 30 + i;
    i2c_start(); if (i2c_err) return 7;
    e = i2c_wr(ADDR << 1); if (e) return 8 + 10 * e;
    e = i2c_wr(I2C_W_BYTE(0)); if (e) return 9 + 10 * e;
    i2c_restart(); if (i2c_err) return 10;
    e = i2c_wr((ADDR << 1) | 1); if (e) return 11 + 10 * e;
    for (i = 0; i < 2; i++) buf[i] = i2c_rd(i == 1);
    i2c_stop(); if (i2c_err) return 12;
    for (i = 0; i < 2; i++) if (buf[i] != I2C_R_BYTE(i)) return 34 + i;
    return 0;
}
int main(void)
{
    uint8_t e;
    ocb_init();
    PORT &= ~(SDA | SCL); DDR &= ~(SDA | SCL);
    delay_after(100); wait_for(EV_DLY);
    for (;;) {
        e = seq();
        if (e) { ERR1(e); i2c_recover(); } else X16(R_XFERS)++;
    }
}
#endif

#ifdef ROLE_WSC
#ifndef WSP
#define WSP 6
#endif
#ifndef NLED
#define NLED 8
#endif
#ifndef GAPC
#define GAPC 4000
#endif
#ifndef WS_T1H
#define WS_T1H 48
#endif
#ifndef WS_PER
#define WS_PER 75
#endif
#ifndef WS_T0H
#define WS_T0H 24
#endif
/*                              CTRL  PIN   OUT                          CLK   TIM   A       B       C       DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t ctl[15] = { 0xA0, 0x01, 0x10 | LCO_OUTSEL(WSP), 0x00, 0x00, WS_T1H, WS_PER, WS_T0H, 0x00, 0xF0, 0xE4, 0x00, 0, 0x40, 0 };
static inline uint8_t wsb(uint16_t k) { return (uint8_t)((k * 53 + 7) ^ (k >> 2)); }
int main(void)
{
    uint16_t k;
    lc_setup(LC_T1, ctl);
    delay_after(200); wait_for(EV_DLY);
    for (;;) {
        for (k = 0; k < 3 * NLED; k++) {
            while (!(LT1STAT & LCS_TXE)) ;
            LT1DATA = wsb(k);
        }
        while (LT1STAT & LCS_BUSY) ;
        delay_after(GAPC); wait_for(EV_DLY);
        X16(R_XFERS)++;
    }
}
#endif

#ifdef ROLE_HOG
int main(void) { hog(); }
#endif
