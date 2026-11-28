#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Interrupt during a wait (system testbench, both cores, core clock divider 1, 2, 3).

Specified behaviour (spec sections corebeh H4-H6, Q1-Q4, intro of 'Interrupts and waiting', comm C4):
  W1  OUT to WAITL puts the core into the wait state at the end of the cycle. If a selected flag is already set
      when the mask is written, the core does not wait (H4, C4).
  W2  The core is enabled again in the cycle after one in which a selected flag was set (H4).
  W3  An enabled interrupt that is pending (I flag set, flag set in IFR, bit set in IER) ends a wait as it ends
      SLEEP (intro, H6).
  W4  An interrupt is taken in a cycle that would start a new instruction if I is set (Q2). A core that leaves a
      wait by an interrupt therefore takes the interrupt before it executes the instruction after the OUT;
      the return address is that instruction (execution continues there after RETI).
  W5  Taking an interrupt does not clear a software flag or the DLY flag (Q4); the program finds the reason for
      the end of a wait in IFR (H5).
  W6  No event and no interrupt is lost or taken twice.

Test a (core 0 waits; core 1 raises software flags at swept times, ARB 0/1/2):
  modes ev (SW0 = wait mask), int (SW1 = interrupt only), both (SW0 and SW1 written in one cycle), ev_int (SW0, then
  SW1 g cycles later), int_ev (SW1, then SW0).  The time of the raise is swept from 8 core cycles before to 8 core
  cycles after the cycle in which core 0 writes WAITL.  Checks: interrupt count, order of interrupt and the first
  instruction after the wait, IFR content, the second wait (event only, no interrupt pending) ends, wake-up latency
  from the log of the testbench (+wlog), and that the log shows raises before, in and after the cycle of the OUT.
Test b (both cores at once): each core sets its own wake-up time DLY = now + N and waits on DLY with DLY also enabled
  as interrupt: event and interrupt arrive in the same cycle, on both cores, N swept; the DLY flag is not aligned with
  the core clock enable.
usage: waitirq.py [--cdivs 1,2,3] [--arbs 0,1,2] [--modes ...] [--tests a,b]
"""
import subprocess, sys, os, re, argparse, collections
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.join(here, "..")
BUILD = os.path.join(root, "build", "wi"); os.makedirs(BUILD, exist_ok=True)
VVP = os.environ.get("WI_VVP", os.path.join(root, "build", "tb_sys.vvp"))

RTL = "../src/rsoc8/rtl/rcore8d.v ../src/rsoc8/rtl/rdual.v ../src/rsoc8/rtl/rlinecells.v ../src/rsoc8/rtl/rlcports.v ../src/rsoc8/rtl/revents.v ../src/rsoc8/rtl/rtimers.v ../src/rsoc8/rtl/rclock.v ../src/rsoc8/rtl/rhost.v ../src/rsoc8/rtl/rpe_top.v ../src/rsoc8/rtl/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"

def build(name, text):
    s = os.path.join(BUILD, name + ".S"); open(s, "w").write(text)
    elf = os.path.join(BUILD, name + ".elf")
    subprocess.run(["avr-gcc", "-mmcu=attiny40", "-nostdlib", "-o", elf, s], check=True)
    subprocess.run(["avr-objcopy", "-O", "binary", "-j", ".text", elf, os.path.join(BUILD, name + ".bin")], check=True)
    b = open(os.path.join(BUILD, name + ".bin"), "rb").read(); b += b"\0" * (len(b) % 2)
    open(os.path.join(BUILD, name + ".hex"), "w").write("\n".join("%04x" % (b[i] | b[i + 1] << 8) for i in range(0, len(b), 2)) + "\n")
    nm = subprocess.run(["avr-nm", elf], capture_output=True, text=True, check=True).stdout
    return os.path.join(BUILD, name + ".hex"), {l.split()[2]: int(l.split()[0], 16) // 2 for l in nm.splitlines() if len(l.split()) == 3}

def sim(h0, h1, cdiv, maxcyc=6000):
    r = subprocess.run(["vvp", "-n", VVP, "+hex0=" + h0, "+hex1=" + h1, "+wlog", "+cdiv=%d" % cdiv, "+maxcyc=%d" % (maxcyc * cdiv)],
                       capture_output=True, text=True)
    return r.stdout.splitlines()

def parse(lines):
    ex = next((l for l in lines if l.startswith(("EXIT", "TIMEOUT"))), "no exit")
    ev = collections.defaultdict(list)
    for l in lines:
        if l.startswith("WL "):
            p = l.split(); ev[p[2]].append(p)
    return ex, ev

NOPS = lambda n: ["        nop"] * n

# ------------------------------------------------------------------ test a
ISR_SW = """isr:    push r16
        in r16, 0x3F
        push r16
        lds r16, 0x70
        inc r16
        sts 0x70, r16
        cbi 0x07, 5
        pop r16
        out 0x3F, r16
        pop r16
        reti
"""
def core0_a(arb, pad0, sd=False):
    return "\n".join(["        .text", "        .org 0", "        rjmp start", "        .org 28", "        rjmp isr",
        "start:  ldi r17, 0", "        sts 0x70, r17", "        sts 0x71, r17", "        sts 0x72, r17", "        sts 0x73, r17",
        "        ldi r16, 0xD8", "        out 0x3C, r16", "        ldi r16, %d" % arb, "        ldi r30, 0x50", "        ldi r31, 0x3F", "        st Z, r16",
        "        ldi r16, 0x20", "        out 0x23, r16",              # IER: flag 13 = SW1, vector 14
        "        ldi r16, 3", "        out 0x0E, r16",                  # start core 1
        "        ldi r18, 12", "dl:     dec r18", "        brne dl"] + (
        ["        ldi r16, 0x10", "        out 0x21, r16", "        ldi r16, 0"] + NOPS(pad0) + ["        sei", "waitl:  out 0x20, r16"] if sd else
        ["        sei", "        nop"] + NOPS(pad0) + ["        ldi r16, 0x10", "        out 0x21, r16", "        ldi r16, 0", "waitl:  out 0x20, r16"]) + [
        "resume: lds r18, 0x70", "        sts 0x71, r18", "        in r19, 0x07", "        sts 0x72, r19",
        "        cbi 0x07, 4",
        "        ldi r16, 0x10", "        out 0x21, r16", "        ldi r16, 0", "        out 0x20, r16",   # second wait: event only
        "res2:   lds r18, 0x70", "        sts 0x73, r18",
        "        lds r16, 0x70", "        out 0x1A, r16", "        lds r16, 0x71", "        out 0x1B, r16", "        lds r16, 0x72", "        out 0x1C, r16",
        "        lds r16, 0x73", "        out 0x1A, r16", "        out 0x1F, r17", "x:      rjmp x", ISR_SW])

def core1_a(mode, p1, g):
    L = ["        .text", "        .org 0", "start:  ldi r17, 0"]
    if mode == "both": L += ["        ldi r16, 0x30"]
    L += NOPS(p1)
    L += {"ev": ["        sbi 0x07, 4"], "int": ["        sbi 0x07, 5"], "both": ["raise:  out 0x07, r16"],
          "ev_int": ["        sbi 0x07, 4"] + NOPS(g) + ["        sbi 0x07, 5"],
          "int_ev": ["        sbi 0x07, 5"] + NOPS(g) + ["        sbi 0x07, 4"]}[mode]
    # rescue raises of SW0: the first ends the first wait if the interrupt had been served before the wait was entered,
    # the second ends the second wait
    L += ["        ldi r18, 60", "d1:     dec r18", "        brne d1", "        sbi 0x07, 4",
          "        ldi r18, 60", "d2:     dec r18", "        brne d2", "        sbi 0x07, 4", "y:      rjmp y"]
    return "\n".join(L) + "\n"

def run_a(mode, arb, cdiv, p1, g, pad0=0, sd=False):
    h0, s0 = build("a0", core0_a(arb, pad0, sd)); h1, s1 = build("a1", core1_a(mode, p1, g))
    ex, ev = parse(sim(h0, h1, cdiv))
    return ex, ev, s0

def analyse_a(mode, ex, ev, s0, cdiv):
    errs = []; info = {}
    if ex.split()[:2] != ["EXIT", "0"]: errs.append("did not finish: " + ex)
    marks = [(int(p[3]), int(p[4], 16), int(p[5], 16)) for p in ev.get("W", [])]
    vals = [v for c, a, v in marks if c == 0]
    if len(vals) != 4: errs.append("markers %s" % vals); return errs, info
    isrn, mseen, ifrs, isrn2 = vals
    wantn = 0 if mode == "ev" else 1
    if isrn != wantn or isrn2 != wantn: errs.append("interrupts taken: %d then %d, expected %d (W6)" % (isrn, isrn2, wantn))
    starts = [(int(p[1]), int(p[4], 16), p[5], p[6]) for p in ev.get("S", []) if p[3] == "0"]
    cyc_out = next((c for c, pc, t, i in starts if pc == s0["waitl"] and t == "0"), None)     # the OUT itself, not an interrupt entry before it
    first_res = next(((c, t, i) for c, pc, t, i in starts if pc == s0["resume"]), None)
    if first_res is None or cyc_out is None: errs.append("no start at waitl/resume"); return errs, info
    # W4: a request that is pending at the first start after the wait is taken before that instruction
    if first_res[1] != first_res[2]: errs.append("at the first start after the wait: take %s but request %s (W4)" % (first_res[1], first_res[2]))
    # interrupt entries that began before or at the first start after the wait must have run their ISR before that instruction
    exp_m = sum(1 for c, pc, t, i in starts if t == "1" and c <= first_res[0])
    if mode in ("int", "both", "int_ev") and exp_m != 1: errs.append("mode %s: the interrupt was not taken before the first instruction after the wait (W3, W4)" % mode)
    if mseen != exp_m: errs.append("%d interrupts before the first instruction after the wait, expected %d (W4)" % (mseen, exp_m))
    flags = [(int(p[1]), int(p[3], 16)) for p in ev.get("FLAGS", [])]
    waits = [(int(p[1]), int(p[3], 2)) for p in ev.get("WAIT", [])]
    t_ev = next((c for c, f in flags if f & 0x1000), None); t_int = next((c for c, f in flags if f & 0x2000), None)
    rel = {"ev": [t_ev], "int": [t_int], "both": [t_ev, t_int], "ev_int": [t_ev], "int_ev": [t_int, t_ev]}[mode]
    t_first = min(x for x in rel if x is not None) if any(x is not None for x in rel) else None
    if t_first is None: errs.append("flag never raised"); return errs, info
    info["d"] = t_first - cyc_out                        # first raise relative to the cycle of OUT WAITL (clock cycles)
    w_start = next((c for c, w in waits if w & 1 and cyc_out - 1 <= c <= first_res[0]), None)     # the first wait only
    w_end = next((c for c, w in waits if not w & 1 and w_start is not None and c > w_start), None)
    if w_start is not None and w_end is None: errs.append("core 0 entered a wait at %d and never left it (W2, W3)" % w_start)
    info["waited"] = w_start is not None and w_end is not None
    if w_start is not None:
        pend_int = t_int is not None and t_int <= cyc_out and not any(t == "1" and c < cyc_out for c, pc, t, i in starts)
        if (t_ev is not None and t_ev <= cyc_out) or (mode != "ev" and pend_int):
            errs.append("core 0 entered a wait at %d although a selected flag or enabled interrupt was already set at the OUT (cycle %d) (W1)" % (w_start, cyc_out))
    if info["waited"]:
        # the wait of the first OUT ends with the first selected flag or enabled interrupt that is set after the wait was entered
        t_src = next((c for c, f in flags if c >= w_start - 1 and f & 0x3000), None)
        if t_src is None: errs.append("wait ended without a flag")
        else:
            info["lat_end"] = w_end - t_src
            if w_end - t_src > cdiv: errs.append("wait ended %d clock cycles after the flag (cycle %d), expected at most %d (W2, W3)" % (w_end - t_src, t_src, cdiv))
            if w_end < t_src - 1: errs.append("wait ended at %d before a flag was set (cycle %d)" % (w_end, t_src))
            # was the flag that ended the wait the one at t_src? only if the wait starts before the raise
        info["early_int"] = t_int is not None and t_int < w_start - 1 and mode == "int"
    else:
        # no wait: the selected flag or the enabled interrupt must have been visible at the OUT (W1)
        if t_first > cyc_out + cdiv: errs.append("no wait although no flag (first at cycle %d) was set at the OUT (cycle %d) (W1)" % (t_first, cyc_out))
    return errs, info

# ------------------------------------------------------------------ test b
ISR_D = """isr:    push r16
        in r16, 0x3F
        push r16
        lds r16, %(isrn)d
        inc r16
        sts %(isrn)d, r16
        ldi r16, 0
        out 0x22, r16
        pop r16
        out 0x3F, r16
        pop r16
        reti
"""
def prog_b(c, arb, n):
    cell = 0x70 + 8 * c
    L = ["        .text", "        .org 0", "        rjmp start", "        .org 16", "        rjmp isr", "start:  ldi r17, 0"]
    L += ["        sts %d, r17" % (cell + k) for k in range(4)]
    if c == 0:
        L += ["        ldi r16, 0xD8", "        out 0x3C, r16", "        ldi r16, %d" % arb, "        ldi r30, 0x50", "        ldi r31, 0x3F", "        st Z, r16",
              "        ldi r16, 3", "        out 0x0E, r16"]
    L += ["        ldi r16, 0x80", "        out 0x22, r16", "        sei", "        nop",
          "        in r20, 0x24", "        in r21, 0x25", "        subi r20, -%d" % n, "        sbci r21, 0xFF", "        out 0x25, r21", "        out 0x24, r20",
          "        ldi r16, 0", "        out 0x21, r16", "        ldi r16, 0x80",
          "waitl:  out 0x20, r16",
          "resume: lds r18, %d" % cell, "        sts %d, r18" % (cell + 1), "        in r19, 0x06", "        sts %d, r19" % (cell + 2),
          "        lds r16, %d" % cell, "        out 0x1A, r16", "        lds r16, %d" % (cell + 1), "        out 0x1B, r16",
          "        lds r16, %d" % (cell + 2), "        out 0x1C, r16",
          "        ldi r16, 1", "        sts %d, r16" % (cell + 3)]
    if c == 0:
        L += ["w:      lds r16, %d" % (0x78 + 3), "        tst r16", "        breq w", "        out 0x1F, r17"]
    L += ["x:      rjmp x", ISR_D % dict(isrn=cell)]
    return "\n".join(L) + "\n"

def run_b(arb, cdiv, n0, n1):
    h0, s0 = build("b0", prog_b(0, arb, n0)); h1, s1 = build("b1", prog_b(1, arb, n1))
    ex, ev = parse(sim(h0, h1, cdiv))
    return ex, ev, (s0, s1)

def analyse_b(ex, ev, syms, cdiv):
    errs = []; info = {}
    if ex.split()[:2] != ["EXIT", "0"]: errs.append("did not finish: " + ex)
    marks = collections.defaultdict(list)
    for p in ev.get("W", []): marks[int(p[3])].append(int(p[5], 16))
    flags = [(int(p[1]), int(p[3], 16), int(p[4], 16)) for p in ev.get("FLAGS", [])]
    waits = [(int(p[1]), int(p[3], 2)) for p in ev.get("WAIT", [])]
    for c in (0, 1):
        if marks[c] != [1, 1, marks[c][2] if len(marks[c]) > 2 else 0] or len(marks[c]) != 3:
            errs.append("core %d markers (interrupts, interrupts before the first instruction after the wait, IFRL) = %s, expected 1, 1, x" % (c, marks[c]))
        elif not marks[c][2] & 0x80: errs.append("core %d IFRL %02x: DLY flag not set after the wait" % (c, marks[c][2]))
        starts = [(int(p[1]), int(p[4], 16), p[5], p[6]) for p in ev.get("S", []) if p[3] == str(c)]
        cyc_out = next((x for x, pc, t, i in starts if pc == syms[c]["waitl"] and t == "0"), None)
        fl = next((x for x, f0, f1 in flags if ((f0 if c == 0 else f1) & 0x80)), None)
        fr = next(((x, t, i) for x, pc, t, i in starts if pc == syms[c]["resume"]), None)
        if cyc_out is None or fl is None or fr is None: errs.append("core %d: no start at waitl/resume/flag" % c); continue
        # the first start after the flag is the interrupt entry (the instruction at resume is delayed by it)
        first_after = next((x for x, pc, t, i in starts if x > fl and x > cyc_out), None)
        info["d%d" % c] = fl - cyc_out
        if fl > cyc_out + 1 or True:
            info["lat%d" % c] = None
        # waited?
        w = [(x, v) for x, v in waits if x >= cyc_out - 1]
        wb = next((x for x, v in w if v & (1 << c)), None)
        we = next((x for x, v in w if wb is not None and x > wb and not v & (1 << c)), None)
        info["waited%d" % c] = wb is not None
        if wb is not None and we is None: errs.append("core %d waited and never left" % c)
        if wb is not None and we is not None:
            info["lat%d" % c] = we - fl
            if we - fl > cdiv: errs.append("core %d wait ended %d clock cycles after DLY, expected at most %d" % (c, we - fl, cdiv))
            if we < fl - 1: errs.append("core %d wait ended at %d before DLY at %d" % (c, we, fl))
        # an interrupt entry must precede the instruction at resume
        if fr[1] != fr[2]: errs.append("core %d: take %s request %s at resume" % (c, fr[1], fr[2]))
    return errs, info

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdivs", default="1,2,3"); ap.add_argument("--arbs", default="0,1,2")
    ap.add_argument("--modes", default="ev,int,both,ev_int,int_ev"); ap.add_argument("--tests", default="a,b")
    ap.add_argument("--span", type=int, default=6)
    a = ap.parse_args()
    runs = bad = 0
    cover = collections.Counter(); lats = collections.defaultdict(collections.Counter)
    for cdiv in [int(x) for x in a.cdivs.split(",")]:
        if "a" in a.tests:
            for arb in [int(x) for x in a.arbs.split(",")]:
                for mode in a.modes.split(","):
                    # calibration: find p1 for which the first raise falls in the cycle of OUT WAITL (d = 0)
                    pc_ = 0
                    for _ in range(5):
                        ex, ev, s0 = run_a(mode, arb, cdiv, pc_, 1 if mode in ("ev_int", "int_ev") else 0)
                        e, info = analyse_a(mode, ex, ev, s0, cdiv)
                        d0 = info.get("d")
                        if d0 is None or abs(d0) <= cdiv: break
                        pc_ = max(0, pc_ - int(round(d0 / cdiv)))
                    gaps = (0, 1, 2) if mode in ("ev_int", "int_ev") else (0,)
                    for g in gaps:
                        for p1 in range(max(0, pc_ - a.span), pc_ + a.span + 1):
                            ex, ev, s0 = run_a(mode, arb, cdiv, p1, g)
                            e, info = analyse_a(mode, ex, ev, s0, cdiv)
                            runs += 1
                            if "d" in info: cover[(cdiv, "a", mode, max(-4, min(4, info["d"] // cdiv)))] += 1
                            if info.get("waited") and info.get("lat_end") is not None: lats[(cdiv, "a", mode)][info["lat_end"]] += 1
                            if e:
                                bad += 1; print("FAIL a mode %s arb %d cdiv %d p1 %d gap %d (d=%s):" % (mode, arb, cdiv, p1, g, info.get("d"))); [print("   ", x) for x in e[:5]]; sys.stdout.flush()
        if "c" in a.tests:       # SEI directly before OUT WAITL
            for arb in [int(x) for x in a.arbs.split(",")]:
                for mode in ("int", "both", "ev_int"):
                    pc_ = 0
                    for _ in range(5):
                        ex, ev, s0 = run_a(mode, arb, cdiv, pc_, 0, 0, True)
                        e, info = analyse_a(mode, ex, ev, s0, cdiv)
                        d0 = info.get("d")
                        if d0 is None or abs(d0) <= cdiv: break
                        pc_ = max(0, pc_ - int(round(d0 / cdiv)))
                    for p1 in range(max(0, pc_ - a.span), pc_ + a.span + 1):
                        ex, ev, s0 = run_a(mode, arb, cdiv, p1, 0, 0, True)
                        e, info = analyse_a(mode, ex, ev, s0, cdiv)
                        runs += 1
                        if "d" in info: cover[(cdiv, "c", mode, max(-4, min(4, info["d"] // cdiv)))] += 1
                        if e:
                            bad += 1; print("FAIL c(sei before OUT) mode %s arb %d cdiv %d p1 %d (d=%s):" % (mode, arb, cdiv, p1, info.get("d"))); [print("   ", x) for x in e[:5]]; sys.stdout.flush()
        if "b" in a.tests:
            for arb in [int(x) for x in a.arbs.split(",")]:
                # calibrate N: smallest N for which core 0 waits
                for dn in (0, 1, 2):
                    for n in range(8 * cdiv, 26 * cdiv):
                        ex, ev, syms = run_b(arb, cdiv, n, n + dn)
                        e, info = analyse_b(ex, ev, syms, cdiv)
                        runs += 1
                        for c in (0, 1):
                            if "d%d" % c in info: cover[(cdiv, "b", "dly", max(-4, min(4, info["d%d" % c] // cdiv)))] += 1
                            if info.get("lat%d" % c) is not None: lats[(cdiv, "b", "dly")][info["lat%d" % c]] += 1
                        if e:
                            bad += 1; print("FAIL b arb %d cdiv %d N %d/%d:" % (arb, cdiv, n, n + dn)); [print("   ", x) for x in e[:5]]; sys.stdout.flush()
    print("waitirq: %d runs, %d failing" % (runs, bad))
    print("arrival of the flag relative to the OUT WAITL, in core cycles (clipped at +-4), runs per value:")
    for k in sorted(set((c, t, m) for c, t, m, _ in cover)):
        print("  cdiv %d %s %-6s %s" % (k[0], k[1], k[2], " ".join("%+d:%d" % (d, cover[(k[0], k[1], k[2], d)]) for d in range(-4, 5) if cover[(k[0], k[1], k[2], d)])))
    print("wait end after the flag (clock cycles), runs per value:")
    for k in sorted(lats): print("  cdiv %d %s %-6s %s" % (k[0], k[1], k[2], dict(sorted(lats[k].items()))))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
