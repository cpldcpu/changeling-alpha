/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Two cores, image of core 0: starts core 1; both cores add to one counter under a lock;
   core 1 reports with a software event flag. */
#include "ex_shared.h"

int main(void)
{
    uint8_t i;
    SHARED_COUNT = 0;
    CORECTL = CORE_EN(0) | CORE_EN(1);             /* core 1 starts at address 0 of its code memory */
    for (i = 0; i < 100; i++) {
        lock_take(0);                              /* waits until the lock is free */
        SHARED_COUNT++;
        lock_release(0);
    }
    wait_for(EV_SW0);                              /* set by core 1 when it has finished */
    IFRH &= (uint8_t)~0x10;                        /* clear software flag 0 */
    /* SHARED_COUNT is 200 here */
    for (;;) wait_for(EV_SW1);
}
