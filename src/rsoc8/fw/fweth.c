/* Firmware test 15: 10BASE-T ping endpoint, one core (core 0) for both directions.
   Fixed MAC 02:C0:FF:EE:00:01 and IPv4 address 192.168.4.2. Answers an ARP request for its address and an ICMP
   echo request. Frames for other MAC addresses, with a wrong FCS, or with wrong checksums are ignored.
   Receive: cell R0 on pin 1 (both-edge sampling, A = 9, B = 24); the CRC unit takes the bits behind the
   delimiter and CRCST.EQF tells the FCS result. The answer is built in place in the receive buffer.
   Transmit: cell T0 on pin 0 at 6 clock cycles per bit. The FCS is made with CRCIN before the first byte is sent.
   The idle pulse (TP_IDL) is made with LCRUN.IDLE: set while the last byte is sent, cleared 3 bit times after.
   Half duplex: the core never receives and sends at the same time, so one core is enough also at +cdiv=2. */
#include "rpe.h"
#include "fweth.h"
#ifndef TDM
#define TDM 0                       /* 1: second output (TD-) on pin 2 */
#endif
#ifndef FAULT
#define FAULT 0                     /* inserted faults for the tests of the model: 1 FCS not inverted, 2 EQF ignored,
                                       3 ICMP checksum off by one, 4 MAC address of IP frames not checked, 5 no idle pulse (asm) */
#endif
#ifndef IDLEHOLD
#define IDLEHOLD 8                  /* time base cycles of the idle pulse behind the last bit, plus loop delay */
#endif
#ifndef IFG
#define IFG 640                     /* clock cycles between the end of the received frame and the first bit sent */
#endif
#define buf (frm + 8)                 /* 8 bytes in front: preamble and delimiter */
uint8_t frm[8 + BUFSZ + 4] __attribute__((section(".noinit")));   /* not cleared at start: the clear loop would take 8000 cycles */
static const uint8_t mymac[6] = {0x02, 0xC0, 0xFF, 0xEE, 0x00, 0x01};
static const uint8_t myip[4]  = {192, 168, 4, 2};

void __attribute__((naked, used, section(".init3"))) fw15_stack(void) { SPH = 0x08; SPL = 0x3F; }

#ifdef DBG
#define DBGX(c) do { _IO8(0x1F) = (c); for(;;); } while (0)
#else
#define DBGX(c) return
#endif
static uint16_t csum(const uint8_t *p, uint16_t n)      /* ones' complement sum, not inverted */
{
    uint16_t s = 0, w;
    while (n > 1) { w = ((uint16_t)p[0] << 8) | p[1]; p += 2; n -= 2; s += w; if (s < w) s++; }
    if (n) { w = (uint16_t)p[0] << 8; s += w; if (s < w) s++; }
    return s;
}

uint16_t rx_frame(void);
void tx_bytes(const uint8_t *p, uint16_t n);
void crc_feed(const uint8_t *p, uint16_t n);

static void crc_init(uint8_t ctl)
{
    CRCCTL = ctl;
    CRCVAL0 = 0xFF; CRCVAL1 = 0xFF; CRCVAL2 = 0xFF; CRCVAL3 = 0xFF;
}

static void tx_frame(uint16_t m, uint16_t t_idle)       /* buf[0..m) is the frame, m >= 60 */
{
    uint8_t *p = buf + m, i;
    crc_init(CRC_EN | CRC_RIGHT | CRC_SRC_SW);
    crc_feed(buf, m);
    crc_wait();
    *p++ = FAULT == 1 ? CRCVAL0 : ~CRCVAL0; *p++ = ~CRCVAL1; *p++ = ~CRCVAL2; *p = ~CRCVAL3;
    while ((uint16_t)(time_now() - t_idle) < IFG) ;
    tx_bytes(frm, m + 12);
    while (LT0STAT & LCS_BUSY) ;
    i = DLYL;
    while ((uint8_t)(DLYL - i) < IDLEHOLD) ;
    LC_REG(LC_T0, LC_RUN) = 0;
}

static void __attribute__((noinline)) cp(uint8_t *d, const uint8_t *s, uint8_t n) { while (n--) *d++ = *s++; }
static void __attribute__((noinline)) zero(uint8_t *d, uint16_t n) { while (n--) *d++ = 0; }
static void swap_macs(void) { cp(buf, buf + 6, 6); cp(buf + 6, mymac, 6); }

static uint8_t eq(const uint8_t *a, const uint8_t *b, uint8_t n)
{
    while (n--) if (*a++ != *b++) return 0;
    return 1;
}

static void handle(uint16_t n, uint16_t t_idle)
{
    uint16_t m = n - 4, tot, c; uint8_t mine, bc;
    mine = eq(buf, mymac, 6);
    bc = (buf[0] & buf[1] & buf[2] & buf[3] & buf[4] & buf[5]) == 0xFF;
    if (buf[12] == 0x08 && buf[13] == 0x06) {                       /* ARP request for our address */
        static const uint8_t arph[8] = {0, 1, 8, 0, 6, 4, 0, 1};
        if (!(mine || bc)) DBGX(1); if (m < 42) DBGX(2); if (!eq(buf + 14, arph, 8)) DBGX(3); if (!eq(buf + 38, myip, 4)) DBGX(4);
        swap_macs();
        buf[21] = 2;
        cp(buf + 32, buf + 22, 10);                                 /* target = old sender */
        cp(buf + 22, mymac, 6); cp(buf + 28, myip, 4);
        zero(buf + 42, 18);
        tx_frame(60, t_idle);
    } else if (buf[12] == 0x08 && buf[13] == 0x00 && (mine || FAULT == 4)) {        /* ICMP echo request */
        if (buf[14] != 0x45 || buf[23] != 1 || (buf[20] & 0x3F) || buf[21] || !eq(buf + 30, myip, 4)) return;
        tot = ((uint16_t)buf[16] << 8) | buf[17];
        if (tot < 28 || tot + 14 > m) return;
        if (csum(buf + 14, 20) != 0xFFFF || buf[34] != 8 || buf[35] != 0 || csum(buf + 34, tot - 20) != 0xFFFF) return;
        swap_macs();
        cp(buf + 30, buf + 26, 4); cp(buf + 26, myip, 4);
        buf[15] = 0; buf[18] = 0; buf[19] = 0; buf[20] = 0x40; buf[21] = 0; buf[22] = 64; buf[24] = 0; buf[25] = 0;
        c = ~csum(buf + 14, 20); buf[24] = c >> 8; buf[25] = c;
        buf[34] = 0; buf[36] = 0; buf[37] = 0;
        c = ~csum(buf + 34, tot - 20) + (FAULT == 3); buf[36] = c >> 8; buf[37] = c;
        m = tot + 14;
        if (m < 60) { zero(buf + m, 60 - m); m = 60; }
        tx_frame(m, t_idle);
    }
}

/* Settings of the CRC unit (CRC-32, right shift, residual reference), transmit cell 0 (pin 0, Manchester, B = 3,
   TWOPH) and receive cell 0 (pin 1, both clock edges, A = 9, B = 24, delimiter 0xD5). Pairs of offset and value
   in the configuration page; the cell control registers come last. */
static const uint8_t cfg[] = {
    0x40, 0x00, 0x41, 31, 0x42, 0x20, 0x43, 0x83, 0x44, 0xB8, 0x45, 0xED,
    0x4A, 0xE3, 0x4B, 0x20, 0x4C, 0xBB, 0x4D, 0xDE,
    LC_T0 + LC_PIN, LCP_OEM_ON, LC_T0 + LC_OUT, LCO_OUTSEL(0) | LCO_OUTEN | (TDM ? LCO_NSEL(2) | LCO_NEN : 0), LC_T0 + LC_TIM, LCT_TWOPH,
    LC_T0 + LC_B_REG, 3, LC_T0 + LC_ENC, LUT_ENC_MANCH, LC_T0 + LC_SH, 0xE0 | 0x10, LC_T0 + LC_CTRL, LCC_EN | LCC_TXEN,
    LC_R0 + LC_PIN, LCP_INSEL(1), LC_R0 + LC_TIM, LCT_EDGE_BOTH | LCT_ACC_WAIT | LCT_STOP_SAMPLE,
    LC_R0 + LC_A_REG, 9, LC_R0 + LC_B_REG, 24, LC_R0 + LC_DEC, LUT_DEC_INVERT, LC_R0 + LC_SH, 0xE0 | 0x10 | 0x02,
    LC_R0 + LC_MATCH, 0xD5, LC_R0 + LC_EVM, LCS_RXF | LCS_IDLE, LC_R0 + LC_CTRL, LCC_EN | LCC_RXEN | LCC_UNIT,
    0xFF};

int main(void)
{
    uint8_t st, ovr; const uint8_t *q;
    uint16_t n, t_idle;
    for (st = 0; st < 7; st++) frm[st] = 0x55;
    frm[7] = 0xD5;
    for (q = cfg; q[0] != 0xFF; q += 2) _CF8(q[0]) = q[1];       /* configuration page: offset, value */
    for (;;) {
        while (LR0STAT & LCS_RXF) (void)LR0DATA;
        LR0STAT = LCS_IDLE | LCS_OVR | LCS_MATCH | LCS_STUFF | LCS_EOP;
        crc_init(CRC_EN | CRC_RIGHT | CRC_SRC_R0);
        n = rx_frame();
        t_idle = time_now();
        ovr = LR0STAT & LCS_OVR;
        st = CRCST;
        LR0STAT = LCS_IDLE;
#ifdef DBG
        if (ovr) DBGX(11); if (!(st & CRCST_EQF)) DBGX(10 + n / 256); if (n<18||n>BUFSZ) DBGX(12);
#endif
        if (!ovr && ((st & CRCST_EQF) || FAULT == 2) && n >= 18 && n <= BUFSZ) handle(n, t_idle);
    }
}
