/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
; USB low-speed device: receive loop and answer path in assembly (reduced AVR core).
;
; Before a call the sync byte waits in the transmit buffer of cell T0 with the transmitter off
; (LC_T0 LCCTRL = EN, LT0DATA = 0x80), and the timer counts every second clock cycle and captures
; the reference event of receive cell R0 (start of the end of packet).
;
;   uint8_t usb_rx_token(uint8_t *buf, uint16_t pid_answer, uint8_t addr)   pid_answer = answer << 8 | pid
;       Receives one token into buf and checks its CRC5. If the CRC5 is correct, the first byte is
;       pid and the second byte is addr, the sync byte of the answer is started 164 clock cycles
;       after the start of the end of packet, followed by the packet identifier answer; the caller
;       supplies the bytes after it.
;   uint8_t usb_rx_data_ack(uint8_t *buf)
;       Receives a data packet into buf. If the CRC unit reports the residual at the last byte
;       boundary (CRCST.EQF, reference value 0xB001), the handshake ACK is sent. Returns the number of bytes, with bit 7 set if the packet was acknowledged.
;
; Registers: r16 scratch, r17 is zero (compiler convention), r20-r27, r30, r31 may be changed.

#define LR0STAT 0x08
#define LR0DATA 0x09
#define LT0DATA 0x0B
#define WAITL   0x20
#define WAITH   0x21
#define TCNTL   0x26
#define ICRL    0x28
#define CRCST   0x2A
#define T_ANS   82              /* timer counts = 164 clock cycles after the start of the end of packet */

; receive loop: bytes to X until the stored end-of-packet flag; then r23 = captured time
.macro RXLOOP
    ldi  r16, 0x01              ; event of receive cell 0 (high byte of the wait mask)
1:  out  WAITH, r16
    out  WAITL, r17             ; wait
    in   r23, LR0STAT
    sbrs r23, 7                 ; a byte?
    rjmp 2f
    in   r23, LR0DATA
    st   X+, r23
    rjmp 1b
2:  sbrs r23, 5                 ; end of packet?
    rjmp 1b
    in   r23, ICRL
.endm

; start the prepared sync byte at the captured time + T_ANS, switch the receiver off.
; Z and r25 are loaded before the packet (PREP), so that the path behind the end of packet is short.
.macro PREP
    ldi  r30, 0x10              ; Z = LCCTRL of transmit cell 0 (0x3F10)
    ldi  r31, 0x3F
    ldi  r25, 0xA0              ; EN | TXEN
.endm
.macro ANSWER
3:  in   r16, TCNTL
    sub  r16, r23
    cpi  r16, T_ANS
    brcs 3b
    st   Z, r25                 ; the sync byte starts
    ldi  r30, 0x00              ; LCCTRL of receive cell 0: off, the own packet is not received
    st   Z, r17
.endm

    .text
; uint8_t usb_rx_token(uint8_t *buf, uint16_t pid_answer, uint8_t addr)   pid_answer = answer << 8 | pid
;   The CRC unit is in token mode (usb_crc_token_mode). The first byte selects the reference value
;   of the CRC5 for that kind of token. Returns bit 1: CRC5 correct; bit 0: answer started.
    .global usb_rx_token
usb_rx_token:
    push r28
    push r29
    push r18
    mov  r18, r23               ; packet identifier of the answer
    mov  r26, r24
    mov  r27, r25
    ldi  r28, 0x4A              ; Y = CRCREF0 (0x3F4A)
    ldi  r29, 0x3F
    PREP
    ldi  r16, 0x01
0:  out  WAITH, r16
    out  WAITL, r17             ; wait for the first byte
    in   r23, LR0STAT
    sbrc r23, 7
    rjmp 4f
    ldi  r24, 0x20              ; an end of packet without a byte (keep-alive): clear the flag
    out  LR0STAT, r24
    rjmp 0b
4:  in   r21, LR0DATA           ; packet identifier
    st   X+, r21
    ldi  r24, 0x15              ; value that a correct IN token leaves in the CRC register
    cpi  r21, 0x69
    breq 5f
    ldi  r24, 0x1D              ; SETUP
    cpi  r21, 0x2D
    breq 5f
    ldi  r24, 0x05              ; OUT
5:  st   Y, r24
    mov  r28, r26               ; Y = second byte of the buffer
    mov  r29, r27
    RXLOOP
    ldi  r24, 0
    in   r16, CRCST
    sbrs r16, 7                 ; CRC5 correct at the last byte boundary?
    rjmp 8f
    ldi  r24, 2
    cp   r21, r22               ; the expected kind of token?
    brne 8f
    ld   r16, Y
    cp   r16, r20               ; for this address?
    brne 8f
    ANSWER
    ldi  r16, 0x02              ; wait for the transmit buffer of cell 0
    out  WAITH, r16
    out  WAITL, r17
    out  LT0DATA, r18           ; packet identifier of the answer
    ldi  r24, 3
8:  ldi  r25, 0x20
    out  LR0STAT, r25           ; clear the end-of-packet flag
    pop  r18
    pop  r29
    pop  r28
    ret

; void usb_crc_token_mode(void): CRC5, start value 0x1F, bits of receive cell 0
    .global usb_crc_token_mode
usb_crc_token_mode:
    ldi  r30, 0x40              ; Z = CRCCTL (0x3F40)
    ldi  r31, 0x3F
    ldi  r24, 0xC8              ; EN | RIGHT | source receive cell 0
    st   Z+, r24
    ldi  r24, 4
    st   Z+, r24                ; CRCLEN
    ldi  r24, 0x14
    st   Z+, r24                ; CRCPOLY0
    st   Z+, r17                ; CRCPOLY1
    ldi  r30, 0x46
    ldi  r24, 0x1F
    st   Z+, r24                ; CRCVAL0
    st   Z+, r17                ; CRCVAL1
    ldi  r30, 0x4B
    st   Z, r17                 ; CRCREF1
    ret

; void usb_crc_data_mode(uint8_t start_low): CRC-16, start value 0xFE00 + start_low
;   (0x97 for DATA0, 0x1F for DATA1), reference value 0xB001. The source is not changed.
    .global usb_crc_data_mode
usb_crc_data_mode:
    ldi  r30, 0x41              ; Z = CRCLEN (0x3F41)
    ldi  r31, 0x3F
    ldi  r25, 15
    st   Z+, r25
    ldi  r25, 0x01
    st   Z+, r25                ; CRCPOLY0
    ldi  r25, 0xA0
    st   Z+, r25                ; CRCPOLY1
    ldi  r30, 0x46
    st   Z+, r24                ; CRCVAL0
    ldi  r25, 0xFE
    st   Z+, r25                ; CRCVAL1
    ldi  r30, 0x4A
    ldi  r25, 0x01
    st   Z+, r25                ; CRCREF0
    ldi  r25, 0xB0
    st   Z+, r25                ; CRCREF1
    ret

    .global usb_rx_data_ack
usb_rx_data_ack:
    mov  r26, r24
    mov  r27, r25
    mov  r22, r24               ; start of the buffer, for the byte count
    PREP
    RXLOOP
    in   r24, CRCST             ; status of the CRC unit
    sbrs r24, 7                 ; equal to the residual at the last byte boundary?
    rjmp 9f
    ANSWER
    ldi  r16, 0x02              ; wait for the transmit buffer of cell 0
    out  WAITH, r16
    out  WAITL, r17
    ldi  r25, 0xD2              ; packet identifier ACK
    out  LT0DATA, r25
    mov  r24, r26
    sub  r24, r22
    ori  r24, 0x80
    rjmp 8f
9:  mov  r24, r26
    sub  r24, r22
8:  ldi  r25, 0x20
    out  LR0STAT, r25
    ret
