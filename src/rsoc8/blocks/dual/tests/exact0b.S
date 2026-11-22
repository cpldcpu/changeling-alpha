; exact timing test, image of core 0, variant b: core 1 gets priority and is started; then core 0
; either uses the shared bus continuously (a) or waits for a flag that is never set (b)
        .text
        .org 0
        ldi r17, 0
        ldi r16, 0xD8
        out 0x3C, r16
        ldi r16, 2
        ldi r30, 0x50
        ldi r31, 0x3F
        st Z, r16               ; ARB: core 1 wins collisions
        ldi r28, 0x00
        ldi r29, 0x01
        ldi r20, 0x80
        ldi r16, 0x03
        out 0x0E, r16           ; start core 1
        out 0x21, r20
        out 0x20, r17           ; wait for flag 15
a:      rjmp a
