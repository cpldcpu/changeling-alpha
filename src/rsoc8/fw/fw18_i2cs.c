/* Firmware test 18: I2C slave with line cells (the slave of fw12_c0.c, extended) against the master model (+i2cm).
   One core. Pins: 4 SDA, 5 SCL (open drain, the model is the master), 6 DONE (driven by the model, rises at the end of the
   test). Receive cell 0 is clocked by SCL and takes the eight bits of a byte, transmit cell 0 shifts out the bits of a read,
   the acknowledge is driven through the direction register. Start and stop are found with the pin change event.
   Address ADDR (0x52). A write stores its data bytes in the log S_RX (S_NRX bytes, read by the testbench). A read returns
   the bytes 0x69 + 3 i until the master does not acknowledge a byte. A transfer to another address gets no
   acknowledge and nothing is driven.
   Defines: SLOWACK = n: n * 4 core cycles of delay between the end of the eighth clock and the acknowledge (finds how late
   the acknowledge may be); STRETCH = n: the slave holds SCL low (direction register) from the end of the eighth clock until
   the acknowledge is driven, after a delay of n * 4 core cycles (clock stretching in firmware, there is none in the cells);
   LATEDATA = n: n * 4 core cycles of delay before the first byte of a read is written to the transmit cell. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define SDA  0x10
#define SCL  0x20
#define DONE 0x40
#define ADDR 0x52
#define S_NRX    (*(volatile uint8_t *)0x0701)     /* data bytes received in writes */
#define S_NADDR  (*(volatile uint8_t *)0x0700)     /* addresses acknowledged */
#define S_NOTH   (*(volatile uint8_t *)0x0702)     /* addresses of other devices (not acknowledged) */
#define S_NRD    (*(volatile uint8_t *)0x0703)     /* data bytes sent in reads */
#define S_RX     ((volatile uint8_t *)0x0710)
#define R_BYTE(i) ((uint8_t)(0x69 + 3 * (i)))
#ifndef SLOWACK
#define SLOWACK 0
#endif
#ifndef STRETCH
#define STRETCH 0
#endif
#ifndef LATEDATA
#define LATEDATA 0
#endif
/*                                    CTRL  PIN   OUT   CLK   TIM   A  B  C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t rx[15] = { 0xC0, 0x80, 0x00, 0xB0, 0x41, 1, 1, 0, 0xF0, 0x00, 0xE0, 0x00, 0, 0x80, 0 };
static const uint8_t tx[15] = { 0x80, 0x02, 0x80, 0xA0, 0x41, 1, 1, 1, 0x00, 0xF0, 0xE0, 0x00, 0x04, 0x00, 0 };
static void spin(uint8_t n) { while (n--) __asm__ __volatile__("nop\n\tnop\n\tnop"); }
static void rx_reset(void) { LC_REG(LC_R0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN; }
/* the eighth clock has been received: acknowledge in the ninth, return at its end */
static void ack(void)
{
    while (PINR & SCL) ;            /* eighth clock ends */
#if STRETCH
    DDR |= SCL;                     /* hold SCL low: firmware clock stretching */
    spin(STRETCH);
    DDR |= SDA;
    spin(4);                        /* set-up time of the acknowledge before SCL is released */
    DDR &= ~SCL;
#else
#if SLOWACK
    spin(SLOWACK);
#endif
    DDR |= SDA;                     /* SDA low */
#endif
    while (!(PINR & SCL)) ;
    while (PINR & SCL) ;            /* ninth clock ends */
}
int main(void)
{
    uint8_t b, p = 0, again = 0, i, nack;
    CORECTL = CORE_EN(0);
    PORT &= ~(SDA | SCL);
    DDR &= ~(SDA | SCL | DONE);
    ODE = SDA;                                              /* the cell output only pulls SDA low */
    lc_setup(LC_R0, rx); lc_setup(LC_T0, tx);
    PCMSK = SDA | DONE;
    for (;;) {
        if (!again) {
            IFRL = EV_PC;
            wait_for(EV_PC);
            p = PINR;
            if (p & DONE) break;
        }
        again = 0;
        if ((p & (SDA | SCL)) != SCL) continue;             /* not a start: SDA low while SCL is high */
        rx_reset();
        wait_for(EV_LR0); b = LR0DATA;
        if ((b >> 1) != ADDR) { S_NOTH++; continue; }       /* not addressed: no acknowledge */
        S_NADDR++;
        ack();
        if (b & 1) {                                        /* read: the cell shifts the byte out */
            LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(4) | LCO_OUTEN;      /* the cell takes the pin from the port register */
            LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
#if LATEDATA
            spin(LATEDATA);
#endif
            for (i = 0;; i++) {
                LT0DATA = R_BYTE(i);                        /* starts at once: the first bit is on the pin */
                DDR &= ~SDA;                                /* only now release the acknowledge of the address (first byte) */
                rx_reset();
                wait_for(EV_LR0); b = LR0DATA;              /* eight clocks have passed */
                S_NRD++;
                while (PINR & SCL) ;                        /* the cell releases SDA after the eighth falling edge */
                while (!(PINR & SCL)) ;                     /* acknowledge clock of the master */
                nack = PINR & SDA;
                while (PINR & SCL) ;
                if (nack) break;
            }
            LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(4);
            LC_REG(LC_T0, LC_CTRL) = LCC_EN;
            continue;
        }
        DDR &= ~SDA; rx_reset();
        for (;;) {                                          /* write: data bytes until stop or repeated start */
            IFRL = EV_PC;
            wait_for(EV_LR0 | EV_PC);
            if (LR0STAT & LCS_RXF) {
                b = LR0DATA;
                if (S_NRX < 32) S_RX[S_NRX] = b;
                S_NRX++;
                ack();
                DDR &= ~SDA; rx_reset();
                continue;
            }
            p = PINR;
            if (p & DONE) EXIT(0);
            if (p & SCL) { again = 1; break; }              /* SDA changed while SCL is high: stop or start */
        }
    }
    EXIT(0);
}
