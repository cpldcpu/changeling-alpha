/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* USB low-speed device on pair 0: definitions shared by firmware files */
#ifndef USB_H
#define USB_H
#include "rpe.h"
#define PID_OUT   0xE1
#define PID_IN    0x69
#define PID_SETUP 0x2D
#define PID_DATA0 0xC3
#define PID_DATA1 0x4B
#define PID_ACK   0xD2
#define PID_NAK   0x5A
#define PID_STALL 0x1E
/* USB_CPB: clock cycles per bit. 40 with the 60 MHz clock, 10 with the 15 MHz oscillator. */
#ifndef USB_CPB
#define USB_CPB 40
#endif
#define USB_TPS (USB_CPB == 40 ? 1 : 0)   /* timer prescaler for the answer time */
/* line cell settings: dp, dm are the pin numbers of D+ and D-
                         CTRL  PIN            OUT CLK                      TIM            A   B   C  DEC           ENC SH    MATCH RUN                          EVM                 CS */
#define USB_RX(dp, dm) { 0xC0, LCP_INSEL(dp), 0,  LCK_CSEL(dm) | LCK_BLEN, LCT_EDGE_BOTH, USB_CPB / 2, USB_CPB, 0, LUT_DEC_NRZI, 0,  0xF2, 0x80, LCR_LIM(6) | LCR_REF_BOTHL, LCS_RXF | LCS_EOP, 0 }
#define USB_TX(dp, dm) { 0xA0, LCP_OEM_BUSY, LCO_OUTSEL(dp) | LCO_OUTEN | LCO_NSEL(dm) | LCO_NEN, 0, 0, 1, USB_CPB, 1, 0, LUT_ENC_NRZI, 0xF0, 0, LCR_LIM(6) | LCR_EOP, LCS_TXE, 0 }

struct usb_state {
    uint8_t addr;
    uint8_t ep0_len; const uint8_t *ep0_ptr;
    uint8_t ep1_len; const uint8_t *ep1_ptr;
    uint8_t dlen, tok[3], data[12];
};
enum { USB_NONE, USB_EOP, USB_SETUP, USB_OUT, USB_NAK, USB_IN0, USB_IN1 };
uint8_t usb_poll(struct usb_state *s);
void usb_crc_token_mode(void);
void usb_crc_data_mode(uint8_t start_low);
#endif
