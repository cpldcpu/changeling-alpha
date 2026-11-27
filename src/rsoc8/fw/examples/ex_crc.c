/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* CRC unit, two uses. */
#include "rpe.h"

/* CRC-16 with polynomial 0x8005, shifted right (as used by USB), over a buffer.
   crc_setup takes the width minus one and the polynomial without its top term, bit-reversed for right shift. */
static uint16_t crc16(const uint8_t *p, uint8_t n)
{
    crc_setup(CRC_EN | CRC_RIGHT | CRC_SRC_SW | CRC_OWNER(0), 15, 0xA001, 0xFFFF);
    while (n--) { CRCIN = *p++; crc_wait(); }                /* 4 clock cycles per byte */
    return (uint16_t)~crc_value();
}

/* Check of a received Ethernet frame: the unit takes the bits from receive cell 0. After the last
   bit of a correct frame the value equals the residual, which is stored as reference. */
static void crc_frame_check_setup(void)
{
    crc_setup(CRC_EN | CRC_RIGHT | CRC_SRC_R0 | CRC_OWNER(0), 31, 0xEDB88320ul, 0xFFFFFFFFul);
    CRCREF0 = 0xE3; CRCREF1 = 0x20; CRCREF2 = 0xBB; CRCREF3 = 0xDE;       /* 0xDEBB20E3 */
}
static uint8_t crc_frame_ok(void) { return (CRCST & CRCST_EQF) != 0; }

int main(void)
{
    static const uint8_t msg[9] = "123456789";
    volatile uint16_t c = crc16(msg, 9);
    crc_frame_check_setup();
    (void)c; (void)crc_frame_ok();
    for (;;) wait_for(EV_SW0);
}
