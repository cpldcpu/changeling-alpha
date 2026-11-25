#!/usr/bin/env python3
"""Runs the check of exc_top with the SAT solver of Yosys and lists every violated check.

usage: run_exc.py bmc <depth>    bounded check from reset
       run_exc.py ind <n>        induction step: from any state, if no check is violated in n-1 consecutive
                                 cycles, none is violated in the next one
The environment variable YOSYS names the Yosys command (default: yosys). Exit status 1 if a check is violated.
"""
import os, re, subprocess, sys
mode, n = sys.argv[1], int(sys.argv[2]); yosys = os.environ.get("YOSYS", "yosys")
chk = dict((int(l.split("\t")[0]), l.split("\t")[1].strip()) for l in open("exc_checks.txt"))
K = len(chk); mask = 0; found = []; waived = []; rounds = 0; maxr = int(os.environ.get("MAXCEX", "0"))   # MAXCEX: stop after that many counterexamples
PREP = ("read_verilog -formal exc_top.v; read_verilog rdual_comb.v; prep -top exc_top; flatten; async2sync; chformal -lower; "
        "opt -full; opt_clean; ")
if mode == "bmc":
    SAT = "sat -seq %d -prove-asserts -set-assumes -show fail_vec" % n
else:       # the start state is free (initial values removed) except that the reset phase is over (step = 3);
            # the checks are assumed in the first n-1 cycles
    SAT = "setattr -unset init w:*; sat -seq %d -set-at 1 step 3 %s -prove-skip %d -prove-asserts -set-assumes -show fail_vec" % (
        n, " ".join("-set-at %d fail_any 0" % t for t in range(1, n)), n - 1)
while True:
    open("exc_mask.vh", "w").write("localparam [%d:0] MASK = %d'h%x;\n" % (K - 1, K, mask))
    out = subprocess.run([yosys, "-p", PREP + SAT], capture_output=True, text=True).stdout
    if "no model found: SUCCESS" in out: break
    assert "model found: FAIL" in out, out[-3000:]
    rows = re.findall(r"^\s*(\d+) \\fail_vec\s+\S+\s+\S+\s+([01]+)\s*$", out, re.M)
    hit = [(int(t), int(b, 2)) for t, b in rows if int(b, 2)]
    assert hit, "violation not located"
    t, v = hit[-1] if mode == "ind" else hit[0]
    for k in range(K):
        if v >> k & 1:
            if chk[k].startswith("WAIVED "): waived.append(k); print("  waived   (cycle %d): %s" % (t, chk[k][7:]), flush=True)
            else: found.append(k); print("  VIOLATED (cycle %d): %s" % (t, chk[k]), flush=True)
    mask |= v; rounds += 1
    if maxr and rounds >= maxr: print("  stopped after %d counterexamples" % rounds); break
open("exc_mask.vh", "w").write("localparam [%d:0] MASK = %d'd0;\n" % (K - 1, K))
print("  %s %d: %d of %d checks violated, %d waived" % (mode, n, len(found), K, len(waived)))
sys.exit(1 if found else 0)
