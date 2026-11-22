; USB low-speed device: one call handles one token and its transaction (reduced AVR core).
;
;   uint8_t usb_poll(struct usb_state *s)
;
; struct usb_state:  0 addr      device address
;                    1 ep0_len   bytes of the packet for the next IN on endpoint 0 (0: answer NAK)
;                    2 ep0_ptr   the packet: identifier, data, CRC-16
;                    4 ep1_len   the same for endpoint 1
;                    5 ep1_ptr
;                    7 dlen      bytes of the last received data packet (identifier, data, CRC)
;                    8 tok[3]    last token
;                   11 data[12]  last data packet
;
; Return value:  0 nothing for this device (other address, wrong CRC, single byte)
;                1 end of packet without a packet (keep-alive, or the start of a bus reset)
;                2 SETUP with its data packet received and acknowledged
;                3 OUT with its data packet received and acknowledged
;                4 IN answered with NAK
;                5 IN on endpoint 0: packet sent and acknowledged by the host
;                6 IN on endpoint 1: packet sent and acknowledged by the host
;
; Before the first call: line cells set up, CRC unit in token mode (usb_crc_token_mode), the sync
; byte in the transmit buffer with the transmitter off, the timer counting every second clock cycle
; and capturing the reference event of receive cell 0.
;
; The CRC unit checks every packet: CRC5 of a token, with the reference value selected by the kind
; of token, and CRC-16 of a data packet (SETUP is followed by DATA0, OUT by DATA1).
; Registers: r16 scratch, r17 zero; r18, r28, r29 are saved.

#define LR0STAT 0x08
#define LR0DATA 0x09
#define LT0STAT 0x0A
#define LT0DATA 0x0B
#define WAITL   0x20
#define WAITH   0x21
#define TCNTL   0x26
#define ICRL    0x28
#define CRCST   0x2A
/* answer 4.1 bit times after the start of the end of packet, in timer counts */
#ifndef USB_CPB
#define USB_CPB 40
#endif
#if USB_CPB == 40
#define T_ANS   82              /* prescaler 2: 164 clock cycles */
#else
#define T_ANS   41              /* 10 clock cycles per bit, prescaler 1 */
#endif

.macro WAIT_RX                  ; wait for an event of receive cell 0, status to r23
    ldi  r16, 0x01
    out  WAITH, r16
    out  WAITL, r17
    in   r23, LR0STAT
.endm
.macro WAIT_TX                  ; wait for the transmit buffer of cell 0
    ldi  r16, 0x02
    out  WAITH, r16
    out  WAITL, r17
.endm
.macro CLR_EOP
    ldi  r16, 0x20
    out  LR0STAT, r16
.endm
.macro CRC5_INIT                ; start value of the CRC5 for the next token (every received bit has changed it)
    ldi  r30, 0x46              ; Z = CRCVAL0 (0x3F46)
    ldi  r31, 0x3F
    ldi  r16, 0x1F
    st   Z, r16
.endm
.macro RXLOOP                   ; bytes to X until the stored end-of-packet flag; then r23 = captured time
1:  WAIT_RX
    sbrs r23, 7
    rjmp 2f
    in   r23, LR0DATA
    st   X+, r23
    rjmp 1b
2:  sbrs r23, 5
    rjmp 1b
    in   r23, ICRL
.endm
.macro PREP                     ; address and value for the start of the answer
    ldi  r30, 0x10              ; Z = LCCTRL of transmit cell 0 (0x3F10)
    ldi  r31, 0x3F
    ldi  r25, 0xA0              ; EN | TXEN
.endm
.macro ANSWER                   ; start the prepared sync byte at the captured time + T_ANS; receiver off
3:  in   r16, TCNTL
    sub  r16, r23
    cpi  r16, T_ANS
    brcs 3b
    st   Z, r25
    ldi  r30, 0x00
    st   Z, r17
.endm
.macro XPTR off                 ; X = s + off
    mov  r26, r28
    mov  r27, r29
    subi r26, lo8(-(\off))
    sbci r27, hi8(-(\off))
.endm

    .text
    .global usb_poll
usb_poll:
    push r28
    push r29
    push r18
    mov  r28, r24
    mov  r29, r25
    ld   r18, Y                 ; device address
    XPTR 8
p_first:
    WAIT_RX
    sbrc r23, 7
    rjmp p_pid
    sbrs r23, 5
    rjmp p_first
    CLR_EOP
    CRC5_INIT
    ldi  r24, 1                 ; end of packet without a packet
    rjmp p_done
p_pid:
    in   r21, LR0DATA           ; packet identifier
p_got:
    st   X+, r21
    ldi  r30, 0x4A              ; Z = CRCREF0: value that a correct token of this kind leaves
    ldi  r31, 0x3F
    ldi  r24, 0x15              ; IN
    cpi  r21, 0x69
    breq 4f
    ldi  r24, 0x1D              ; SETUP
    cpi  r21, 0x2D
    breq 4f
    ldi  r24, 0x05              ; OUT
4:  st   Z, r24
    PREP
p_second:
    WAIT_RX
    sbrc r23, 7
    rjmp 5f
    sbrs r23, 5
    rjmp p_second
    rjmp p_ignore               ; a packet of one byte
5:  in   r20, LR0DATA           ; address and lowest endpoint bit
    st   X+, r20
    RXLOOP
    in   r16, CRCST
    sbrs r16, 7                 ; CRC5 correct at the last byte boundary?
    rjmp p_ignore
    mov  r16, r20
    andi r16, 0x7F
    cp   r16, r18               ; for this device?
    breq 14f
    rjmp p_ignore
14: cpi  r21, 0x69
    breq 15f
    rjmp p_out
15:

    ; ---------------------------------------------------------------- IN
    ANSWER                      ; the sync byte starts; what follows is decided while it is sent
    mov  r30, r28               ; Z = packet slot of the endpoint
    mov  r31, r29
    sbrc r20, 7
    rjmp 6f
    subi r30, lo8(-1)
    sbci r31, hi8(-1)
    rjmp 7f
6:  subi r30, lo8(-4)
    sbci r31, hi8(-4)
7:  ld   r22, Z+                ; number of bytes
    ld   r26, Z+
    ld   r27, Z                 ; X = packet
    cpi  r22, 0
    brne 8f
    WAIT_TX
    ldi  r24, 0x5A              ; NAK
    out  LT0DATA, r24
    rcall p_turn
    ldi  r24, 4
    rjmp p_done
8:  WAIT_TX
    ld   r24, X+
    out  LT0DATA, r24
    dec  r22
    brne 8b
    rcall p_turn
    XPTR 8
9:  WAIT_RX                     ; handshake of the host, or the next token
    sbrc r23, 7
    rjmp 10f
    sbrs r23, 5
    rjmp 9b
    CLR_EOP
    CRC5_INIT
    ldi  r24, 1
    rjmp p_done
10: in   r21, LR0DATA
    cpi  r21, 0xD2              ; ACK?
    breq 11f
    rjmp p_got                  ; no: the packet was not acknowledged, this is the next token
11: WAIT_RX                     ; end of the handshake
    sbrc r23, 7
    in   r16, LR0DATA
    sbrs r23, 5
    rjmp 11b
    CLR_EOP
    CRC5_INIT
    ldi  r24, 5
    sbrc r20, 7
    ldi  r24, 6
    rjmp p_done

    ; ---------------------------------------------------------------- SETUP or OUT: a data packet follows
p_out:
    CLR_EOP
    ldi  r24, 0x97              ; CRC start value for DATA0 behind SETUP
    cpi  r21, 0x2D
    breq 12f
    ldi  r24, 0x1F              ; for DATA1 behind OUT
12: rcall usb_crc_data_mode
    PREP
    XPTR 11
    mov  r22, r26
    RXLOOP
    in   r16, CRCST
#ifdef FLT_NOCRC
    nop                         ; fault insertion: a wrong CRC-16 is accepted
    nop
#else
    sbrs r16, 7                 ; CRC-16 correct?
    rjmp 13f
#endif
    ANSWER
    WAIT_TX
    ldi  r24, 0xD2              ; ACK
    out  LT0DATA, r24
    sub  r26, r22               ; number of bytes received
    mov  r30, r28
    mov  r31, r29
    subi r30, lo8(-7)
    sbci r31, hi8(-7)
    st   Z, r26
    rcall p_turn
    rcall usb_crc_token_mode
    ldi  r24, 2
    cpi  r21, 0x2D
    breq p_done
    ldi  r24, 3
    rjmp p_done
13: CLR_EOP
    rcall usb_crc_token_mode
    ldi  r24, 0
    rjmp p_done

p_ignore:
    CLR_EOP
    CRC5_INIT
    ldi  r24, 0
p_done:
    pop  r18
    pop  r29
    pop  r28
    ret

; after an own packet: wait for its end, receiver on, transmitter off with the next sync byte waiting
p_turn:
    sbic LT0STAT, 5
    rjmp p_turn
    ldi  r30, 0x00
    ldi  r31, 0x3F
    ldi  r24, 0xC0
    st   Z, r24                 ; LCCTRL of receive cell 0: EN | RXEN
    ldi  r30, 0x10
    ldi  r24, 0x80
    st   Z, r24                 ; LCCTRL of transmit cell 0: EN
    out  LT0DATA, r24           ; sync byte
    CRC5_INIT
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

; void usb_crc_data_mode(uint8_t start_low): CRC-16, start value 0xFE00 + start_low, reference 0xB001
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
