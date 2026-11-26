/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 1, one core: UART through a pair of line cells on one pin, time base and wake-up,
   pin change interrupt, software event flags. Exit code 0 = pass. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)

static volatile uint8_t pc_count;
ISR(VEC_PC) { pc_count++; }

static const uint8_t msg[] = { 'r', 'c', 'o', 'r', 'e', '8', 0x00, 0xFF, 0x55, 0xA5 };

int main(void)
{
    uint8_t i;
    /* transmit cell 0: UART on pin 5, 8 clock cycles per bit, start and stop bit, idle high */
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(5) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = 8;
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)  = 0xE0 | 0x10 | 0x01;            /* 8 bits, LSB first, start and stop bit */
    LC_REG(LC_T0, LC_RUN) = 0x04;                           /* idle level high */
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
    /* receive cell 0: UART on pin 5 */
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(5);
    LC_REG(LC_R0, LC_TIM) = LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME;
    LC_REG(LC_R0, LC_A_REG) = 12;
    LC_REG(LC_R0, LC_B_REG) = 8;
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = 0xE0 | 0x10;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN;

    for (i = 0; i < sizeof msg; i++) {
        while (!(LT0STAT & LCS_TXE)) ;
        LT0DATA = msg[i];
        wait_for(EV_LR0);                                   /* stop until the frame has arrived */
        if (!(LR0STAT & LCS_RXF)) EXIT(1);
        if (LR0DATA != msg[i]) EXIT(2);
    }
    if (LR0STAT & (LCS_RXF | LCS_OVR)) EXIT(3);
    if (IFRH & 0x01) EXIT(4);                               /* event flag follows the status */

    /* time base and wake-up time */
    {
        uint16_t t0 = time_now(), t1;
        delay_after(200);
        wait_for(EV_DLY);
        t1 = time_now();
        EXIT((uint8_t)((t1 - t0) >> 2));
        delay_until(t1 - 5);                                /* already past: flag at once */
        if (!(IFRL & 0x80)) EXIT(6);
    }

    /* pin change interrupt on pin 2, driven by the port */
    PCMSK = 0x04; DDR = 0x04; PORT = 0x04;
    for (i = 0; i < 10; i++) __asm__("nop");
    IFRL = EV_PC;                                           /* clear what the set-up caused */
    IERL = EV_PC;
    sei();
    PORT &= ~0x04;
    for (i = 0; i < 10; i++) __asm__("nop");
    PORT |= 0x04;
    for (i = 0; i < 10; i++) __asm__("nop");
    cli();
    if (pc_count != 2) EXIT(7);
    if (!(PINR & 0x04)) EXIT(8);

    /* software flags */
    IFRH |= 0x10;
    if ((IFRH & 0xF0) != 0x10) EXIT(9);
    wait_for(EV_SW0);                                       /* flag is set: no wait */
    IFRH &= ~0x10;
    if (IFRH & 0xF0) EXIT(10);

    /* a core that does not own pair 1 reads zero from its cells */
    if (LT1STAT != 0 || LR1STAT != 0) EXIT(11);
    EXIT(0);
}
