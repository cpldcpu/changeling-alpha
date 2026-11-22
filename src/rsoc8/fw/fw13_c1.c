/* Firmware test 13, image of core 1: USB low-speed host (stimulus and checks) */
#include "fw13.h"
#include "rpe_core1.h"
static const uint8_t rxc[15] = USB_RX(2, 3);
static const uint8_t txc[15] = USB_TX(2, 3);
static uint8_t buf[12];

static void rx_arm(void) { LC_REG(LC_R1, LC_CTRL) = 0; LC_REG(LC_R1, LC_CTRL) = LCC_EN | LCC_RXEN; }
static uint8_t rx_packet(void)
{
    uint8_t n = 0, st;
    for (;;) {
        wait_for(EV_LR1);
        st = LR1STAT;
        if (st & LCS_RXF) { buf[n] = LR1DATA; if (n < sizeof buf - 1) n++; }
        else if (st & LCS_EOP) { LR1STAT = LCS_EOP; if (n) break; }
    }
    rx_arm();
    return n;
}
static void tx(const uint8_t *p, uint8_t n)
{
    LC_REG(LC_R1, LC_CTRL) = 0;                             /* do not receive the own packet */
    LT1DATA = 0x80;
    while (n--) { wait_for(EV_LT1); LT1DATA = *p++; }
    while (LT1STAT & LCS_BUSY) ;
    rx_arm();
}
static uint16_t crc16(const uint8_t *p, uint8_t n)
{
    uint16_t v = 0xFFFF; uint8_t i;
    while (n--) { v ^= *p++; for (i = 0; i < 8; i++) v = (v & 1) ? (v >> 1) ^ 0xA001 : v >> 1; }
    return ~v;
}
static void token(uint8_t pid, uint8_t *t)
{
    uint16_t f = DEV_ADDR | (DEV_EP << 7); uint8_t v = 0x1F, i;
    for (i = 0; i < 11; i++) { uint8_t fb = (v ^ (uint8_t)(f >> i)) & 1; v >>= 1; if (fb) v ^= 0x14; }
    f |= (uint16_t)(v ^ 0x1F) << 11;
    t[0] = pid; t[1] = (uint8_t)f; t[2] = (uint8_t)(f >> 8);
}
static void gap(void) { delay_after(240); wait_for(EV_DLY); }       /* from the start of an end of packet: 2 bit times, then 4 of idle */

int main(void)
{
    uint8_t t[3], d[11], n, i, e = 1; uint16_t c;
    lc_setup(LC_T1, txc); lc_setup(LC_R1, rxc);
    delay_after(2000); wait_for(EV_DLY);                    /* the device sets itself up */
    token(PID_SETUP, t); tx(t, 3); gap();
    d[0] = PID_DATA0; for (i = 0; i < 8; i++) d[1 + i] = setup_data[i];
    c = crc16(setup_data, 8); d[9] = (uint8_t)c; d[10] = (uint8_t)(c >> 8);
    tx(d, 11);
    n = rx_packet(); if (n != 1 || buf[0] != PID_ACK) e = 80 + n;
    gap();
    token(PID_IN, t);
#ifdef BADTOKEN
    t[2] ^= 0x10;                                           /* one wrong bit in the CRC5 */
#endif
    tx(t, 3);
    n = rx_packet();
    if (e == 1) {
        if (n != 7 || buf[0] != PID_DATA1) e = 90 + n;
        else {
            for (i = 0; i < 4; i++) if (buf[1 + i] != in_data[i]) e = 100 + i;
            c = crc16(in_data, 4); if (buf[5] != (uint8_t)c || buf[6] != (uint8_t)(c >> 8)) e = 110;
        }
    }
    gap();
    t[0] = PID_ACK; tx(t, 1);
    M_DONE = e;
    for (;;) wait_for(EV_SW3);
}
