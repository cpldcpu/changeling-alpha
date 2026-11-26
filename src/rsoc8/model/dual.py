# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Behavioural model of the register-side behaviour of rdual: bus arbiter, locks, wait masks, core
enable and wait state, ARB. Written from the specification: rules U1-U9 (shared bus), C5-C10 (locks),
H1-H9 (core control, wait, sleep, break, halt), register map entries LOCK 0x05, CORECTL 0x0E,
WAITL/WAITH 0x20/0x21 and ARB. The cores are replaced by scripted bus users ("ops"), see tb/stub_core.v.

Ops of one core are executed in order; an op is consumed in a cycle in which the core advances.
 kind: NOP, READ addr, WRITE addr data mask unlock, SLEEP, BREAK, SETI, CLRI (the I flag of the core)
"""
from collections import Counter
NOP, READ, WRITE, SLEEP, BREAK, SETI, CLRI = range(7)
A_LOCK, A_CTL, A_WL, A_WH, A_ARB = 0x005, 0x00E, 0x020, 0x021, 0x150


def passthru(addr):          # the testbench returns this for registers that are not in rdual
    return (addr & 0xFF) ^ 0x5A


class Dual:
    def __init__(s, ops):
        s.ops = ops; s.pc = [0, 0]
        s.en = [1, 0]                    # H1: core 0 enabled, core 1 stopped
        s.wt = [0, 0]; s.brk = [0, 0]; s.ie = [0, 0]
        s.mask = [0, 0]
        s.arb = 0
        s.last = 1                       # core granted at the last collision; after reset: gap, core 0 wins the first one
        s.held = [0] * 4; s.owner = [0] * 4
        s.cov = Counter()

    def op(s, c):
        return s.ops[c][s.pc[c]] if s.pc[c] < len(s.ops[c]) else (NOP, 0, 0, 0, 0)

    def read(s, gs, addr, wt=None):
        if addr == A_CTL: return (gs << 7) | (s.wt[1] << 5) | (s.wt[0] << 4) | (s.en[1] << 1) | s.en[0]
        if addr == A_LOCK:
            mine = other = 0
            for n in range(4):
                if s.held[n]:
                    if s.owner[n] == gs: mine |= 1 << n
                    else: other |= 1 << n
            return (other << 4) | mine
        if addr == A_WL: return s.mask[gs] & 0xFF
        if addr == A_WH: return s.mask[gs] >> 8
        if addr == A_ARB: return s.arb
        return passthru(addr)

    def step(s, cke=1, evt=(0, 0), irq=(0, 0), halt=(0, 0), brk_clr=(0, 0)):
        cv = s.cov
        ops = [s.op(0), s.op(1)]
        base = [int(s.en[c] and not s.wt[c] and not (s.brk[c] or halt[c]) and cke) for c in (0, 1)]
        rq = [int(ops[c][0] in (READ, WRITE)) for c in (0, 1)]
        req = [base[c] & rq[c] for c in (0, 1)]
        # U2: one core requests: granted. Both: MODE 1 core 0, 2 core 1, 0 the one not granted at the last collision
        g = [0, 0]
        if req[0] and not req[1]: g[0] = 1
        elif req[1] and not req[0]: g[1] = 1
        elif req[0] and req[1]:
            cv['collision_mode%d' % s.arb] += 1
            if s.arb == 1: g[0] = 1
            elif s.arb == 2: g[1] = 1
            else: g[0 if s.last == 1 else 1] = 1
            if s.arb == 0: cv['collision_alternate_grant_core%d' % (0 if g[0] else 1)] += 1
        cen = [base[c] & (1 if not rq[c] else g[c]) for c in (0, 1)]
        hold = int((req[0] and not g[0]) or (req[1] and not g[1]))
        gs = 1 if g[1] else 0
        rb = s.read(gs, ops[gs][1]) if (g[0] or g[1]) and ops[gs][0] == READ else None
        out = (cen[0], cen[1], hold, s.wt[0], s.wt[1], s.en[0], s.en[1], s.brk[0], s.brk[1], rb)
        # All state advances only in cycles with the core clock enable (gap G: the specification does not say so for the
        # wait compare; a flag that is high for one source clock cycle only is missed by a slow core)
        if not cke: s.cov['cycles_without_cke'] += 1; return out
        # ---- state update
        en_new = list(s.en)
        ev = [evt[0], evt[1]]
        # wake, from the masks before this cycle
        wake = [s.wt[c] and (bool(s.mask[c] & ev[c]) or bool(s.ie[c] and irq[c])) for c in (0, 1)]
        go = [0, 0]
        new_mask = list(s.mask)
        for c in (0, 1):
            if cen[c] and ops[c][0] == WRITE and g[c]:
                _, addr, data, wm, unl = ops[c]
                cv['write_%03x_core%d' % (addr, c)] += 1
                if addr == A_CTL:
                    old = (s.wt[1] << 5) | (s.wt[0] << 4) | (s.en[1] << 1) | s.en[0] | (c << 7)
                    en_new = [((old & ~wm) | (data & wm)) >> i & 1 for i in (0, 1)]
                elif addr == A_WL:
                    new_mask[c] = (s.mask[c] & 0xFF00) | (((s.mask[c] & 0xFF) & ~wm | (data & wm)) & 0xFF); go[c] = 1
                elif addr == A_WH:
                    new_mask[c] = (s.mask[c] & 0xFF) | ((((s.mask[c] >> 8) & ~wm) | (data & wm)) & 0xFF) << 8
                elif addr == A_ARB:
                    if unl:
                        s.arb = (((s.arb & ~wm) | (data & wm)) & 3); cv['arb_write_unlocked'] += 1
                    else: cv['arb_write_locked_ignored'] += 1
                elif addr == A_LOCK:
                    for n in range(4):
                        if (wm >> n) & 1:
                            if (data >> n) & 1:
                                if not s.held[n]:
                                    s.held[n] = 1; s.owner[n] = c; cv['lock_take_free_core%d_l%d' % (c, n)] += 1
                                else: cv['lock_take_busy_%s_l%d' % ('own' if s.owner[n] == c else 'other', n)] += 1
                            else:
                                if s.held[n] and s.owner[n] == c: s.held[n] = 0; cv['lock_release_owner_l%d' % n] += 1
                                elif s.held[n]: cv['lock_release_foreign_ignored_l%d' % n] += 1
                                else: cv['lock_release_free_l%d' % n] += 1
            if cen[c] and ops[c][0] == READ and g[c]:
                cv['read_%03x_core%d' % (ops[c][1], c)] += 1
            if cen[c] and ops[c][0] == SLEEP: go[c] = 1; cv['sleep_core%d' % c] += 1
        # wait logic (H4, H6): a selected flag already set when the mask is written: no wait
        for c in (0, 1):
            if wake[c]:
                s.wt[c] = 0; cv['wake_core%d_%s' % (c, 'flag' if s.mask[c] & ev[c] else 'irq')] += 1
            if go[c]:
                m = new_mask[c]
                hit = bool(m & ev[c]) or bool(s.ie[c] and irq[c])
                if not hit: s.wt[c] = 1; cv['wait_entered_core%d' % c] += 1
                else: cv['wait_not_entered_by_%s_core%d' % ('flag' if m & ev[c] else 'irq_only', c)] += 1
        s.mask = new_mask
        # BREAK and halt
        for c in (0, 1):
            if brk_clr[c]: s.brk[c] = 0; cv['break_cleared'] += 1
            if cen[c] and ops[c][0] == BREAK: s.brk[c] = 1; cv['break_core%d' % c] += 1
            if halt[c]: cv['halt_cycles_core%d' % c] += 1
            if cen[c] and ops[c][0] == SETI: s.ie[c] = 1
            if cen[c] and ops[c][0] == CLRI: s.ie[c] = 0
        # H2: start. H3: stop
        for c in (0, 1):
            if en_new[c] and not s.en[c]:
                if s.wt[c]: cv['start_clears_wait'] += 1
                s.wt[c] = 0; cv['start_core%d' % c] += 1
            if s.en[c] and not en_new[c]: cv['stop_core%d' % c] += 1
        s.en = en_new
        if req[0] and req[1]: s.last = 1 if g[1] else 0
        for c in (0, 1):
            if cen[c]: s.pc[c] += 1
        if cen[0] and cen[1]: cv['both_advance'] += 1
        return out
