/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* I2C master in firmware (fw/i2cm.h): read 6 bytes from register 0x01 of a device at address 0x29.
   SDA pin 4, SCL pin 5, open drain through the direction register, about 250 kHz. */
#define SDA 0x10
#define SCL 0x20
#define I2C_Q 60                                   /* quarter of a bit time in clock cycles */
#include "i2cm.h"

static uint8_t sensor_read(uint8_t *buf)
{
    uint8_t i;
    i2c_err = I2C_OK;
    PORT &= (uint8_t)~(SDA | SCL);                 /* a pin is pulled low by setting its direction bit */
    i2c_start();
    if (i2c_wr(0x29 << 1) || i2c_wr(0x01)) { i2c_stop(); return I2C_NACK; }
    i2c_restart();
    if (i2c_wr((0x29 << 1) | 1)) { i2c_stop(); return I2C_NACK; }
    for (i = 0; i < 6; i++) buf[i] = i2c_rd(i == 5);         /* no acknowledge after the last byte */
    i2c_stop();
    return i2c_err;                                /* I2C_TMO: clock held low; I2C_ARB: arbitration lost */
}

int main(void)
{
    uint8_t d[6];
    PCMSK = 0x40;                                  /* interrupt line of the device on pin 6, active low */
    for (;;) {
        IFRL = EV_PC;
        if (PINR & 0x40) wait_for(EV_PC);          /* stop until the pin changes */
        if (!(PINR & 0x40)) sensor_read(d);
    }
}
