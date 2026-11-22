/* Firmware test 17: I2C master in firmware (fw/i2cm.h) against the slave model (+i2cs). One core, pins 4 SDA, 5 SCL.
   SCEN selects what the model is expected to do; the firmware exits with 0 if the outcome is the expected one:
     0 normal: write of 3 bytes, read of 4 bytes, write of 1 byte + repeated start + read of 2 bytes; also with stretching
     1 the model does not acknowledge the address (+i2cs_noack): the master must see I2C_NACK, send a stop and leave the bus idle
     2 SDA is stuck low at the start (+i2cs_stuck=5): i2c_start() reports I2C_BUSY, i2c_recover() frees the bus, then the
       transfer of scenario 0 (first part) works
     3 SDA is stuck low for ever (+i2cs_stuck=999): the recovery fails, the firmware reports I2C_BUSY and ends
     4 SCL is stuck low (+i2cs_sclstuck): the master reports I2C_TMO
     5 the model does not acknowledge data byte 1 (+i2cs_nackdata=1): the master sees I2C_NACK on that byte
   Exit codes other than 0: 10 + step: unexpected error code, 30 + n: wrong read byte n, 40 +: wrong outcome of the scenario. */
#include "i2cm.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#ifndef SCEN
#define SCEN 0
#endif
#ifndef ADDR
#define ADDR 0x52
#endif
#define CK(e, c) do { if (e) EXIT((c) + 10 * (e)); } while (0)
static uint8_t buf[4];
static void init(void)
{
    CORECTL = CORE_EN(0);
    PORT &= ~(SDA | SCL); DDR &= ~(SDA | SCL);
    delay_after(100); wait_for(EV_DLY);
}
static uint8_t write3(void)       /* address, three bytes, stop */
{
    uint8_t i, e;
    i2c_start(); if (i2c_err) return i2c_err;
    e = i2c_wr(ADDR << 1); if (e) { if (e == I2C_NACK) i2c_stop(); return e; }
    for (i = 0; i < 3; i++) { e = i2c_wr(I2C_W_BYTE(i)); if (e) { if (e == I2C_NACK) i2c_stop(); return e; } }
    i2c_stop();
    return i2c_err;
}
int main(void)
{
    uint8_t e, i;
    init();
#if SCEN == 1
    i2c_start(); CK(i2c_err, 0);
    e = i2c_wr(ADDR << 1);
    if (e != I2C_NACK) EXIT(40 + e);
    i2c_stop();
    if ((PINR & (SDA | SCL)) != (SDA | SCL) || (DDR & (SDA | SCL))) EXIT(46);
    EXIT(0);
#elif SCEN == 2 || SCEN == 3
    i2c_start();
    if (i2c_err != I2C_BUSY) EXIT(41);                  /* the stuck bus must be seen */
    e = i2c_recover();
#if SCEN == 3
    if (e != I2C_BUSY) EXIT(42);
    if (DDR & (SDA | SCL)) EXIT(43);                    /* no line is held by the master */
    EXIT(0);
#else
    if (e) EXIT(42);
    e = write3(); CK(e, 1);
    EXIT(0);
#endif
#elif SCEN == 4
    i2c_start();
    if (i2c_err != I2C_TMO) EXIT(41);
    EXIT(0);
#elif SCEN == 5
    i2c_start(); CK(i2c_err, 1);
    e = i2c_wr(ADDR << 1); CK(e, 2);
    e = i2c_wr(I2C_W_BYTE(0)); CK(e, 3);
    e = i2c_wr(I2C_W_BYTE(1));
    if (e != I2C_NACK) EXIT(40 + e);
    i2c_stop();
    EXIT(0);
#else
    e = write3(); CK(e, 1);
    i2c_start(); CK(i2c_err, 2);
    e = i2c_wr((ADDR << 1) | 1); CK(e, 3);
    for (i = 0; i < 4; i++) buf[i] = i2c_rd(i == 3);
    i2c_stop(); CK(i2c_err, 4);
    for (i = 0; i < 4; i++) if (buf[i] != I2C_R_BYTE(i)) EXIT(30 + i);
    i2c_start(); CK(i2c_err, 5);
    e = i2c_wr(ADDR << 1); CK(e, 6);
    e = i2c_wr(I2C_W_BYTE(0)); CK(e, 7);
    i2c_restart(); CK(i2c_err, 8);
    e = i2c_wr((ADDR << 1) | 1); CK(e, 9);
    for (i = 0; i < 2; i++) buf[i] = i2c_rd(i == 1);
    i2c_stop(); CK(i2c_err, 4);
    for (i = 0; i < 2; i++) if (buf[i] != I2C_R_BYTE(i)) EXIT(34 + i);
    EXIT(0);
#endif
}
