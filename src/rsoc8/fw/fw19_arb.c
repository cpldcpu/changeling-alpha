/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Firmware test 19: two masters. The chip is a master (fw/i2cm.h, with the arbitration check) and starts a write at the same
   time as the master model (+i2cm +i2cm_arb). Pins 4 SDA, 5 SCL, 6 GO (output of the chip: it rises one instruction before the
   chip pulls SDA low; the model starts i2cm_arbd cycles after it), 7 DONE (input, driven by the model).
   The chip writes ADDR (default 0x52) and the three bytes 0x3C + 27 i. With DATAXOR, the first data byte is XORed with it.
   EXPECT = 0: the chip must win and finish the transfer; EXPECT = 4 (I2C_ARB): the chip must lose, release both lines and
   send nothing more. Exit code 0 = outcome as expected; 50 + code: another outcome. */
#define GOPIN 0x40
#include "i2cm.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define DONEPIN 0x80
#ifndef ADDR
#define ADDR 0x52
#endif
#ifndef EXPECT
#define EXPECT 0
#endif
#ifndef DATAXOR
#define DATAXOR 0
#endif
int main(void)
{
    uint8_t e = 0, i;
    CORECTL = CORE_EN(0);
    PORT &= ~(SDA | SCL | GOPIN); DDR &= ~(SDA | SCL | DONEPIN); DDR |= GOPIN;
    delay_after(100); wait_for(EV_DLY);
    i2c_start();
    if (i2c_err) EXIT(60 + i2c_err);
    e = i2c_wr(ADDR << 1);
    if (!e) for (i = 0; i < 3 && !e; i++) e = i2c_wr(I2C_W_BYTE(i) ^ (i == 0 ? DATAXOR : 0));
    if (e == I2C_NACK) { e = 5; i2c_stop(); }               /* nobody acknowledges: not the expected case */
    else if (!e) i2c_stop();
    if (e == I2C_ARB && (DDR & (SDA | SCL))) e = 6;         /* lost, but a line is still held */
    while (!(PINR & DONEPIN)) ;                             /* wait for the model */
    if (e != EXPECT) EXIT(50 + e);
    EXIT(0);
}
