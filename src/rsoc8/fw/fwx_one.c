/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Stress test 3: one core serves two protocols in one loop (wait_for with the event flags of both pairs).
   Pair 0: UART echo (receive pin RXP, transmit pin TXP, CPB clock cycles per bit).
   Pair 1: SPI slave (pins 0 MOSI, 1 SCK, 2 MISO, 3 CS, 4 ready), NBS bytes per transfer, mode SMODE. The master model sends
   0xA5 + 29 i and expects 0x3C + 53 i. Chip select is taken by the cells (LCCS); the firmware does not poll it.
   The transmit cell of the SPI slave raises EV_LT1 when its buffer has been loaded into the shift register; the next byte is
   written then, so it has a whole byte time. The cells are set up once; after the last byte of a transfer the first byte of
   the next one is loaded.
   Options: BUSY=n (n NOPs per loop), WAITMASK_ONLY (no polling), EXTRAS as in fwx_c0.c is not available here. */
#include "fwx.h"
#ifndef CPB
#define CPB 60
#endif
#ifndef RXP
#define RXP 6
#endif
#ifndef TXP
#define TXP 7
#endif
#ifndef SMODE
#define SMODE 0
#endif
#ifndef NBS
#define NBS 4
#endif
#define PREF(x) ((x) > 256 ? ((x) > 512 ? ((x) > 1024 ? ((x) > 2048 ? ((x) > 4096 ? ((x) > 8192 ? 6 : 5) : 4) : 3) : 2) : 1) : 0)
#define U(x, p) (((x) + (1u << (p)) / 2) >> (p))
#define PRE_T   PREF(CPB)
#define PRE_R   PREF((3 * CPB + 1) / 2)
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
static const uint8_t st[15] = { 0xA0, 0x01, 0x50, 0x20 | CPHA, EDGE | 1, 1, 1, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x40, 0x70 };
static const uint8_t sr[15] = { 0xC0, 0x00, 0x00, 0x30,        EDGE | 1, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x70 };

static inline void tx(uint8_t b) { while (!(LT0STAT & LCS_TXE)) ; LT0DATA = b; }
int main(void)
{
    uint8_t s0, d, rxn = 0, txn = 0, v;
    uint16_t mask;
    PROT_WRITE(LCOWN, 0x00);
    /* UART on pair 0 */
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
    /* SPI slave on pair 1 */
    lc_setup(LC_T1, st); lc_setup(LC_R1, sr);
    LT1DATA = S_BYTE(0); txn = 1;
    PORT |= RDY_PIN; DDR |= RDY_PIN;                        /* ready for the master model */
    for (;;) {
        mask = EV_LR0 | EV_LR1 | (txn < NBS ? EV_LT1 : 0);
        wait_for(mask);
        s0 = LR0STAT;
        if (s0 & LCS_OVR) { LR0STAT = LCS_OVR; tx('#'); ERR0(1); }
        if (s0 & LCS_RXF) { d = LR0DATA; tx(d); X16(R_C0N)++; }
        if (txn < NBS && (LT1STAT & LCS_TXE)) { LT1DATA = S_BYTE(txn); txn++; }
        s0 = LR1STAT;
        if (s0 & LCS_OVR) { LR1STAT = LCS_OVR; ERR1(50); }
        while (LR1STAT & LCS_RXF) {
            v = LR1DATA;
            if (v != M_BYTE(rxn)) ERR1(10 + rxn);
            if (++rxn == NBS) {
                rxn = 0; txn = 0; X16(R_XFERS)++;
                if (LT1STAT & LCS_TXE) { LT1DATA = S_BYTE(0); txn = 1; }
            }
        }
#ifdef BUSY
        { uint8_t j; for (j = 0; j < BUSY; j++) __asm__ __volatile__("nop"); }
#endif
    }
}
