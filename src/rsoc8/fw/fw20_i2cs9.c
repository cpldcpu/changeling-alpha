/* Firmware test 20: the I2C slave of fw18_i2cs.c with the bus condition detector of the receive cell (LCX_BCD) and the
   start of the transmit cell at the shift edge (LCX_ESTR). Against the master model (+i2cm), same transfers as test 18.
   Pins: 4 SDA, 5 SCL (open drain, the model is the master), 6 DONE.
   Differences to test 18:
   - Start and stop come from the flags LCX_STA and LCX_STP of receive cell 0 (event of the cell, LCX_BEV), not from the pin
     change event and a read of the pins. The start resets the receiver, so the address byte needs no restart of the cell.
   - A byte of a read is written to the transmit cell while SCL is still high in the acknowledge clock (or low before it);
     the cell puts out the first bit at the falling edge of SCL. SDA is never changed by the cell while SCL is high.
   The acknowledge is driven through the direction register as before, and the receive cell is restarted after every
   acknowledge clock, because it has counted that clock as a bit.
   Defines: LATEDATA = n: n * 4 core cycles of delay before the first byte of a read is written.
   NOBCD, NOESTR: fault insertion, the test must fail. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define SDA  0x10
#define SCL  0x20
#define DONE 0x40
#define ADDR 0x52
#define S_NRX    (*(volatile uint8_t *)0x0701)
#define S_NADDR  (*(volatile uint8_t *)0x0700)
#define S_NOTH   (*(volatile uint8_t *)0x0702)
#define S_NRD    (*(volatile uint8_t *)0x0703)
#define S_RX     ((volatile uint8_t *)0x0710)
#define R_BYTE(i) ((uint8_t)(0x69 + 3 * (i)))
#ifndef LATEDATA
#define LATEDATA 0
#endif
#ifdef NOESTR
#define TXX 0                       /* fault insertion: the frame starts at the write */
#else
#define TXX LCX_ESTR
#endif
#ifdef NOBCD
#define RXX LCX_BEV                 /* fault insertion: detector off */
#else
#define RXX (LCX_BCD | LCX_BEV)
#endif
/*                                    CTRL  PIN   OUT   CLK   TIM   A  B  C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t rx[15] = { 0xC0, 0x80, 0x00, 0xB0, 0x41, 1, 1, 0, 0xF0, 0x00, 0xE0, 0x00, 0, 0x80, 0 };
static const uint8_t tx[15] = { 0x80, 0x02, 0x80, 0xA0, 0x41, 1, 1, 1, 0x00, 0xF0, 0xE0, 0x00, 0x04, 0x00, 0 };
static uint8_t b;
static void spin(uint8_t n) __attribute__((unused));
static void spin(uint8_t n) { while (n--) __asm__ __volatile__("nop\n\tnop\n\tnop"); }
static void rx_reset(void) { LC_REG(LC_R0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN; }
/* waits for a received byte (returns 0, byte in b) or a bus condition (returns LCX_STA and/or LCX_STP, flags cleared) */
static uint8_t get(void)
{
    uint8_t x;
    for (;;) {
        wait_for(EV_LR0 | EV_PC);
        if (PINR & DONE) EXIT(0);
        if (LR0STAT & LCS_RXF) { b = LR0DATA; return 0; }
        x = LC_REG(LC_R0, LC_X) & (LCX_STA | LCX_STP);
        if (x) { LC_REG(LC_R0, LC_X) = RXX | x; return x; }
    }
}
/* the eighth clock has been received: acknowledge in the ninth, return at its end */
static void ack(void)
{
    while (PINR & SCL) ;
    DDR |= SDA;
    while (!(PINR & SCL)) ;
    while (PINR & SCL) ;
    DDR &= ~SDA;
    rx_reset();
}
int main(void)
{
    uint8_t x, again = 0, i;
    CORECTL = CORE_EN(0);
    PORT &= ~(SDA | SCL);
    DDR &= ~(SDA | SCL | DONE);
    ODE = SDA;
    LC_REG(LC_R0, LC_X) = RXX;
    LC_REG(LC_T0, LC_X) = TXX;
    lc_setup(LC_R0, rx); lc_setup(LC_T0, tx);
    PCMSK = DONE;
    for (;;) {
        if (!again) { x = get(); if (!(x & LCX_STA)) continue; }       /* bytes for other devices and stops are passed over */
        again = 0;
        x = get();                                                      /* address byte; the start has aligned the receiver */
        if (x) { again = (x & LCX_STA) != 0; continue; }
        if ((b >> 1) != ADDR) { S_NOTH++; continue; }
        S_NADDR++;
        if (b & 1) {
            while (PINR & SCL) ;                                        /* eighth clock ends */
            DDR |= SDA;                                                 /* acknowledge */
            LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
#if LATEDATA
            spin(LATEDATA);
#endif
            for (i = 0;; i++) {
                LT0DATA = R_BYTE(i);                                    /* goes out at the next falling edge of SCL */
                while (!(PINR & SCL)) ;
                while (PINR & SCL) ;                                    /* acknowledge clock ends: the cell has started */
                if (i == 0) { LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(4) | LCO_OUTEN; DDR &= ~SDA; }
                rx_reset();
                x = get();                                              /* eight clocks have passed */
                if (x) { again = (x & LCX_STA) != 0; break; }
                S_NRD++;
                while (PINR & SCL) ;                                    /* the cell releases SDA after the eighth falling edge */
                while (!(PINR & SCL)) ;                                 /* acknowledge clock of the master */
                if (PINR & SDA) { while (PINR & SCL) ; rx_reset(); break; }
            }
            LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(4);
            LC_REG(LC_T0, LC_CTRL) = LCC_EN;
            continue;
        }
        ack();
        for (;;) {                                                      /* write: data bytes until stop or repeated start */
            x = get();
            if (x) { again = (x & LCX_STA) != 0; break; }
            if (S_NRX < 32) S_RX[S_NRX] = b;
            S_NRX++;
            ack();
        }
    }
}
