"""Behavioural model of the synchronous control part of the clocking block (rclk_ctl): registers, presence
check, source request, dividers, trim counter with window and loop, clock output, debug signal.
Written from the specification: section Clocking, Clocking registers (CLKCTL ... CLKOUT, DBGSEL, CLKSTAT),
rules K1-K12. The two asynchronous clocks and the gates (rclk_src) are not modelled; its outputs tgl_ext,
tgl_osc, open_osc are inputs here.

Places where the specification gives no cycle-exact rule are marked GAP-n; the model fixes a choice there
and the choice is listed in the report.
"""
from collections import Counter
M16 = 0xFFFF
CLKCTL, OSCTRIM, CDIV, PDIV, TRINT, TRCNTL, TRCNTH, TGTL, TGTH, TRWIN, CLKOUT = (0x120 + i for i in range(11))
CLKSTAT, DBGSEL = 0x00F, 0x152


class ClkCtl:
    EARLY_LE = True   # an event not later than target - window is not used (specification from draft 0.32)
    SYNC = 2          # GAP-1: delay of the synchronisers in cycles; the spec says only "through a synchroniser"

    def __init__(s):
        s.booted = 0
        s.src = 0; s.oscen = 0; s.ctl = 0        # CLKCTL: SRC OSCEN, ctl = bits 6:2 (LOOP TRIMD REFSEL[2] REFCELL)
        s.sel = 0                                # selected source (the one that rclk_src is told)
        s.trim = 0x80; s.cdiv = 0; s.pdiv = 0; s.int = 0; s.tgt = 0; s.win_r = 0; s.cko_r = 0; s.dbg_r = 0
        s.cnth_lat = 0
        s.se = [0, 0, 0]; s.so = [0, 0, 0]; s.sa = [0, 0]
        s.wctr = 0; s.seen_e = 0; s.seen_o = 0; s.pres_e = 0; s.pres_o = 0
        s.sh = [0, 0, 0]; s.sp = [0, 0, 0]       # reference synchronisers
        s.st = 0                                 # 0 idle, 1 waiting for the first event, 2 counting
        s.cnt = 0; s.trcnt = 0; s.per = 0
        s.mdone = 0; s.mvalid = 0; s.done_q = 0
        s.cc = 0; s.pc = 0; s.cke = 1; s.ptick = 1   # GAP-2: reset phase of the dividers
        s.oc = 0; s.cko_q = 0; s.dbg_q = 0
        s.cov = Counter()

    # ---- register fields
    def loop(s): return (s.ctl >> 0) & 1
    def trimd(s): return (s.ctl >> 1) & 1
    def refsel(s): return (s.ctl >> 2) & 3
    def refcell(s): return (s.ctl >> 4) & 1

    def read(s, addr, strap):
        if addr == CLKSTAT:
            return (strap << 7) | (s.mvalid << 5) | (s.mdone << 4) | (s.trimd() << 3) | (s.pres_e << 2) | (s.pres_o << 1) | s.sa[1]
        if addr == DBGSEL: return s.dbg_r
        if addr == CLKCTL: return (s.refcell() << 6) | (s.refsel() << 4) | (s.trimd() << 3) | (s.loop() << 2) | (s.oscen << 1) | s.src
        if addr == OSCTRIM: return s.trim
        if addr == CDIV: return s.cdiv
        if addr == PDIV: return s.pdiv
        if addr == TRINT: return ((int(s.st != 0 and s.refsel() != 2)) << 7) | s.int
        if addr == TRCNTL: return s.trcnt & 0xFF
        if addr == TRCNTH: return s.cnth_lat
        if addr == TGTL: return s.tgt & 0xFF
        if addr == TGTH: return s.tgt >> 8
        if addr == TRWIN: return s.win_r
        if addr == CLKOUT: return s.cko_r
        return 0

    def step(s, strap=0, addr=0, re=0, we=0, wd=0, unlock=0, host=0, tgl_ext=0, tgl_osc=0, open_osc=0,
             ref_host=0, ref_pin=0, ref_evt=(0, 0), smp=(0, 0), acc=(0, 0), txs=(0, 0), ccen=(0, 0), hold=0):
        c = s.cov
        ok = unlock or host
        if we: c['write_%03x%s' % (addr, '' if addr not in (CLKCTL, CDIV) else ('_accepted' if ok else '_rejected'))] += 1
        if re: c['read_%03x' % addr] += 1
        if (s.dbg_r >> 7): c['debug_sel_%d_enabled_cycles' % (s.dbg_r & 15)] += 1
        if s.cko_r >> 7: c['clock_out_div_%d_cycles' % (s.cko_r & 7)] += 1
        if s.cdiv: c['core_div_nonzero_cycles'] += 1
        if s.pdiv: c['periph_div_nonzero_cycles'] += 1
        prot = int(addr in (CLKCTL, CDIV))
        rd = s.read(addr, strap) if re else 0
        sel_o = s.sel if s.booted else strap
        # K1 (literal): the enable of the oscillator stays active while it is the requested or the active source
        act = s.sa[1]
        osc_en = (s.oscen | s.src | s.sel | act) if s.booted else strap   # GAP-3: K1 says requested or active; the selected source is added (GAP-3b)
        # ---- trim counter combinational part
        line = s.refsel() == 2
        edge_pin = (s.sp[1] and not s.sp[2]) if (s.refsel() & 1) else (s.sh[1] and not s.sh[2])
        rev = (ref_evt[s.refcell()] if line else (edge_pin and not (s.refsel() & 2)))
        rev = int(bool(rev))
        wspan = s.win_r * 64
        # window rule for a line reference: an event earlier than target minus window is not used.
        # Literal reading: early if the time since the start of the interval is LESS than target - window.
        early = int(line and s.win_r != 0 and (s.cnt + wspan <= s.tgt if s.EARLY_LE else s.cnt + wspan < s.tgt))
        rev_c = int(rev and not early)
        if rev and early: c['event_early_ignored'] += 1
        fin = int(s.st == 2 and rev_c and (line or s.per == s.int))
        diff = s.trcnt - s.tgt
        adiff = abs(diff)
        valid = int(s.win_r == 0 or adiff < wspan)
        trim_evt = int(s.done_q and valid)
        up = int(s.done_q and valid and s.loop() and diff < 0 and s.trim != 0xFF)
        dn = int(s.done_q and valid and s.loop() and diff > 0 and s.trim != 0)
        ctl_wr = int(we and addr == CLKCTL and ok)
        meas_wr = int(we and addr == TRINT and (wd >> 7) & 1)
        # ---- debug signal selection
        sel_d = s.dbg_r & 15
        dsig = {0: smp[0], 1: smp[1], 2: txs[0], 3: txs[1], 4: acc[0], 5: acc[1], 6: ref_evt[0], 7: ref_evt[1],
                8: ccen[0], 9: ccen[1], 10: hold, 11: s.ptick, 12: s.cke, 13: int(s.st != 0), 14: trim_evt}.get(sel_d, 0)  # GAP-4: 15
        out = (rd, prot, sel_o, osc_en, s.trim, s.cke, s.ptick, trim_evt, s.cko_r >> 7, s.cko_q, s.dbg_r >> 7, s.dbg_q)
        # ================= clock edge
        s.cko_r_old = s.cko_r
        n = {}
        if not s.booted:
            s.booted = 1; s.src = strap; s.oscen = strap; s.sel = strap          # K4
        elif s.src != s.sel and (s.pres_o if s.src else s.pres_e):                # K3
            s.sel = s.src; c['switch_to_%d' % s.src] += 1
        elif s.src != s.sel: c['switch_pending_target_absent_cycles'] += 1
        if ctl_wr:
            s.src = wd & 1; s.oscen = (wd >> 1) & 1; s.ctl = (wd >> 2) & 0x1F       # bit 7 is reserved: ignored
            c['clkctl_write']+=1
        elif we and addr == CLKCTL: c['clkctl_write_rejected'] += 1
        # presence (K2)
        te = s.se[2] ^ s.se[1]; to = s.so[2] ^ s.so[1]
        s.se = [tgl_ext] + s.se[:2]; s.so = [tgl_osc] + s.so[:2]; s.sa = [open_osc, s.sa[0]]
        s.wctr = (s.wctr + 1) & 0x3FF
        if s.wctr == 0:
            s.pres_e = int(s.seen_e or te); s.pres_o = int(s.seen_o or to); s.seen_e = s.seen_o = 0
        else:
            if te: s.seen_e = 1
            if to: s.seen_o = 1
        # dividers (K5): a new value takes effect when the running count ends
        cc_n = s.cdiv if s.cc == 0 else s.cc - 1
        pc_n = s.pdiv if s.pc == 0 else s.pc - 1
        s.cc = cc_n; s.cke = int(cc_n == 0); s.pc = pc_n; s.ptick = int(pc_n == 0)
        if we and addr == CDIV and ok: s.cdiv = wd
        if we and addr == PDIV: s.pdiv = wd
        # trim counter
        s.sh = [ref_host] + s.sh[:2]; s.sp = [ref_pin] + s.sp[:2]
        dq = s.done_q
        s.done_q = fin
        cnt_old = s.cnt; trcnt_old = s.trcnt
        s.cnt = min(s.cnt + 1, M16)
        if ctl_wr:
            if s.st: c['measurement_aborted_by_clkctl_write'] += 1
            s.st = 0
        elif s.st == 0:
            if line or meas_wr or (s.loop() and not (s.refsel() & 2)): s.st = 1
        elif s.st == 1:
            if rev: s.st = 2; s.cnt = 1; s.per = 0; c['measurement_started_%s' % ('line' if line else 'pin')] += 1
        else:
            if rev_c:
                if fin:
                    s.trcnt = cnt_old; s.mdone = 1
                    c['measurement_end_%s' % ('line' if line else 'pin')] += 1
                    if line: s.cnt = 1
                    else: s.st = 0
                else: s.per = (s.per + 1) & 0x7F       # GAP-5: width of the period counter when INT is changed during a measurement
        if meas_wr: s.mdone = 0; c['meas_write'] += 1
        if dq: s.mvalid = valid
        if dq: c['done_valid' if valid else 'done_invalid'] += 1
        if we and addr == OSCTRIM:
            s.trim = wd
            if up or dn: c['trim_write_vs_loop_step_same_cycle'] += 1
        elif up: s.trim += 1; c['loop_up'] += 1
        elif dn: s.trim -= 1; c['loop_down'] += 1
        elif dq and valid and s.loop(): c['loop_equal'] += 1
        if dq and valid and s.loop() and ((diff < 0 and s.trim == 0xFF) or (diff > 0 and s.trim == 0)): c['loop_limit'] += 1
        if re and addr == TRCNTL: s.cnth_lat = trcnt_old >> 8
        # registers written by the bus (read-back masks from the register tables)
        if we and addr == TRINT: s.int = wd & 0x7F
        if we and addr == TGTL: s.tgt = (s.tgt & 0xFF00) | wd
        if we and addr == TGTH: s.tgt = (s.tgt & 0xFF) | (wd << 8)
        if we and addr == TRWIN: s.win_r = wd
        if we and addr == CLKOUT: s.cko_r = wd & 0x87
        if we and addr == DBGSEL: s.dbg_r = wd & 0x8F
        # outputs
        s.cko_q = (s.oc >> (s.cko_r_old & 7)) & 1                              # uses the counter and CLKOUT of this cycle
        s.oc = (s.oc + 1) & 0xFF
        s.dbg_q = int(dsig)
        return out
