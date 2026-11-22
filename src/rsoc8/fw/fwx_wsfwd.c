/* Stress test 4b: the chip as a WS2812 LED with forwarding (as fw10.c). Receive cell 0 on pin WSIN keeps the first three bytes of
   a frame; transmit cell 0 forwards every further bit on pin WSOUT with its own pulse widths (T1H 48, T0H 24, minimum period WS_OPER).
   The idle flag of the receive cell (150 clock cycles without an edge after the last bit) ends the frame: the forward cell is
   switched off and the counters are reset. Shared memory: R_XFERS frames completed, R_C0N 16 bit: bytes received in the last
   frame, 0x0730..0x0732 the three kept bytes of the last frame, 0x0733 number of frames with the wrong byte count.
   Options: NBYTES (bytes per frame, default 300), RXMODE (the first three bytes are read by the firmware as they arrive, always). */
#include "fwx.h"
#ifndef WSIN
#define WSIN 0
#endif
#ifndef WSOUT
#define WSOUT 1
#endif
#ifndef NBYTES
#define NBYTES 300
#endif
#ifndef WS_OPER
#define WS_OPER 70
#endif
/*                           CTRL  PIN               OUT   CLK   TIM   A   B    C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t led[15] = { 0xC0, LCP_INSEL(WSIN), 0x00, 0x00, 0x68, 36, 150, 0, 0xF0, 0x00, 0xE0, 0x00, 0, 0x90, 0 };
static const uint8_t fwd[15] = { 0x80, 0x01, 0x10 | LCO_OUTSEL(WSOUT), 0x00, 0x02, 48, WS_OPER, 24, 0x00, 0xF0, 0xEC, 0x00, 0, 0x00, 0 };
int main(void)
{
    uint16_t n = 0; uint8_t st, b;
    PROT_WRITE(LCOWN, 0x00);
    lc_setup(LC_T0, fwd); lc_setup(LC_R0, led);
    for (;;) {
        wait_for(EV_LR0);
        st = LR0STAT;
        if (st & LCS_RXF) {
            b = LR0DATA;
            if (n < 3) X8(0x0730 + n) = b;
            n++;
            if (n == 3) LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
        }
        if (st & LCS_OVR) { LR0STAT = LCS_OVR; ERR0(50); }
        if ((st & LCS_IDLE) && !(st & LCS_RXF)) {
            LR0STAT = LCS_IDLE;
            if (n) {
                LC_REG(LC_T0, LC_CTRL) = LCC_EN;
                X16(R_C0N) = n;
                if (n != NBYTES) X8(0x0733)++;
                X16(R_XFERS)++;
                n = 0;
            }
        }
    }
}
