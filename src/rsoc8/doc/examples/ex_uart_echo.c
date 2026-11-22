/* UART echo at 115200 baud, 8N1, with a 60 MHz clock. Receive on pin 4, transmit on pin 5.
   One bit is 520 clock cycles. The cell timers have 8 bits, so both cells use prescaler 4
   (PRE = 2): one bit is 130 time units. */
#include "rpe.h"

int main(void)
{
    uint8_t st;

    /* transmit cell 0: 8 data bits, LSB first, start and stop bit, idle level high */
    LC_REG(LC_T0, LC_PIN)   = LCP_OEM_ON;                    /* pin always driven */
    LC_REG(LC_T0, LC_OUT)   = LCO_OUTSEL(5) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = 130;                           /* bit time */
    LC_REG(LC_T0, LC_ENC)   = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)    = LCH_LEN(8) | LCH_LSBF | LCH_SS;
    LC_REG(LC_T0, LC_RUN)   = LCR_IDLE;
    LC_REG(LC_T0, LC_CTRL)  = LCC_EN | LCC_TXEN | LCC_PRE(2);

    /* receive cell 0: the falling edge of the start bit starts the timer; first sample after
       1.5 bit times, then one sample per bit time; the cell waits for the next edge after 8 bits */
    LC_REG(LC_R0, LC_PIN)   = LCP_INSEL(4);
    LC_REG(LC_R0, LC_TIM)   = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = 195;                           /* 1.5 bit times */
    LC_REG(LC_R0, LC_B_REG) = 130;
    LC_REG(LC_R0, LC_DEC)   = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)    = LCH_LEN(8) | LCH_LSBF;
    LC_REG(LC_R0, LC_EVM)   = LCS_RXF;                       /* event flag while a frame is stored */
    LC_REG(LC_R0, LC_CTRL)  = LCC_EN | LCC_RXEN | LCC_PRE(2);

    for (;;) {
        wait_for(EV_LR0);                                    /* the core stops until a frame has arrived */
        st = LR0STAT;
        if (st & LCS_OVR) LR0STAT = LCS_OVR;                 /* a frame was lost: clear the flag */
        if (st & LCS_RXF) {
            uint8_t c = LR0DATA;
            while (!(LT0STAT & LCS_TXE)) ;
            LT0DATA = c;
        }
    }
}
