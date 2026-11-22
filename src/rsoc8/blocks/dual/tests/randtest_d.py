#!/usr/bin/env python3
"""Random-program lockstep test for rdual: RTL trace versus the two-core reference model.
usage: randtest_d.py first_seed last_seed cycles"""
import zlib, random, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from randtest import gen

def ldi(r, k): return 0xE000 | ((k & 0xF0) << 4) | ((r - 16) << 4) | (k & 15)

def image(seed, core):
    rnd = random.Random(seed * 2 + core + 77)
    # BUSW=1: programs rich in instructions that request the shared bus (more collisions and holds); ARB=n forces the arbiter mode
    prog = gen(seed * 2 + core, 1024, [4, 3, 4, 10, 25, 6, 2, 8, 12, 10, 12, 3, 4, 4, 3, 2, 2] if os.environ.get("BUSW") else None)
    for i in range(len(prog)):
        if prog[i] == 0x9598 and rnd.random() < 0.9:                        # BREAK halts a core for good
            prog[i] = 0x0000
        if rnd.random() < 0.05:
            r = rnd.randrange(16) << 4
            prog[i] = rnd.choice([
                0x9588,                                                      # SLEEP
                0xB800 | r | rnd.choice([0x200, 0x201, 0x006, 0x007, 0x00E, 0x005]),   # OUT WAITL/H, events, CORECTL, LOCK
                0xB000 | r | rnd.choice([0x200, 0x201, 0x00E, 0x005]),       # IN
                0x9A00 | 4 << 3 | rnd.randrange(8), 0x9800 | 4 << 3 | rnd.randrange(8),   # SBI/CBI 0x04
                0x9A00 | 5 << 3 | rnd.randrange(4), 0x9800 | 5 << 3 | rnd.randrange(4),   # SBI/CBI LOCK
                0x9B00 | 5 << 3 | rnd.randrange(8), 0x9900 | 5 << 3 | rnd.randrange(8),   # SBIS/SBIC LOCK
                0x9A00 | 6 << 3 | rnd.randrange(8), 0x9800 | 6 << 3 | rnd.randrange(8),   # SBI/CBI events
                0x9A00 | 6 << 3 | rnd.randrange(8), 0x9800 | 6 << 3 | rnd.randrange(8),
                0x9478, 0xB800 | r | 0x600, 0xB800 | r | 0x604,              # SEI, OUT interrupt requests
                ldi(31, rnd.choice([0x40, 0x44, 0x48, 0x4C])),               # Z into a code memory
                ldi(27, rnd.choice([0x40, 0x48, 0x01, 0x3F]))])              # X
    if core == 0:
        arb = rnd.choice([0, 0, 1, 2, 3])
        if os.environ.get("ARB"): arb = int(os.environ["ARB"])
        ctl = rnd.choice([0x03, 0x03, 0x03, 0x01])
        pre = [ldi(16, 0xD8), 0xBF0C, ldi(17, arb), ldi(30, 0x50), ldi(31, 0x3F), 0x8310,   # unlock, ARB
               ldi(16, ctl), 0xB90E,                                                         # CORECTL
               ldi(30, rnd.randrange(256)), ldi(31, rnd.choice([0x40, 0x48, 0x00, 0x3F, 0x07]))]
        prog[:len(pre)] = pre
    return prog

def norm(lines, c0):
    out = []
    for l in lines:
        if l[:1].isdigit():
            c, rest = l.split(" ", 1)
            out.append("%d %s" % (int(c) - c0, rest))
        else:
            out.append(l)
    return out

def compare(hex0, hex1, cycles, pmw, tag="x", cov=None):
    t_rtl, t_mod = "build/rand/rtl_%s.trace" % tag, "build/rand/mod_%s.trace" % tag
    subprocess.run(["vvp", "-n", "build/tbd.vvp", "+hex0=" + hex0, "+hex1=" + hex1, "+trace=" + t_rtl,
                    "+maxcyc=%d" % cycles, "+noexit", "+cdiv=%s" % os.environ.get("CDIV", "1")] + (["+hrand=%d" % (zlib.crc32(hex0.encode()) % 100000 + 1)] if os.environ.get("HRAND") else []) + (["+pmw"] if pmw else []), stdout=subprocess.DEVNULL if not os.environ.get("HRAND") else open("build/host.log", "a"), check=True)
    ra = open(t_rtl).read().splitlines()
    r0 = next((int(l.split()[0]) for l in ra if l[0].isdigit()), 1)
    # the model's first instruction start is in its cycle 1 (cycle 0 is the fetch after reset)
    subprocess.run([sys.executable, "-I", "model/rmodel_d.py", hex0, hex1, t_mod, "--cycles", str(cycles - r0 + 1)]
                   + (["--pmw"] if pmw else []) + (["--cov", cov] if cov else []), check=True)
    return norm(ra, r0), norm(open(t_mod).read().splitlines(), 1)

def main():
    seeds = range(int(sys.argv[1]), int(sys.argv[2]))
    cycles = int(sys.argv[3])
    os.makedirs("build/rand", exist_ok=True)
    bad, events, multi = 0, 0, 0
    for seed in seeds:
        pmw = seed % 2 == 1
        h0, h1 = "build/rand/d%d_0.hex" % seed, "build/rand/d%d_1.hex" % seed
        for h, c in ((h0, 0), (h1, 1)):
            open(h, "w").write("\n".join("%04x" % w for w in image(seed, c)) + "\n")
        a, b = compare(h0, h1, cycles, pmw, cov="build/rand/cov_d.txt")
        n = min(len(a), len(b))
        events += sum(1 for l in a if l[0].isdigit())
        multi += len(set(l.split()[1] for l in a if l[0].isdigit())) > 1
        diff = next((i for i in range(n) if a[i] != b[i]), None)
        if diff is None and len(a) != len(b):
            diff = n
        if diff is not None:
            bad += 1
            i = diff
            print("seed %d: first difference at line %d of %d/%d" % (seed, i, len(a), len(b)))
            for j in range(max(0, i - 4), i): print(" same:", a[j][:78])
            print(" rtl :", a[i][:100] if i < len(a) else "-"); print(" mod :", b[i][:100] if i < len(b) else "-")
            if bad >= 3:
                break
    print("seeds %d..%d: %d mismatching, %d instruction starts compared, %d runs with both cores"
          % (seeds[0], seeds[-1], bad, events, multi))
    return bad

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
