# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Behavioural model of the timer, PWM and CRC unit (rules B1-B7, F1-F7 of the specification).
step() advances one clock cycle; the inputs of the cycle are passed in, the outputs seen in the
cycle (read data, event pulses, PWM outputs) are returned."""

M32 = 0xFFFFFFFF

class Timers:
    def __init__(s):
        s.tcr = s.tcap = s.ocra = s.ocrb = 0
        s.tcnt = s.icr = s.psc = 0
        s.cprev = 0
        s.wtmp = [0, 0]; s.rtmp = [0, 0]
        s.pwmc = s.pwmtop = 0; s.pwm = [0, 0, 0]
        s.ppsc = s.pcnt = s.atop = 0; s.ad = [0, 0, 0]
        s.cctl = s.clen = s.poly = s.val = 0
        s.sbuf = s.scnt = 0
        s.ref = 0; s.fbq = 0; s.eqf = 0

    def cstep(s, v, b):
        right = (s.cctl >> 6) & 1
        if right:
            fb = (v & 1) ^ b; v >>= 1
        else:
            fb = ((v >> s.clen) & 1) ^ b; v = (v << 1) & M32
        return v ^ (s.poly if fb else 0)

    def step(s, ptick=1, addr=0, core=0, host=0, re=0, we=0, wd=0, pins=0xFF, acc=0, ref=0, rxs=0, rxb=0, txs=0, txb=0, rxf=0):
        run, ctc, ps = s.tcr >> 7, (s.tcr >> 6) & 1, s.tcr & 7
        pg3, pg4, lo = (addr >> 4) == 0x13, (addr >> 4) == 0x14, addr & 15
        c_en, right, csrc, owner = s.cctl >> 7, (s.cctl >> 6) & 1, (s.cctl >> 3) & 7, s.cctl & 1
        cok = host or core == owner
        busy = s.scnt != 0
        # ---- read data
        rd = 0
        if addr == 0x26: rd = s.tcnt & 0xFF
        if addr == 0x28: rd = s.icr & 0xFF
        if addr in (0x27, 0x29): rd = s.rtmp[core]
        cmask = M32 if right else ((2 << s.clen) - 1)
        eq = ((s.val ^ s.ref) & cmask) == 0
        if addr == 0x2A and cok: rd = ((int(eq) if s.fbq else s.eqf) << 7) | (int(eq) << 6) | (0x20 if busy else 0)
        if pg3:
            rd = {0: s.tcr, 1: s.tcap, 2: s.ocra & 0xFF, 3: s.ocra >> 8, 4: s.ocrb & 0xFF, 5: s.ocrb >> 8,
                  8: s.pwmc, 9: s.pwmtop, 10: s.pwm[0], 11: s.pwm[1], 12: s.pwm[2]}.get(lo, 0)
        if pg4 and cok:
            rd = {0: s.cctl | (2 if busy else 0), 1: s.clen, 2: s.poly & 0xFF, 3: (s.poly >> 8) & 0xFF,
                  4: (s.poly >> 16) & 0xFF, 5: s.poly >> 24, 6: s.val & 0xFF, 7: (s.val >> 8) & 0xFF,
                  8: (s.val >> 16) & 0xFF, 9: s.val >> 24, 10: s.ref & 0xFF, 11: (s.ref >> 8) & 0xFF,
                  12: (s.ref >> 16) & 0xFF, 13: s.ref >> 24}.get(lo, 0)
        # ---- timer
        psm = (1 << ps) - 1
        t_wr = we and addr == 0x26
        tstep = ptick and run and (s.psc & psm) == psm and not t_wr
        clr = ctc and s.tcnt == s.ocra
        tn = 0 if clr else (s.tcnt + 1) & 0xFFFF
        ovf = int(bool(tstep and s.tcnt == 0xFFFF and not clr))
        oca = int(bool(tstep and tn == s.ocra)); ocb = int(bool(tstep and tn == s.ocrb))
        cpin = (pins >> (s.tcap & 7)) & 1
        cs = (s.tcap >> 5) & 3
        if cs == 0: cev = (s.cprev and not cpin) if s.tcap >> 7 else (cpin and not s.cprev)
        elif cs == 1: cev = (acc >> (s.tcap & 1)) & 1
        elif cs == 2: cev = (ref >> (s.tcap & 1)) & 1
        else: cev = 0
        capt = int(bool(cev and run))
        # ---- PWM outputs of this cycle
        pen = s.pwmc & 7; pany = pen != 0
        pout = sum(((pen >> n) & 1 and s.pcnt < s.ad[n]) << n for n in range(3))
        ppm = (1 << ((s.pwmc >> 4) & 7)) - 1
        pstep = ptick and pany and (s.ppsc & ppm) == ppm
        pwrap = s.pcnt == s.atop
        # ---- CRC
        sw = csrc == 0
        lstb, lbit = {1: (rxs & 1, rxb & 1), 2: (txs & 1, txb & 1), 3: (rxs >> 1, rxb >> 1), 4: (txs >> 1, txb >> 1)}.get(csrc, (0, 0))
        v = s.val
        if c_en and (busy if sw else lstb):
            v = s.cstep(v, ((s.sbuf & 1) if right else (s.sbuf >> 7)) if sw else lbit)
        if c_en and sw and busy:
            v = s.cstep(v, ((s.sbuf >> 1) & 1) if right else ((s.sbuf >> 6) & 1))
        in_wr = we and addr == 0x2A and cok and c_en and sw
        fbnd = int(bool(c_en and ((s.scnt == 1) if sw else (rxf & 1) if csrc == 1 else (rxf >> 1) if csrc == 3 else 0)))
        # ================= state update
        old_tcnt, old_icr = s.tcnt, s.icr
        s.cprev = cpin
        if capt: s.icr = old_tcnt
        if t_wr: s.tcnt = (s.wtmp[core] << 8) | wd
        elif tstep: s.tcnt = tn
        if not run: s.psc = 0
        elif ptick: s.psc = (s.psc + 1) & 127
        if we and addr == 0x27: s.wtmp[core] = wd
        if re and addr == 0x26: s.rtmp[core] = old_tcnt >> 8
        if re and addr == 0x28: s.rtmp[core] = old_icr >> 8
        # PWM
        if not pany: s.ppsc = 0
        elif ptick: s.ppsc = (s.ppsc + 1) & 127
        if not pany: s.pcnt = 0
        elif pstep: s.pcnt = 0 if pwrap else (s.pcnt + 1) & 255
        if not pany or (pstep and pwrap):
            s.atop = s.pwmtop; s.ad = list(s.pwm)
        # CRC
        if s.fbq: s.eqf = int(eq)
        s.fbq = fbnd
        s.val = v
        if we and pg4 and cok and 6 <= lo <= 9:
            sh = 8 * (lo - 6)
            s.val = (s.val & ~(0xFF << sh) & M32) | (wd << sh)
        if in_wr: s.sbuf, s.scnt = wd, 4
        elif busy:
            s.sbuf = (s.sbuf >> 2) if right else ((s.sbuf << 2) & 0xFF)
            s.scnt -= 1
        # configuration registers
        if we and pg3:
            if lo == 0: s.tcr = wd & 0xC7
            elif lo == 1: s.tcap = wd & 0xE7
            elif lo == 2: s.ocra = (s.ocra & 0xFF00) | wd
            elif lo == 3: s.ocra = (s.ocra & 0x00FF) | (wd << 8)
            elif lo == 4: s.ocrb = (s.ocrb & 0xFF00) | wd
            elif lo == 5: s.ocrb = (s.ocrb & 0x00FF) | (wd << 8)
            elif lo == 8: s.pwmc = wd & 0x77
            elif lo == 9: s.pwmtop = wd
            elif 10 <= lo <= 12: s.pwm[lo - 10] = wd
        if we and pg4:
            if lo == 0 and (cok or not c_en): s.cctl = wd & 0xF9
            elif lo == 1 and cok: s.clen = wd & 0x1F
            elif 2 <= lo <= 5 and cok:
                sh = 8 * (lo - 2)
                s.poly = (s.poly & ~(0xFF << sh) & M32) | (wd << sh)
            elif 10 <= lo <= 13 and cok:
                sh = 8 * (lo - 10)
                s.ref = (s.ref & ~(0xFF << sh) & M32) | (wd << sh)
        return rd, capt, oca, ocb, ovf, pen, pout
