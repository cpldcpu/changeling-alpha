/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Stress tests, image of core 0. The role is chosen by -D:
     ROLE_ECHO  UART echo on pair 0 (receive pin RXP, transmit pin TXP, CPB clock cycles per bit), no use of pair 1
     ROLE_IDLE  start core 1 and sleep
     ROLE_SPIS  SPI slave on pair 0 (pins 0 MOSI, 1 SCK, 2 MISO, 3 CS, 4 ready), endless transfers of NBS bytes, mode SMODE
   Other options:
     TWO        pair 1 belongs to core 1; this core starts core 1 after its own set-up
     ARBV=n     value written to ARB (0 alternate, 1 core 0 wins, 2 core 1 wins); default: not written
     EXTRAS     PWM on the three PWM pins (top 99, duty 25, 50, 75 cycles) and a periodic compare A event, served by an
                interrupt that takes a time stamp from the time base (OCA_PERIOD, tolerance OCA_TOL)
     WAITOCA    ROLE_ECHO: the stamp is taken in the main loop (wait_for with both flags) instead of an interrupt
     BUSY=n     delay loop of n NOPs per served byte (slow firmware)
   Errors are counted in the shared data memory (fwx.h). */
#include "fwx.h"
#ifndef CPB
#define CPB 60
#endif
#ifndef RXP
#define RXP 4
#endif
#ifndef TXP
#define TXP 5
#endif
#ifndef OCA_PERIOD
#define OCA_PERIOD 997
#endif
#ifndef OCA_TOL
#define OCA_TOL 80
#endif
#define PREF(x) ((x) > 256 ? ((x) > 512 ? ((x) > 1024 ? ((x) > 2048 ? ((x) > 4096 ? ((x) > 8192 ? 6 : 5) : 4) : 3) : 2) : 1) : 0)
#define U(x, p) (((x) + (1u << (p)) / 2) >> (p))
#define PRE_T   PREF(CPB)
#define PRE_R   PREF((3 * CPB + 1) / 2)

#ifdef EXTRAS
static uint16_t last_t, nstamp, nbad, maxdev;
static void stamp(void)
{
    uint16_t t = time_now();
    if (nstamp) {
        int16_t dv = (int16_t)(t - last_t - OCA_PERIOD);
        if (dv < 0) dv = -dv;
        if ((uint16_t)dv > maxdev) { maxdev = dv; X16(R_OCADEV) = dv; }
        if ((uint16_t)dv > OCA_TOL) { nbad++; X16(R_OCABAD) = nbad; }
    }
    last_t = t; nstamp++; X16(R_OCAN) = nstamp;
#ifdef PWMFAULT                                             /* fault insertion: the duty of channel 1 is changed */
    if (nstamp == 20) PWM1 = 60;
#endif
#ifdef OCAFAULT                                             /* fault insertion: one service takes longer than the period */
    if (nstamp == 10) { volatile uint16_t j; for (j = 0; j < 400; j++) ; }
#endif
}
#ifndef WAITOCA
ISR(VEC_OCA) { stamp(); }
#endif
static void extras_init(void)
{
    PWMTOP = 99; PWM0 = 25; PWM1 = 50; PWM2 = 75;
    PWMC = PWMC_EN(0) | PWMC_EN(1) | PWMC_EN(2);
    OCRA = OCA_PERIOD - 1;
#ifdef OCBX
    OCRB = OCA_PERIOD / 2;                                  /* compare B in the middle of the period, served by core 1 */
#endif
    timer_set(0);
    TCR = TCR_RUN | TCR_CTC;
    IFRL = EV_OCA;
#ifndef WAITOCA
    IERL = EV_OCA;
    sei();
#endif
}
#endif

#ifdef ROLE_ECHO
static inline void tx(uint8_t b) { while (!(LT0STAT & LCS_TXE)) ; LT0DATA = b; }
static void cells_init(void)
{
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(TXP) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = (uint8_t)U(CPB, PRE_T);
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)  = LCH_LEN(8) | LCH_LSBF | LCH_SS;
    LC_REG(LC_T0, LC_RUN) = LCR_IDLE;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN | LCC_PRE(PRE_T);
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(RXP);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = (uint8_t)U((3 * CPB + 1) / 2, PRE_R);
    LC_REG(LC_R0, LC_B_REG) = (uint8_t)U(CPB, PRE_R);
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = LCH_LEN(8) | LCH_LSBF;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_R);
}
#endif

#ifdef ROLE_SPIS
#ifndef SMODE
#define SMODE 0
#endif
#ifndef NBS
#define NBS 4
#endif
#define CS_PIN  0x08
#define RDY_PIN 0x10
#if SMODE == 0 || SMODE == 3
#define EDGE 0x40
#else
#define EDGE 0x80
#endif
#if SMODE & 1
#define CPHA 0x02
#else
#define CPHA 0x00
#endif
/*                                CTRL  PIN   OUT   CLK        TIM       A  B  C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t st[15] = { 0xA0, 0x01, 0x50, 0x20 | CPHA, EDGE | 1, 1, 1, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0x70 };
static const uint8_t sr[15] = { 0xC0, 0x00, 0x00, 0x30,        EDGE | 1, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x70 };
#endif


#ifdef ROLE_HOG                                             /* bus hog: an I/O read in nearly every cycle, never waits */
#define HOG16 "in r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\tin r16, 0x00\n\t"
static void hog(void) { for (;;) __asm__ __volatile__(HOG16 HOG16 ::: "r16"); }
#endif
int main(void)
{
#ifdef TWO
    PROT_WRITE(LCOWN, 0x02);                                /* pair 0 core 0, pair 1 core 1 */
#else
    PROT_WRITE(LCOWN, 0x00);
#endif
#ifdef ARBV
    PROT_WRITE(ARB, ARBV);
#endif
#ifdef ROLE_HOG
    CORECTL = CORE_EN(0) | CORE_EN(1);
    hog();
#endif
#ifdef ROLE_IDLE                                            /* core 0 only starts core 1 and sleeps */
    CORECTL = CORE_EN(0) | CORE_EN(1);
    for (;;) wait_for(EV_SW3);
#endif
#ifdef ROLE_ECHO
    {
        uint8_t st, d;
        cells_init();
#ifdef EXTRAS
        extras_init();
#endif
#ifdef TWO
        CORECTL = CORE_EN(0) | CORE_EN(1);
#endif
        for (;;) {
#if defined(EXTRAS) && defined(WAITOCA)
            wait_for(EV_LR0 | EV_OCA);
            if (IFRL & EV_OCA) { IFRL = EV_OCA; stamp(); }
#else
            wait_for(EV_LR0);
#endif
            st = LR0STAT;
            if (st & LCS_OVR) { LR0STAT = LCS_OVR; tx('#'); ERR0(1); }
            if (st & LCS_RXF) {
                d = LR0DATA; tx(d);
                X16(R_C0N)++;
            }
#ifdef BUSY
            { uint8_t j; for (j = 0; j < BUSY; j++) __asm__ __volatile__("nop"); }
#endif
        }
    }
#endif
#ifdef ROLE_SPIS
    {
        uint8_t v, sent, got, sb, mb;
#ifdef EXTRAS
        extras_init();
#endif
#ifdef TWO
        CORECTL = CORE_EN(0) | CORE_EN(1);
#endif
        PORT &= ~RDY_PIN; DDR |= RDY_PIN;
        for (;;) {
            LC_REG(LC_T0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = 0;
            lc_setup(LC_T0, st); lc_setup(LC_R0, sr);
            LT0DATA = S_BYTE(0);
            PORT |= RDY_PIN;
            while (PINR & CS_PIN) ;                         /* chip select low */
            sent = 1; got = 0; sb = S_BYTE(1); mb = M_BYTE(0);
            while (!(PINR & CS_PIN)) {
                if (sent < NBS && (LT0STAT & LCS_TXE)) { LT0DATA = sb; sb += 53; sent++; }
                if (LR0STAT & LCS_RXF) {
                    v = LR0DATA;
                    if (v != mb) ERR0(10 + got);
                    got++; mb += 29;
                }
            }
            PORT &= ~RDY_PIN;
            while (LR0STAT & LCS_RXF) { v = LR0DATA; if (v != mb) ERR0(10 + got); got++; mb += 29; }
            if (LR0STAT & LCS_OVR) { ERR0(50); LR0STAT = LCS_OVR; }
            if (got != NBS) ERR0(60);
            X16(R_C0N)++;
        }
    }
#endif
}
