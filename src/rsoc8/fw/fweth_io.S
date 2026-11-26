/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
#include "fweth.h"
#ifndef FAULT
#define FAULT 0
#endif
/* Byte loops of fweth.c. AVRrc: arguments in r25:r24 (pointer) and r23:r22 (count, at least 1). */
#define LT0STAT 0x0A
#define LT0DATA 0x0B
#define CRCIN   0x2A
        .text
/* void tx_bytes(const uint8_t *p, uint16_t n): send n >= 3 bytes through transmit cell 0. A byte is written as soon
   as the transmit buffer is empty (LT0STAT.TXE); the next write has to follow within one byte time, 48 clock cycles.
   After the first byte has started, LCRUN.IDLE of the cell is set, so that the line stays high behind the last bit
   (idle pulse). It is set there and not before the frame, because the line would go high before the first bit. */
        .global tx_bytes
tx_bytes:
        mov  r30, r24
        mov  r31, r25
1:      sbis LT0STAT, 6
        rjmp 1b
        ld   r20, Z+
        out  LT0DATA, r20
        subi r22, 1
        sbci r23, 0
2:      sbis LT0STAT, 6                 /* TXE again: the first byte has started, the cell is busy */
        rjmp 2b
        ldi  r26, 0x1C                  /* LCRUN of transmit cell 0 at 0x3F1C */
        ldi  r27, 0x3F
        ldi  r21, 4                     /* IDLE */
#if FAULT != 5
        st   X, r21
#endif
        rjmp 4f
3:      sbis LT0STAT, 6
        rjmp 3b
4:      ld   r20, Z+
        out  LT0DATA, r20
        subi r22, 1
        sbci r23, 0
        brne 3b
        ret
/* void crc_feed(const uint8_t *p, uint16_t n): write n bytes to CRCIN. The unit needs 4 clock cycles per byte;
   the loop needs 7 core cycles, so no byte is overwritten. */
        .global crc_feed
crc_feed:
        mov  r30, r24
        mov  r31, r25
1:      ld   r20, Z+
        out  CRCIN, r20
        subi r22, 1
        sbci r23, 0
        brne 1b
        ret
/* uint16_t rx_frame(void): polls receive cell 0 and stores the bytes in buf (as long as there is room). Returns the
   number of bytes received (also those that did not fit) when the cell reports IDLE after at least one byte;
   IDLE without a byte is cleared. Loop: about 5 core cycles when idle, 14 per byte. */
#define LR0STAT 0x08
#define LR0DATA 0x09
        .global rx_frame
rx_frame:
        ldi  r26, lo8(frm + 8)
        ldi  r27, hi8(frm + 8)
        clr  r24
        clr  r25
2:      in   r20, LR0STAT
        sbrc r20, 7
        rjmp 3f
        sbrs r20, 4
        rjmp 2b
        mov  r21, r24
        or   r21, r25
        brne 4f
        ldi  r20, 0x10
        out  LR0STAT, r20
        rjmp 2b
4:      ret
3:      in   r21, LR0DATA
        cpi  r24, lo8(BUFSZ)
        ldi  r23, hi8(BUFSZ)
        cpc  r25, r23
        brsh 5f
        st   X+, r21
5:      subi r24, -1
        sbci r25, -1
        rjmp 2b
