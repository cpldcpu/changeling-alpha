/* Firmware test A (UART against an independent model, tb/uart_model.v), one core: echo.
   UART on pin 4 (receive) and pin 5 (transmit); 8 data bits (or 7 data bits and a parity bit: the frame
   is always 8 bits wide and is passed on unchanged), 1 stop bit.
   Receive cell 0 receives the frame. Receive cell 1 on the same pin takes one extra sample per byte:
     default   the level of the stop bit, 9.5 bit times after the start edge; a low level is a framing error
               and the firmware sends '!' after the echo and restarts receive cell 0
     STARTCHK  the level in the middle of the start bit; a high level is a glitch: both cells are restarted
   Receive cell 0 reports an overrun (frame lost, holding register full) with LCS_OVR: the firmware sends '#'.
   Build options (-D): CPB=<clock cycles per bit>, STARTCHK, NORESYNC (no restart after a framing error),
   STALL=<peripheral cycles> (wait before the first byte is read), BUSY=<nops per byte> (slow firmware),
   PARCHK=1 (even) or 2 (odd): the frame is 7 data bits and a parity bit in bit 7; a wrong parity is answered with a
   frame that has a correct parity bit and the data 0x3F ('?') after the echo.
   Timer values of the cells are 8 bit: the cell prescaler PRE divides the time unit by 2^PRE. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#ifndef CPB
#define CPB 60
#endif
#define PREF(x) ((x) > 256 ? ((x) > 512 ? ((x) > 1024 ? ((x) > 2048 ? ((x) > 4096 ? ((x) > 8192 ? 6 : 5) : 4) : 3) : 2) : 1) : 0)
#define U(x, p) (((x) + (1u << (p)) / 2) >> (p))
#define PRE_T   PREF(CPB)                          /* transmit cell */
#define PRE_R   PREF((3 * CPB + 1) / 2)            /* receive cell 0: first sample 1.5 bit times after the edge */
#ifdef STARTCHK
#define A1_CYC  ((CPB + 1) / 2)                    /* middle of the start bit */
#else
#define A1_CYC  ((19 * CPB + 1) / 2)               /* middle of the stop bit: 9.5 bit times */
#endif
#define PRE_S   PREF(A1_CYC)

static inline void tx(uint8_t b) { while (!(LT0STAT & LCS_TXE)) ; LT0DATA = b; }
static void restart_r0(void)
{
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_PRE(PRE_R);               /* RXEN cleared: receiver reset (rule R12) */
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_R);
}
#ifdef STARTCHK
static void restart_r1(void)
{
    LC_REG(LC_R1, LC_CTRL) = LCC_EN | LCC_PRE(PRE_S);
    LC_REG(LC_R1, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_S);
}
#endif

int main(void)
{
    uint8_t st, d;
#ifdef BUSY
    uint8_t j;
#endif
    PROT_WRITE(LCOWN, 0x00);                                       /* both pairs belong to this core */
    /* transmit cell 0: UART on pin 5, start and stop bit, idle high */
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(5) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = (uint8_t)U(CPB, PRE_T);
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)  = LCH_LEN(8) | LCH_LSBF | LCH_SS;
    LC_REG(LC_T0, LC_RUN) = LCR_IDLE;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN | LCC_PRE(PRE_T);
    /* receive cell 0: data frame, first sample 1.5 bit times after the falling edge, then every bit time */
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(4);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = (uint8_t)U((3 * CPB + 1) / 2, PRE_R);
    LC_REG(LC_R0, LC_B_REG) = (uint8_t)U(CPB, PRE_R);
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = LCH_LEN(8) | LCH_LSBF;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_R);
    /* receive cell 1: one sample per byte, a frame of one bit */
    LC_REG(LC_R1, LC_PIN) = LCP_INSEL(4);
    LC_REG(LC_R1, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R1, LC_A_REG) = (uint8_t)U(A1_CYC, PRE_S);
    LC_REG(LC_R1, LC_B_REG) = (uint8_t)U(CPB, PRE_S);
    LC_REG(LC_R1, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R1, LC_SH)  = LCH_LEN(1) | LCH_LSBF;
    LC_REG(LC_R1, LC_EVM) = LCS_RXF;
    LC_REG(LC_R1, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_S);
#ifdef STALL
    delay_after(STALL); wait_for(EV_DLY);
#endif
    for (;;) {
        wait_for(EV_LR0 | EV_LR1);
        st = LR0STAT;
        if (st & LCS_OVR) { LR0STAT = LCS_OVR; tx('#'); }
        if (st & LCS_RXF) {
            d = LR0DATA; tx(d);
#ifdef PARCHK
            {   uint8_t p = d ^ (d >> 4); p ^= p >> 2; p ^= p >> 1;                 /* bit 0: parity of all eight bits */
                if ((p & 1) != (PARCHK == 1 ? 0 : 1)) tx(PARCHK == 1 ? 0x3F : 0xBF);
            }
#endif
        }
        if (LR1STAT & LCS_RXF) {
            d = LR1DATA;
#ifdef STARTCHK
            if (d) { restart_r0(); restart_r1(); }                 /* start bit is high: glitch */
#else
            if (!d) {                                              /* stop bit is low: framing error */
                tx('!');
#ifndef NORESYNC
                restart_r0();
#endif
            }
#endif
        }
#ifdef BUSY
        for (j = 0; j < BUSY; j++) __asm__ __volatile__("nop");
#endif
    }
}
