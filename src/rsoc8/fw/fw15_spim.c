/* Firmware test 15: SPI master with transmit cell 0 and receive cell 0 against the slave model (+spislv).
   Defines: MODE (0-3), HB (half bit time B in clock cycles, bit time 2 HB), NB (bytes per transfer), NX (transfers),
   CSDLY (clock cycles from chip select to the first data write), CSHOLD (cycles from end of transfer to chip select high).
   Exit code 0 = all bytes received from the model as expected, no overrun. */
#include "fw15.h"
#ifndef MODE
#define MODE 0
#endif
#ifndef HB
#define HB 8
#endif
#ifndef NB
#define NB 1
#endif
#ifndef NX
#define NX 3
#endif
#ifndef CSDLY
#define CSDLY 8
#endif
#ifndef CSHOLD
#define CSHOLD 8
#endif
/*                                CTRL  PIN   OUT   CLK                       TIM   A  B   C  DEC   ENC   SH    MATCH RUN EVM   CS */
static uint8_t mt[15] = { 0xA0, 0x01, 0x13, 0x08, 0x04, 1, HB, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0x00 };
static const uint8_t mr[15] = { 0xC0, 0x40, 0x00, 0x00, 0x02, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x00 };
/* LCCLK of the transmit cell: bit 3 NFN (second output is the bit clock), bit 2 CPOL, bit 1 CPHA; MODE bit 1 = CPOL, bit 0 = CPHA */
int main(void)
{
    uint8_t x, v, sent, got, e = 0;
    uint8_t mb, sb;
    CORECTL = CORE_EN(0);
    mt[3] = 0x08 | ((MODE & 2) ? 0x04 : 0) | ((MODE & 1) ? 0x02 : 0);
    PORT |= CS_PIN; DDR |= CS_PIN;                          /* chip select high */
    lc_setup(LC_T0, mt); lc_setup(LC_R0, mr);
    delay_after(200); wait_for(EV_DLY);
    for (x = 0; x < NX; x++) {
        PORT &= ~CS_PIN;
        if (CSDLY) { delay_after(CSDLY); wait_for(EV_DLY); }
        sent = 0; got = 0; mb = M_BYTE(0); sb = S_BYTE(0);
        LT0DATA = mb; sent = 1; mb += 29;
        while (got < NB) {
            if (sent < NB && (LT0STAT & LCS_TXE)) { LT0DATA = mb; mb += 29; sent++; }
            if (LR0STAT & LCS_RXF) {
                v = LR0DATA; got++;
                if (v != sb && !e) e = 10 + got;
                sb += 53;
            }
        }
        while (LT0STAT & LCS_BUSY) ;
        if (CSHOLD) { delay_after(CSHOLD); wait_for(EV_DLY); }
        PORT |= CS_PIN;
        if (LR0STAT & LCS_OVR) { if (!e) e = 50; LR0STAT = LCS_OVR; }
        delay_after(40); wait_for(EV_DLY);
    }
    EXIT(e);
}
