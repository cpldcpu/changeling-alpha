/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test (UART with the additional frame bit of the line cells, register LCX, against tb/uart_model.v), one core.
   UART on pin 4 (receive) and pin 5 (transmit), 8 data bits, an additional bit, 1 stop bit. One receive cell, one transmit cell.
   -DPAR=1 (odd) or 2 (even): the cells generate and check the parity. Every character is sent back; after a character
            with a wrong parity (LCS_FERR) the firmware sends '?'.
   -DNINE:  the additional bit is a ninth data bit. The firmware reads it from LCX of the receive cell and writes it to
            LCX of the transmit cell before the data, so the character is sent back with the same ninth bit.
   -DTWOSTOP: 8 data bits, no parity, two stop bits on transmit: the transmit cell sends a ninth data bit that is
            always 1 (LCX_PAR_BIT9 | LCX_X9) before its stop bit. The receive cell has no additional bit.
   -DCPB=<clock cycles per bit> */
#include "rpe.h"
#ifndef CPB
#define CPB 60
#endif
#ifdef NINE
#define XPAR LCX_PAR_BIT9
#define RPAR XPAR
#elif defined(TWOSTOP)
#define XPAR (LCX_PAR_BIT9 | LCX_X9)
#define RPAR 0
#else
#define XPAR PAR
#define RPAR XPAR
#endif
static inline void tx(uint8_t b) { while (!(LT0STAT & LCS_TXE)) ; LT0DATA = b; }
int main(void)
{
    uint8_t st, d;
    PROT_WRITE(LCOWN, 0x00);
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(5) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = CPB;
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)  = LCH_LEN(8) | LCH_LSBF | LCH_SS;
    LC_REG(LC_T0, LC_RUN) = LCR_IDLE;
    LC_REG(LC_T0, LC_X)   = XPAR;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(4);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = (3 * CPB + 1) / 2;
    LC_REG(LC_R0, LC_B_REG) = CPB;
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = LCH_LEN(8) | LCH_LSBF;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_X)   = RPAR;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN;
    for (;;) {
        wait_for(EV_LR0);
        st = LR0STAT;
        if (!(st & LCS_RXF)) continue;
#ifdef NINE
        {   uint8_t x9 = LC_REG(LC_R0, LC_X) & LCX_X9;             /* ninth bit of the oldest frame: read before the data */
            d = LR0DATA;
            while (!(LT0STAT & LCS_TXE)) ;
            LC_REG(LC_T0, LC_X) = XPAR | x9;                       /* taken over with the write of the frame */
            LT0DATA = d;
        }
#else
        d = LR0DATA; tx(d);
        if (st & LCS_FERR) { LR0STAT = LCS_FERR; tx('?'); }
#endif
    }
}
