/* Firmware test 4: receive a 10BASE-T frame from the testbench generator on pin 1.
   The settings come from the build: -DLCA_VAL, -DLCB_VAL in half clock periods.
   60 MHz clock: 12 samples per bit, A = 9, B = 24.   30 MHz clock: 6 samples per bit, A = 4, B = 12. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define NPAY 24
static uint8_t rxb[NPAY + 2];

int main(void)
{
    uint8_t i, nr = 0, st;
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(1);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_BOTH | LCT_ACC_WAIT | LCT_STOP_SAMPLE;
    LC_REG(LC_R0, LC_A_REG) = LCA_VAL;
    LC_REG(LC_R0, LC_B_REG) = LCB_VAL;
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_INVERT;
    LC_REG(LC_R0, LC_SH)  = 0xE0 | 0x10 | 0x02;
    LC_REG(LC_R0, LC_MATCH) = 0xD5;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF | LCS_IDLE;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_UNIT;
    for (;;) {
        wait_for(EV_LR0);
        st = LR0STAT;
        if (st & LCS_RXF) { if (nr < sizeof rxb) rxb[nr++] = LR0DATA; else EXIT(1); }
        else if (st & LCS_IDLE) { if (nr) break; LR0STAT = LCS_IDLE; }
    }
    if (LR0STAT & LCS_OVR) EXIT(2);
    if (nr != NPAY) EXIT(40 + nr);
    for (i = 0; i < NPAY; i++) if (rxb[i] != (uint8_t)(i * 37 + 11)) EXIT(100 + i);
    EXIT(0);
}
