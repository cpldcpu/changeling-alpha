/* Firmware test 16: SPI slave with transmit cell 0 and receive cell 0 (clocked by the pin, chip select by the cell)
   against the master model (+spimst). Both cells are set up again for every transfer.
   Defines: MODE (0-3), NB (bytes per transfer), NX (transfers), ABORT1 (first transfer is aborted by the model after
   fewer bits: no byte count check there), LATEB and LATE (the byte with this number is written LATE clock cycles
   after the transmit buffer became empty, instead of at once; default: none).
   The firmware reports through the exit code: 0 = all bytes from the master as expected, no overrun, as many
   bytes as NB; 10 + i = byte i from the master wrong; 50 = receive overrun; 60 = wrong number of bytes.
   NOREINIT: the cells are set up only once (what a transfer that the master aborts leaves in the transmit buffer).
   With SHOWSTAT the exit code is LT0STAT as read just before the late write. */
#include "fw15.h"
#ifndef MODE
#define MODE 0
#endif
#ifndef NB
#define NB 4
#endif
#ifndef NX
#define NX 3
#endif
#ifndef LATEB
#define LATEB 255
#endif
#ifndef LATE
#define LATE 0
#endif
/* the master samples on this edge; the transmit cell shifts on the other one: modes 0 and 3 rising, 1 and 2 falling */
#if MODE == 0 || MODE == 3
#define EDGE 0x40
#else
#define EDGE 0x80
#endif
#if MODE & 1
#define CPHA 0x02
#else
#define CPHA 0x00
#endif
/*                                CTRL  PIN   OUT   CLK        TIM       A  B  C  DEC   ENC   SH    MATCH RUN EVM   CS */
static const uint8_t st[15] = { 0xA0, 0x01, 0x50, 0x20 | CPHA, EDGE | 1, 1, 1, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0x70 };
static const uint8_t sr[15] = { 0xC0, 0x00, 0x00, 0x30,        EDGE | 1, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x70 };
#if LATE
static uint8_t late_stat;      /* LT0STAT just before the late write: 0x60 = shifting, 0x40 = the cell has run empty */
#endif
int main(void)
{
    uint8_t x, v, sent, got, sb, mb, e = 0;
    CORECTL = CORE_EN(0);
    PORT &= ~RDY_PIN; DDR |= RDY_PIN;
    for (x = 0; x < NX; x++) {
#ifdef NOREINIT                                             /* the cells are set up once; later transfers only load the first byte */
        if (x == 0) {
#endif
        LC_REG(LC_T0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = 0;
        lc_setup(LC_T0, st); lc_setup(LC_R0, sr);
#ifdef NOREINIT
        }
#endif
        LT0DATA = S_BYTE(0);                                /* first byte before the chip select; ignored if the buffer is still full */
        PORT |= RDY_PIN;
        while (PINR & CS_PIN) ;                             /* chip select low */
        sent = 1; got = 0; sb = S_BYTE(1); mb = M_BYTE(0);
        while (!(PINR & CS_PIN)) {
            if (sent < NB && (LT0STAT & LCS_TXE)) {
#if LATE
                if (sent == LATEB) { uint16_t t0 = time_now(); while ((uint16_t)(time_now() - t0) < LATE) ; late_stat = LT0STAT; }
#endif
                LT0DATA = sb; sb += 53; sent++;
            }
            if (LR0STAT & LCS_RXF) {
                v = LR0DATA;
#ifdef ABORT1
                if (x != 0)
#endif
                if (v != mb && !e) e = 10 + got;
                got++; mb += 29;
            }
        }
        PORT &= ~RDY_PIN;
        while (LR0STAT & LCS_RXF) { v = LR0DATA; if (v != mb && !e) e = 10 + got; got++; mb += 29; }
        if ((LR0STAT & LCS_OVR) && !e) e = 50;
#ifdef ABORT1
        if (x != 0)
#endif
        if (got != NB && !e) e = 60;
    }
#if defined(SHOWSTAT) && LATE
    EXIT(late_stat);
#endif
    EXIT(e);
}
