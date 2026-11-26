/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* Stress tests (two protocols at once): common definitions. Results of the two cores are left in the shared data memory
   at fixed addresses, the testbench (tb/stress.v) reads them at the end. */
#ifndef FWX_H
#define FWX_H
#include "rpe.h"
#define X8(a)  (*(volatile uint8_t  *)(a))
#define X16(a) (*(volatile uint16_t *)(a))
#define R_XFERS  0x0710   /* 16 bit: rounds (transfers, frames, characters) completed by the protocol of core 1, or by the single core */
#define R_ERR    0x0712   /* first error code of core 1 (0 = none) */
#define R_ERRN   0x0713   /* number of errors of core 1 */
#define R_C0ERR  0x0714   /* core 0: first error code */
#define R_C0ERRN 0x0715   /* core 0: number of errors (overrun markers sent, wrong bytes, ...) */
#define R_C0N    0x0716   /* 16 bit: units completed by core 0 */
#define R_OCAN   0x0718   /* 16 bit: compare events served (time stamp ISR) */
#define R_OCABAD 0x071A   /* 16 bit: stamps whose spacing is not the period +- OCA_TOL */
#define R_OCADEV 0x071C   /* 16 bit: largest deviation of a spacing from the period */
#define R_STAMP  0x0720   /* 16 bit: last stamp (time base) */
#define R_OCBN   0x0724   /* 16 bit: compare B events served by core 1 (time stamp ISR) */
#define R_OCBBAD 0x0726
#define R_OCBDEV 0x0728
#define R_START  0x07F0   /* 8 bit: set to 1 by core 1 when its set-up is done */
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define M_BYTE(i) ((uint8_t)(0xA5 + 29 * (i)))      /* SPI: master sends */
#define S_BYTE(i) ((uint8_t)(0x3C + 53 * (i)))      /* SPI: slave sends */
#define ERR1(c) do { if (!X8(R_ERR)) X8(R_ERR) = (c); X8(R_ERRN)++; } while (0)
#define ERR0(c) do { if (!X8(R_C0ERR)) X8(R_C0ERR) = (c); X8(R_C0ERRN)++; } while (0)
#endif
