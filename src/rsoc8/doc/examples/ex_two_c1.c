/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Two cores, image of core 1. */
#include "ex_shared.h"
#include "rpe_core1.h"                             /* stack and start-up of an image for core 1 */

int main(void)
{
    uint8_t i;
    for (i = 0; i < 100; i++) {
        lock_take(0);
        SHARED_COUNT++;
        lock_release(0);
    }
    IFRH |= 0x10;                                  /* software flag 0: seen by both cores */
    for (;;) wait_for(EV_SW3);
}
