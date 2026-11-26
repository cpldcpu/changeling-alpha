/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 14, one core: frame check of a 10BASE-T frame with the CRC unit.
   The testbench sends a frame with its check sequence and the idle pulse behind it on pin 1
   (+eth=60000 +ethfcs). The CRC unit takes the bits of receive cell 0 behind the start-of-frame
   delimiter and compares with the residual. Built with -DBAD it expects a frame with an error. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define NPAY 24
static uint8_t rxb[NPAY + 6];
int main(void)
{
    uint8_t i, nr = 0, st, cs;
    crc_setup(CRC_RIGHT | CRC_SRC_R0, 31, 0xEDB88320, 0xFFFFFFFF);
    CRCREF0 = 0xE3; CRCREF1 = 0x20; CRCREF2 = 0xBB; CRCREF3 = 0xDE;
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(1);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_BOTH | LCT_ACC_WAIT | LCT_STOP_SAMPLE;
    LC_REG(LC_R0, LC_A_REG) = 9;
    LC_REG(LC_R0, LC_B_REG) = 24;
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_INVERT;
    LC_REG(LC_R0, LC_SH)  = 0xE0 | 0x10 | 0x02;
    LC_REG(LC_R0, LC_MATCH) = 0xD5;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF | LCS_IDLE;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_UNIT;
    for (;;) {
        wait_for(EV_LR0);
        st = LR0STAT;
        if (st & LCS_RXF) { if (nr < sizeof rxb) rxb[nr++] = LR0DATA; else EXIT(1); }
        else if (st & LCS_IDLE) { if (nr) break; LR0STAT = LCS_IDLE; }
    }
    cs = CRCST;
    if (nr != NPAY + 4) EXIT(40 + nr);
#ifdef BAD
    if (cs & CRCST_EQF) EXIT(2);
#else
    if (!(cs & CRCST_EQF)) EXIT(3);
    for (i = 0; i < NPAY; i++) if (rxb[i] != (uint8_t)(i * 37 + 11)) EXIT(100 + i);
#endif
    _IO8(0x1D) = cs;                                        /* the testbench prints the status */
    EXIT(0);
}
