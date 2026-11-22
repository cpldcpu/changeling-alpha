"""Behavioural model of the event flags, interrupt enable masks, time base and wake-up times.
Written from the specification text: sections Events and timers, register map (IFR, IER, DLY),
rules D1-D4 (time base and wake-up time), E1-E5 (event flags), Q1 and Q4 (interrupt request, flags
cleared on entry), and the conventions for 16-bit registers.

One call of step() is one clock cycle. It returns what the block shows in that cycle (read data,
the flags of both cores, the interrupt requests) and then updates the state at the clock edge.
Not modelled here: the wait mask and the locks (they are in rdual, see model/dual.py).
"""
from collections import Counter

LATCHED = (0, 1, 2, 3, 4)      # PC CAPT OCA OCB OVF in IFRL bits 0..4; TRIM is bit 6 (also latched)
M16 = 0xFFFF


class Events:
    def __init__(s):
        s.lat = 0          # IFRL bits 0..4 and bit 6 (TRIM) as a mask over IFRL
        s.sw = 0           # IFRH bits 7:4
        s.dly = [0, 0]
        s.ier = [0, 0]
        s.wake = [0, 0]
        s.tbase = 0
        s.wtmp = [0, 0]    # high byte last written to DLYH, per core
        s.rtmp = [0, 0]    # high byte latched by the last read of DLYL, per core
        s.cov = Counter()

    # ---- what a core sees
    def ifr(s, core, mbx, lc, own):
        lcv = 0
        for n in range(4):
            if (lc >> n) & 1 and (own[n >> 1] == core):    # pair n>>1 is owned by the core
                lcv |= 1 << n
        lo = s.lat | (mbx << 5) | (s.dly[core] << 7)
        hi = lcv | (s.sw << 4)
        return lo | (hi << 8)

    def step(s, ptick=1, addr=0, core=0, re=0, we=0, wd=0, wm=0xFF, pc=0, capt=0, oca=0, ocb=0, ovf=0, trim=0,
             mbx=0, lc=0, own=(0, 1), ack0=0, ack1=0):
        c = s.cov
        tb0 = s.tbase
        f = [s.ifr(0, mbx, lc, own), s.ifr(1, mbx, lc, own)]
        evt = f[0] | (f[1] << 16)
        irq = [f[k] & s.ier[k] for k in (0, 1)]
        # ---- read data
        rd = 0
        if addr == 0x06: rd = f[core] & 0xFF
        elif addr == 0x07: rd = f[core] >> 8
        elif addr == 0x22: rd = s.ier[core] & 0xFF
        elif addr == 0x23: rd = s.ier[core] >> 8
        elif addr == 0x24: rd = s.tbase & 0xFF
        elif addr == 0x25: rd = s.rtmp[core]
        # ---- hardware events: pulses set latched flags (bit 0..4 and 6 of IFRL)
        setm = pc | (capt << 1) | (oca << 2) | (ocb << 3) | (ovf << 4) | (trim << 6)
        clr = 0
        # clearing by a write of ones (E1)
        if we and addr == 0x06: clr |= wd & wm & 0x5F
        # clearing when the interrupt is taken (Q4): the five timer and pin-change flags only
        ackm = (ack0 | ack1) & 0x1F
        clr |= ackm
        # E1: an event in the same cycle as the clearing write leaves the flag set.
        # Q4 says nothing about an event in the cycle of the entry; the same rule is assumed (gap G2).
        both = setm & clr
        for b in range(7):
            if (both >> b) & 1:
                c['lat_set_vs_%s_b%d' % ('w1c' if (we and addr == 0x06 and (wd & wm) >> b & 1) else 'ack', b)] += 1
        s.lat = (s.lat & ~clr) | setm
        for b in range(7):
            if (setm >> b) & 1: c['event_b%d' % b] += 1
            if (clr >> b) & 1: c['clear_b%d' % b] += 1
        # ---- software flags: masked write, bits 7:4 of IFRH
        if we and addr == 0x07:
            m = wm & 0xF0
            s.sw = (s.sw & ~(m >> 4)) | ((wd & m) >> 4)
            for b in range(4):
                if (m >> (4 + b)) & 1: c['sw%d_write%d' % (b, (wd >> (4 + b)) & 1)] += 1
            if wm & 0x0F: c['ifrh_write_level_bits'] += 1
        # ---- interrupt enable
        if we and addr == 0x22:
            s.ier[core] = (s.ier[core] & ~wm & 0xFF) | (wd & wm) | (s.ier[core] & 0xFF00)
            for b in range(8):
                if (wm >> b) & 1: c['ierl_b%d_write%d' % (b, (wd >> b) & 1)] += 1
        if we and addr == 0x23:
            hi = (s.ier[core] >> 8)
            hi = (hi & ~wm & 0xFF) | (wd & wm)
            s.ier[core] = (s.ier[core] & 0xFF) | (hi << 8)
            for b in range(8):
                if (wm >> b) & 1: c['ierh_b%d_write%d' % (b, (wd >> b) & 1)] += 1
        # ---- time base, wake-up times (D1-D3)
        if re: c['read_%02x' % addr] += 1
        if we: c['write_%02x' % addr] += 1
        tb_n = (s.tbase + 1) & M16
        if ptick:
            s.tbase = tb_n
            for k in (0, 1):
                if tb_n == s.wake[k]:
                    s.dly[k] = 1
                    c['dly_set_by_time_base_core%d' % k] += 1
        if re and addr == 0x24:
            s.rtmp[core] = tb0 >> 8
            c['dlyl_read_core%d' % core] += 1
        if we and addr == 0x25:
            s.wtmp[core] = wd
            c['dlyh_write_core%d' % core] += 1
        if we and addr == 0x24:
            old = tb0                       # time base before this cycle's step
            new = (s.wtmp[core] << 8) | wd
            d = (new - old) & M16
            # D3: past if the difference is 0 or at least 0x8000, or if the time base reaches the time in this cycle
            past = d == 0 or d >= 0x8000 or (ptick and d == 1)
            old_wake = s.wake[core]
            s.wake[core] = new
            s.dly[core] = int(past)
            key = 'dlyl_write_diff0' if d == 0 else 'dlyl_write_diff1_tick' if (d == 1 and ptick) else \
                  'dlyl_write_diff1_notick' if d == 1 else 'dlyl_write_diff8000' if d == 0x8000 else \
                  'dlyl_write_diff7fff' if d == 0x7FFF else 'dlyl_write_past' if d > 0x8000 else 'dlyl_write_future'
            c[key] += 1
            c['dlyl_write_core%d' % core] += 1
            if ptick and tb_n == old_wake: c['dlyl_write_in_cycle_of_old_match'] += 1
        # ---- acks
        for k, a in enumerate((ack0, ack1)):
            for b in range(5):
                if (a >> b) & 1: c['ack_core%d_flag%d' % (k, b)] += 1
        return rd, evt, irq[0], irq[1]
