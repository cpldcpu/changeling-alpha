/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 2, image of core 0: starts core 1, receives the bytes core 1 sends through the
   line cells of pair 1, checks the hand-over through shared memory and software flags, and
   increments a shared counter under a lock at the same time as core 1. Exit code 0 = pass. */
#include "fw2.h"
static const uint8_t expect[NMSG] = { 'd', 'u', 'a', 'l', 0x00, 0xFF, 0x5A, 0xC3 };

int main(void)
{
    uint8_t i;
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(6);                   /* UART receive on pin 6 */
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = 12;
    LC_REG(LC_R0, LC_B_REG) = 8;
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = 0xE0 | 0x10;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN;
    if (CORECTL & CORE_ID) EXIT(1);
    CORECTL = CORE_EN(0) | CORE_EN(1);                      /* start core 1 */

    for (i = 0; i < NMSG; i++) {
        wait_for(EV_LR0);
        if (LR0DATA != expect[i]) EXIT(2);
    }
    if (LT1STAT != 0) EXIT(3);                              /* pair 1 belongs to core 1 */
    if (IFRH & 0x0C) EXIT(7);                               /* and core 0 does not see its event flags */
    LC_REG(LC_T1, LC_B_REG) = 99;                           /* ignored */

    wait_for(EV_SW0);                                       /* core 1 has written the shared byte */
    if (SHARED_FLAG != 0x5A) EXIT(4);
    IFRH &= ~0x10;

    for (i = 0; i < ROUNDS; i++) {                          /* shared counter under lock 0 */
        lock_take(0);
        SHARED_CNT = SHARED_CNT + 1;
        lock_release(0);
    }
    wait_for(EV_SW1);                                       /* core 1 has finished its rounds */
    if (SHARED_CNT != 2 * ROUNDS) EXIT(5);
    if (LOCK != 0) EXIT(6);
    EXIT(0);
}
