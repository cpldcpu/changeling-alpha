/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* PWM on output pins 5 to 7 and a periodic event from the 16-bit timer. */
#include "rpe.h"

int main(void)
{
    uint8_t duty = 0;
    PWMTOP = 99;                                   /* period 100 cycles: 600 kHz at 60 MHz */
    PWM0 = 25; PWM1 = 50; PWM2 = 75;               /* high time in cycles */
    PWMC = PWMC_EN(0) | PWMC_EN(1) | PWMC_EN(2);

    OCRA = 59999;                                  /* compare A every 60000 cycles: 1 ms */
    TCR  = TCR_RUN | TCR_CTC;                      /* count, restart at compare A */
    for (;;) {
        IFRL = EV_OCA;                             /* clear the flag */
        wait_for(EV_OCA);                          /* the core stops for the rest of the millisecond */
        PWM0 = duty;                               /* taken over at the next restart of the PWM counter */
        if (++duty == 100) duty = 0;
    }
}
