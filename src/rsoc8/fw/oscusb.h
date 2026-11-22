/* Clock of the USB device from the internal oscillator (see fwusb.c). Shared by the images:
   osc_adjust and osc_loop_on are used by the lock tracking on core 0; osc_start is compiled where
   OSC_WITH_START is defined (core 0 in the one-core build, core 1 in the two-core build). */
#ifndef OSCUSB_H
#define OSCUSB_H
/* Clock from the internal oscillator, trimmed to 15 MHz with the keep-alive signal of the host as
   reference: the receive cell reports every end of packet, the trim counter measures the clock
   cycles between two of them, 15000 for one frame.
   1. Coarse: two measurements in a row that agree are taken as one frame; the trim value is
      corrected by the measured error (0.5 % or 75 counts per step).
   2. Then the loop of the clocking block is switched on with a window of 192 counts (1.3 %). It
      moves the trim value by one step per frame; intervals that end at a packet are outside the
      window. */
#define FRAME_CNT 15000u
#ifndef OSC_LOST_N
#define OSC_LOST_N 3            /* keep-alive signals in a row without a valid measurement: lock is lost */
#endif
#define OSC_REC_STEPS 3         /* trim steps per keep-alive signal during the recovery (1.5 %) */
#define OSC_FINAL (CKC_OSCEN | CKC_SRC | CKC_REF_CELL | CKC_REFCELL(0))
#ifdef OSC_PROBE
#define PROBE(x) _IO8(0x1C) = (x)
#else
#define PROBE(x)
#endif

/* change the trim value by the error c (counts per frame) in steps of 75 counts, at most nmax steps;
   returns the number of steps */
static uint8_t __attribute__((unused)) osc_adjust(uint16_t c, uint8_t nmax)
{
    uint8_t t = OSCTRIM, n = 0;
    while (c < FRAME_CNT - 37 && t < 255 && n < nmax) { c += 75; t++; n++; }
    while (c > FRAME_CNT + 37 && t > 0   && n < nmax) { c -= 75; t--; n++; }
    OSCTRIM = t;
    return n;
}
static void __attribute__((unused)) osc_loop_on(void)
{
    TRWIN = 3;
    PROT_WRITE(CLKCTL, OSC_FINAL | CKC_LOOP);
}
#ifdef OSC_WITH_START
static void osc_start(void)
{
    uint16_t c, last = 0; uint8_t tries = 0;
    PROT_WRITE(CLKCTL, CKC_OSCEN);
    while (!(CLKSTAT & CKS_OSCRUN)) ;
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC);
    while (!(CLKSTAT & CKS_SRC)) ;
    TRTGT = FRAME_CNT; TRWIN = 0;
    PROT_WRITE(CLKCTL, OSC_FINAL);
    for (;;) {
        IFRL = EV_TRIM; wait_for(EV_TRIM);
        c = TRCNT;
        if (c > 11000 && c < 19000 && c - last + 40 < 80) {         /* a frame, twice the same length */
            if (c > FRAME_CNT - 60 && c < FRAME_CNT + 60) break;
            osc_adjust(c, 255); c = 0;
            if (++tries == 8) break;
        }
        last = c;
    }
    osc_loop_on();
    _IO8(0x1D) = OSCTRIM;                                   /* mark for the testbench */
}
#endif

#ifdef OSC_WITH_TRACK
/* Loss of lock: osc_track is called once per keep-alive signal. Two things are checked.
   a) While the loop works, every frame sets EV_TRIM. OSC_LOST_N keep-alive signals in a row without it.
   b) The timer captures the start of every end of packet of the host, so the time between two
      keep-alive signals is measured exactly (one frame, 15000 counts) whatever else is on the bus.
      A frame that is more than 1.5 % off, twice in a row. This also covers a clock that is slow: the
      counter of the clocking block then accepts a keep-alive signal and the next packet end as one
      interval, and the loop sees a wrong but valid count.
   Then the loop is switched off and the trim value is corrected in firmware from the frame time:
   two frames in a row that agree within 40 counts, at most OSC_REC_STEPS trim steps per keep-alive
   signal so that the time spent here stays small, until the frame time is within 60 counts of 15000;
   then the loop is switched on again. Frames that do not follow each other (frame time outside 11000
   to 19000, for instance one keep-alive signal missing) are not used.
   The USB device is not reliable while the error is above the 1.5 % of the bus. */
static uint8_t osc_lost, osc_rec, osc_bad; static uint16_t osc_last, osc_cap;
static void osc_track(uint16_t cap)
{
    uint16_t c = cap - osc_cap;                  /* c: time since the previous keep-alive signal */
    uint8_t one = (c > 11000 && c < 19000);
    PROBE(0x10);
    osc_cap = cap;
    if (!osc_rec) {
        if (one) osc_bad = (c - FRAME_CNT + 225 > 450) ? osc_bad + 1 : 0;
        if (IFRL & EV_TRIM) { IFRL = EV_TRIM; osc_lost = 0; } else osc_lost++;
        if (osc_lost >= OSC_LOST_N || osc_bad >= 2) {
            osc_rec = 1; osc_last = 0;
            PROT_WRITE(CLKCTL, OSC_FINAL);
            PROBE(1);
        }
    } else if (one) {
        if (c - osc_last + 40 < 80) {
            if (c > FRAME_CNT - 60 && c < FRAME_CNT + 60) {
                osc_loop_on(); osc_rec = 0; osc_lost = 0; osc_bad = 0; osc_last = 0; IFRL = EV_TRIM; PROBE(2);
            } else { osc_adjust(c, OSC_REC_STEPS); osc_last = 0; }
        } else osc_last = c;
    }
    PROBE(0x11);
}
#endif
#endif
