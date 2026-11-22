; directed test, image of core 0: arbitration mode, start of core 1, lock, software flags and
; wait, read and write of the other core's code memory, own code memory as data, SLEEP ended
; by an interrupt that core 1 raises
        .text
        .org 0
        rjmp start
        rjmp isr1
start:  ldi r17, 0
        ldi r16, 0xD8
        out 0x3C, r16           ; unlock
        ldi r16, 2
        ldi r30, 0x50
        ldi r31, 0x3F
        st Z, r16               ; ARB: core 1 wins collisions
        ldi r16, 0x03
        out 0x0E, r16           ; CORECTL: start core 1
t0:     sbi 0x05, 0             ; take lock 0
        sbis 0x05, 0
        rjmp t0
        lds r18, 0x60           ; shared counter
        inc r18
        sts 0x60, r18
        cbi 0x05, 0             ; release
        ldi r16, 0x10
        out 0x21, r16           ; wait mask: SW0
        out 0x20, r17
        cbi 0x07, 4
        lds r19, 0x61           ; written by core 1 before it set SW0
        sts 0x70, r19
        ldi r30, 0x00
        ldi r31, 0x49           ; 0x4900: table in the code memory of core 1
        ld r20, Z+
        ld r21, Z+
        sts 0x71, r20
        sts 0x72, r21
        ldi r22, 0x3C
        st Z, r22               ; store into the code memory of core 1 (0x4902)
        ld r23, Z
        sts 0x73, r23
        ldi r30, 0x80
        ldi r31, 0x41           ; 0x4180: table in the own code memory
        ld r24, Z
        sts 0x74, r24
        ldi r16, 0x80
        out 0x21, r16           ; wait mask: flag 15, never set
        sei
        sbi 0x07, 5             ; SW1: core 1 may raise the interrupt
        sleep
        ldi r25, 0x55
        sts 0x76, r25
        in r26, 0x0E
        sts 0x77, r26           ; CORECTL as core 0 reads it
        cbi 0x05, 3             ; lock 3 is held by core 1: no effect
        in r26, 0x05
        sts 0x7A, r26           ; LOCK as core 0 reads it
end:    rjmp end
isr1:   ldi r20, 0x77
        sts 0x75, r20
        reti
        .org 0x180
        .byte 0x77, 0x00
