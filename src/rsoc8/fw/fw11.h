/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* shared between the two images of firmware test 11: SPI master (core 1, pair 1) and SPI slave
   (core 0, pair 0) on pins 0 MOSI, 1 SCK, 2 MISO, 3 chip select; modes 0 and 1; 16 clock cycles per bit */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define S_READY  (*(volatile uint8_t *)0x0700)     /* slave: configured for this mode, first byte loaded */
#define M_DONE   (*(volatile uint8_t *)0x0701)     /* master: 1 = all bytes as expected, else error code */
#define NB 8
#define M_BYTE(i, m) ((uint8_t)(0xA5 + 29 * (i) + (m)))      /* master to slave */
#define S_BYTE(i, m) ((uint8_t)(0x3C + 53 * (i) + 7 * (m)))  /* slave to master */
