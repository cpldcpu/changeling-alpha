/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* shared between the two images of firmware test 13: USB low-speed at 40 clock cycles per bit.
   Core 1 with pair 1 plays the host on pins 2 (D+) and 3 (D-). Core 0 with pair 0 is the device on
   pins 0 (D+) and 1 (D-). The testbench wires 0 to 2 and 1 to 3 and pulls D+ low (+short=0213 +pd=05),
   so the idle state is D+ low, D- high.
   Sequence: SETUP token, DATA0 with 8 bytes, handshake ACK from the device; IN token, DATA1 with
   4 bytes from the device, handshake ACK from the host. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define M_DONE (*(volatile uint8_t *)0x0700)       /* host: 1 = pass, else error code */
#define PID_SETUP 0x2D
#define PID_IN    0x69
#define PID_DATA0 0xC3
#define PID_DATA1 0x4B
#define PID_ACK   0xD2
#define DEV_ADDR  0x12
#define DEV_EP    1
/*                 CTRL  PIN   OUT   CLK   TIM   A   B   C  DEC   ENC   SH    MATCH RUN   EVM   CS */
#define USB_RX(dp, dm) { 0xC0, LCP_INSEL(dp), 0, LCK_CSEL(dm) | LCK_BLEN, LCT_EDGE_BOTH, 20, 40, 0, LUT_DEC_NRZI, 0, 0xF2, 0x80, LCR_LIM(6) | LCR_REF_BOTHL, LCS_RXF | LCS_EOP, 0 }
#define USB_TX(dp, dm) { 0xA0, LCP_OEM_BUSY, LCO_OUTSEL(dp) | LCO_OUTEN | LCO_NSEL(dm) | LCO_NEN, 0, 0, 1, 40, 1, 0, LUT_ENC_NRZI, 0xF0, 0, LCR_LIM(6) | LCR_EOP, LCS_TXE, 0 }
static const uint8_t setup_data[8] = { 0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x12, 0x00 };   /* GET_DESCRIPTOR(device) */
static const uint8_t in_data[4]    = { 0x12, 0x01, 0x10, 0x01 };
