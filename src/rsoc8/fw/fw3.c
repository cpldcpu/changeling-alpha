/* Firmware test 3, one core with both pairs: a 10BASE-T frame at 6 clock cycles per bit.
   Transmit cell 0 sends Manchester code on pin 0; receive cell 1 samples the same pin on both
   clock edges, finds the start-of-frame delimiter and delivers the bytes. The core feeds the
   transmitter and empties the receiver at the same time, one byte every 48 clock cycles. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define NPAY 24
static uint8_t txb[8 + NPAY], rxb[NPAY + 2];

int main(void)
{
    uint8_t i, nt = 0, nr = 0, st;
    for (i = 0; i < 7; i++) txb[i] = 0x55;
    txb[7] = 0xD5;
    for (i = 0; i < NPAY; i++) txb[8 + i] = (uint8_t)(i * 37 + 11);

    LCOWN = 0x00;                                           /* without the unlock sequence: ignored */
    if (LCOWN != 0x02) EXIT(9);
    CCP_UNLOCK();
    LCOWN = 0x00;                                           /* core 0 owns both pairs */
    if (LCOWN != 0x00) EXIT(10);

    LC_REG(LC_T0, LC_PIN) = LCP_OEM_BUSY;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(0) | LCO_OUTEN;
    LC_REG(LC_T0, LC_TIM) = LCT_TWOPH;
    LC_REG(LC_T0, LC_B_REG) = 3;                            /* half a bit = 3 clock cycles */
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_MANCH;
    LC_REG(LC_T0, LC_SH)  = 0xE0 | 0x10;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;

    LC_REG(LC_R1, LC_PIN) = LCP_INSEL(0) | LCP_INV;         /* idle line reads low */
    LC_REG(LC_R1, LC_TIM) = LCT_EDGE_BOTH | LCT_ACC_WAIT | LCT_STOP_SAMPLE;
    LC_REG(LC_R1, LC_A_REG) = 9;                            /* 0.75 bit in half clock periods */
    LC_REG(LC_R1, LC_B_REG) = 24;                           /* timeout: 2 bits */
    LC_REG(LC_R1, LC_DEC) = LUT_DEC_LEVEL;                  /* inverted input, so level decoding */
    LC_REG(LC_R1, LC_SH)  = 0xE0 | 0x10 | 0x02;             /* 8 bits, LSB first, match */
    LC_REG(LC_R1, LC_MATCH) = 0xD5;
    LC_REG(LC_R1, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_UNIT;

    for (;;) {
        if (nt < sizeof txb && (LT0STAT & LCS_TXE)) LT0DATA = txb[nt++];
        st = LR1STAT;
        if (st & LCS_RXF) { if (nr < sizeof rxb) rxb[nr++] = LR1DATA; else EXIT(1); }
        else if ((st & LCS_IDLE) && nt == sizeof txb) break;
    }
    if (LR1STAT & (LCS_OVR | LCS_STUFF)) EXIT(2);
    if (!(LR1STAT & LCS_MATCH)) EXIT(3);
    if (nr != NPAY) EXIT(40 + nr);
    for (i = 0; i < NPAY; i++) if (rxb[i] != txb[8 + i]) EXIT(100 + i);
    EXIT(0);
}
