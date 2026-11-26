/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
; exact timing test, image of core 1: a loop that uses the shared bus in most instructions
        .text
        .org 0
        ldi r26, 0x80
        ldi r27, 0x00
        ldi r18, 60
l:      st X+, r18
        ld r19, -X
        push r19
        pop r20
        rcall f
        in r21, 0x02
        sbi 0x04, 1
        dec r18
        brne l
        break
f:      ret
