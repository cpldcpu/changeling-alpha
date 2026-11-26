#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Random-program lockstep test: RTL trace versus reference model trace."""
import random, subprocess, sys, os

def gen(seed, words, weights=None):
    rnd = random.Random(seed)
    prog = []
    classes = [
        lambda: rnd.randrange(0x0400, 0x3000),                      # two-register ALU, CPSE, MOV
        lambda: rnd.randrange(0x3000, 0x8000),                      # immediate ALU
        lambda: 0xE000 | rnd.randrange(0x1000),                     # LDI
        lambda: 0x8000 | rnd.randrange(2) << 9 | rnd.randrange(16) << 4 | rnd.choice([0, 8]),
        lambda: 0x9000 | rnd.randrange(2) << 9 | rnd.randrange(16) << 4 | rnd.choice([1, 2, 9, 10, 12, 13, 14, 15]),
        lambda: 0x9400 | rnd.randrange(32) << 4 | rnd.choice([0, 1, 2, 3, 5, 6, 7, 10]),
        lambda: 0x9408 | rnd.randrange(16) << 4,                    # BSET/BCLR
        lambda: rnd.choice([0x9508, 0x9518, 0x9409, 0x9509, 0x9598, 0x95A8]),
        lambda: 0x9800 | rnd.randrange(0x400),                      # CBI SBIC SBI SBIS
        lambda: 0xA000 | rnd.randrange(0x1000),                     # LDS STS
        lambda: 0xB000 | rnd.randrange(0x1000),                     # IN OUT
        lambda: 0xB000 | rnd.randrange(2) << 11 | rnd.randrange(16) << 4 | 0x600 | rnd.choice([0xD, 0xF, 0x0]),  # SP, SREG, irq reg... (0x3D,0x3F,0x30)
        lambda: 0xC000 | rnd.randrange(0x2000),                     # RJMP RCALL
        lambda: 0xC000 | rnd.randrange(2) << 12 | (rnd.randrange(-20, 20) & 0xFFF),
        lambda: 0xF000 | rnd.randrange(0x800),                      # BRBS BRBC
        lambda: 0xF800 | rnd.randrange(0x800) & ~8,                 # BLD BST SBRC SBRS
        lambda: rnd.randrange(0x10000),                             # anything
    ]
    weights = weights or [14, 12, 8, 4, 10, 8, 3, 3, 5, 4, 5, 3, 1, 4, 6, 5, 5]
    for _ in range(words):
        w = rnd.choices(classes, weights)[0]() & 0xFFFF
        if (w & 0xFFFF) == 0x9588 or (w & 0xFE0F) == 0x9408 and (w & 0x01F0) == 0x0180:   # SLEEP
            w = 0x0000
        prog.append(w)
    return prog

def main():
    seeds = range(int(sys.argv[1]), int(sys.argv[2]))
    n = int(sys.argv[3])
    has_h = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    vvp = sys.argv[5] if len(sys.argv) > 5 else "build/tb.vvp"
    os.makedirs("build/rand", exist_ok=True)
    bad = 0
    for seed in seeds:
        hexf = "build/rand/p%d.hex" % seed
        open(hexf, "w").write("\n".join("%04x" % w for w in gen(seed, 1024)) + "\n")
        t_rtl, t_mod = "build/rand/rtl.trace", "build/rand/mod.trace"
        subprocess.run(["vvp", "-n", vvp, "+hex=" + hexf, "+trace=" + t_rtl, "+n=%d" % n, "+noexit"],
                       stdout=subprocess.DEVNULL, check=True)
        subprocess.run([sys.executable, "-I", "model/rmodel.py", hexf, t_mod, "-n", str(n),
                        "--has_h", str(has_h), "--cov", "build/rand/cov.txt", "--noexit"], check=True)
        a, b = open(t_rtl).read().splitlines(), open(t_mod).read().splitlines()
        if a != b:
            bad += 1
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    print("seed %d: first difference at boundary %d" % (seed, i))
                    print(" prev:", a[i - 1][:60] if i else "-")
                    print(" rtl :", x[:60]); print(" mod :", y[:60])
                    print(" instr at prev pc: %04x" % int(open(hexf).read().split()[int(a[i-1][:4], 16)], 16) if i else "")
                    break
            else:
                print("seed %d: length differs rtl=%d mod=%d" % (seed, len(a), len(b)))
            if bad >= 5:
                break
    print("seeds %d..%d: %d mismatching" % (seeds[0], seeds[-1], bad))
    return bad

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
