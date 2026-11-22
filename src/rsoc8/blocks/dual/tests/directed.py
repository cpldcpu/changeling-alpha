#!/usr/bin/env python3
"""Directed tests for rdual: RTL against the model, expected memory contents, exact timing."""
import subprocess, sys, os
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "model")); sys.path.insert(0, here)
import rmodel_d as M, randtest_d as T

def build(name):
    subprocess.run(["avr-gcc", "-mmcu=attiny40", "-nostdlib", "-o", "build/%s.elf" % name, "tests/%s.S" % name], check=True)
    subprocess.run(["avr-objcopy", "-O", "binary", "-j", ".text", "build/%s.elf" % name, "build/%s.bin" % name], check=True)
    b = open("build/%s.bin" % name, "rb").read(); b += b"\0" * (len(b) % 2)
    words = [b[i] | b[i + 1] << 8 for i in range(0, len(b), 2)]
    open("build/%s.hex" % name, "w").write("\n".join("%04x" % w for w in words) + "\n")
    return words

def run(n0, n1, cycles, pmw):
    w0, w1 = build(n0), build(n1)
    os.makedirs("build/rand", exist_ok=True)
    a, b = T.compare("build/%s.hex" % n0, "build/%s.hex" % n1, cycles, pmw, tag=n0)
    s = M.System(w0, w1, pmw=pmw)
    for _ in range(cycles): s.cycle()
    return a == b, s, a

ok = True
same, s, tr = run("dual0", "dual1", 700, True)
exp = {0x60: 2, 0x61: 0x99, 0x70: 0x99, 0x71: 0xA5, 0x72: 0x5A, 0x73: 0x3C, 0x74: 0x77, 0x75: 0x77, 0x76: 0x55,
       0x77: 0x03, 0x78: 0x93, 0x79: 0x08, 0x7A: 0x80}
got = {a: s.ram[a] for a in exp}
res = got == exp and s.brk[1] == 1 and s.rom[1][0x81] & 0xFF == 0x3C
print("dual: RTL equals model %s, results %s, wake-ups %d, interrupts %d, steals %d, refetches %d"
      % (same, res, s.cov["wake"], s.cov["irq"], s.cov["steal"], s.cov["refetch"]))
if not res: print("  got", {hex(a): hex(v) for a, v in got.items() if exp[a] != v}, "break", s.brk)
ok &= same and res

same_a, sa, ta = run("exact0a", "exact1", 1500, False)
same_b, sb, tb = run("exact0b", "exact1", 1500, False)
c1a = [l for l in ta if l.split()[1:2] == ["1"]]; c1b = [l for l in tb if l.split()[1:2] == ["1"]]
strip = lambda ls: [" ".join(l.split()[:3]) for l in ls]          # cycle, core, address
exact = strip(c1a) == strip(c1b) and len(c1a) > 400 and sa.brk[1] == 1
print("exact timing: RTL equals model %s/%s, core 1 identical with busy and with waiting core 0: %s "
      "(%d instructions; core 0 held in %d cycles of the busy run, core 1 in 0: %s)"
      % (same_a, same_b, exact, len(c1a), sa.cov["hold"], sb.cov["hold"] == 0))
ok &= same_a and same_b and exact and sa.cov["hold"] > 50
for arb in (0, 1, 2):
    src = open("tests/stress.S").read()
    for c in (0, 1):
        open("tests/stress%d_%d.S" % (c, arb), "w").write(src.replace("@ARB@", str(arb)).replace("@CORE@", str(c)))
    same, s, tr = run("stress0_%d" % arb, "stress1_%d" % arb, 16000, False)
    n = [sum(1 for l in tr if l.split()[1:2] == [str(c)]) for c in (0, 1)]
    done = s.ram[0x90] == 0xA0 and s.ram[0x91] == 0xA1
    print("stress, arbitration mode %d: RTL equals model %s, both loops finished %s, instructions %d + %d, collisions %d"
          % (arb, same, done, n[0], n[1], s.cov["collision"]))
    ok &= same and done and s.cov["collision"] > 300
    for c in (0, 1): os.remove("tests/stress%d_%d.S" % (c, arb))
sys.exit(0 if ok else 1)
