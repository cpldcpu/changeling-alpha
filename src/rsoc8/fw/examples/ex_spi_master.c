/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* SPI master, mode 0, 16 clock cycles per bit (3.75 MHz at 60 MHz). MOSI pin 0, SCK pin 1,
   MISO pin 2, chip select pin 3 from the port register. */
#include "rpe.h"
#define CS_PIN 0x08
/*                             CTRL  PIN   OUT   CLK   TIM   A  B  C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t mt[15] = { 0xA0, 0x01, 0x13, 0x08, 0x04, 1, 8, 1, 0x00, 0xF0, 0xE0, 0,    0,  0x00, 0 };
static const uint8_t mr[15] = { 0xC0, 0x40, 0x00, 0x00, 0x02, 1, 1, 0, 0xF0, 0x00, 0xE0, 0,    0,  0x80, 0 };
/* transmit cell: true output MOSI on pin 0, second output is the bit clock on pin 1, two timer
   periods of 8 cycles per bit. receive cell: samples pin 2 in the middle of each transmitted bit. */

static void spi_transfer(const uint8_t *out, uint8_t *in, uint8_t n)
{
    uint8_t sent = 0, got = 0;
    PORT &= ~CS_PIN;
    while (got < n) {
        if (sent < n && (LT0STAT & LCS_TXE)) LT0DATA = out[sent++];   /* next byte follows without a gap */
        if (LR0STAT & LCS_RXF) in[got++] = LR0DATA;
    }
    while (LT0STAT & LCS_BUSY) ;
    PORT |= CS_PIN;
}

int main(void)
{
    static const uint8_t cmd[4] = { 0x9F, 0x00, 0x00, 0x00 };
    uint8_t id[4];
    PORT |= CS_PIN; DDR |= CS_PIN;
    lc_setup(LC_T0, mt); lc_setup(LC_R0, mr);
    spi_transfer(cmd, id, 4);
    for (;;) wait_for(EV_SW0);
}
