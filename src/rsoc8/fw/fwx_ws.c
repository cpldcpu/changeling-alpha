/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Stress test 4a: the chip as WS2812 controller. Transmit cell 0 on pin WSP sends frames of NLED LEDs (3 NLED bytes, data ws_pat(k)
   as in tb/uart_model.v) without a gap between the bytes; between the frames the line is low for GAPC clock cycles (more than the
   reset time of 3000). One core, endless. Rounds (frames) are counted at R_XFERS.
   WS_T1H, WS_PER, WS_T0H: timing of the cell in clock cycles (48, 75, 24). */
#include "fwx.h"
#ifndef WSP
#define WSP 6
#endif
#ifndef NLED
#define NLED 100
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
    PROT_WRITE(LCOWN, 0x00);
    lc_setup(LC_T0, ctl);
    delay_after(200); wait_for(EV_DLY);
    for (;;) {
        for (k = 0; k < 3 * NLED; k++) {
            while (!(LT0STAT & LCS_TXE)) ;
            LT0DATA = wsb(k);
        }
        while (LT0STAT & LCS_BUSY) ;
        delay_after(GAPC); wait_for(EV_DLY);
        X16(R_XFERS)++;
    }
}
