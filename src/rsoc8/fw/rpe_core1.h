/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Start-up code for an image that runs on core 1. Include it once in the image and link with
   fw/build.sh name 1.
   - The stack pointer is set to 0x043F.
   - Initialised variables are copied from code memory 1 (data address 0x4800). The copy loop of the
     compiler library reads from 0x4000, which is the code memory of core 0, so it is replaced here. */
#ifndef RPE_CORE1_H
#define RPE_CORE1_H
#include "rpe.h"
void __attribute__((naked, used, section(".init3"))) rpe_core1_stack(void) { SPH = 0x04; SPL = 0x3F; }
void __attribute__((naked, used, section(".init4"))) __do_copy_data(void)
{
    __asm__ __volatile__(
        "ldi r26, lo8(__data_start)\n\t"
        "ldi r27, hi8(__data_start)\n\t"
        "ldi r30, lo8(__data_load_start + 0x4800)\n\t"
        "ldi r31, hi8(__data_load_start + 0x4800)\n\t"
        "ldi r18, hi8(__data_end)\n\t"
        "rjmp 2f\n"
        "1:\tld r19, Z+\n\t"
        "st X+, r19\n"
        "2:\tcpi r26, lo8(__data_end)\n\t"
        "cpc r27, r18\n\t"
        "brne 1b\n");
}
#endif
