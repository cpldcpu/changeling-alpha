; directed test, image of core 1
        .text
        .org 0
        rjmp s1
        .org 0x100
        .byte 0xA5, 0x5A, 0x00, 0x00
s1:     ldi r17, 0
t1:     sbi 0x05, 0             ; take lock 0
        sbis 0x05, 0
        rjmp t1
        lds r18, 0x60
        inc r18
        sts 0x60, r18
        cbi 0x05, 0
        ldi r16, 0x99
        sts 0x61, r16
        sbi 0x07, 4             ; SW0
        ldi r16, 0x20
        out 0x21, r16           ; wait mask: SW1
        out 0x20, r17
        sbi 0x05, 3             ; take lock 3 and keep it
        ldi r16, 1
        out 0x30, r16           ; interrupt request 1 of core 0
        in r26, 0x0E
        sts 0x78, r26           ; CORECTL as core 1 reads it
        in r27, 0x05
        sts 0x79, r27           ; LOCK as core 1 reads it
        break
