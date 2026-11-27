#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Access to the other core's code memory (rule U7) and core 0 executing from code memory 1 (rule M5).

  steal    the owner core runs a kernel (alu: no bus access; mix: loads from its own code memory, stack, calls,
           RAM, registers) while the other core loads and stores in the owner's code memory with all
           addressing modes and every phase.  Expected, from the rules only:
             - loaded bytes equal the table, stored bytes arrive (checked in memory),
             - the owner's architectural result equals the Python simulation of its kernel and the run where
               the other core accesses its own code memory instead (baseline),
             - alu owner: the owner needs exactly 2 more cycles per access (held in the access cycle and in the
               refetch cycle), unless the owner is the core named by ARB: then the accessor is held until the
               owner waits, and the owner is not delayed at all (LOOPDONE is 1 when the accessor has finished its first access),
  wait     the owner is waiting while the other core accesses its code memory: the owner is not affected
           at the time, and its first cycle after the wake-up is used for the re-read: exactly +1 cycle,
  boot     the owner is stopped: the other core writes a new program into its code memory, starts it, it runs,
           stops it in the middle of a loop, writes again, restarts,
  cross    both cores access each other's code memory at the same time,
  exec0    core 0 executes from code memory 1 while core 1 is stopped (with loads and stores in that
           memory), and is held until core 1 has stopped itself if it is running.
"""
import sys, os, argparse, collections, re, subprocess
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import arbsweep as A
from arbsweep import build, norm, run_rtl, parse_trace, model_trace, accumulate_cov, HOLDS

DONE, LDONE, RES = [0xA0, 0xA1], [0xA4, 0xA5], [0xA8, 0xA9]
def CM(c): return 0x4000 | (c << 11)
TABO, SCRO = 0x600, 0x700
def tabv(c, j): return (j * 13 + 5 + 7 * c) & 255
def lo(x): return x & 255
def hi(x): return (x >> 8) & 255

def prologue(c, arb, start1=True):
    L = ["        .text", "        .org 0", "        ldi r17, 0"]
    if c == 0:
        L += ["        ldi r16, 0xD8", "        out 0x3C, r16", "        ldi r16, %d" % arb, "        ldi r30, 0x50",
              "        ldi r31, 0x3F", "        st Z, r16"]
        if start1: L += ["        ldi r16, 0x03", "        out 0x0E, r16"]
    return L

def epilogue(c, helpers=()):
    L = ["sync:   ldi r16, 1", "        sts %d, r16" % DONE[c], "w:      lds r16, %d" % DONE[1 - c], "        tst r16",
         "        breq w", "        ldi r18, 30", "d:      dec r18", "        brne d", "        ldi r16, 0x55",
         "        out 0x3F, r16", "e:      rjmp e"]
    L += ["        " + x if not re.match(r"\w+:", x) else x for x in helpers]
    L += ["        .org 0x%x" % TABO] + ["        .byte " + ",".join(str(tabv(c, j)) for j in range(i, i + 16)) for i in range(0, 256, 16)]
    return L

KINDS = []
for p in "XYZ":
    for st in (False, True):
        for m in ("", "+", "-"):
            KINDS.append((p, st, m))
PREG = {"X": 26, "Y": 28, "Z": 30}

def accesses(target, K, padf, first_hook=None):
    """list of asm lines and expectations for K loads and stores in the memory of core `target`"""
    L, acc, scr = [], 0, {}
    for k in range(K):
        p, st, m = KINDS[k % len(KINDS)]
        P = PREG[p]
        if st:
            idx = (k * 5) % 24; addr = CM(target) + SCRO + idx; val = (0x80 + k) & 255
            scr[idx] = val
        else:
            idx = (k * 7) % 100; addr = CM(target) + TABO + idx; val = tabv(target, idx); acc += val
        reg = addr + (1 if m == "-" else 0)
        L += ["        nop"] * padf(k)
        L += ["        ldi r%d, %d" % (P, lo(reg)), "        ldi r%d, %d" % (P + 1, hi(reg))]
        if st:
            L += ["        ldi r19, %d" % val, "        st %s, r19" % ({"": p, "+": p + "+", "-": "-" + p}[m])]
        else:
            L += ["        ld r19, %s" % {"": p, "+": p + "+", "-": "-" + p}[m], "        add r20, r19", "        adc r21, r17"]
        if k == 0 and first_hook: L += first_hook
    return L, acc, scr

def owner_alu(c):
    L = ["        ldi r18, 3", "        ldi r20, 0", "        ldi r21, 0", "        ldi r22, 0", "        ldi r23, 0",
         "        ldi r24, 0", "        ldi r26, 0", "        ldi r27, 0",
         "lp:     add r20, r18", "        adc r21, r17", "        eor r22, r20", "        inc r23", "        cpse r23, r23",
         "        inc r26", "        sbrc r20, 0", "        inc r27", "        dec r24", "        brne lp", "lend:"]
    r = dict(r20=0, r21=0, r22=0, r23=0, r24=0, r26=0, r27=0)
    for _ in range(256):
        s = r["r20"] + 3; r["r20"] = s & 255; r["r21"] = (r["r21"] + (s >> 8)) & 255
        r["r22"] ^= r["r20"]; r["r23"] = (r["r23"] + 1) & 255
        if r["r20"] & 1: r["r27"] = (r["r27"] + 1) & 255
        r["r24"] = (r["r24"] - 1) & 255
    return L, {int(k[1:]): v for k, v in r.items()}, {}, []

NMIX = 200
def owner_mix(c):
    ra = 0x300 + 0x200 * c; ls = 0x80 + 0x10 * c
    L = ["        ldi r30, %d" % lo(CM(c) + TABO), "        ldi r31, %d" % hi(CM(c) + TABO),
         "        ldi r28, %d" % lo(ra), "        ldi r29, %d" % hi(ra), "        ldi r24, %d" % NMIX,
         "        ldi r20, 0", "        ldi r21, 0", "        ldi r22, 0", "        ldi r23, 0",
         "lp:     ld r19, Z+", "        add r20, r19", "        adc r21, r17", "        push r20", "        rcall f", "        pop r18",
         "        eor r22, r18", "        st Y+, r19", "        lds r18, %d" % ls, "        inc r18", "        sts %d, r18" % ls,
         "        in r18, %d" % (2 + c), "        inc r18", "        out %d, r18" % (2 + c), "        dec r24", "        brne lp", "lend:"]
    acc = 0; r22 = 0; mem = {}
    for i in range(NMIX):
        v = tabv(c, i); acc += v; r20 = acc & 255; r22 ^= r20; mem[ra + i] = v
    mem[ls] = NMIX & 255
    z = CM(c) + TABO + NMIX; y = ra + NMIX
    regs = {20: acc & 255, 21: (acc >> 8) & 255, 22: r22, 23: NMIX & 255, 24: 0, 30: lo(z), 31: hi(z), 28: lo(y), 29: hi(y)}
    return L, regs, mem, ["f:      inc r23", "        ret"]

OWNER = {"alu": owner_alu, "mix": owner_mix}

def wait_seq(c):
    return ["        ldi r16, 1", "        sts %d, r16" % LDONE[c], "        ldi r16, 0x10", "        out 0x21, r16",
            "        ldi r16, 0", "        out 0x20, r16", "resume: nop"]

def setev(): return ["        ldi r16, 0x10", "        out 0x07, r16"]

def named(arb, owner): return (arb == 1 and owner == 0) or (arb == 2 and owner == 1)

# ------------------------------------------------------------------ common run
def runpair(h0, h1, tag, side=False, pmw=True, cdiv=1, limit=30000):
    n = A.model_length(h0, h1, side, limit=limit, pmw=pmw)
    if n is None: return None
    n = n + 10          # +maxcyc counts enabled core cycles
    rtl, cov = run_rtl(h0, h1, n, tag, side, cdiv, pmw=pmw)
    r0 = next((int(l.split()[0]) for l in rtl if l[:1].isdigit()), 1)
    mod, s = model_trace(h0, h1, n, side, r0, pmw=pmw)
    a = norm(rtl, r0); b = norm(mod, 1)
    errs = []
    k = min(len(a), len(b))
    d = next((i for i in range(k) if a[i] != b[i]), None)
    if d is None and len(a) != len(b): d = k
    if d is not None:
        errs.append("RTL differs from model at line %d: rtl %s | model %s" % (d, a[d][:90] if d < len(a) else "-", b[d][:90] if d < len(b) else "-"))
    last, dump = parse_trace(a)
    return dict(errs=errs, lines=a, last=last, dump=dump, cov=cov)

def cyc_at(lines, core, pc):
    for l in lines:
        if l[:1].isdigit():
            p = l.split()
            if int(p[1]) == core and int(p[2], 16) == pc: return int(p[0])
    return None

def regs_of(res, c): return bytes.fromhex(res["last"][c][3])
def rom_of(res, m):
    """bytes of a code memory in address order (the dump prints 16-bit words, high byte first)"""
    b = bytes.fromhex(res["dump"]["rom%d" % m]); o = bytearray(len(b))
    o[0::2], o[1::2] = b[1::2], b[0::2]
    return bytes(o)

def count(cov, kind, core): return sum(1 for l in cov if l.split()[:2] == [kind, str(core)])

# ------------------------------------------------------------------ steal / wait
def steal(owner_kind, arb, acc_core, variant, K, baseline, cdiv=1, tag="c"):
    o = 1 - acc_core
    padf = lambda k: ((k * 5 + 2 + variant) % 7)
    # owner
    if owner_kind == "wait":
        oL, oregs, omem, ohelp = [], {}, {}, []
    else:
        oL, oregs, omem, ohelp = OWNER[owner_kind](o)
    ob = prologue(o, arb) + oL + wait_seq(o)
    ob = ob[:ob.index("resume: nop")] + ["resume: nop"]
    hook = ["        lds r23, %d" % LDONE[o], "        sts %d, r23" % RES[acc_core]]
    target = acc_core if baseline else o
    adelay = ["        ldi r18, %d" % (40 + variant), "dl:     dec r18", "        brne dl", "        ldi r20, 0", "        ldi r21, 0"]
    aL, acc, scr = accesses(target, K, padf, first_hook=hook)
    ab = prologue(acc_core, arb) + adelay + aL + setev()
    t = {o: ob + epilogue(o, ohelp), acc_core: ab + epilogue(acc_core)}
    hx = {}; sym = {}
    for c in (0, 1): hx[c], sym[c] = build("%s%d" % (tag, c), "\n".join(t[c]) + "\n")
    r = runpair(hx[0], hx[1], tag, pmw=True, cdiv=cdiv)
    if r is None: return dict(errs=["model: programs did not finish"]), None
    errs = r["errs"]
    ram = bytes.fromhex(r["dump"]["ram"])
    for c in (0, 1):
        if ram[DONE[c]] != 1: errs.append("core %d not done" % c)
        if r["last"][c][2] != "%04x" % sym[c]["e"]: errs.append("core %d pc %s not at e" % (c, r["last"][c][2]))
    ra, ro = regs_of(r, acc_core), regs_of(r, o)
    s = acc
    if (ra[4], ra[5]) != (s & 255, (s >> 8) & 255): errs.append("accessor sum %02x%02x expected %04x" % (ra[5], ra[4], s))
    mem_t = rom_of(r, target)
    for j, v in scr.items():
        if mem_t[SCRO + j] != v: errs.append("stored byte %d in memory %d is %02x expected %02x" % (j, target, mem_t[SCRO + j], v))
    # table must be unchanged in both memories
    for m in (0, 1):
        mm = rom_of(r, m)
        for j in range(256):
            if mm[TABO + j] != tabv(m, j): errs.append("table of memory %d changed at %d" % (m, j)); break
    for rn, v in oregs.items():
        if ro[rn - 16] != v: errs.append("owner r%d = %02x expected %02x" % (rn, ro[rn - 16], v))
    for a_, v in omem.items():
        if ram[a_] != v: errs.append("owner ram[%03x] = %02x expected %02x" % (a_, ram[a_], v))
    exp_ld = 1 if (owner_kind == "wait" or (named(arb, o) and not baseline)) else 0
    if baseline: exp_ld = 1 if owner_kind == "wait" else 0
    if ram[RES[acc_core]] != exp_ld: errs.append("LOOPDONE seen after the first access = %d expected %d" % (ram[RES[acc_core]], exp_ld))
    info = dict(lend=cyc_at(r["lines"], o, sym[o]["lend"]) if owner_kind != "wait" else None,
                resume=cyc_at(r["lines"], o, sym[o]["resume"]), S=count(r["cov"], "S", o), R=count(r["cov"], "R", o),
                regs=(ro, ram), cov=r["cov"])
    if not baseline: accumulate_cov(r["cov"], arb)
    return dict(errs=errs, **info), r

def steal_case(owner_kind, arb, acc_core, variant, K, cdiv=1):
    d, _ = steal(owner_kind, arb, acc_core, variant, K, False, cdiv)
    b, _ = steal(owner_kind, arb, acc_core, variant, K, True, cdiv, tag="cb")
    errs = list(d["errs"]) + ["baseline: " + e for e in b["errs"]]
    if not errs:
        o = 1 - acc_core
        if d["regs"][0] != b["regs"][0]: errs.append("owner registers differ from the baseline run")
        dram, bram = d["regs"][1], b["regs"][1]
        if owner_kind != "wait" and not named(arb, o):
            if d["S"] != K or d["R"] != K: errs.append("owner stolen %d times, refetch %d times, expected %d each" % (d["S"], d["R"], K))
        if owner_kind == "alu":
            exp = 0 if named(arb, o) else 2 * K
            got = d["lend"] - b["lend"]
            if got != exp: errs.append("alu owner delayed by %d cycles, expected %d" % (got, exp))
        if owner_kind == "wait":
            if d["resume"] - b["resume"] != 1 or d["S"] != 0 or d["R"] != 1:
                errs.append("owner resume shift %d (expected 1), stolen %d, refetch %d" % (d["resume"] - b["resume"], d["S"], d["R"]))
        if owner_kind == "mix" and named(arb, o) and d["S"] != 0:
            errs.append("named owner stolen %d times" % d["S"])
    return errs

# ------------------------------------------------------------------ cross
def cross(arb, variant, K, cdiv=1, tag="x"):
    waiter = {1: 0, 2: 1}.get(arb, 0)
    t = {}; exp = {}
    for c in (0, 1):
        padf = lambda k, c=c: ((k * (3 + 2 * c) + variant + c) % (5 + c))
        aL, acc, scr = accesses(1 - c, K, padf)
        b = prologue(c, arb) + ["        ldi r20, 0", "        ldi r21, 0"] + aL
        if c == waiter: b += wait_seq(c)[:-1] + ["resume: nop"]
        else: b += setev()
        t[c] = b + epilogue(c); exp[c] = (acc, scr)
    hx, sym = {}, {}
    for c in (0, 1): hx[c], sym[c] = build("%s%d" % (tag, c), "\n".join(t[c]) + "\n")
    r = runpair(hx[0], hx[1], tag, pmw=True, cdiv=cdiv)
    if r is None: return ["model: programs did not finish"]
    errs = r["errs"]; ram = bytes.fromhex(r["dump"]["ram"])
    for c in (0, 1):
        if ram[DONE[c]] != 1: errs.append("core %d not done" % c)
        rg = regs_of(r, c); s = exp[c][0]
        if (rg[4], rg[5]) != (s & 255, (s >> 8) & 255): errs.append("core %d sum %02x%02x expected %04x" % (c, rg[5], rg[4], s))
        mm = rom_of(r, 1 - c)
        for j, v in exp[c][1].items():
            if mm[SCRO + j] != v: errs.append("core %d store %d: %02x expected %02x" % (c, j, mm[SCRO + j], v))
    accumulate_cov(r["cov"], arb)
    return errs

# ------------------------------------------------------------------ boot: write the program of a stopped core, run it, stop it, rewrite
def words_of(text, name):
    h, sym = build(name, text)
    return [int(x, 16) for x in open(h).read().split()], sym

PROG_A = """        .text
        .org 0
        ldi r16, 0x77
        sts 0xB0, r16
        ldi r16, 1
        sts 0xB1, r16
        ldi r17, 0
        ldi r19, 0
q:      inc r19
        sts 0xB2, r19
        rjmp q
"""
PROG_B = """        .text
        .org 0
        ldi r16, 0x99
        sts 0xB3, r16
        ldi r19, 0
z:      inc r19
        sts 0xB4, r19
        rjmp z
"""

def boot(arb, variant, cdiv=1, tag="b"):
    wa, _ = words_of(PROG_A, "pa"); wb, _ = words_of(PROG_B, "pb")
    def store_words(ws, base):
        L = []
        for i, w in enumerate(ws):
            for bsel in (0, 1):
                L += ["        ldi r26, %d" % lo(base + 2 * i + bsel), "        ldi r27, %d" % hi(base + 2 * i + bsel),
                      "        ldi r19, %d" % ((w >> (8 * bsel)) & 255), "        st X, r19"]
        return L
    # core 1 image at reset: counts in 0xB5 until core 0 stops it (this is also the proof that it ran)
    c1 = ["        .text", "        .org 0", "        ldi r17, 0", "        ldi r19, 0", "o:      inc r19", "        sts 0xB5, r19", "        rjmp o"]
    c0 = prologue(0, arb, start1=False)
    c0 += store_words(wa, CM(1))
    c0 += ["        ldi r16, 3", "        out 0x0E, r16"]                      # start core 1: runs program A
    c0 += ["        ldi r18, %d" % (60 + variant), "dl:     dec r18", "        brne dl"]
    c0 += ["        ldi r16, 1", "        out 0x0E, r16"]                      # stop core 1 in the middle of its loop
    c0 += ["        lds r20, 0xB2", "        nop", "        nop", "        nop", "        lds r21, 0xB2",    # no longer advancing
           "        sts 0xB6, r20", "        sts 0xB7, r21"]
    c0 += store_words(wb, CM(1))
    c0 += ["        ldi r16, 3", "        out 0x0E, r16"]                      # restart: program B from address 0
    c0 += ["        ldi r18, 60", "dm:     dec r18", "        brne dm", "        ldi r16, 1", "        out 0x0E, r16", "        lds r22, 0xB4", "        sts 0xB8, r22"]
    # core 1 must stop at the end: DONE1 is set by core 0 for it
    c0 += ["        ldi r16, 1", "        sts %d, r16" % DONE[1]]
    c1text = "\n".join(c1) + "\n"
    h0, s0 = build(tag + "0", "\n".join(c0 + epilogue(0)) + "\n")
    # core 1 image for the model: reset image is stub; the epilogue is not used
    h1, s1 = build(tag + "1", c1text)
    # model_length needs both DONE flags: core 0 sets DONE1 itself
    r = runpair(h0, h1, tag, pmw=True, cdiv=cdiv)
    if r is None: return ["model: programs did not finish"]
    errs = r["errs"]; ram = bytes.fromhex(r["dump"]["ram"])
    chk = {0xB0: 0x77, 0xB1: 1, 0xB3: 0x99}
    for a_, v in chk.items():
        if ram[a_] != v: errs.append("ram[%02x] = %02x expected %02x" % (a_, ram[a_], v))
    if ram[0xB6] != ram[0xB7]: errs.append("core 1 counter moved after the stop: %02x -> %02x" % (ram[0xB6], ram[0xB7]))
    if ram[0xB2] == 0 or ram[0xB4] == 0: errs.append("program A / B did not run (counters %02x %02x)" % (ram[0xB2], ram[0xB4]))
    if ram[0xB2] != ram[0xB6]: errs.append("counter A after the stop differs from the value read right after: %02x %02x" % (ram[0xB2], ram[0xB6]))
    if ram[0xB8] != ram[0xB4]: errs.append("core 1 counter B moved after the final stop")
    last, _ = r["last"], 0
    accumulate_cov(r["cov"], arb)
    return errs

# ------------------------------------------------------------------ exec0: core 0 executes from code memory 1
def exec0(arb, variant, core1_running, cdiv=1, tag="e"):
    NTAB = 40
    snippet = """snip:   ldi r20, 0
        ldi r21, 0
        ldi r30, %d
        ldi r31, %d
        ldi r26, %d
        ldi r27, %d
        ldi r24, %d
sl:     ld r19, Z+
        add r20, r19
        adc r21, r17
        push r20
        rcall sf
        pop r18
        eor r22, r18
        st X+, r19
        dec r24
        brne sl
        ldi r28, %d
        ldi r29, %d
        ld r25, Y
        ldi r30, lo8(pm(back))
        ldi r31, hi8(pm(back))
        ijmp
sf:     inc r23
        ret
snip_end:
""" % (lo(CM(1) + TABO), hi(CM(1) + TABO), lo(CM(1) + SCRO), hi(CM(1) + SCRO), NTAB, lo(CM(1) + TABO + 5), hi(CM(1) + TABO + 5))
    c0 = prologue(0, arb, start1=False) + ["        ldi r22, 0", "        ldi r23, 0"]
    # copy the snippet from the own code memory (word 0x280 on) to code memory 1 (word 0x100 on)
    c0 += ["        ldi r30, lo8(%d)" % (CM(0) + 0x500), "        ldi r31, hi8(%d)" % (CM(0) + 0x500),
           "        ldi r26, lo8(%d)" % (CM(1) + 0x200), "        ldi r27, hi8(%d)" % (CM(1) + 0x200),
           "        ldi r24, snip_end-snip", "cp:     ld r19, Z+", "        st X+, r19", "        dec r24", "        brne cp"]
    if core1_running:
        c0 += ["        ldi r16, 3", "        out 0x0E, r16"]
    c0 += ["        ldi r18, %d" % (10 + variant), "dd:     dec r18", "        brne dd", "        sts %d, r18" % RES[0],
           "        ldi r30, lo8(0x500)", "        ldi r31, hi8(0x500)", "        ijmp",       # word address 0x500 = code memory 1, word 0x100
           "back:   sts %d, r20" % (RES[0] + 2), "        sts %d, r21" % (RES[0] + 3), "        sts %d, r25" % (RES[0] + 4),
           "        sts %d, r23" % (RES[0] + 5), "        lds r16, %d" % LDONE[1], "        sts %d, r16" % (RES[0] + 6)]
    c0 += ["        ldi r16, 1", "        sts %d, r16" % DONE[1]]       # core 1 does not run the epilogue
    c0t = "\n".join(c0 + epilogue(0, ["        .org 0x500"] + snippet.splitlines())) + "\n"
    # core 1: counts for a while, sets LDONE and stops itself
    c1 = ["        .text", "        .org 0", "        ldi r17, 0", "        ldi r19, 0", "        ldi r18, 0", "l1:     inc r19", "        sts 0xBA, r19",
          "        dec r18", "        brne l1", "        ldi r16, 1", "        sts %d, r16" % LDONE[1], "        out 0x0E, r16", "x:      rjmp x"]
    h0, s0 = build(tag + "0", c0t)
    c1 += ["        .org 0x%x" % TABO] + ["        .byte " + ",".join(str(tabv(1, j)) for j in range(i, i + 16)) for i in range(0, 256, 16)]
    h1, s1 = build(tag + "1", "\n".join(c1) + "\n")
    r = runpair(h0, h1, tag, pmw=True, cdiv=cdiv)
    if r is None: return ["model: programs did not finish"]
    errs = r["errs"]; ram = bytes.fromhex(r["dump"]["ram"]); rom1 = rom_of(r, 1)
    acc = sum(tabv(1, j) for j in range(NTAB))
    got = (ram[RES[0] + 2], ram[RES[0] + 3])
    if got != (acc & 255, (acc >> 8) & 255): errs.append("sum %02x%02x expected %04x" % (got[1], got[0], acc))
    if ram[RES[0] + 4] != tabv(1, 5): errs.append("ld Y after the loop %02x expected %02x" % (ram[RES[0] + 4], tabv(1, 5)))
    if ram[RES[0] + 5] != NTAB: errs.append("calls %d expected %d" % (ram[RES[0] + 5], NTAB))
    for j in range(NTAB):
        if rom1[SCRO + j] != tabv(1, j): errs.append("store %d: %02x" % (j, rom1[SCRO + j])); break
    if core1_running:
        if ram[RES[0] + 6] != 1: errs.append("core 0 ran in code memory 1 while core 1 was still running (LDONE1 = %d)" % ram[RES[0] + 6])
        if ram[0xBA] != 0: errs.append("core 1 counter %02x expected 00 (256 iterations)" % ram[0xBA])
        # trace: first start of core 0 with pc >= 0x400 is after the last start of core 1
        c0first = next((int(l.split()[0]) for l in r["lines"] if l[:1].isdigit() and l.split()[1] == "0" and int(l.split()[2], 16) >= 0x400), None)
        c1last = max(int(l.split()[0]) for l in r["lines"] if l[:1].isdigit() and l.split()[1] == "1")
        if c0first is None or c0first <= c1last: errs.append("core 0 started in code memory 1 at cycle %s, core 1 last start at %d" % (c0first, c1last))
    accumulate_cov(r["cov"], arb)
    return errs

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tests", nargs="?", default="all")
    ap.add_argument("--arbs", default="0,1,2"); ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--cdiv", type=int, default=1); ap.add_argument("--k", type=int, default=54)
    a = ap.parse_args()
    arbs = [int(x) for x in a.arbs.split(",")]
    todo = ["steal", "wait", "cross", "boot", "exec0"] if a.tests == "all" else a.tests.split(",")
    runs = bad = 0
    def rep(name, errs):
        nonlocal runs, bad
        runs += 1
        if errs:
            bad += 1; print("FAIL", name); [print("    ", e) for e in errs[:6]]; sys.stdout.flush()
    for arb in arbs:
        for v in range(a.variants):
            if "steal" in todo:
                for kind in ("alu", "mix"):
                    for ac in (0, 1):
                        rep("steal %s arb %d accessor core %d variant %d" % (kind, arb, ac, v), steal_case(kind, arb, ac, v, a.k, a.cdiv))
            if "wait" in todo:
                for ac in (0, 1):
                    rep("wait arb %d accessor core %d variant %d" % (arb, ac, v), steal_case("wait", arb, ac, v, 12 + v, a.cdiv))
            if "cross" in todo:
                rep("cross arb %d variant %d" % (arb, v), cross(arb, v, a.k, a.cdiv))
            if "boot" in todo:
                rep("boot arb %d variant %d" % (arb, v), boot(arb, v, a.cdiv))
            if "exec0" in todo:
                for run1 in (False, True):
                    rep("exec0 arb %d variant %d core1_running %s" % (arb, v, run1), exec0(arb, v, run1, a.cdiv))
    print("arbcode %s: %d cases, %d failing" % (a.tests, runs, bad))
    sc = collections.Counter()
    for k, n in HOLDS.items():
        if k[0] == "S": sc[(k[1], k[3], k[4])] += n
    print("owner stolen by state/instruction (core, state, instruction: cycles):")
    for k in sorted(sc): print("   core %d state %d %-6s %d" % (k[0], k[1], k[2], sc[k]))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
