#!/usr/bin/env python3
"""Instruction-level reference model of the reduced AVR instruction set as implemented by rcore8.

Written independently of the RTL: flags follow the boolean formulas of the AVR instruction set
manual, the RTL derives them from adder carries. Used for lockstep comparison of state traces.
"""
import sys
from collections import Counter


class Exit(Exception):
    pass


class Model:
    def __init__(self, rom, pc_w=10, ram_aw=7, sp_w=8, nirq=4, has_h=0, sp_reset=0x7F,
                 ram_lo=64, ram_sz=64):
        self.rom = list(rom) + [0] * ((1 << pc_w) - len(rom))
        self.pc_w, self.ram_aw, self.sp_w, self.nirq, self.has_h = pc_w, ram_aw, sp_w, nirq, has_h
        self.pcm = (1 << pc_w) - 1
        self.spm = (1 << sp_w) - 1
        self.tw = pc_w - 8 if pc_w > 8 else 1
        self.R = [0] * 16
        self.pc = 0
        self.sp = sp_reset & self.spm
        self.I = self.T = self.H = self.V = self.N = self.Z = self.C = 0
        self.ram = [0] * (1 << ram_aw)
        self.io = [0] * 64
        self.pending = 0
        self.i_delay = 0
        self.exit = None
        self.noexit = False
        self.ram_lo, self.ram_sz = ram_lo, ram_sz
        self.cov = Counter()

    # ------------------------------------------------------------ state helpers
    def sreg(self):
        h = self.H if self.has_h else 0
        return (self.I << 7) | (self.T << 6) | (h << 5) | ((self.N ^ self.V) << 4) | \
               (self.V << 3) | (self.N << 2) | (self.Z << 1) | self.C

    def set_sreg(self, v):
        self.I, self.T = (v >> 7) & 1, (v >> 6) & 1
        if self.has_h:
            self.H = (v >> 5) & 1
        self.V, self.N, self.Z, self.C = (v >> 3) & 1, (v >> 2) & 1, (v >> 1) & 1, v & 1

    def line(self):
        return "%04x %s %02x %04x %x %s %s" % (
            self.pc, "".join("%02x" % r for r in self.R), self.sreg(), self.sp, self.pending,
            "".join("%02x" % b for b in self.ram[self.ram_lo:self.ram_lo + self.ram_sz]),
            "".join("%02x" % b for b in self.io))

    # ------------------------------------------------------------ buses
    def io_read(self, a):
        return self.pending if a == 0x30 else self.io[a]

    def io_write(self, a, data, mask=0xFF):
        new = (self.io[a] & ~mask & 0xFF) | (data & mask)
        self.io[a] = new
        if a == 0x30:
            self.pending |= new & ((1 << self.nirq) - 1)
        if a == 0x32 and not self.noexit:
            self.exit = new

    def dread(self, adr):
        adr &= 0xFFFF
        if adr & 0x4000:
            w = self.rom[(adr >> 1) & self.pcm]
            return (w >> 8) & 0xFF if adr & 1 else w & 0xFF
        if (adr >> 6) & 0xFF == 0:
            return self.io_read(adr & 63)
        return self.ram[adr & ((1 << self.ram_aw) - 1)]

    def dwrite(self, adr, v):
        adr &= 0xFFFF
        if adr & 0x4000:
            return
        if (adr >> 6) & 0xFF == 0:
            self.io_write(adr & 63, v)
        else:
            self.ram[adr & ((1 << self.ram_aw) - 1)] = v & 0xFF

    def push(self, v):
        self.dwrite(self.sp, v)
        self.sp = (self.sp - 1) & self.spm

    def pop(self):
        self.sp = (self.sp + 1) & self.spm
        return self.dread(self.sp)

    def push_pc(self, ret):
        self.push(ret & 0xFF)
        self.push((ret >> 8) & ((1 << self.tw) - 1))

    # ------------------------------------------------------------ flag formulas (instruction set manual)
    def fl_add(self, d, r, res):
        d3, r3, R3 = (d >> 3) & 1, (r >> 3) & 1, (res >> 3) & 1
        d7, r7, R7 = (d >> 7) & 1, (r >> 7) & 1, (res >> 7) & 1
        self.H = (d3 & r3) | (r3 & (R3 ^ 1)) | ((R3 ^ 1) & d3)
        self.V = (d7 & r7 & (R7 ^ 1)) | ((d7 ^ 1) & (r7 ^ 1) & R7)
        self.N = R7
        self.Z = int(res == 0)
        self.C = (d7 & r7) | (r7 & (R7 ^ 1)) | ((R7 ^ 1) & d7)

    def fl_sub(self, d, r, res, keep_z):
        d3, r3, R3 = (d >> 3) & 1, (r >> 3) & 1, (res >> 3) & 1
        d7, r7, R7 = (d >> 7) & 1, (r >> 7) & 1, (res >> 7) & 1
        self.H = ((d3 ^ 1) & r3) | (r3 & R3) | (R3 & (d3 ^ 1))
        self.V = (d7 & (r7 ^ 1) & (R7 ^ 1)) | ((d7 ^ 1) & r7 & R7)
        self.N = R7
        z = int(res == 0)
        self.Z = (z & self.Z) if keep_z else z
        self.C = ((d7 ^ 1) & r7) | (r7 & R7) | (R7 & (d7 ^ 1))

    def fl_logic(self, res):
        self.V = 0
        self.N = (res >> 7) & 1
        self.Z = int(res == 0)

    # ------------------------------------------------------------ one step
    def step(self):
        """Execute one instruction or take one interrupt."""
        if self.I and not self.i_delay and self.pending:
            n = 1
            while not (self.pending >> (n - 1)) & 1:
                n += 1
            self.pending &= ~(1 << (n - 1))
            self.push_pc(self.pc)
            self.I = 0
            self.pc = n & self.pcm
            self.cov["irq"] += 1
            if self.exit is not None:
                raise Exit()
            return
        ins = self.rom[self.pc]
        self.pc = (self.pc + 1) & self.pcm
        self.i_delay = 0
        self.execute(ins)
        if self.exit is not None:
            raise Exit()

    def skip(self):
        self.pc = (self.pc + 1) & self.pcm

    def ptr_get(self, which):
        lo = 10 + 2 * which
        return self.R[lo] | (self.R[lo + 1] << 8)

    def ptr_set(self, which, v):
        lo = 10 + 2 * which
        self.R[lo], self.R[lo + 1] = v & 0xFF, (v >> 8) & 0xFF

    def execute(self, ins):
        R, cov = self.R, self.cov
        d, r = (ins >> 4) & 15, ins & 15
        K = ((ins >> 4) & 0xF0) | (ins & 0x0F)
        b = ins & 7
        top6 = ins & 0xFC00
        top4 = ins & 0xF000

        if top6 == 0x0400:                       # CPC
            res = (R[d] - R[r] - self.C) & 0xFF
            self.fl_sub(R[d], R[r], res, True); cov["cpc"] += 1
        elif top6 == 0x0800:                     # SBC
            res = (R[d] - R[r] - self.C) & 0xFF
            self.fl_sub(R[d], R[r], res, True); R[d] = res; cov["sbc"] += 1
        elif top6 == 0x0C00:                     # ADD
            res = (R[d] + R[r]) & 0xFF
            self.fl_add(R[d], R[r], res); R[d] = res; cov["add"] += 1
        elif top6 == 0x1000:                     # CPSE
            cov["cpse"] += 1
            if R[d] == R[r]:
                self.skip(); cov["cpse_skip"] += 1
        elif top6 == 0x1400:                     # CP
            res = (R[d] - R[r]) & 0xFF
            self.fl_sub(R[d], R[r], res, False); cov["cp"] += 1
        elif top6 == 0x1800:                     # SUB
            res = (R[d] - R[r]) & 0xFF
            self.fl_sub(R[d], R[r], res, False); R[d] = res; cov["sub"] += 1
        elif top6 == 0x1C00:                     # ADC
            res = (R[d] + R[r] + self.C) & 0xFF
            self.fl_add(R[d], R[r], res); R[d] = res; cov["adc"] += 1
        elif top6 == 0x2000:                     # AND
            R[d] &= R[r]; self.fl_logic(R[d]); cov["and"] += 1
        elif top6 == 0x2400:                     # EOR
            R[d] ^= R[r]; self.fl_logic(R[d]); cov["eor"] += 1
        elif top6 == 0x2800:                     # OR
            R[d] |= R[r]; self.fl_logic(R[d]); cov["or"] += 1
        elif top6 == 0x2C00:                     # MOV
            R[d] = R[r]; cov["mov"] += 1
        elif top4 == 0x3000:                     # CPI
            res = (R[d] - K) & 0xFF
            self.fl_sub(R[d], K, res, False); cov["cpi"] += 1
        elif top4 == 0x4000:                     # SBCI
            res = (R[d] - K - self.C) & 0xFF
            self.fl_sub(R[d], K, res, True); R[d] = res; cov["sbci"] += 1
        elif top4 == 0x5000:                     # SUBI
            res = (R[d] - K) & 0xFF
            self.fl_sub(R[d], K, res, False); R[d] = res; cov["subi"] += 1
        elif top4 == 0x6000:                     # ORI
            R[d] |= K; self.fl_logic(R[d]); cov["ori"] += 1
        elif top4 == 0x7000:                     # ANDI
            R[d] &= K; self.fl_logic(R[d]); cov["andi"] += 1
        elif top4 == 0xE000:                     # LDI
            R[d] = K; cov["ldi"] += 1
        elif top4 == 0xC000 or top4 == 0xD000:   # RJMP, RCALL
            k = ins & 0x0FFF
            if k & 0x800:
                k -= 0x1000
            if top4 == 0xD000:
                self.push_pc(self.pc); cov["rcall"] += 1
            else:
                cov["rjmp"] += 1
            self.pc = (self.pc + k) & self.pcm
        elif top4 == 0xA000:                     # LDS, STS (one-word form)
            adr = (((ins >> 8) & 1) ^ 1) << 7 | ((ins >> 8) & 1) << 6 | ((ins >> 10) & 1) << 5 | \
                  ((ins >> 9) & 1) << 4 | (ins & 15)
            if ins & 0x0800:
                self.dwrite(adr, R[d]); cov["sts"] += 1
            else:
                R[d] = self.dread(adr); cov["lds"] += 1
        elif top4 == 0xB000:                     # IN, OUT
            a = ((ins >> 5) & 0x30) | (ins & 15)
            if ins & 0x0800:
                cov["out"] += 1
                if a == 0x3F:
                    self.set_sreg(R[d])
                    if R[d] & 0x80:
                        self.i_delay = 1
                elif a == 0x3D:
                    self.sp = ((self.sp & ~0xFF) | R[d]) & self.spm
                elif a == 0x3E:
                    if self.sp_w > 8:
                        self.sp = ((R[d] << 8) | (self.sp & 0xFF)) & self.spm
                else:
                    self.io_write(a, R[d])
            else:
                cov["in"] += 1
                if a == 0x3F:
                    R[d] = self.sreg()
                elif a == 0x3D:
                    R[d] = self.sp & 0xFF
                elif a == 0x3E:
                    R[d] = (self.sp >> 8) & 0xFF
                else:
                    R[d] = self.io_read(a)
        elif top4 == 0xF000:
            sub = (ins >> 10) & 3
            if sub < 2:                          # BRBS, BRBC
                k = (ins >> 3) & 0x7F
                if k & 0x40:
                    k -= 0x80
                bit = (self.sreg() >> b) & 1
                cov["brbs" if sub == 0 else "brbc"] += 1
                if bit == (1 if sub == 0 else 0):
                    self.pc = (self.pc + k) & self.pcm; cov["br_taken"] += 1
            elif ins & 8:
                cov["undef"] += 1
            elif (ins & 0xFE00) == 0xF800:       # BLD
                R[d] = (R[d] & ~(1 << b) & 0xFF) | (self.T << b); cov["bld"] += 1
            elif (ins & 0xFE00) == 0xFA00:       # BST
                self.T = (R[d] >> b) & 1; cov["bst"] += 1
            elif (ins & 0xFE00) == 0xFC00:       # SBRC
                cov["sbrc"] += 1
                if not (R[d] >> b) & 1:
                    self.skip()
            else:                                # SBRS
                cov["sbrs"] += 1
                if (R[d] >> b) & 1:
                    self.skip()
        elif top4 == 0x8000:                     # LD/ST through Y or Z, no displacement
            if (ins & 0x0C07) != 0:
                cov["undef"] += 1
            else:
                which = 1 if ins & 8 else 2
                adr = self.ptr_get(which)
                if ins & 0x0200:
                    self.dwrite(adr, R[d]); cov["st"] += 1
                else:
                    R[d] = self.dread(adr); cov["ld"] += 1
                    if adr & 0x4000:
                        cov["ld_flash"] += 1
        elif top4 == 0x9000:
            self.exec9(ins, d, b)
        else:
            cov["nop"] += 1                      # 0x0000 and the undefined 0x00xx..0x03xx range

    def exec9(self, ins, d, b):
        R, cov = self.R, self.cov
        grp = (ins >> 9) & 7
        nib = ins & 15
        if grp in (0, 1):                        # 1001 000x / 1001 001x
            store = grp == 1
            if nib == 15:
                if store:
                    self.push(R[d]); cov["push"] += 1
                else:
                    R[d] = self.pop(); cov["pop"] += 1
                return
            if nib not in (1, 2, 9, 10, 12, 13, 14):
                cov["undef"] += 1
                return
            which = 0 if nib >= 12 else (1 if nib >= 8 else 2)
            mode = nib & 3                       # 0 plain, 1 post-increment, 2 pre-decrement
            p = self.ptr_get(which)
            adr = (p - 1) & 0xFFFF if mode == 2 else p
            newp = (p + 1) & 0xFFFF if mode == 1 else adr
            if store:
                val = R[d]
                self.dwrite(adr, val)
                if mode:
                    self.ptr_set(which, newp)
                cov["st_%d" % mode] += 1
            else:
                val = self.dread(adr)
                if mode:
                    self.ptr_set(which, newp)
                R[d] = val                       # destination wins over the pointer update
                cov["ld_%d" % mode] += 1
                if adr & 0x4000:
                    cov["ld_flash"] += 1
        elif grp == 2:                           # 1001 010x
            v = R[d]
            if nib == 0:                         # COM
                res = (~v) & 0xFF
                R[d] = res; self.fl_logic(res); self.C = 1; cov["com"] += 1
            elif nib == 1:                       # NEG
                res = (-v) & 0xFF
                R[d] = res
                self.H = ((res >> 3) & 1) | ((v >> 3) & 1)
                self.V = int(res == 0x80); self.N = res >> 7; self.Z = int(res == 0); self.C = int(res != 0)
                cov["neg"] += 1
            elif nib == 2:                       # SWAP
                R[d] = ((v << 4) | (v >> 4)) & 0xFF; cov["swap"] += 1
            elif nib == 3:                       # INC
                res = (v + 1) & 0xFF
                R[d] = res; self.V = int(res == 0x80); self.N = res >> 7; self.Z = int(res == 0); cov["inc"] += 1
            elif nib == 10:                      # DEC
                res = (v - 1) & 0xFF
                R[d] = res; self.V = int(res == 0x7F); self.N = res >> 7; self.Z = int(res == 0); cov["dec"] += 1
            elif nib in (5, 6, 7):               # ASR, LSR, ROR
                top = (v >> 7) if nib == 5 else (0 if nib == 6 else self.C)
                res = (top << 7) | (v >> 1)
                R[d] = res
                self.C = v & 1; self.N = res >> 7; self.V = self.N ^ self.C; self.Z = int(res == 0)
                cov[("asr", "lsr", "ror")[nib - 5]] += 1
            elif nib == 8:
                if not ins & 0x0100:             # BSET, BCLR
                    s, val = (ins >> 4) & 7, 0 if ins & 0x80 else 1
                    cov["bset" if val else "bclr"] += 1
                    if s == 0: self.C = val
                    elif s == 1: self.Z = val
                    elif s == 2: self.N = val
                    elif s == 3: self.V = val
                    elif s == 5:
                        if self.has_h: self.H = val
                    elif s == 6: self.T = val
                    elif s == 7:
                        self.I = val
                        if val:
                            self.i_delay = 1
                else:
                    m = (ins >> 4) & 15
                    if m in (0, 1):              # RET, RETI
                        hi = self.pop() & ((1 << self.tw) - 1)
                        lo = self.pop()
                        self.pc = ((hi << 8) | lo) & self.pcm
                        if m == 1:
                            self.I = 1; self.i_delay = 1; cov["reti"] += 1
                        else:
                            cov["ret"] += 1
                    elif m == 8:
                        raise RuntimeError("SLEEP is not modelled")
                    elif m in (9, 10):
                        cov["break_wdr"] += 1
                    else:
                        cov["undef"] += 1
            elif nib == 9 and (ins & 0x00F0) == 0:   # IJMP, ICALL
                z = self.ptr_get(2)
                if ins & 0x0100:
                    self.push_pc(self.pc); cov["icall"] += 1
                else:
                    cov["ijmp"] += 1
                self.pc = z & self.pcm
            else:
                cov["undef"] += 1
        elif grp in (4, 5):                      # 1001 10xx: CBI, SBIC, SBI, SBIS
            a, kind = (ins >> 3) & 31, (ins >> 8) & 3
            if kind == 0:
                self.io_write(a, 0x00, 1 << b); cov["cbi"] += 1
            elif kind == 2:
                self.io_write(a, 0xFF, 1 << b); cov["sbi"] += 1
            else:
                bit = (self.io_read(a) >> b) & 1
                cov["sbic" if kind == 1 else "sbis"] += 1
                if bit == (0 if kind == 1 else 1):
                    self.skip()
        else:
            cov["undef"] += 1                    # ADIW/SBIW and MUL space


def load_hex(path):
    return [int(x, 16) for x in open(path).read().split()]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("hex"); ap.add_argument("trace")
    ap.add_argument("-n", type=int, default=1000)
    for p, dflt in (("pc_w", 10), ("ram_aw", 7), ("sp_w", 8), ("nirq", 4), ("has_h", 0),
                    ("sp_reset", 0x7F), ("ram_lo", 64), ("ram_sz", 64)):
        ap.add_argument("--" + p, type=int, default=dflt)
    ap.add_argument("--cov", default=None)
    ap.add_argument("--noexit", action="store_true")
    a = ap.parse_args()
    m = Model(load_hex(a.hex), a.pc_w, a.ram_aw, a.sp_w, a.nirq, a.has_h, a.sp_reset, a.ram_lo, a.ram_sz)
    m.noexit = a.noexit
    with open(a.trace, "w") as f:
        try:
            for _ in range(a.n):
                f.write(m.line() + "\n")
                m.step()
        except Exit:
            pass
    if a.cov:
        with open(a.cov, "a") as f:
            f.write(" ".join("%s=%d" % kv for kv in sorted(m.cov.items())) + "\n")


if __name__ == "__main__":
    main()
