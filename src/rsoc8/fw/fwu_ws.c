/* Firmware test C (tb/uart_model.v scenarios 20 and 21, tb/ws2812_model.v), one core: UART to WS2812.
   Receive cell 0 receives the UART on pin 4 (8N1, CPB clock cycles per bit, -DCPB=n). Transmit cell 1 sends the
   WS2812 stream on pin 6 (bit period 75 cycles, T0H 24, T1H 48, as in fw10.c).
   Frame on the UART: one byte n (number of LEDs, 1 to 255), then 3 n data bytes.
   Default: the whole frame is collected in RAM first and then sent without gaps (a gap of the WS2812 stream longer
   than the reset time of 3000 cycles would latch the LEDs in the middle of the frame, and the data of the UART
   arrives slower than the LEDs consume it at any rate below 1 Mbaud).
   -DSTREAM: every byte is forwarded as it arrives (needs data at least as fast as the LEDs consume it).
   RAM byte 0x0700 counts the overruns of the UART receive cell. */
#include "rpe.h"
#ifndef CPB
#define CPB 60
#endif
#define PREF(x) ((x) > 256 ? ((x) > 512 ? ((x) > 1024 ? ((x) > 2048 ? 4 : 3) : 2) : 1) : 0)
#define U(x, p) (((x) + (1u << (p)) / 2) >> (p))
#define PRE_R   PREF((3 * CPB + 1) / 2)
#define N_OVR (*(volatile uint8_t *)0x0700)
/*                              CTRL  PIN   OUT   CLK   TIM   A    B    C   DEC   ENC   SH    MATCH RUN EVM   CS */
#ifndef T1H_CYC
#define T1H_CYC 48
#endif
static const uint8_t ctl[15] = { 0xA0, 0x01, 0xD0, 0x00, 0x00, T1H_CYC, 75, 24, 0x00, 0xF0, 0xE4, 0x00, 0, 0x40, 0 };
static uint8_t buf[765] __attribute__((section(".noinit")));   /* not cleared by the start-up code (saves 4000 cycles at start) */

static uint8_t rx(void)
{
    for (;;) {
        if (LR0STAT & LCS_OVR) { LR0STAT = LCS_OVR; N_OVR++; }
        if (LR0STAT & LCS_RXF) return LR0DATA;
        wait_for(EV_LR0);
    }
}
static void ws(uint8_t b) { while (!(LT1STAT & LCS_TXE)) ; LT1DATA = b; }

int main(void)
{
    uint16_t i, total; uint8_t n;
    PROT_WRITE(LCOWN, 0x00);
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(4);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = (uint8_t)U((3 * CPB + 1) / 2, PRE_R);
    LC_REG(LC_R0, LC_B_REG) = (uint8_t)U(CPB, PRE_R);
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = LCH_LEN(8) | LCH_LSBF;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN | LCC_PRE(PRE_R);
    lc_setup(LC_T1, ctl);
    N_OVR = 0;
    for (;;) {
        n = rx();
        total = 3 * (uint16_t)n;
#ifdef STREAM
        for (i = 0; i < total; i++) ws(rx());
#else
        for (i = 0; i < total; i++) buf[i] = rx();
        for (i = 0; i < total; i++) ws(buf[i]);
#endif
    }
}
