/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* shared between the two images of firmware test 12: I2C. Core 1 is a master in firmware (open
   drain through the direction register). Core 0 is a slave: pin change event for start and stop,
   receive cell 0 clocked by SCL for the eight bits, transmit cell 0 for the bits of a read, the
   acknowledge bit through the direction register. Slave pins: 4 SDA, 5 SCL. Master pins: 6 SDA,
   7 SCL. The testbench wires 4 to 6 and 5 to 7 (+short=4657); undriven pins read high.
   The two devices need separate pins, because each pin has one direction bit. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#ifdef MASTER
#define SDA 0x40
#define SCL 0x80
#else
#define SDA 0x10
#define SCL 0x20
#endif
#define M_DONE   (*(volatile uint8_t *)0x0700)     /* master: 1 = pass, else error code */
#define S_NRX    (*(volatile uint8_t *)0x0701)     /* slave: number of data bytes received */
#define S_RX     ((volatile uint8_t *)0x0702)
#define ADDR     0x52
#define RDBYTE   0x69
