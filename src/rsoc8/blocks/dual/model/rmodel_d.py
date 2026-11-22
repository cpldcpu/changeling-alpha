#!/usr/bin/env python3
"""Reference model of rdual: two rcore8 cores, private code memories, shared bus.

Instruction semantics come from rmodel.Model (one instance per core). This file adds the cycle
behaviour of the specification: pipeline (P1-P7), shared bus (U1-U8), memory map (M1-M5), core
control (H1-H10), interrupts and unlock window (Q1-Q5), locks (C5-C10).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rmodel import Model, load_hex

A_LOCK, A_CTL, A_WAITL, A_WAITH, A_ARB = 0x005, 0x00E, 0x020, 0x021, 0x150
NOPM = (False, False, 0, False, 0, 0)        # re, we, address (11 bits), data access, byte, data


class Core(Model):
    def __init__(self, sysm, cid, has_h):
        Model.__init__(self, [], pc_w=11 if cid == 0 else 10, ram_aw=11, sp_w=12, nirq=sysm.nirq,
                       has_h=has_h, sp_reset=0x83F if cid == 0 else 0x43F)
        self.s, self.cid = sysm, cid
        self.ram = sysm.ram
        self.st = "FLUSH"
        self.fp = 0                  # address fetched in this cycle
        self.ccp = 0
        self.mask = 0
        self.noexit = True
        self.info = None

    def fpx(self, a=None):
        a = self.fp if a is None else a
        return a & 0x7FF if self.cid == 0 else 0x400 | (a & 0x3FF)

    # ---- memory map
    def bus_read(self, a):
        s = self.s
        if a == A_CTL:   return (self.cid << 7) | (s.wt[1] << 5) | (s.wt[0] << 4) | s.en
        if a == A_LOCK:
            mine = sum(1 << n for n in range(4) if s.lk[n] == self.cid)
            oth = sum(1 << n for n in range(4) if s.lk[n] == 1 - self.cid)
            return (oth << 4) | mine
        if a == A_WAITL: return self.mask & 0xFF
        if a == A_WAITH: return self.mask >> 8
        if a == A_ARB:   return s.arb
        if a == 0x030:   return s.pend[0]
        if a == 0x034:   return s.pend[1]
        return s.io[a]

    def bus_write(self, a, data, mask=0xFF):
        s = self.s
        old = {A_CTL: self.bus_read(A_CTL), A_WAITL: self.mask & 0xFF, A_WAITH: self.mask >> 8,
               A_ARB: s.arb}.get(a, s.io[a])
        new = (old & ~mask & 0xFF) | (data & mask)
        s.io[a] = (s.io[a] & ~mask & 0xFF) | (data & mask)
        if a == 0x030:   s.pend_set[0] |= s.io[a] & ((1 << s.nirq) - 1)
        elif a == 0x034: s.pend_set[1] |= s.io[a] & ((1 << s.nirq) - 1)
        elif a == A_CTL: s.en_new = new & 3
        elif a == A_WAITH: self.mask = (self.mask & 0xFF) | (new << 8)
        elif a == A_WAITL:
            self.mask = (self.mask & 0xFF00) | new
            self.go_wait = True
        elif a == A_ARB:
            self.prot_used = True
            if self.ccp: s.arb = new & 3
        elif a == A_LOCK:
            for n in range(4):
                if (mask >> n) & 1:
                    if (data >> n) & 1:
                        if s.lk[n] is None: s.lk[n] = self.cid
                    elif s.lk[n] == self.cid:
                        s.lk[n] = None

    def io_read(self, a):  return self.bus_read(a)
    def io_write(self, a, data, mask=0xFF): self.bus_write(a, data, mask)

    def dread(self, adr):
        adr &= 0xFFFF
        assert not adr & 0x4000
        if (adr >> 8) & 0x3F == 0x3F: return self.bus_read(0x100 | (adr & 0xFF))
        if (adr >> 6) & 0xFF == 0:    return self.bus_read(adr & 63)
        return self.ram[adr & 0x7FF]

    def dwrite(self, adr, v):
        adr &= 0xFFFF
        assert not adr & 0x4000
        if (adr >> 8) & 0x3F == 0x3F: self.bus_write(0x100 | (adr & 0xFF), v)
        elif (adr >> 6) & 0xFF == 0:  self.bus_write(adr & 63, v)
        else: self.ram[adr & 0x7FF] = v

    def push(self, v):
        self.ram[self.sp & 0x7FF] = v
        self.sp = (self.sp - 1) & self.spm

    def pop(self):
        self.sp = (self.sp + 1) & self.spm
        return self.ram[self.sp & 0x7FF]

    def push_pc(self, ret):                      # low byte in this cycle, high byte in the next
        self.push(ret & 0xFF)
        self.call_hi = (ret >> 8) & ((1 << self.tw) - 1)

    # ---- instruction classes
    @staticmethod
    def ptr_access(ins):
        if ins & 0xF000 == 0x8000 and ins & 0x0C07 == 0:
            return (bool(ins & 0x0200), 1 if ins & 8 else 2, 0)
        if ins & 0xFC00 == 0x9000 and (ins & 15) in (1, 2, 9, 10, 12, 13, 14):
            nib = ins & 15
            return (bool(ins & 0x0200), 0 if nib >= 12 else (1 if nib >= 8 else 2), nib & 3)
        return None

    @staticmethod
    def io_a(ins): return ((ins >> 5) & 0x30) | (ins & 15)

    def needs_bus(self, ins):
        if self.ptr_access(ins) or ins & 0xF000 == 0xA000: return True          # LD, ST, LDS, STS
        if ins & 0xFC0F == 0x900F: return True                                   # PUSH, POP
        if ins & 0xF000 == 0xD000 or ins in (0x9509, 0x9508, 0x9518): return True  # calls and returns
        if ins & 0xF000 == 0xB000: return self.io_a(ins) < 0x3C                  # IN, OUT
        return ins & 0xFC00 == 0x9800                                            # SBI, CBI, SBIC, SBIS

    # ---- what the core wants in this cycle: (bus request, code port use)
    def peek(self):
        s, st = self.s, self.st
        self.irq_take = False
        if st == "EXEC":
            self.ins = s.prd(self.cid)
            self.irq_take = bool(self.I and not self.i_delay and s.pend[self.cid])
            return (self.irq_take or self.needs_bus(self.ins), (True, False, self.fpx(), False, 0, 0))
        if st == "FLUSH": return (False, (True, False, self.fpx(), False, 0, 0))
        if st == "CALL2": return (True, (True, False, self.fpx(), False, 0, 0))
        if st == "RET2":  return (True, NOPM)
        if st == "RET3":  return (False, (True, False, self.fpx((self.ret_hi << 8) | self.ret_lo), False, 0, 0))
        if st == "LD2":   return (False, NOPM)
        if st == "LDF1":  return (False, (True, False, (self.info[0] >> 1) & 0x7FF, True, 0, 0))
        if st == "LDF2":  return (False, (True, False, self.fpx(), False, 0, 0))
        if st == "STF1":  return (False, (False, True, (self.info[0] >> 1) & 0x7FF, True, self.info[0] & 1, self.R[self.info[1]]))
        raise RuntimeError(st)

    # ---- one enabled cycle
    def step(self, ev, i_before, pend_before):
        s, st = self.s, self.st
        self.go_wait = False
        self.prot_used = False
        m = self.pcm
        if st == "EXEC":
            if self.irq_take:
                n = 1
                while not (s.pend[self.cid] >> (n - 1)) & 1: n += 1
                s.pend_clr[self.cid] |= 1 << (n - 1)
                ret = (self.fp - 1) & m
                self.push(ret & 0xFF)
                self.call_hi = (ret >> 8) & ((1 << self.tw) - 1)
                self.I = 0
                self.fp = n
                s.cov["irq"] += 1
                self.st = "CALL2"
                return
            ins = self.ins
            d = (ins >> 4) & 15
            self.i_delay = 0
            ccp_set = False
            self.call_hi = None
            nxt = (self.fp + 1) & m
            if ins in (0x9508, 0x9518):                              # RET, RETI
                self.ret_hi = self.pop() & ((1 << self.tw) - 1)
                self.is_reti = ins == 0x9518
                self.st = "RET2"
            elif ins == 0x9588:                                      # SLEEP
                self.fp = nxt; self.go_wait = True
            elif ins == 0x9598:                                      # BREAK
                self.fp = nxt; s.brk_set[self.cid] = 1
            elif ins & 0xF800 == 0xB800 and self.io_a(ins) == 0x3C:  # OUT CCP
                self.fp = nxt; ccp_set = self.R[d] == 0xD8
            elif ins & 0xF800 == 0xB000 and self.io_a(ins) == 0x3C:  # IN CCP
                self.fp = nxt; self.R[d] = 0
            else:
                pa = self.ptr_access(ins)
                kind = None
                if pa:
                    store, which, mode = pa
                    p = self.ptr_get(which)
                    adr = (p - 1) & 0xFFFF if mode == 2 else p
                    if adr & 0x4000: kind = "flash"
                    elif (adr >> 8) & 0x3F == 0x3F or (adr >> 6) & 0xFF == 0: kind = "bus"
                    else: kind = "ram"
                if kind == "flash":
                    s.cov[("st" if store else "ld") + ("_code_own" if bool(adr & 0x800) == bool(self.cid) else "_code_other")] += 1
                    self.info = (adr, d, which, mode, p)
                    self.st = "STF1" if store else "LDF1"
                else:
                    ld2 = (pa and not store and kind == "ram") or ins & 0xF800 == 0xA000 or ins & 0xFE0F == 0x900F
                    taken = ins & 0xF000 == 0xC000 or ins == 0x9409
                    if ins & 0xF800 == 0xF000:
                        bit = (self.sreg() >> (ins & 7)) & 1
                        taken = bit == (0 if ins & 0x400 else 1)
                    self.pc = self.fp
                    self.execute(ins)
                    if self.call_hi is not None:
                        self.fp = self.pc; self.st = "CALL2"
                    elif ld2:
                        self.st = "LD2"
                    elif taken or self.pc != self.fp:
                        self.fp = self.pc; self.st = "FLUSH"
                    else:
                        self.fp = nxt
            if ccp_set:                         self.ccp = 4
            elif self.prot_used and self.ccp:   self.ccp = 0
            elif self.ccp:                      self.ccp -= 1
            if self.go_wait:
                if not (self.mask & ev or (i_before and pend_before)):
                    s.wt_set[self.cid] = 1
        elif st in ("FLUSH", "LD2"):
            self.fp = (self.fp + 1) & m; self.st = "EXEC"
        elif st == "CALL2":
            self.push(self.call_hi)
            self.fp = (self.fp + 1) & m; self.st = "EXEC"
        elif st == "RET2":
            self.ret_lo = self.pop()
            self.st = "RET3"
        elif st == "RET3":
            self.fp = (((self.ret_hi << 8) | self.ret_lo) + 1) & m
            if self.is_reti: self.I = 1; self.i_delay = 1
            self.st = "EXEC"
        elif st == "LDF1":
            self.st = "LDF2"
        elif st == "LDF2":
            adr, d, which, mode, p = self.info
            w = s.prd(self.cid)
            if mode: self.ptr_set(which, (p + 1) & 0xFFFF if mode == 1 else adr)
            self.R[d] = (w >> 8) & 0xFF if adr & 1 else w & 0xFF
            self.fp = (self.fp + 1) & m; self.st = "EXEC"
        elif st == "STF1":
            adr, d, which, mode, p = self.info
            if mode: self.ptr_set(which, (p + 1) & 0xFFFF if mode == 1 else adr)
            self.st = "FLUSH"

    def restart(self):
        self.st = "FLUSH"; self.fp = 0; self.i_delay = 0; self.ccp = 0

    def line(self):
        s = self.s
        held = sum(1 << n for n in range(4) if s.lk[n] is not None)
        own = sum(1 << n for n in range(4) if s.lk[n] == 1)
        return "%04x %s %02x %04x %x%x %x %x %x %x%x" % (
            (self.fp - 1) & self.pcm, "".join("%02x" % r for r in self.R), self.sreg(), self.sp,
            s.pend[0], s.pend[1], s.en, s.wt[0] | (s.wt[1] << 1), s.arb, held, own)


class System:
    def __init__(self, rom0, rom1, has_h=0, nirq=4, pmw=False):
        self.nirq, self.pmw = nirq, pmw
        self.rom = [list(rom0) + [0] * (1024 - len(rom0)), list(rom1) + [0] * (1024 - len(rom1))]
        self.ram = [0] * 2048
        self.io = [0] * 512
        self.pend = [0, 0]
        self.en, self.wt, self.brk = 1, [0, 0], [0, 0]
        self.arb, self.last = 0, 1
        self.lk = [None] * 4
        self.q = [0, 0]              # code memory outputs
        self.valid, self.src, self.lastrd = [1, 1], [0, 0], [0, 0]
        self.c = [Core(self, 0, has_h), Core(self, 1, has_h)]
        self.cyc = 0
        self.out = []
        self.cov = {"hold": 0, "steal": 0, "refetch": 0, "wake": 0, "wait": 0, "collision": 0, "both": 0, "x_fetch": 0, "irq": 0,
                    "ld_code_own": 0, "ld_code_other": 0, "st_code_own": 0, "st_code_other": 0}

    def prd(self, i):
        return self.q[1 - i] if self.src[i] else self.q[i]

    def cycle(self):
        c, en = self.c, self.en
        ev = self.io[6] | (self.io[7] << 8)
        pk = [c[0].peek(), c[1].peek()]
        (rq0, (re0, we0, a0, d0, ws0, wd0)), (rq1, (re1, we1, a1, d1, ws1, wd1)) = pk
        base = [bool((en >> i) & 1 and not self.wt[i] and not self.brk[i]) for i in (0, 1)]
        refetch = [base[i] and not self.valid[i] for i in (0, 1)]
        pre = [base[i] and not refetch[i] for i in (0, 1)]
        use0, use1 = re0 or we0, re1 or we1
        fd0 = use0 and d0 and bool(a0 & 0x400)
        fd1 = use1 and d1 and not a1 & 0x400
        ff0 = re0 and not d0 and bool(a0 & 0x400)
        prio0, prio1 = self.arb == 1, self.arb == 2
        st0 = pre[0] and fd0 and not refetch[1] and (not base[1] or not prio1)
        stolen1 = st0 and base[1]
        st1 = pre[1] and fd1 and not refetch[0] and (not base[0] or not prio0) and not stolen1
        stolen0 = st1 and base[0]
        ok0 = st0 if fd0 else (not (en >> 1) & 1 if ff0 else True)
        ok1 = st1 if fd1 else True
        run0, run1 = pre[0] and not stolen0 and ok0, pre[1] and not stolen1 and ok1
        req0, req1 = run0 and rq0, run1 and rq1
        g0 = req0 and (not req1 or prio0 or (not prio1 and self.last == 1))
        g1 = req1 and not g0
        cen = [run0 and (not rq0 or g0), run1 and (not rq1 or g1)]
        if req0 and req1: self.cov["collision"] += 1
        if (req0 and not g0) or (req1 and not g1): self.cov["hold"] += 1
        if stolen0 or stolen1: self.cov["steal"] += 1
        if refetch[0] or refetch[1]: self.cov["refetch"] += 1
        if cen[0] and cen[1]: self.cov["both"] += 1
        if cen[0] and ff0: self.cov["x_fetch"] += 1

        for i in (0, 1):
            if cen[i] and c[i].st == "EXEC":
                self.out.append("%d %d %s" % (self.cyc, i, c[i].line()))

        # values at the start of the cycle that registered logic uses
        wake = [self.wt[i] and bool(c[i].mask & ev or (c[i].I and self.pend[i])) for i in (0, 1)]
        ib = [c[0].I, c[1].I]; pb = list(self.pend)
        self.pend_set, self.pend_clr = [0, 0], [0, 0]
        self.wt_set, self.brk_set = [0, 0], [0, 0]
        self.en_new = en

        # code memories: new outputs from the content before this cycle's write
        q = list(self.q); valid = list(self.valid); src = list(self.src)
        c1_in0 = cen[1] and fd1
        c0_in1 = cen[0] and use0 and bool(a0 & 0x400)
        wr = []
        if refetch[0]: q[0] = self.rom[0][self.lastrd[0]]; valid[0] = 1
        elif c1_in0:
            valid[0] = 0
            if re1: q[0] = self.rom[0][a1 & 0x3FF]
            if we1: wr.append((0, a1 & 0x3FF, ws1, wd1))
        elif cen[0] and not a0 & 0x400:
            if re0: q[0] = self.rom[0][a0 & 0x3FF]; self.lastrd[0] = a0 & 0x3FF
            if we0: wr.append((0, a0 & 0x3FF, ws0, wd0))
        if refetch[1]: q[1] = self.rom[1][self.lastrd[1]]; valid[1] = 1
        elif c0_in1:
            valid[1] = 0
            if re0: q[1] = self.rom[1][a0 & 0x3FF]
            if we0: wr.append((1, a0 & 0x3FF, ws0, wd0))
        elif cen[1] and not fd1:
            if re1: q[1] = self.rom[1][a1 & 0x3FF]; self.lastrd[1] = a1 & 0x3FF
            if we1: wr.append((1, a1 & 0x3FF, ws1, wd1))
        if cen[0] and re0: src[0] = 1 if a0 & 0x400 else 0
        if cen[1] and re1: src[1] = 0 if a1 & 0x400 else 1

        # the cores (at most one of them uses the shared bus)
        for i in (0, 1):
            if cen[i]:
                c[i].step(ev, ib[i], pb[i])
        if self.pmw:
            for m, a, hi, v in wr:
                self.rom[m][a] = (self.rom[m][a] & 0x00FF) | (v << 8) if hi else (self.rom[m][a] & 0xFF00) | v
        self.q, self.valid, self.src = q, valid, src
        if req0 and req1: self.last = 1 if g1 else 0

        # registered updates
        for i in (0, 1):
            self.pend[i] = (self.pend[i] & ~self.pend_clr[i]) | self.pend_set[i]
            if wake[i]: self.wt[i] = 0; self.cov["wake"] += 1
            if self.wt_set[i]: self.wt[i] = 1; self.cov["wait"] += 1
            if self.brk_set[i]: self.brk[i] = 1
            if (self.en_new >> i) & 1 and not (en >> i) & 1:
                c[i].restart(); self.wt[i] = 0; self.valid[i] = 1; self.src[i] = 0
        self.en = self.en_new
        self.cyc += 1

    def dump(self):
        return ["ram " + "".join("%02x" % b for b in self.ram), "io " + "".join("%02x" % b for b in self.io),
                "rom0 " + "".join("%04x" % w for w in self.rom[0]), "rom1 " + "".join("%04x" % w for w in self.rom[1])]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("hex0"); ap.add_argument("hex1"); ap.add_argument("trace")
    ap.add_argument("--cycles", type=int, default=4000)
    ap.add_argument("--has_h", type=int, default=0)
    ap.add_argument("--pmw", action="store_true")
    ap.add_argument("--cov", default=None)
    a = ap.parse_args()
    s = System(load_hex(a.hex0), load_hex(a.hex1), a.has_h, pmw=a.pmw)
    for _ in range(a.cycles):
        s.cycle()
    with open(a.trace, "w") as f:
        f.write("\n".join(s.out + s.dump()) + "\n")
    if a.cov:
        cov = dict(s.cov)
        for k in ("rcall", "icall", "push", "pop"):
            cov[k] = s.c[0].cov[k] + s.c[1].cov[k]
        with open(a.cov, "a") as f:
            f.write(" ".join("%s=%d" % kv for kv in sorted(cov.items())) + "\n")


if __name__ == "__main__":
    main()
