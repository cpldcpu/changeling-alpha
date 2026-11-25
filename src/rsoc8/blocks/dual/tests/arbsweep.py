#!/usr/bin/env python3
"""Arbitration sweep for rdual: both cores run a kernel of one instruction class on private cells with
different pad lengths between the instances, so that the accesses of the two cores meet in every cycle of
every instruction.  For each run:
  1. the RTL trace (every instruction start of both cores, final memories) must equal the cycle model,
  2. the architectural result is checked against values computed here from the instruction semantics only
     (registers, stack pointer, program counter, memory cells, number of accesses to two registers with
     side effects: read counter 0x0F and write counter 0x0C of the testbench, option +side),
  3. exact timing (rule U5): the core named by ARB has the same instruction start cycles whatever the other
     core executes.
usage: arbsweep.py [--classes a,b] [--vs a,b] [--arbs 0,1,2] [--variants n] [--cdiv n] [--n instances]
                   [--list] [--cov file]
"""
import subprocess, sys, os, itertools, argparse, collections, re
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(here, "..")
sys.path.insert(0, os.path.join(root, "model")); sys.path.insert(0, here)
import rmodel_d as M
from rmodel import load_hex

BUILD = os.path.join(root, "build", "arb")
os.makedirs(BUILD, exist_ok=True)
VVP = os.environ.get("ARB_VVP", os.path.join(root, "build", "tbd.vvp"))

# ------------------------------------------------------------------ memory map of the tests
TB = [0x100, 0x200]        # table of 64 bytes, read by loads
SB = [0x180, 0x280]        # store area
LT = [0x40, 0x60]          # table of 32 bytes for LDS
LS = [0x80, 0x90]          # 16 bytes written by STS
DONE = [0xA0, 0xA1]
SP0 = [0x83F, 0x43F]
def T(c, i): return (3 + 50 * c + 7 * i) & 255
def L(c, i): return (11 + c + 5 * i) & 255

def lo(x): return x & 255
def hi(x): return x >> 8

ACC = ["add r20, r19", "adc r21, r17"]

class Cls:
    """name; setup(c,N) -> asm; inst(c,k) -> asm; exp(c,N) -> dict(regs, mem, rd{addr}, wr{addr})"""
    def __init__(s, name, setup, inst, exp, side=False, helpers=None):
        s.name, s.setup, s.inst, s.exp, s.side, s.helpers = name, setup, inst, exp, side, helpers or (lambda c: [])

def accsum(vals):
    a = sum(vals); return {20: a & 255, 21: (a >> 8) & 255}

PREG = {"X": 26, "Y": 28, "Z": 30}
def ldcls(ptr, mode):
    P = PREG[ptr]
    def setup(c, N):
        a = TB[c] + (N if mode == "m" else 0)
        return ["ldi r%d, %d" % (P, lo(a)), "ldi r%d, %d" % (P + 1, hi(a))]
    def inst(c, k):
        op = {"": ptr, "p": ptr + "+", "m": "-" + ptr}[mode]
        return ["ld r19, " + op] + (["inc r%d" % P] if mode == "" else []) + ACC
    def exp(c, N):
        r = accsum([T(c, i) for i in range(N)])
        a = TB[c] + (0 if mode == "m" else N)
        r[P] = lo(a); r[P + 1] = hi(a)
        return dict(regs=r, mem={}, rd={}, wr={})
    return Cls("ld_" + ptr + mode, setup, inst, exp)

def stcls(ptr, mode):
    P = PREG[ptr]
    def setup(c, N):
        a = SB[c] + (N if mode == "m" else 0)
        return ["ldi r%d, %d" % (P, lo(a)), "ldi r%d, %d" % (P + 1, hi(a)), "ldi r19, %d" % (0x30 + c)]
    def inst(c, k):
        op = {"": ptr, "p": ptr + "+", "m": "-" + ptr}[mode]
        return ["st %s, r19" % op] + (["inc r%d" % P] if mode == "" else []) + ["inc r19"]
    def exp(c, N):
        mem = {}
        for k in range(N):
            mem[SB[c] + (N - 1 - k if mode == "m" else k)] = (0x30 + c + k) & 255
        a = SB[c] + (0 if mode == "m" else N)
        return dict(regs={P: lo(a), P + 1: hi(a), 19: (0x30 + c + N) & 255}, mem=mem, rd={}, wr={})
    return Cls("st_" + ptr + mode, setup, inst, exp)

def pushpop():
    def setup(c, N): return ["ldi r19, %d" % (0x40 + c)]
    def inst(c, k): return ["push r19", "inc r19", "nop", "pop r18"] + ["add r20, r18", "adc r21, r17"]
    def exp(c, N):
        r = accsum([0x40 + c + k for k in range(N)])
        return dict(regs=r, mem={SP0[c] & 0x7FF: (0x40 + c + N - 1) & 255}, rd={}, wr={})
    return Cls("pushpop", setup, inst, exp)

def calls(kind):
    def helpers(c):
        if kind == "rcall2": return ["fn2: rcall fn", "inc r22", "ret", "fn: inc r22", "ret"]
        return ["fn: inc r22", "ret"]
    def setup(c, N):
        if kind == "icall": return ["ldi r30, lo8(pm(fn))", "ldi r31, hi8(pm(fn))"]
        return []
    def inst(c, k):
        return {"rcall": ["rcall fn"], "rcall2": ["rcall fn2"], "icall": ["icall"]}[kind]
    def exp(c, N): return dict(regs={22: (2 * N if kind == "rcall2" else N) & 255}, mem={}, rd={}, wr={})
    return Cls(kind, setup, inst, exp, helpers=helpers)

def incls():
    return Cls("in_tick", lambda c, N: [], lambda c, k: ["in r19, 0x0F"] + ACC,
               lambda c, N: dict(regs={}, mem={}, rd={0x0F: N}, wr={}), side=True)
def outcls():
    return Cls("out_wc", lambda c, N: ["ldi r19, 1"], lambda c, k: ["out 0x0C, r19", "inc r19"],
               lambda c, N: dict(regs={19: (1 + N) & 255}, mem={}, rd={}, wr={0x0C: N}), side=True)
def sbiwc():
    return Cls("sbicbi_wc", lambda c, N: [], lambda c, k: [("sbi" if k % 2 == 0 else "cbi") + " 0x0C, %d" % (k % 8)],
               lambda c, N: dict(regs={}, mem={}, rd={}, wr={0x0C: N}), side=True)
def sbibits():
    def ops(c, N):
        o = []
        for k in range(N):
            b = (k % 4) + 4 * c
            o.append(("sbi" if (k < 4 or k % 2 == 1) else "cbi", b))
        return o
    def exp(c, N):
        v = 0
        for op, b in ops(c, N): v = (v | 1 << b) if op == "sbi" else (v & ~(1 << b))
        return dict(regs={}, mem={}, rd={}, wr={}, io={0x0B: v}, iomask={0x0B: 0xF << (4 * c)})
    return Cls("sbicbi_bits", lambda c, N: [], lambda c, k: ["%s 0x0B, %d" % ops(c, 64)[k]], exp)
def sbisc():
    return Cls("sbisc_tick", lambda c, N: [], lambda c, k: [("sbis" if k % 2 == 0 else "sbic") + " 0x0F, 0", "inc r22"],
               lambda c, N: dict(regs={}, mem={}, rd={0x0F: N}, wr={}), side=True)
def ldscls():
    return Cls("lds", lambda c, N: [], lambda c, k: ["lds r19, %d" % (LT[c] + (5 * k) % 32)] + ACC,
               lambda c, N: dict(regs=accsum([L(c, (5 * k) % 32) for k in range(N)]), mem={}, rd={}, wr={}))
def stscls():
    def exp(c, N):
        mem = {}
        for k in range(N): mem[LS[c] + k % 16] = (0x50 + c + k) & 255
        return dict(regs={19: (0x50 + c + N) & 255}, mem=mem, rd={}, wr={})
    return Cls("sts", lambda c, N: ["ldi r19, %d" % (0x50 + c)], lambda c, k: ["sts %d, r19" % (LS[c] + k % 16), "inc r19"], exp)
def ldio():
    return Cls("ld_io", lambda c, N: ["ldi r26, 0x0F", "ldi r27, 0"], lambda c, k: ["ld r19, X"] + ACC,
               lambda c, N: dict(regs={}, mem={}, rd={0x0F: N}, wr={}), side=True)
def stio():
    return Cls("st_io", lambda c, N: ["ldi r26, 0x0C", "ldi r27, 0", "ldi r19, 7"], lambda c, k: ["st X, r19", "inc r19"],
               lambda c, N: dict(regs={19: (7 + N) & 255}, mem={}, rd={}, wr={0x0C: N}), side=True)

CLASSES = collections.OrderedDict()
for p in "XYZ":
    for m in ("", "p", "m"):
        for f in (ldcls, stcls):
            cl = f(p, m); CLASSES[cl.name] = cl
for cl in [pushpop(), calls("rcall"), calls("rcall2"), calls("icall"), incls(), outcls(), sbiwc(), sbibits(), sbisc(),
           ldscls(), stscls(), ldio(), stio()]:
    CLASSES[cl.name] = cl

# ------------------------------------------------------------------ program text
PADS = [(0, 1), (1, 0), (2, 3), (3, 2), (0, 2), (2, 0), (1, 3), (3, 1)]     # constant pad per core and variant: the phase drifts
def pad(core, variant, k):
    return PADS[variant % len(PADS)][core]

def program(core, cl, arb, N, variant):
    c = core
    L_ = ["        .text", "        .org 0", "        ldi r17, 0"]
    if c == 0:
        L_ += ["        ldi r16, 0xD8", "        out 0x3C, r16", "        ldi r16, %d" % arb, "        ldi r30, 0x50",
               "        ldi r31, 0x3F", "        st Z, r16", "        ldi r16, 0x03", "        out 0x0E, r16"]
    # tables
    L_ += ["        ldi r26, %d" % lo(TB[c]), "        ldi r27, %d" % hi(TB[c]), "        ldi r18, %d" % T(c, 0),
           "        ldi r19, 64", "i1:     st X+, r18", "        subi r18, -7", "        dec r19", "        brne i1",
           "        ldi r26, %d" % lo(LT[c]), "        ldi r27, %d" % hi(LT[c]), "        ldi r18, %d" % L(c, 0),
           "        ldi r19, 32", "i2:     st X+, r18", "        subi r18, -5", "        dec r19", "        brne i2",
           "        ldi r20, 0", "        ldi r21, 0", "        ldi r22, 0"]
    L_ += ["        " + x for x in cl.setup(c, N)]
    L_ += ["kern:"]
    for k in range(N):
        L_ += ["        nop"] * pad(c, variant, k)
        L_ += ["        " + x for x in cl.inst(c, k)]
    L_ += ["sync:   ldi r16, 1", "        sts %d, r16" % DONE[c], "w:      lds r16, %d" % DONE[1 - c], "        tst r16",
           "        breq w", "        ldi r18, 30", "d:      dec r18", "        brne d", "        ldi r16, 0x55",
           "        out 0x3F, r16", "e:      rjmp e"]
    L_ += ["        " + x if not re.match(r"\w+:", x) else x for x in cl.helpers(c)]
    return "\n".join(L_) + "\n"

def build(name, text):
    sfile = os.path.join(BUILD, name + ".S"); open(sfile, "w").write(text)
    elf = os.path.join(BUILD, name + ".elf")
    subprocess.run(["avr-gcc", "-mmcu=attiny40", "-nostdlib", "-o", elf, sfile], check=True)
    subprocess.run(["avr-objcopy", "-O", "binary", "-j", ".text", elf, os.path.join(BUILD, name + ".bin")], check=True)
    b = open(os.path.join(BUILD, name + ".bin"), "rb").read(); b += b"\0" * (len(b) % 2)
    words = [b[i] | b[i + 1] << 8 for i in range(0, len(b), 2)]
    assert len(words) < 1024, name
    open(os.path.join(BUILD, name + ".hex"), "w").write("\n".join("%04x" % w for w in words) + "\n")
    nm = subprocess.run(["avr-nm", elf], capture_output=True, text=True, check=True).stdout
    sym = {l.split()[2]: int(l.split()[0], 16) // 2 for l in nm.splitlines() if len(l.split()) == 3}
    return os.path.join(BUILD, name + ".hex"), sym

# ------------------------------------------------------------------ model with the two side-effect registers
_orig_read, _orig_write = M.Core.bus_read, M.Core.bus_write
def _rd(self, a):
    s = self.s
    if getattr(s, "side", False):
        if a == 0x0F: v = s.tk & 255; s.tk += 1; return v
        if a == 0x0C: return s.wc & 255
    return _orig_read(self, a)
def _wr(self, a, d, mask=0xFF):
    s = self.s
    if getattr(s, "side", False) and a == 0x0C: s.wc += 1
    _orig_write(self, a, d, mask)
M.Core.bus_read, M.Core.bus_write = _rd, _wr

def run_model(h0, h1, cycles, side, pmw=False):
    s = M.System(load_hex(h0), load_hex(h1), 0, pmw=pmw)
    s.side, s.tk, s.wc = side, 0, 0
    for _ in range(cycles): s.cycle()
    return s

def model_length(h0, h1, side, limit=30000, pmw=False, margin=120):
    """cycles until both cores have set their done flag and idled for 100 cycles"""
    s = M.System(load_hex(h0), load_hex(h1), 0, pmw=pmw)
    s.side, s.tk, s.wc = side, 0, 0
    fin = None
    for n in range(limit):
        s.cycle()
        if fin is None and s.ram[DONE[0]] == 1 and s.ram[DONE[1]] == 1: fin = n
        if fin is not None and n > fin + margin: return n + 1
    return None

def norm(lines, c0):
    out = []
    for l in lines:
        if l[:1].isdigit():
            c, rest = l.split(" ", 1); out.append("%d %s" % (int(c) - c0, rest))
        else: out.append(l)
    return out

def run_rtl(h0, h1, cycles, tag, side, cdiv=1, pmw=False, cov=True):
    tr = os.path.join(BUILD, "rtl_%s.trace" % tag); cf = os.path.join(BUILD, "cov_%s.txt" % tag)
    args = ["vvp", "-n", VVP, "+hex0=" + h0, "+hex1=" + h1, "+trace=" + tr, "+maxcyc=%d" % cycles, "+noexit", "+cdiv=%d" % cdiv]
    if side: args.append("+side")
    if pmw: args.append("+pmw")
    if cov: args.append("+cov=" + cf)
    subprocess.run(args, stdout=subprocess.DEVNULL, check=True)
    return open(tr).read().splitlines(), (open(cf).read().splitlines() if cov else [])

def model_trace(h0, h1, cycles, side, r0, pmw=False):
    s = run_model(h0, h1, cycles - r0 + 1, side, pmw)
    return s.out + s.dump(), s

# ------------------------------------------------------------------ instruction classes of held cycles
def iclass(ins):
    if ins == 0xFFFF: return "IRQ"
    pa = M.Core.ptr_access(ins)
    if pa:
        st, w, mode = pa
        return ("ST" if st else "LD") + "XYZ"[w] + ["", "+", "-"][mode]
    if ins & 0xFC0F == 0x900F: return "PUSH" if ins & 0x200 else "POP"
    if ins & 0xF000 == 0xA000: return "STS" if ins & 0x800 else "LDS"
    if ins & 0xF000 == 0xD000: return "RCALL"
    if ins == 0x9509: return "ICALL"
    if ins == 0x9508: return "RET"
    if ins == 0x9518: return "RETI"
    if ins & 0xF800 == 0xB000: return "IN"
    if ins & 0xF800 == 0xB800: return "OUT"
    if ins & 0xFC00 == 0x9800: return ["CBI", "SBIC", "SBI", "SBIS"][(ins >> 8) & 3]
    return "other"

REQ_STATES = {"RCALL": (0, 2), "ICALL": (0, 2), "RET": (0, 3), "RETI": (0, 3), "IRQ": (0, 2)}
def req_states(cn): return REQ_STATES.get(cn, (0,))

# ------------------------------------------------------------------ one run
def parse_trace(lines):
    """last start line per core, and the dump"""
    last = {}
    for l in lines:
        if l[:1].isdigit():
            p = l.split(); last[int(p[1])] = p
    dump = {l.split()[0]: l.split()[1] for l in lines if l.startswith(("ram ", "io ", "rom0 ", "rom1 "))}
    return last, dump

def check(cls, N, sym, last, dump, cov, side, label, clsB=None):
    errs = []
    ram = bytes.fromhex(dump["ram"]); io = bytes.fromhex(dump["io"])
    cl = [cls[0], cls[1]]
    exp = [cl[0].exp(0, N), cl[1].exp(1, N)]
    for c in (0, 1):
        p = last.get(c)
        if p is None: errs.append("core %d: no instruction start" % c); continue
        regs = bytes.fromhex(p[3]); sreg = int(p[4], 16); sp = int(p[5], 16); pc = int(p[2], 16)
        for r, v in exp[c]["regs"].items():
            if regs[r - 16] != v: errs.append("core %d r%d = %02x expected %02x" % (c, r, regs[r - 16], v))
        if regs[1] != 0: errs.append("core %d r17 = %02x" % (c, regs[1]))
        if sp != SP0[c]: errs.append("core %d sp = %04x expected %04x" % (c, sp, SP0[c]))
        if pc != sym[c]["e"]: errs.append("core %d pc = %04x expected %04x" % (c, pc, sym[c]["e"]))
        if sreg != 0x55: errs.append("core %d sreg = %02x expected 55" % (c, sreg))
        for a, v in exp[c]["mem"].items():
            if ram[a] != v: errs.append("core %d ram[%03x] = %02x expected %02x" % (c, a, ram[a], v))
        for a, v in exp[c].get("io", {}).items():
            m = exp[c]["iomask"][a]
            if io[a] & m != v & m: errs.append("core %d io[%02x]&%02x = %02x expected %02x" % (c, a, m, io[a] & m, v & m))
        for i in range(64):
            if ram[TB[c] + i] != T(c, i): errs.append("core %d table %d" % (c, i)); break
        for i in range(32):
            if ram[LT[c] + i] != L(c, i): errs.append("core %d lds table %d" % (c, i)); break
        if ram[DONE[c]] != 1: errs.append("core %d did not finish" % c)
    # access counts to the registers with side effects: exact per core
    cnt = {}
    for l in cov:
        if l.startswith("CNT"):
            _, c, a, r, w = l.split(); cnt[(int(c), int(a))] = (int(r), int(w))
    for c in (0, 1):
        for a in (0x0F, 0x0C):
            er = exp[c]["rd"].get(a, 0); ew = exp[c]["wr"].get(a, 0)
            got = cnt.get((c, a), (0, 0))
            if side and got != (er, ew): errs.append("core %d accesses of reg %02x: reads/writes %s expected %s" % (c, a, got, (er, ew)))
    if side:
        tk = sum(exp[c]["rd"].get(0x0F, 0) for c in (0, 1)); wc = sum(exp[c]["wr"].get(0x0C, 0) for c in (0, 1))
        t = [l for l in cov if l.startswith("TICK")]
        if t:
            _, a, _, b = t[0].split()
            if (int(a), int(b)) != (tk, wc): errs.append("tick %s wcnt %s expected %d %d" % (a, b, tk, wc))
    return errs

HOLDS = collections.Counter()      # (core, arb, state, iclass) -> cycles
def accumulate_cov(cov, arb):
    for l in cov:
        p = l.split()
        if p[0] in "HSR" and len(p) == 4:
            HOLDS[(p[0], int(p[1]), arb, int(p[2]), iclass(int(p[3], 16)))] += 1

def one(nameA, nameB, arb, variant, N, cdiv, tag=None):
    clA, clB = CLASSES[nameA], CLASSES[nameB]
    side = clA.side or clB.side
    tag = tag or "r"
    h0, s0 = build("%s_0" % tag, program(0, clA, arb, N, variant))
    h1, s1 = build("%s_1" % tag, program(1, clB, arb, N, variant))
    n = model_length(h0, h1, side)
    if n is None: return ["model: programs did not finish"], None, None
    n = n + 10          # +maxcyc counts enabled core cycles
    rtl, cov = run_rtl(h0, h1, n, tag, side, cdiv)
    r0 = next((int(l.split()[0]) for l in rtl if l[:1].isdigit()), 1)
    mod, s = model_trace(h0, h1, n, side, r0)
    a = norm(rtl, r0); b = norm(mod, 1)
    errs = []
    # with cdiv the RTL trace counts enabled cycles only; the run length is in clock cycles
    k = min(len(a), len(b))
    d = next((i for i in range(k) if a[i] != b[i]), None)
    if d is None and len(a) != len(b): d = k
    if d is not None:
        errs.append("RTL differs from model at line %d: rtl %s | model %s" % (d, a[d][:90] if d < len(a) else "-", b[d][:90] if d < len(b) else "-"))
    last, dump = parse_trace(a)
    errs += check((clA, clB), N, (s0, s1), last, dump, cov, side, tag)
    accumulate_cov(cov, arb)
    return errs, a, (s0, s1)

def core_starts(trace, c, stop_pc):
    out = []
    for l in trace:
        if l[:1].isdigit():
            p = l.split()
            if int(p[1]) == c and int(p[2], 16) < stop_pc: out.append(" ".join(p[:3]))        # cycle, core, pc: data of the side-effect registers may differ
    return out

# ------------------------------------------------------------------ interrupts: entry and RETI meet bus accesses of the other core
NIT = (40, 35)           # iterations of core 0 and core 1; each iteration raises one interrupt of the other core
def irq_program(core, arb, variant):
    c = core; R = NIT[c]
    pad = PADS[variant % len(PADS)][c] + (3 if c else 0)
    L_ = ["        .text", "        .org 0", "        rjmp start", "        rjmp isr", "start:  ldi r17, 0"]
    if c == 0:
        L_ += ["        ldi r16, 0xD8", "        out 0x3C, r16", "        ldi r16, %d" % arb, "        ldi r30, 0x50", "        ldi r31, 0x3F",
               "        st Z, r16", "        ldi r16, 0x03", "        out 0x0E, r16"]
    L_ += ["        ldi r26, %d" % lo(TB[c]), "        ldi r27, %d" % hi(TB[c]), "        ldi r18, %d" % T(c, 0), "        ldi r19, 64",
           "i1:     st X+, r18", "        subi r18, -7", "        dec r19", "        brne i1",
           "        ldi r20, 0", "        ldi r21, 0", "        ldi r22, 0", "        ldi r23, 0", "        ldi r26, 0",
           "        ldi r30, %d" % lo(TB[c]), "        ldi r31, %d" % hi(TB[c]), "        ldi r28, %d" % lo(SB[c]), "        ldi r29, %d" % hi(SB[c]),
           "        ldi r25, %d" % R, "        ldi r16, 1", "        sei",
           "l:      out %d, r16" % (0x30 if c == 1 else 0x34),
           "        ld r19, Z+", "        add r20, r19", "        adc r21, r17", "        push r20", "        rcall f", "        pop r18",
           "        eor r22, r18", "        st Y+, r19", "        in r18, %d" % (2 + c), "        inc r18", "        out %d, r18" % (2 + c)]
    L_ += ["        nop"] * pad
    L_ += ["        dec r25", "        brne l",
           "sync:   ldi r18, 1", "        sts %d, r18" % DONE[c], "w:      lds r18, %d" % DONE[1 - c], "        tst r18", "        breq w",
           "        ldi r18, 80", "d:      dec r18", "        brne d", "        ldi r16, 0x55", "        out 0x3F, r16", "e:      rjmp e",
           "f:      inc r26", "        ret", "isr:    in r24, 0x3F", "        inc r23", "        out 0x3F, r24", "        reti"]
    return "\n".join(L_) + "\n"

def irqmix(arb, variant, cdiv=1, tag="i"):
    h0, s0 = build(tag + "_0", irq_program(0, arb, variant)); h1, s1 = build(tag + "_1", irq_program(1, arb, variant))
    n = model_length(h0, h1, False, margin=400)
    if n is None: return ["model: programs did not finish"], None
    n = n + 10          # +maxcyc counts enabled core cycles
    rtl, cov = run_rtl(h0, h1, n, tag, False, cdiv)
    r0 = next((int(l.split()[0]) for l in rtl if l[:1].isdigit()), 1)
    mod, s = model_trace(h0, h1, n, False, r0)
    a = norm(rtl, r0); b = norm(mod, 1)
    errs = []
    k = min(len(a), len(b))
    d = next((i for i in range(k) if a[i] != b[i]), None)
    if d is None and len(a) != len(b): d = k
    if d is not None: errs.append("RTL differs from model at line %d: rtl %s | model %s" % (d, a[d][:90] if d < len(a) else "-", b[d][:90] if d < len(b) else "-"))
    last, dump = parse_trace(a)
    ram = bytes.fromhex(dump["ram"]); io = bytes.fromhex(dump["io"])
    for c in (0, 1):
        R = NIT[c]; Ro = NIT[1 - c]; p = last[c]
        regs = bytes.fromhex(p[3]); sreg = int(p[4], 16); sp = int(p[5], 16); pc = int(p[2], 16)
        acc = sum(T(c, i) for i in range(R)); r22 = 0; run = 0
        for i in range(R): run += T(c, i); r22 ^= run & 255
        exp = {20: acc & 255, 21: (acc >> 8) & 255, 22: r22, 23: Ro, 26: R, 30: lo(TB[c] + R), 31: hi(TB[c] + R), 28: lo(SB[c] + R), 29: hi(SB[c] + R), 25: 0}
        for r, v in exp.items():
            if regs[r - 16] != v: errs.append("core %d r%d = %02x expected %02x" % (c, r, regs[r - 16], v))
        if sp != SP0[c]: errs.append("core %d sp = %04x expected %04x" % (c, sp, SP0[c]))
        if pc != s0["e"] if c == 0 else pc != s1["e"]: errs.append("core %d pc %04x" % (c, pc))
        if sreg != 0x55: errs.append("core %d sreg %02x" % (c, sreg))
        for i in range(R):
            if ram[SB[c] + i] != T(c, i): errs.append("core %d store %d" % (c, i)); break
        if io[2 + c] != R: errs.append("core %d io[%d] = %d expected %d" % (c, 2 + c, io[2 + c], R))
        if ram[DONE[c]] != 1: errs.append("core %d not done" % c)
    accumulate_cov(cov, arb)
    return errs, a

# Classes whose control flow depends on a testbench register that the other core changes by its own accesses.
# sbisc_tick skips on bit 0 of register 0x00F, which counts the reads of both cores; a partner that reads it
# changes the skip decisions of the core under test through data, not through the arbiter. Such partners are
# left out of the exact-timing check of that class. The matrix runs still cover these pairs against the model.
SHARED_DATA = {"sbisc_tick": ("in_tick", "sbisc_tick")}

def timing_check(nameA, arb, others, variant=0, N=48, cdiv=1):
    """U5: the core named by ARB has the same instruction start cycles whatever the other core executes"""
    others = [o for o in others if o not in SHARED_DATA.get(nameA, ())]
    w = 0 if arb == 1 else 1
    ref = None; errs = []
    for nameB in others:
        x, y = (nameA, nameB) if w == 0 else (nameB, nameA)
        e, tr, syms = one(x, y, arb, variant, N, cdiv, tag="t")
        errs += e
        if tr is None: continue
        stop = syms[w]["sync"]
        cur = core_starts(tr, w, stop)
        if ref is None: ref = (nameB, cur)
        elif cur != ref[1]:
            i = next((k for k in range(min(len(cur), len(ref[1]))) if cur[k] != ref[1][k]), min(len(cur), len(ref[1])))
            errs.append("core %d (priority) differs between the runs against %s and %s at start %d (of %d)" % (w, ref[0], nameB, i, len(cur)))
    return errs, (len(ref[1]) if ref else 0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default="all"); ap.add_argument("--vs", default="self")
    ap.add_argument("--arbs", default="0,1,2"); ap.add_argument("--variants", type=int, default=2)
    ap.add_argument("--cdiv", type=int, default=1); ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--swap", action="store_true"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--timing", action="store_true", help="check exact timing (U5) of the winning core")
    ap.add_argument("--covreport", action="store_true"); ap.add_argument("--irq", action="store_true", help="interrupt entry and RETI against bus accesses of the other core")
    a = ap.parse_args()
    if a.list: print(" ".join(CLASSES)); return 0
    if a.irq:
        bad = runs = 0
        for arb in [int(x) for x in a.arbs.split(",")]:
            for v in range(a.variants):
                errs, _ = irqmix(arb, v, a.cdiv); runs += 1
                if errs: bad += 1; print("FAIL irq arb %d variant %d cdiv %d:" % (arb, v, a.cdiv)); [print("   ", e) for e in errs[:6]]
        print("arbsweep irq: %d runs, %d failing" % (runs, bad))
        if a.covreport: report_cov([0, 1, 2])
        return 1 if bad else 0
    if a.timing:
        bad = runs = 0
        for nameA in (list(CLASSES) if a.classes == "all" else a.classes.split(",")):
            for arb in (1, 2):
                errs, n = timing_check(nameA, arb, ["ld_Xp", "pushpop", "rcall2", "in_tick", "sbisc_tick", "sts", "st_Zm", "icall", "out_wc"], 0, a.n, a.cdiv); runs += 1
                if errs: bad += 1; print("FAIL timing %s arb %d:" % (nameA, arb)); [print("   ", e) for e in errs[:4]]
        print("arbsweep timing (U5): %d checks, %d failing; partners left out because of shared testbench data: %s" % (runs, bad, ", ".join("%s against %s" % (k, "/".join(v)) for k, v in SHARED_DATA.items())))
        return 1 if bad else 0
    names = list(CLASSES) if a.classes == "all" else a.classes.split(",")
    vs = {"self": None, "all": list(CLASSES)}.get(a.vs, None) or a.vs.split(",")
    arbs = [int(x) for x in a.arbs.split(",")]
    bad = runs = 0
    for nameA in names:
        for nameB in ([nameA] if a.vs == "self" else vs):
            for arb in arbs:
                for v in range(a.variants):
                    for sw in ((False, True) if a.swap and nameA != nameB else (False,)):
                        x, y = (nameB, nameA) if sw else (nameA, nameB)
                        errs, tr, syms = one(x, y, arb, v, a.n, a.cdiv)
                        runs += 1
                        if errs:
                            bad += 1
                            print("FAIL %s | %s arb %d variant %d cdiv %d:" % (x, y, arb, v, a.cdiv)); [print("   ", e) for e in errs[:6]]
        sys.stdout.flush()
    print("arbsweep: %d runs, %d failing" % (runs, bad))
    if a.covreport: report_cov(arbs)
    return 1 if bad else 0

def report_cov(arbs):
    classes = sorted(set(k[4] for k in HOLDS if k[0] == "H"))
    print("hold coverage (H = held by the arbiter): class/state  core0 core1 (cycles summed over the runs)")
    miss = []
    for cn in ["LDX", "LDX+", "LDX-", "LDY", "LDY+", "LDY-", "LDZ", "LDZ+", "LDZ-", "STX", "STX+", "STX-", "STY", "STY+", "STY-",
               "STZ", "STZ+", "STZ-", "PUSH", "POP", "LDS", "STS", "RCALL", "ICALL", "RET", "RETI", "IN", "OUT", "CBI", "SBIC", "SBI", "SBIS", "IRQ"]:
        row = []
        for st in req_states(cn):
            for c in (0, 1):
                n = sum(v for k, v in HOLDS.items() if k[0] == "H" and k[1] == c and k[3] == st and k[4] == cn)
                row.append("c%d s%d:%d" % (c, st, n))
                if n == 0: miss.append((cn, c, st))
        print("  %-6s %s" % (cn, "  ".join(row)))
    print("not covered:", miss if miss else "none")

if __name__ == "__main__":
    sys.exit(main())
