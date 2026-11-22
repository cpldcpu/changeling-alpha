/* Firmware test 13, image of core 0: USB low-speed device. The receive loop and the answer path
   are in assembly (usb_dev.S); set-up, transmit data and checks are in C. */
#include "fw13.h"
uint8_t usb_rx_token(uint8_t *buf, uint16_t pid_answer, uint8_t addr);     /* pid_answer = answer << 8 | expected token */
uint8_t usb_rx_data_ack(uint8_t *buf);
void usb_crc_token_mode(void);
void usb_crc_data_mode(uint8_t start_low);
static const uint8_t rxc[15] = USB_RX(0, 1);
static const uint8_t txc[15] = USB_TX(0, 1);
static uint8_t tok[3][4], dat[14];

/* after an own packet: transmitter off with the sync byte of the next answer waiting, receiver on */
static void turn(void)
{
    while (LT0STAT & LCS_BUSY) ;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN; LT0DATA = 0x80;
}

int main(void)
{
    uint8_t n, i, a, t0; uint16_t c;
    CORECTL = CORE_EN(0) | CORE_EN(1);
    lc_setup(LC_T0, txc); lc_setup(LC_R0, rxc);
    LC_REG(LC_T0, LC_CTRL) = LCC_EN; LT0DATA = 0x80;        /* prepared sync byte */
    TCAP = TCAP_SRC_REF | TCAP_PIN(0); TCR = TCR_RUN | TCR_PS(1);   /* timer: every second clock cycle; captures the start of an end of packet */
    /* The CRC unit takes every bit behind the sync pattern, the packet identifier included.
       Tokens: CRC5; the routine selects the reference value by the kind of token.
       Data: CRC-16; the start value 0xFE97 becomes 0xFFFF after the eight bits of DATA0. */
    CRCCTL = 0; CRCPOLY2 = 0; CRCPOLY3 = 0; CRCVAL2 = 0; CRCVAL3 = 0; CRCREF2 = 0; CRCREF3 = 0;
    usb_crc_token_mode();

    t0 = usb_rx_token(tok[0], 0, 0);                        /* SETUP token: no answer */
    usb_crc_data_mode(0x97);                                /* in the gap before the data packet */
    n = usb_rx_data_ack(dat);                               /* DATA0, 8 bytes, CRC-16; handshake */
    if (n & 0x80) turn();
    usb_crc_token_mode();

    a = usb_rx_token(tok[1], PID_IN | (PID_DATA1 << 8), (uint8_t)(DEV_ADDR | (DEV_EP << 7)));   /* IN token: sync byte and DATA1 start */
#ifdef BADTOKEN
    /* variant of the test: the host sends the IN token with a wrong CRC5; there must be no answer */
    if (t0 == 2 && (n & 0x80) && a == 0 && tok[1][0] == PID_IN) EXIT(0);
    EXIT(120 + a);
#endif
    if (a & 1) {
        usb_crc_data_mode(0xFF); CRCVAL1 = 0xFF; CRCCTL = CRC_EN | CRC_RIGHT | CRC_SRC_SW;   /* CRC-16 of the bytes to send */
        for (i = 0; i < 4; i++) { CRCIN = in_data[i]; wait_for(EV_LT0); LT0DATA = in_data[i]; }
        c = ~(CRCVAL0 | ((uint16_t)CRCVAL1 << 8));
        wait_for(EV_LT0); LT0DATA = (uint8_t)c;
        wait_for(EV_LT0); LT0DATA = (uint8_t)(c >> 8);
        turn();
    }
    usb_crc_token_mode();
    usb_rx_token(tok[2], 0, 0);                             /* handshake of the host */

    /* checks, after the exchange */
    if (t0 != 2) EXIT(22);                                  /* CRC5 of the SETUP token correct, no answer */
    if (tok[0][0] != PID_SETUP || tok[0][1] != (uint8_t)(DEV_ADDR | (DEV_EP << 7)) || (tok[0][2] & 0x07) != (DEV_EP >> 1)) EXIT(20);
    if (n != (0x80 | 11)) EXIT(30 + (n & 0x0F));
    if (dat[0] != PID_DATA0) EXIT(21);
    for (i = 0; i < 8; i++) if (dat[1 + i] != setup_data[i]) EXIT(50 + i);
    if (a != 3 || tok[1][0] != PID_IN) EXIT(60 + a);
    if (tok[2][0] != PID_ACK) EXIT(70);
    while (!M_DONE) ;
    EXIT(M_DONE == 1 ? 0 : M_DONE);
}
