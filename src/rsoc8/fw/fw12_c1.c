/* Firmware test 12, image of core 1: I2C master in firmware, about 200 kHz at a 60 MHz core clock */
#define MASTER
#include "fw12.h"
#include "rpe_core1.h"
static void hold(void) { delay_after(150); wait_for(EV_DLY); }
static void start(void) { DDR |= SDA; hold(); DDR |= SCL; hold(); }
static void stop(void)  { DDR |= SDA; hold(); DDR &= ~SCL; hold(); DDR &= ~SDA; hold(); }
static uint8_t bit(uint8_t out)     /* out = 1 releases SDA; returns the level sampled while SCL is high */
{
    uint8_t v;
    if (out) DDR &= ~SDA; else DDR |= SDA;
    hold(); DDR &= ~SCL; hold();
    v = (PINR & SDA) ? 1 : 0;
    DDR |= SCL;
    return v;
}
static uint8_t wr(uint8_t b) { uint8_t i; for (i = 0; i < 8; i++) { bit(b & 0x80); b <<= 1; } return bit(1); }   /* 0 = acknowledged */
static uint8_t rd(uint8_t nack) { uint8_t i, b = 0; for (i = 0; i < 8; i++) b = (b << 1) | bit(1); bit(nack); return b; }

int main(void)
{
    uint8_t e = 1, b;
    hold(); hold();
    start(); if (wr(0x30 << 1)) { if (0) e = 0; } else e = 10;     /* another address: no acknowledge */
    stop();
    start(); if (wr(ADDR << 1)) e = 11;
    if (wr(0x3C)) e = 12;
    if (wr(0xC7)) e = 13;
    stop();
    start(); if (wr((ADDR << 1) | 1)) e = 14;
    b = rd(1); if (b != RDBYTE && e == 1) e = 15;
    stop();
    M_DONE = e;
    IFRH |= 0x10;
    for (;;) wait_for(EV_SW3);
}
