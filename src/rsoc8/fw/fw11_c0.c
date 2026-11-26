/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 11, image of core 0: SPI slave with pair 0 */
#include "fw11.h"
static uint8_t st[15] = { 0xA0, 0x01, 0x50, 0x20, 0x41, 1, 1, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0x70 };
static uint8_t sr[15] = { 0xC0, 0x00, 0x00, 0x30, 0x41, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x70 };
int main(void)
{
    uint8_t m, i, v;
    CORECTL = CORE_EN(0) | CORE_EN(1);
    for (m = 0; m < 2; m++) {
        LC_REG(LC_T0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = 0;
        st[3] = m ? 0x22 : 0x20; st[4] = sr[4] = m ? 0x81 : 0x41;
        lc_setup(LC_T0, st); lc_setup(LC_R0, sr);
        LT0DATA = S_BYTE(0, m);                             /* first byte before the chip select */
        M_DONE = 0; S_READY = m + 1;
        while (PINR & 0x08) ;                               /* chip select low: the first byte is taken */
        LT0DATA = S_BYTE(1, m);
        for (i = 0; i < NB; i++) {
            wait_for(EV_LR0);
            v = LR0DATA;
            if (i + 2 < NB) LT0DATA = S_BYTE(i + 2, m);
            if (v != M_BYTE(i, m)) EXIT(10 + 10 * m + i);
        }
        while (!M_DONE) ;
        if (M_DONE != 1) EXIT(M_DONE);
        if (LR0STAT & LCS_OVR) EXIT(40 + m);
        while (!(PINR & 0x08)) ;
    }
    EXIT(0);
}
