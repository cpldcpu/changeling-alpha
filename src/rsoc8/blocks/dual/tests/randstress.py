#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Random two-core stress with more seeds and more collisions (task: arbitration).
Runs randtest_d.py (RTL against the cycle model, every instruction start and the final memories) in several
configurations and reports the number of collisions and held cycles of the model for each.
  BUSW=1   generator with a heavy share of instructions that request the shared bus
  ARB=n    arbiter mode forced (0 alternate, 1 core 0 wins, 2 core 1 wins)
  CDIV=n   core clock enable in one cycle of n
usage: randstress.py first_seed last_seed cycles
"""
import subprocess, sys, os, re
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.join(here, "..")
os.chdir(root)
a, b, cyc = sys.argv[1:4]
COV = "build/rand/cov_d.txt"
def stats():
    t = {"collision": 0, "hold": 0, "steal": 0, "refetch": 0, "irq": 0, "wake": 0, "ld_code_other": 0, "st_code_other": 0, "x_fetch": 0}
    if os.path.exists(COV):
        for l in open(COV):
            for kv in l.split():
                k, v = kv.split("=")
                if k in t: t[k] += int(v)
    return t
configs = [("default generator", {}, None)] + [("BUSW ARB=%d CDIV=%d" % (arb, cd), {"BUSW": "1", "ARB": str(arb), "CDIV": str(cd)}, (arb, cd))
           for cd in (1, 2, 3) for arb in (0, 1, 2)] + [("BUSW random ARB, host halts (HRAND)", {"BUSW": "1", "HRAND": "1"}, None)]
total_bad = 0
for name, env, key in configs:
    n = int(b) - int(a)
    if key and key[1] > 1: n = max(10, n // 3)        # fewer seeds for the divided clock: the cycle model is the same
    if "HRAND" in env: n = max(10, n // 3)
    if os.path.exists(COV): os.remove(COV)
    e = dict(os.environ); e.update(env)
    r = subprocess.run([sys.executable, "tests/randtest_d.py", a, str(int(a) + n), cyc], env=e, capture_output=True, text=True)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
    st = stats()
    ok = r.returncode == 0
    total_bad += 0 if ok else 1
    print("%-40s %s | collisions %d held cycles %d (%.1f per 1000 cycles) steals %d refetches %d interrupt entries %d wake-ups %d"
          % (name, last, st["collision"], st["hold"], 1000.0 * st["hold"] / (n * int(cyc)), st["steal"], st["refetch"], st["irq"], st["wake"]))
    if not ok: print(r.stdout[-1500:])
    sys.stdout.flush()
sys.exit(1 if total_bad else 0)
