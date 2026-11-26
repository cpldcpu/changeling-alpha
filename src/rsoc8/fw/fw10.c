/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 10, one core: WS2812 as controller and as LED with forwarding.
   Transmit cell 1 is the controller on pin 0 and sends two pixels of three bytes.
   Receive cell 0 is the first LED on pin 0: it keeps the first three bytes, then transmit cell 0
   forwards every further bit to pin 1 with new timing.
   Receive cell 1 is the second LED on pin 1 and must get the second pixel. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
/*                              CTRL  PIN   OUT   CLK   TIM   A    B    C   DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t ctl[15] = { 0xA0, 0x01, 0x10, 0x00, 0x00, 48,  75,  24, 0x00, 0xF0, 0xE4, 0x00, 0, 0x40, 0 };
static const uint8_t led[15] = { 0xC0, 0x00, 0x00, 0x00, 0x68, 36, 150,   0, 0xF0, 0x00, 0xE0, 0x00, 0, 0x90, 0 };
static const uint8_t fwd[15] = { 0x80, 0x01, 0x30, 0x00, 0x02, 48,  70,  24, 0x00, 0xF0, 0xEC, 0x00, 0, 0x00, 0 };
static const uint8_t px[6] = { 0xFF, 0x00, 0xA5, 0x3C, 0x81, 0x7E };
static uint8_t l1[8], l2[8];

int main(void)
{
    uint8_t nt = 0, n1 = 0, n2 = 0, i, st;
    PROT_WRITE(LCOWN, 0x00);                               /* both pairs belong to this core */
    lc_setup(LC_R0, led); lc_setup(LC_T0, fwd);
    lc_setup(LC_R1, led); LC_REG(LC_R1, LC_PIN) = LCP_INSEL(1);
    lc_setup(LC_T1, ctl);
    for (;;) {
        wait_for(EV_LT1 | EV_LR0 | EV_LR1);
        st = LR0STAT;
        if (st & LCS_RXF) {
            l1[n1 & 7] = LR0DATA;
            if (++n1 == 3) LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;   /* forward from the fourth byte on */
        } else if ((st & LCS_IDLE) && n1) break;                        /* reset time after the data */
        else if (st & LCS_IDLE) LR0STAT = LCS_IDLE;
        if (LR1STAT & LCS_RXF) l2[n2++ & 7] = LR1DATA;
        if (LR1STAT & LCS_IDLE) LR1STAT = LCS_IDLE;
        if (nt < 6 && (LT1STAT & LCS_TXE)) LT1DATA = px[nt++];
        if (nt == 6) LC_REG(LC_T1, LC_EVM) = 0;
    }
    if (n1 != 6) EXIT(10 + n1);
    if (n2 != 3) EXIT(20 + n2);
    for (i = 0; i < 6; i++) if (l1[i] != px[i]) EXIT(30 + i);
    for (i = 0; i < 3; i++) if (l2[i] != px[3 + i]) EXIT(40 + i);
    EXIT(0);
}
