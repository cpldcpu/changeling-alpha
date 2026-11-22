; stress test, same source for both cores (@CORE@ = 0 or 1): calls, returns, loads, pops and
; register accesses in a loop, so that every cycle of the multi-cycle instructions meets collisions
        .text
        .org 0
        ldi r17, 0
.if @CORE@ == 0
        ldi r16, 0xD8
        out 0x3C, r16
        ldi r16, @ARB@
        ldi r30, 0x50
        ldi r31, 0x3F
        st Z, r16               ; ARB
        ldi r16, 0x03
        out 0x0E, r16           ; start core 1
        ldi r26, 0x00
        ldi r27, 0x01           ; X = 0x0100
.else
        ldi r26, 0x00
        ldi r27, 0x02           ; X = 0x0200
.endif
        ldi r18, 150
        ldi r24, 0
l:      st X+, r18
        ld r19, -X
        add r24, r19
        rcall f
        push r24
        rcall g
        pop r20
        lds r21, 0x60
        add r21, r20
        sts 0x60, r21           ; shared byte, not protected: the result depends on the interleaving
        ld r22, X+
        in r23, 0x02
        eor r23, r22
        out 0x02, r23
        dec r18
        brne l
        ldi r16, 0xA0 + @CORE@
        sts 0x90 + @CORE@, r16
e:      rjmp e
f:      push r18
        rcall g
        pop r25
        ret
g:      lds r25, 0x61
        inc r25
        sts 0x61, r25
        ret
