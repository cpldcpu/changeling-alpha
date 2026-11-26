/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* I2C master in firmware, open drain through the direction register (PORT bit = 0, DDR bit = 1 pulls the pin low),
   extended from the master of firmware test 12 (fw12_c1.c) and the sensor bridge (fwsens_c1.c):
   - clock stretching: after SCL is released it is read back, and the code waits until the pin is high; the high time
     is counted from the moment it is high. A wait longer than I2C_STR_TMO clock cycles is the error I2C_TMO.
   - bus check in i2c_start(): SDA low for longer than I2C_BUSY_TMO cycles is the error I2C_BUSY, SCL low I2C_TMO.
   - i2c_recover(): up to nine clock pulses with SDA released, stop when SDA is high; then a stop condition. The result is
     0 if both lines are high afterwards, else I2C_BUSY.
   - several masters: the high time ends early when another master pulls SCL low; a start that finds SCL already low is
     the error I2C_ARB; while it sends a one the master reads SDA back as soon as SCL is high; a zero means that
     another master sends a zero: the master releases both lines at once and the error is I2C_ARB.
   Pins: SDA, SCL (defaults 4 and 5). The time of a quarter period in clock cycles is I2C_Q, the code adds about 25 cycles
   to each hold. The global i2c_err holds the first error of a transfer (0 = none); after an error all further calls do nothing. */
#ifndef I2CM_H
#define I2CM_H
#include "rpe.h"
#ifndef SDA
#define SDA 0x10
#define SCL 0x20
#endif
#ifndef I2C_Q
#define I2C_Q 60
#endif
#ifndef I2C_STR_TMO
#define I2C_STR_TMO 3000
#endif
#ifndef I2C_BUSY_TMO
#define I2C_BUSY_TMO 600
#endif
#define I2C_OK   0
#define I2C_NACK 1       /* the address or a data byte was not acknowledged (not sticky) */
#define I2C_TMO  2       /* SCL stays low */
#define I2C_BUSY 3       /* SDA or SCL low at the start, or stuck after the recovery */
#define I2C_ARB  4       /* arbitration lost */
#ifndef I2C_W_XOR
#define I2C_W_XOR 0                                     /* fault insertion: data of the writes is changed */
#endif
#define I2C_W_BYTE(i) ((uint8_t)((0x3C + 27 * (i)) ^ I2C_W_XOR))      /* data written by the master (byte i of a segment) */
#define I2C_R_BYTE(i) ((uint8_t)(0x69 + 3 * (i)))       /* data returned by the slave */
#ifdef GOPIN
#define I2C_GO_HIGH() (PORT |= GOPIN)                   /* testbench marker one instruction before the start condition */
#else
#define I2C_GO_HIGH() do { } while (0)
#endif
static uint8_t i2c_err;
static void i2c_hold(void) { delay_after(I2C_Q); wait_for(EV_DLY); }
static void i2c_free(void) { DDR &= ~(SDA | SCL); }
/* high time of SCL: ends after I2C_Q cycles or when SCL is pulled low by another master, whichever comes first */
static void i2c_hold_high(void)
{
    uint16_t t0 = time_now();
    while ((PINR & SCL) && (uint16_t)(time_now() - t0) < I2C_Q) ;
}
/* release SCL and wait until it is high; error I2C_TMO if it stays low */
static void i2c_scl_release(void)
{
    uint16_t t0;
    DDR &= ~SCL;
#ifdef I2C_NOSTRETCH                                    /* fault insertion: the master of fw12_c1.c, SCL is not read back */
    return;
#endif
    if (PINR & SCL) return;
    t0 = time_now();
    while (!(PINR & SCL)) {
        if ((uint16_t)(time_now() - t0) > I2C_STR_TMO) { i2c_err = I2C_TMO; i2c_free(); return; }
    }
}
/* wait until both lines have been high for I2C_BUSY_TMO / 4 cycles in one go; error I2C_BUSY after I2C_BUSY_TMO */
static void i2c_wait_free(void)
{
    uint16_t t0 = time_now();
    while ((PINR & (SDA | SCL)) != (SDA | SCL)) {
        if ((uint16_t)(time_now() - t0) > I2C_BUSY_TMO) { i2c_err = (PINR & SCL) ? I2C_BUSY : I2C_TMO; return; }
    }
}
/* start condition from an idle bus (both lines released) */
static void i2c_start(void)
{
    i2c_err = 0; i2c_free();
    i2c_wait_free();
    if (i2c_err) return;
    I2C_GO_HIGH();
    DDR |= SDA;
    if (!(PINR & SCL)) { i2c_err = I2C_ARB; i2c_free(); return; }     /* another master started earlier and has pulled SCL low: we are too late */
    i2c_hold(); DDR |= SCL; i2c_hold();
}
/* one bit: out = 1 releases SDA; returns the level of SDA at the end of the high time. chk = 1: arbitration check */
static uint8_t i2c_bit(uint8_t out, uint8_t chk)
{
    uint8_t v;
    if (i2c_err) return 1;
    if (out) DDR &= ~SDA; else DDR |= SDA;
    i2c_hold();
    i2c_scl_release();
    if (i2c_err) return 1;
    v = (PINR & SDA) ? 1 : 0;                           /* sampled as soon as SCL is high: with two masters the other one may pull SCL low early */
#ifndef I2C_NOARB                                       /* fault insertion: no arbitration check */
    if (chk && out && !v) { i2c_err = I2C_ARB; i2c_free(); return v; }
#endif
    i2c_hold_high();
    DDR |= SCL;
    return v;
}
/* repeated start: SCL is low */
static void i2c_restart(void)
{
    if (i2c_err) return;
    DDR &= ~SDA; i2c_hold();
    i2c_scl_release(); if (i2c_err) return;
    i2c_hold();
    DDR |= SDA; i2c_hold(); DDR |= SCL; i2c_hold();
}
static void i2c_stop(void)
{
    if (i2c_err) return;
    DDR |= SDA; i2c_hold();
    i2c_scl_release(); if (i2c_err) return;
    i2c_hold();
    DDR &= ~SDA; i2c_hold();
}
/* write a byte; returns I2C_OK, I2C_NACK, or the sticky error */
static uint8_t i2c_wr(uint8_t b)
{
    uint8_t i, a;
    for (i = 0; i < 8; i++) { i2c_bit(b & 0x80, 1); b <<= 1; }
    a = i2c_bit(1, 0);
    if (i2c_err) return i2c_err;
    return a ? I2C_NACK : I2C_OK;
}
/* read a byte; nack = 1 for the last byte of a read */
static uint8_t i2c_rd(uint8_t nack)
{
    uint8_t i, b = 0;
    for (i = 0; i < 8; i++) b = (uint8_t)(b << 1) | i2c_bit(1, 0);
    i2c_bit(nack, 0);
    return b;
}
/* nine clock pulses with SDA released, then a stop condition. Returns I2C_OK if both lines are high afterwards. */
static uint8_t i2c_recover(void)
{
    uint8_t i;
    i2c_err = 0; i2c_free();
    for (i = 0; i < 9; i++) {
        DDR |= SCL; i2c_hold();
        i2c_scl_release(); if (i2c_err) return I2C_BUSY;
        i2c_hold();
        if (PINR & SDA) break;                          /* the slave has let go of SDA */
    }
    DDR |= SCL; i2c_hold();
    DDR |= SDA; i2c_hold();                             /* stop condition: SDA low, SCL high, SDA high */
    i2c_scl_release(); if (i2c_err) return I2C_BUSY;
    i2c_hold();
    DDR &= ~SDA; i2c_hold();
    i2c_err = 0;
    return ((PINR & (SDA | SCL)) == (SDA | SCL)) ? I2C_OK : I2C_BUSY;
}
#endif
