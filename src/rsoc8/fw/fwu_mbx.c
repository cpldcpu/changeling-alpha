/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test B (tb/uart_model.v, scenarios 10 to 14), one core: bridge between the mailbox of the host link
   and a UART (pin 4 receive, pin 5 transmit, 8N1, CPB clock cycles per bit, -DCPB=n).
   A byte from the host (MBSTAT.RXF) goes to the UART transmitter when it can take a frame (LT0STAT.TXE).
   A byte from the UART goes to the mailbox when the host has read the previous one (MBSTAT.TXE); until then
   it stays in the holding register of the receive cell (two frames), further frames are lost (LCS_OVR).
   Counters in RAM for the host: 0x0700 bytes host to UART, 0x0701 bytes UART to host, 0x0702 overrun flags seen. */
#include "rpe.h"
#ifndef CPB
#define CPB 60
#endif
#define PREF(x) ((x) > 256 ? ((x) > 512 ? ((x) > 1024 ? ((x) > 2048 ? 4 : 3) : 2) : 1) : 0)
#define U(x, p) (((x) + (1u << (p)) / 2) >> (p))
#define PRE_T   PREF(CPB)
#define PRE_R   PREF((3 * CPB + 1) / 2)
#define N_M2U (*(volatile uint8_t *)0x0700)
#define N_U2M (*(volatile uint8_t *)0x0701)
#define N_OVR (*(volatile uint8_t *)0x0702)

int main(void)
{
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(5) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = (uint8_t)U(CPB, PRE_T);
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)  = LCH_LEN(8) | LCH_LSBF | LCH_SS;
    LC_REG(LC_T0, LC_RUN) = LCR_IDLE;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN | LCC_PRE(PRE_T);
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(4);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = (uint8_t)U((3 * CPB + 1) / 2, PRE_R);
    LC_REG(LC_R0, LC_B_REG) = (uint8_t)U(CPB, PRE_R);
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = LCH_LEN(8) | LCH_LSBF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_R);
    N_M2U = 0; N_U2M = 0; N_OVR = 0;
    for (;;) {
        if ((MBSTAT & MBS_RXF) && (LT0STAT & LCS_TXE)) {
#ifdef FAULT
            LT0DATA = MBDATA ^ 0x10; N_M2U++;
#else
            LT0DATA = MBDATA; N_M2U++;
#endif
        }
        if ((LR0STAT & LCS_RXF) && (MBSTAT & MBS_TXE)) { MBDATA = LR0DATA; N_U2M++; }
        if (LR0STAT & LCS_OVR) { LR0STAT = LCS_OVR; N_OVR++; }
    }
}
