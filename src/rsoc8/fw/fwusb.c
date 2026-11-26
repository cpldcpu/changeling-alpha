/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* USB low-speed HID device, core 0: enumeration and one interrupt endpoint.
   Token and packet handling with the answer deadlines is in usb_stack.S; this file decodes the
   requests and selects the packets. Descriptors are stored as complete data packets (usb_desc.h).
   Without SENSOR the reports come from a counter in this core. With SENSOR core 1 leaves complete
   report packets (sens.h), and this core only passes them on. */
#include "usb.h"
#ifdef SENSOR
#include "sens.h"
#if defined(OSC) || defined(DESC_C1)
#define USB_DESC_EXTERN         /* the descriptor packets are in the code memory of core 1 (fwsens_c1.c); needed to fit core 0 into 2048 bytes */
#endif
#endif
#include "usb_desc.h"
/* fault insertion for the tests (never set in the real build):
   FLT_CUR GET_REPORT returns a stale report, FLT_DUP a repeated OUT data packet is applied again, FLT_PWM0 the output report is
   not applied, FLT_ZLP no zero-length packet, FLT_ZLPALL a zero-length packet after every control read, FLT_RESTART a SETUP
   during a control read is ignored, FLT_STALLCLR a packet that is not for this device clears the STALL, FLT_CFG GET_CONFIGURATION
   returns the wrong value */
#ifdef FLT_ZLP
#define FLT_ZLP_N(n) 1
#else
#define FLT_ZLP_N(n) (n)
#endif
#ifndef FEAT
#define FEAT 5                  /* requests added in steps: 1 GET_REPORT, 2 SET_REPORT, 3 GET_CONFIGURATION, 4 GET_IDLE, 5 protocol (size measurement) */
#endif

static struct usb_state u;
static const uint8_t rxc[15] = USB_RX(0, 1);
static const uint8_t txc[15] = USB_TX(0, 1);
static const uint8_t pk_stall[2] = { 1, PID_STALL };

static const uint8_t *p0;           /* next packet of the control transfer */
static uint8_t n0;                  /* packets left */
static uint8_t new_addr = 0xFF;     /* address that takes effect after the status stage */
static uint8_t configured;
#if FEAT >= 1
/* the input report that was made last, as a data packet (DATA1) for GET_REPORT; cur[0] = bytes to send; behind it
   the empty DATA0 packet that closes a transfer if the host has asked for more than the 8 bytes */
#ifdef SENSOR
#define cur S_CUR               /* core 1 keeps it (fwsens_c1.c): no copy in the time of the USB core */
#else
/* not initialised (the start-up code of the C runtime takes time that the receive cell needs: it has to be on before the first bus reset) */
static uint8_t cur[16] __attribute__((section(".noinit")));
static uint8_t cur_ok;              /* cur holds a complete report */
static uint8_t get_pend;            /* GET_REPORT arrived while the report is being built: 1 or 2 packets, armed when it is complete */
#endif
static void __attribute__((unused)) cpy(uint8_t *d, const uint8_t *s, uint8_t n) { while (n--) *d++ = *s++; }
#endif
#if FEAT >= 2
static uint8_t outp[16] __attribute__((section(".noinit")));   /* the output report of SET_REPORT as received (identifier, 8 bytes, CRC-16), then the empty DATA0 packet */
static uint8_t outp_ok;             /* outp holds an output report */
static uint8_t ws;                  /* control write: 0 none, 1 waiting for the data, 2 data taken, 3 request refused */
#endif
#if FEAT >= 5
static uint8_t boot;                /* HID protocol: 0 report protocol (default), 1 boot protocol; no effect on the reports */
#endif
#ifndef SENSOR
static uint8_t rep[11];             /* report packet: identifier, 8 bytes, CRC-16 */
static uint8_t rep_cnt;
#endif

static void arm0(const uint8_t *p, uint8_t n) { p0 = p; n0 = n; u.ep0_ptr = p + 1; u.ep0_len = p[0]; }

#ifdef SENSOR
static uint8_t toggle = PID_DATA0;
/* give a waiting report of core 1 to the USB routine; never waits for the lock */
static void report(void)
{
    uint8_t *p;
    if (!configured || u.ep1_len || !S_RDY) return;
    if (!lock_try(0)) return;
    S_ARMED = S_RDY; S_RDY = 0;
    lock_release(0);
    p = S_BUF(S_ARMED - 1);
    p[0] = toggle;
    u.ep1_ptr = p; u.ep1_len = 11;
}
#else
/* The report is built one byte per pass of the main loop. The time between two calls of usb_poll
   has to stay below the time in which the receive cell holds the start of the next token. */
static const uint16_t crc_nib[16] = { 0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
                                      0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400 };
static uint8_t rep_i = 0xFF;        /* next byte to build; 0xFF: nothing to do */
static uint16_t rep_crc;
static void report(void)
{
    uint8_t b; uint16_t v;
    if (rep_i == 0xFF) return;
    if (rep_i == 8) {
        v = ~rep_crc; rep[9] = (uint8_t)v; rep[10] = (uint8_t)(v >> 8);
        u.ep1_ptr = rep; u.ep1_len = 11; rep_i = 0xFF;
#if FEAT >= 1 && !defined(FLT_CUR)
        cur[10] = rep[9]; cur[11] = rep[10];
        cur[0] = 11; cur[1] = PID_DATA1; cur[12] = 3; cur[13] = PID_DATA0; cur[14] = 0; cur[15] = 0; cur_ok = 1;
        if (get_pend) { arm0(cur, get_pend); get_pend = 0; }    /* GET_REPORT was waiting for the report */
#endif
        return;
    }
    b = rep_i ? (uint8_t)(rep_i * 17 + rep_cnt) : rep_cnt;
    rep[1 + rep_i] = b;
#if FEAT >= 1 && !defined(FLT_CUR)
    cur[2 + rep_i] = b;             /* the report for GET_REPORT is built together with it (a copy at the end would take too long in one pass) */
#endif
    rep_i++;
    v = rep_crc;
    v = (v >> 4) ^ crc_nib[(v ^ b) & 15];
    v = (v >> 4) ^ crc_nib[(v ^ (b >> 4)) & 15];
    rep_crc = v;
}
static void report_start(void) { rep_i = 0; rep_crc = 0xFFFF; }
#endif

static void setup(void)
{
    const uint8_t *d = u.data + 1;                          /* bmRequestType, bRequest, wValue, wIndex, wLength */
    uint8_t len = d[7] ? 255 : d[6], t = d[0], r = d[1], w = d[3];
#if FEAT >= 2
    ws = 0;
#endif
#if FEAT >= 1 && !defined(SENSOR)
    get_pend = 0;
#endif
    if (r == 6) {                                        /* GET_DESCRIPTOR */
        if (w == 1)         arm0(usb_pk_device, len >= USB_LEN_DEVICE ? USB_PK_DEVICE_N : len >> 3);
        else if (w == 2) { if (len == 9) arm0(usb_pk_config9, USB_PK_CONFIG9_N);
                              else arm0(usb_pk_config, len >= USB_LEN_CONFIG ? USB_PK_CONFIG_N : len >> 3); }
        else if (w == 0x22) arm0(usb_pk_report, len >= USB_LEN_REPORT ? USB_PK_REPORT_N : len >> 3);
        else                   arm0(pk_stall, 1);
        if (n0 == 0) arm0(pk_stall, 1);
    } else if (t == 0x00 && r == 5) {                 /* SET_ADDRESS */
        new_addr = d[2]; arm0(usb_pk_zero, 1);
    } else if (t == 0x00 && r == 9) {                 /* SET_CONFIGURATION */
        configured = d[2]; arm0(usb_pk_zero, 1);
#ifdef SENSOR
        toggle = PID_DATA0; u.ep1_len = 0; S_ARMED = 0;
#else
        rep[0] = PID_DATA0; u.ep1_len = 0; if (configured) report_start(); else rep_i = 0xFF;
#endif
    } else if (t == 0x21 && r == 0x0A) {              /* HID SET_IDLE */
#if FEAT >= 4
        if (w) arm0(pk_stall, 1);                        /* only idle rate 0 (no repetition) is supported */
        else
#endif
        arm0(usb_pk_zero, 1);
    } else if (t == 0x80 && r == 0) {                 /* GET_STATUS */
        arm0(usb_pk_status, 1);
#if FEAT >= 1
    } else if (t == 0xA1 && r == 1) {                 /* HID GET_REPORT: input report (type 1) or the last output report (type 2) */
        if (len < 8 || w == 0 || w > 2
#if FEAT < 2
            || w == 2
#endif
            ) arm0(pk_stall, 1);
        else {
            uint8_t np = FLT_ZLP_N(1 + (len > 8));
#ifndef SENSOR
            if (w == 1 && (rep_i != 0xFF || !cur_ok)) get_pend = np;   /* no report yet or it is being built: NAK until it is complete */
            else
#endif
#if FEAT >= 2
            if (w == 2 && !outp_ok) arm0(usb_pk_zero, 1);   /* no output report yet: empty */
            else arm0(w == 1 ? cur : outp, np);
#else
            arm0(cur, np);
#endif
        }
#endif
#if FEAT >= 2
    } else if (t == 0x21 && r == 9) {                 /* HID SET_REPORT: one output report of 8 bytes in the data stage */
        if (len != 8 || w != 2) { ws = 3; arm0(pk_stall, 1); }
        else ws = 1;                                        /* the status stage IN is answered with NAK until the data has been taken */
#endif
#if FEAT >= 3
    } else if (t == 0x80 && r == 8) {                 /* GET_CONFIGURATION */
        arm0(usb_pk_val + (
#ifdef FLT_CFG
            !
#endif
            configured ? 5 : 0), 1);
#endif
#if FEAT >= 4
    } else if (t == 0xA1 && r == 2) {                 /* HID GET_IDLE */
        arm0(usb_pk_val, 1);
#endif
#if FEAT >= 5
    } else if (t == 0xA1 && r == 3) {                 /* HID GET_PROTOCOL */
        arm0(usb_pk_val + (boot ? 0 : 5), 1);
    } else if (t == 0x21 && r == 0x0B) {              /* HID SET_PROTOCOL */
        if (d[2] > 1) arm0(pk_stall, 1); else { boot = !d[2]; arm0(usb_pk_zero, 1); }
#endif
    } else arm0(pk_stall, 1);
}

#ifdef OSC
#if defined(SENSOR)
#include "oscusb.h"               /* osc_start and osc_track run on core 1 (fwsens_c1.c) */
#else
#define OSC_WITH_START
#define OSC_WITH_TRACK
#include "oscusb.h"
#endif
#endif

int main(void)
{
#ifdef SENSOR
    S_RDY = 0; S_ARMED = 0; S_FRAME = 0; S_OSC = 0;
    PROT_WRITE(ARB, ARB_CORE0);                             /* this core has the answer deadlines */
#ifndef OSC
    CORECTL = CORE_EN(0) | CORE_EN(1);
#endif
#endif
    lc_setup(LC_T0, txc); lc_setup(LC_R0, rxc);
#if FEAT >= 2
    PWMTOP = 255; PWM0 = 0; PWMC = PWMC_EN(0);              /* the first byte of an output report is the duty on this pin */
#endif
#ifdef OSC
#ifdef SENSOR
    CORECTL = CORE_EN(0) | CORE_EN(1);                      /* core 1 starts the oscillator with the receive cell as reference */
    while (!S_OSC) ;
#else
    osc_start();
#endif
#endif
    LC_REG(LC_T0, LC_CTRL) = LCC_EN; LT0DATA = 0x80;        /* sync byte of the first answer */
    TCAP = TCAP_SRC_REF | TCAP_PIN(0); TCR = TCR_RUN | TCR_PS(USB_TPS);
    CRCCTL = 0; CRCPOLY2 = 0; CRCPOLY3 = 0; CRCVAL2 = 0; CRCVAL3 = 0; CRCREF2 = 0; CRCREF3 = 0;
    usb_crc_token_mode();
    for (;;) {
        uint8_t ev = usb_poll(&u);
#ifdef OSC_PROBE
        _IO8(0x1C) = 0x20 + ev;                             /* testbench: time of this pass up to the next call */
#endif
        switch (ev) {
        case USB_SETUP:
#ifdef FLT_RESTART
            if (n0 && u.ep0_len) break;
#endif
            u.ep0_len = 0; setup(); break;
        case USB_IN0:                                       /* a packet of the control transfer was taken */
            if (new_addr != 0xFF) { u.addr = new_addr; new_addr = 0xFF; }
            p0 += 1 + p0[0];
            if (--n0) { u.ep0_ptr = p0 + 1; u.ep0_len = p0[0]; } else u.ep0_len = 0;
#ifdef FLT_ZLPALL
            if (!n0) { u.ep0_ptr = usb_pk_zero + 1; u.ep0_len = 3; }
#endif
            break;
        case USB_OUT:
#if FEAT >= 2
            /* ws 1: the output report of SET_REPORT. ws 2: it comes again (the host did not see the ACK), already acknowledged by
               the stack, not applied again. ws 3: request refused. ws 0: status stage of a control read. */
#ifdef FLT_DUP
            if (ws == 1 || ws == 2) {
#else
            if (ws == 1) {
#endif
                ws = 2;
                if (u.dlen == 11) {                         /* identifier, 8 bytes, CRC-16 */
                    outp[0] = 11; cpy(outp + 1, u.data, 11); outp[12] = 3; outp[13] = PID_DATA0; outp[14] = 0; outp[15] = 0; outp_ok = 1;
#ifndef FLT_PWM0
                    PWM0 = u.data[1];                       /* visible effect: first byte is the PWM duty */
#endif
                }
                arm0(usb_pk_zero, 1);                       /* status stage: IN is answered with an empty DATA1 */
            } else if (ws == 0)
#endif
            u.ep0_len = 0;
            break;
        case USB_IN1:                                       /* the report was taken */
#ifdef SENSOR
            toggle ^= PID_DATA0 ^ PID_DATA1; u.ep1_len = 0; S_ARMED = 0; break;
#else
            rep[0] ^= PID_DATA0 ^ PID_DATA1; rep_cnt++;
            u.ep1_len = 0; report_start(); break;
#endif
        case USB_EOP:                                       /* keep-alive, or a bus reset if the pins stay low */
            delay_after(3 * USB_CPB); wait_for(EV_DLY);
            if (LR0STAT & LCS_BOTHL) {
                u.addr = 0; u.ep0_len = 0; u.ep1_len = 0; configured = 0; new_addr = 0xFF;
#if FEAT >= 5
                boot = 0;
#endif
#ifdef SENSOR
                S_ARMED = 0; S_FRAME = 0;
#else
                rep_i = 0xFF;
#endif
                _IO8(0x1E) = 0xB5;                          /* mark for the testbench */
            }
            else {
#ifdef SENSOR
                S_FRAME++;
#endif
#if defined(OSC) && !defined(OSC_NOTRACK)
#ifdef SENSOR
                S_CAP = ICR; IFRH |= 1 << IFRH_SW0;         /* core 1 tracks the oscillator: time of the keep-alive signal, then the flag */
#else
                osc_track(ICR);
#endif
#endif
            }
            break;
#ifdef FLT_STALLCLR
        default: if (u.ep0_ptr == pk_stall + 1) u.ep0_len = 0; break;
#else
        default: break;
#endif
        }
        report();
#ifdef OSC_PROBE
        _IO8(0x1C) = 0x13;
#endif
    }
}
