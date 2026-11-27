/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 12, image of core 0: I2C slave */
#include "fw12.h"
/*                              CTRL  PIN   OUT   CLK   TIM   A  B  C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t rx[15] = { 0xC0, 0x80, 0x00, 0xB0, 0x41, 1, 1, 0, 0xF0, 0x00, 0xE0, 0x00, 0, 0x80, 0 };
static const uint8_t tx[15] = { 0x80, 0x02, 0x80, 0xA0, 0x41, 1, 1, 1, 0x00, 0xF0, 0xE0, 0x00, 0x04, 0x00, 0 };

static void rx_reset(void) { LC_REG(LC_R0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN; }
static void ack(void)
{
    while (PINR & SCL) ;            /* eighth clock ends */
    DDR |= SDA;                     /* SDA low */
    while (!(PINR & SCL)) ;
    while (PINR & SCL) ;            /* ninth clock ends */
}
int main(void)
{
    uint8_t b, p = 0, again = 0;
    CORECTL = CORE_EN(0) | CORE_EN(1);
    PORT &= ~(SDA | SCL);
    ODE = SDA;                                              /* the cell output only pulls SDA low */
    lc_setup(LC_R0, rx); lc_setup(LC_T0, tx);
    PCMSK = SDA;
    for (;;) {
        if (!again) {
            IFRL = EV_PC;
            wait_for(EV_PC | EV_SW0);
            if (IFRH & 0x10) break;                         /* the master has finished */
            p = PINR;
        }
        again = 0;
        if ((p & (SDA | SCL)) != SCL) continue;             /* not a start: SDA low while SCL is high */
        rx_reset();
        wait_for(EV_LR0); b = LR0DATA;
        if ((b >> 1) != ADDR) continue;                     /* not addressed: no acknowledge */
        ack();
        if (b & 1) {                                        /* read: the cell shifts the byte out */
            LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(4) | LCO_OUTEN;      /* the cell takes the pin from the port register */
            LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
            LT0DATA = RDBYTE;
            DDR &= ~SDA;
            rx_reset();
            wait_for(EV_LR0); b = LR0DATA;                  /* eight clocks have passed */
            while (PINR & SCL) ;
            LC_REG(LC_T0, LC_CTRL) = LCC_EN;                /* release SDA for the acknowledge bit of the master */
            LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(4);
            continue;
        }
        DDR &= ~SDA; rx_reset();
        for (;;) {                                          /* write: data bytes until stop or repeated start */
            IFRL = EV_PC;
            wait_for(EV_LR0 | EV_PC);
            if (LR0STAT & LCS_RXF) {
                b = LR0DATA; S_RX[S_NRX] = b; S_NRX++;
                ack();
                DDR &= ~SDA; rx_reset();
                continue;
            }
            p = PINR;
            if (p & SCL) { again = 1; break; }              /* SDA changed while SCL is high: stop or start */
        }
    }
    if (M_DONE != 1) EXIT(M_DONE);
    if (S_NRX != 2 || S_RX[0] != 0x3C || S_RX[1] != 0xC7) EXIT(40 + S_NRX);
    EXIT(0);
}
