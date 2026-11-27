/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* WS2812 controller on pin 0: 8 LEDs, 1.25 us per bit (75 clock cycles at 60 MHz).
   The transmit cell works in compare mode: the output is high for A cycles for a one and for
   C cycles for a zero, and one bit lasts B cycles. */
#include "rpe.h"
#define NLED 8
/*                              CTRL  PIN   OUT   CLK   TIM   A   B   C   DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t ws[15] = { 0xA0, 0x01, 0x10, 0x00, 0x00, 48, 75, 24, 0x00, 0xF0, 0xE4, 0,    0,  0x40, 0 };
static uint8_t grb[3 * NLED];

static void ws_show(void)
{
    uint8_t i;
    for (i = 0; i < 3 * NLED; i++) {
        wait_for(EV_LT0);                 /* buffer empty; the next byte follows without a gap */
        LT0DATA = grb[i];
    }
    while (LT0STAT & LCS_BUSY) ;
    delay_after(4800); wait_for(EV_DLY);  /* reset time: 80 us low */
}

int main(void)
{
    uint8_t i, phase = 0;
    lc_setup(LC_T0, ws);
    for (;;) {
        for (i = 0; i < NLED; i++) {
            grb[3 * i]     = (uint8_t)(i * 32 + phase);      /* green */
            grb[3 * i + 1] = (uint8_t)(255 - i * 32);        /* red */
            grb[3 * i + 2] = phase;                          /* blue */
        }
        ws_show();
        phase++;
    }
}
