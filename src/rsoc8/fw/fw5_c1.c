/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 5, image of core 1: sends a 10BASE-T frame through transmit cell 1 on pin 0 */
#include "rpe.h"
#define NPAY 24
#include "rpe_core1.h"
static uint8_t txb[8 + NPAY];
int main(void)
{
    uint8_t i;
    for (i = 0; i < 7; i++) txb[i] = 0x55;
    txb[7] = 0xD5;
    for (i = 0; i < NPAY; i++) txb[8 + i] = (uint8_t)(i * 37 + 11);
    LC_REG(LC_T1, LC_PIN) = LCP_OEM_BUSY;
    LC_REG(LC_T1, LC_OUT) = LCO_OUTSEL(0) | LCO_OUTEN;
    LC_REG(LC_T1, LC_TIM) = LCT_TWOPH;
    LC_REG(LC_T1, LC_B_REG) = 3;
    LC_REG(LC_T1, LC_ENC) = LUT_ENC_MANCH;
    LC_REG(LC_T1, LC_SH)  = 0xE0 | 0x10;
    LC_REG(LC_T1, LC_EVM) = LCS_TXE;
    LC_REG(LC_T1, LC_CTRL) = LCC_EN | LCC_TXEN;
    for (i = 0; i < sizeof txb; i++) { wait_for(EV_LT1); LT1DATA = txb[i]; }
    for (;;) wait_for(EV_SW3);
}
