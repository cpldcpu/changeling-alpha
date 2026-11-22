/* Scenarios for the timing diagrams of the datasheet. Build with -DSCEN=n, run with +wave=<file>.
   The rates are chosen low in clock cycles per bit so that single clock cycles are visible.
   1 UART, 8 cycles per bit: transmit cell 0 on pin 0, receive cell 0 on the same pin
   2 SPI master mode 0, 8 cycles per bit: MOSI pin 0, SCK pin 1; receive cell 0 samples pin 0
   3 compare mode (pulse width): A 12, B 20, C 5 on pin 0
   4 Manchester, two timer periods of 3 cycles per bit: transmit cell 0, receive cell 1 on pin 0
   5 NRZI with bit stuffing and end sequence (USB low-speed framing at 10 cycles per bit), pins 0 and 1 */
#include "rpe.h"
#define USB_CPB 10
#include "usb.h"
#define MARK(v) (_IO8(0x19) = (v))
static void pause(uint16_t n) { delay_after(n); wait_for(EV_DLY); }

int main(void)
{
    volatile uint8_t d;
#if SCEN == 1
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON; LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(0) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = 8; LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH) = LCH_LEN(8) | LCH_LSBF | LCH_SS; LC_REG(LC_T0, LC_RUN) = LCR_IDLE;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(0);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = 12; LC_REG(LC_R0, LC_B_REG) = 8; LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH) = LCH_LEN(8) | LCH_LSBF; LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN;
    pause(40); LR0STAT = 0x3E;
    MARK(1); pause(6);
    LT0DATA = 0x53;
    wait_for(EV_LR0); d = LR0DATA;
    pause(14); MARK(0);
#elif SCEN == 2
    static const uint8_t mt[15] = { 0xA0, 0x01, 0x13, 0x08, 0x04, 1, 4, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0 };
    static const uint8_t mr[15] = { 0xC0, 0x00, 0x00, 0x00, 0x02, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0 };
    lc_setup(LC_T0, mt); lc_setup(LC_R0, mr);
    pause(40);
    MARK(1); pause(6);
    LT0DATA = 0xA6;
    wait_for(EV_LR0); d = LR0DATA;
    pause(10); MARK(0);
#elif SCEN == 3
    static const uint8_t ws[15] = { 0xA0, 0x01, 0x10, 0x00, 0x00, 12, 20, 5, 0x00, 0xF0, 0xE4, 0, 0, 0x40, 0 };
    lc_setup(LC_T0, ws);
    pause(40);
    MARK(1); pause(6);
    LT0DATA = 0xB0;
    while (!(LT0STAT & LCS_TXE)) ;
    while (LT0STAT & LCS_BUSY) ;
    pause(10); MARK(0);
#elif SCEN == 4
    PROT_WRITE(LCOWN, 0x00);         /* core 0 owns both pairs */
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_BUSY; LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(0) | LCO_OUTEN;
    LC_REG(LC_T0, LC_TIM) = LCT_TWOPH; LC_REG(LC_T0, LC_B_REG) = 3; LC_REG(LC_T0, LC_ENC) = LUT_ENC_MANCH;
    LC_REG(LC_T0, LC_SH) = 0xE0 | 0x10; LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
    LC_REG(LC_R1, LC_PIN) = LCP_INSEL(0) | LCP_INV;
    LC_REG(LC_R1, LC_TIM) = LCT_EDGE_BOTH | LCT_ACC_WAIT | LCT_STOP_SAMPLE;
    LC_REG(LC_R1, LC_A_REG) = 9; LC_REG(LC_R1, LC_B_REG) = 24; LC_REG(LC_R1, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R1, LC_SH) = 0xE0 | 0x10 | 0x02; LC_REG(LC_R1, LC_MATCH) = 0xD5;
    LC_REG(LC_R1, LC_EVM) = LCS_RXF; LC_REG(LC_R1, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_UNIT;
    PORT &= ~1; DDR &= ~1;
    pause(40);
    MARK(1); pause(6);
    LT0DATA = 0x55;                  /* preamble */
    while (!(LT0STAT & LCS_TXE)) ;
    LT0DATA = 0xD5;                  /* start of frame: the match pattern */
    while (!(LT0STAT & LCS_TXE)) ;
    LT0DATA = 0x4B;                  /* first data byte */
    wait_for(EV_LR1); d = LR1DATA;
    pause(30); MARK(0);
#elif SCEN == 5
    static const uint8_t txc[15] = USB_TX(0, 1);
    lc_setup(LC_T0, txc);
    pause(60);
    MARK(1); pause(6);
    LT0DATA = 0xFE;                  /* seven ones in a row: one stuffed bit */
    while (!(LT0STAT & LCS_TXE)) ;
    while (LT0STAT & LCS_BUSY) ;
    pause(12); MARK(0);
#endif
    (void)d;
    _IO8(0x1F) = 0;
    for (;;) ;
}
