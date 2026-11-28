# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Behavioural model of the host link (rhost) at the level of SPI bytes in and bus/control actions out.
Written from the specification: section Host link and debug, rules L1-L14, command table, status table, mailbox
registers MBSTAT and MBDATA. No timing inside a transaction is modelled; the host clock is slow enough that every
action of a byte is finished before the next one, and the environment inputs are constant during a transaction.

xact(nbits, data) returns the bytes that the chip sends back (one per completed byte) and the list of actions:
   ('W', addr, data)   write access through the host port
   ('R', addr)         read access through the host port
   ('I', cmd, core, word)   inject (cmd 1), execute (2), step (3: word is None)
   ('B', mask)         clear break flags
"""
from collections import Counter


def is_reg(a):            # the two register windows of the data address space: 0x0000-0x003F and 0x3F00-0x3FFF
    return (a < 0x4000) and ((a >> 8) == 0x3F or (a >> 6) == 0)


def memval(mem, a):
    return mem.get(a, (a * 13 + 7) & 0xFF)


class Host:
    def __init__(s):
        s.c_rst = 1; s.c_core = 0; s.c_halt = 0; s.err = 0
        s.mb_rxf = 0; s.mb_txe = 1; s.mb_rx = 0; s.mb_tx = 0
        s.mem = {}; s.hold = 0
        s.env = dict(quiet=0, busy=0, brk=0, en=0, wait=0, pc0=0, pc1=0)
        s.cov = Counter()

    # ---- environment
    def set_env(s, quiet, busy, fail, brk, en, wait, pc0, pc1):
        s.env = dict(quiet=quiet, busy=busy, brk=brk, en=en, wait=wait, pc0=pc0, pc1=pc1)
        if fail: s.err = 1; s.cov['inj_fail_pulse'] += 1

    def acc_ok(s): return s.c_rst or s.env['quiet']

    def core_ok(s, honour_rst_busy):
        c = s.c_core; halted = s.c_halt | s.env['brk']
        ok = (halted >> c) & 1 and (s.env['en'] >> c) & 1 and not (s.env['wait'] >> c) & 1
        if honour_rst_busy: ok = ok and not s.c_rst and not s.env['busy']
        return bool(ok)

    # ---- firmware side of the mailbox registers
    def fw(s, addr, we, re, wd, host):
        cv = s.cov; rd = 0
        if addr == 0x0C: rd = (s.mb_rxf << 7) | (s.mb_txe << 6)
        if addr == 0x0D: rd = s.mb_rx
        if re and addr == 0x0D and not host:
            if s.mb_rxf: cv['fw_read_mbdata_clears_rxf'] += 1
            s.mb_rxf = 0
        if we and addr == 0x0D and not host: s.mb_tx = wd; s.mb_txe = 0; cv['fw_write_mbdata'] += 1
        if re and addr == 0x0D and host: cv['host_read_mbdata_no_side_effect'] += 1
        return rd

    STALE_HOLD = False           # False: spec text (a refused read returns zero, also in the repeated bytes). True: the value of the last read of any command is repeated
    GAP_REST_BUSY = False        # GAP-H1: whether c_rst and a running injection refuse inject, execute and step (spec: only halted, enabled, not waiting)

    def xact(s, nbits, data):
        cv = s.cov
        nfull = nbits // 8; extra = nbits % 8
        out = [0] * (nfull + 1); acts = []
        cmd = None; addr = 0; word = 0; txn = 0; take = 0; hold = s.hold
        first_reg = False
        for k in range(nfull):
            b = data[k]; nxt = 0
            if k == 0:
                cmd = b; cv['cmd_%02x' % b] += 1
                if b == 0x0A:
                    if s.core_ok(s.GAP_REST_BUSY): acts.append(('I', 3, s.c_core, None)); cv['step_ok'] += 1
                    else: s.err = 1; cv['step_refused'] += 1
            elif cmd == 0x02:
                if k == 1: addr = b << 8
                elif k == 2: addr |= b
                else:
                    a = (addr + k - 3) & 0xFFFF
                    if s.acc_ok(): acts.append(('W', a, b)); s.mem[a] = b; cv['write_%s' % ('reg' if is_reg(a) else 'mem')] += 1
                    else: s.err = 1; cv['write_refused'] += 1
            elif cmd == 0x03:
                if k == 1: addr = b << 8
                elif k == 2: addr |= b; cur = addr
                else:
                    if k == 3:
                        reg = is_reg(addr)
                        if s.acc_ok(): acts.append(('R', addr)); nxt = memval(s.mem, addr); hold = nxt; cv['read_%s' % ('reg' if reg else 'mem')] += 1
                        else:
                            s.err = 1; cv['read_refused'] += 1
                            if not s.STALE_HOLD: hold = 0
                    elif not is_reg(cur):
                        # GAP-H2: whether an address is a memory or a register is decided where the previous byte was read
                        cur = (cur + 1) & 0xFFFF
                        if s.acc_ok():
                            acts.append(('R', cur)); nxt = memval(s.mem, cur); cv['read_mem_next_byte'] += 1
                            if is_reg(cur): cv['read_crossing_into_register_space'] += 1
                            hold = nxt           # the repeated byte is the last value read in this command
                        else:
                            s.err = 1; cv['read_refused'] += 1
                            if not s.STALE_HOLD: hold = 0
                    else:
                        nxt = hold; cv['read_reg_repeat'] += 1
                        if hold != 0 and not s.acc_ok(): cv['refused_register_read_repeats_nonzero'] += 1
            elif cmd == 0x04:
                if k == 1:
                    newh = b & 3
                    m = s.c_halt & ~newh & 3
                    if m: acts.append(('B', m)); cv['brk_clear'] += 1
                    cv['control_rst%d_core%d_halt%d' % (b >> 7, (b >> 4) & 1, newh)] += 1
                    s.c_rst = (b >> 7) & 1; s.c_core = (b >> 4) & 1; s.c_halt = newh
            elif cmd == 0x05:
                c = s.c_core
                e = s.env
                st0 = ((1 if s.acc_ok() else 0) << 7) | (e['busy'] << 6) | (e['brk'] << 4) | ((s.c_halt | e['brk']) & 3)
                st1 = (s.err << 7) | (s.c_rst << 6) | (e['wait'] << 4) | (c << 2) | e['en']
                pc = e['pc1'] if c else e['pc0']
                if k == 1: nxt = st0
                elif k == 2: nxt = st1; cv['status_err_%d' % s.err] += 1; s.err = 0
                elif k == 3: nxt = (pc >> 8) & 7
                elif k == 4: nxt = pc & 0xFF
            elif cmd in (0x06, 0x09):
                if k == 1: word = b << 8
                elif k == 2:
                    word |= b
                    if s.core_ok(s.GAP_REST_BUSY): acts.append(('I', 1 if cmd == 0x06 else 2, s.c_core, word)); cv['inject_ok' if cmd == 6 else 'execute_ok'] += 1
                    else: s.err = 1; cv['inject_refused'] += 1
            elif cmd == 0x07:
                if k == 1:
                    if not s.mb_rxf: s.mb_rx = b; s.mb_rxf = 1; cv['mbox_write_ok'] += 1
                    else: s.err = 1; cv['mbox_write_refused'] += 1
            elif cmd == 0x08:
                if k == 1: nxt = (s.mb_rxf << 7) | (s.mb_txe << 6)
                elif k == 2: nxt = s.mb_tx; take = int(not s.mb_txe)
            out[k + 1] = nxt
        # a byte after the second byte of a mailbox read, clocked at least in part: TXE is set
        if cmd == 0x08 and take and (nfull >= 4 or (nfull == 3 and extra >= 1)):
            s.mb_txe = 1; cv['mbox_read_takes_byte'] += 1
        s.hold = hold if cmd == 0x03 else s.hold
        return out[:nfull], acts, (1 - s.c_rst, s.c_halt, s.c_core, s.mb_rxf)
