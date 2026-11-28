#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Faults in the re-read of the code memory after a host access (rule L6), checked with the random
test with host stimulus. Run from the package directory after tests/run_all.sh."""
import os, subprocess

MUTS = [
    ("    wire       hhold = h_acc | (|dirty);", "    wire       hhold = h_acc;"),
    ("dirty <= (dirty & ~rest) | {h_cm1, h_cm0};", "dirty <= 2'b00;"),
    ("assign cm1_addr   = h_cm1 ? h_addr[10:1] : rest[1] ? lastr1 : ca1;", "assign cm1_addr   = h_cm1 ? h_addr[10:1] : ca1;"),
    ("            if (cr0 & ~hhold) lastr0 <= ca0;", "            if (cr0 & ~hhold) lastr0 <= 10'd0;"),
    ("i_delay <= inj ? (i_delay | set_i_ins) : set_i_ins;", "i_delay <= set_i_ins;"),
]
srcs = {f: open(f).read() for f in ('../../../src/rsoc8/rtl/rdual.v', '../../../src/rsoc8/rtl/rcore8d.v')}
env = dict(os.environ, HRAND='1')
det = 0
for a, b in MUTS:
    f = next(k for k, v in srcs.items() if v.count(a) == 1)
    open('build/mut.v', 'w').write(srcs[f].replace(a, b))
    other = [k for k in srcs if k != f][0]
    subprocess.run(['iverilog', '-g2005', '-DSIM', '-o', 'build/tbd.vvp', 'tb/tb_dual.v', 'build/mut.v', other], check=True)
    out = subprocess.run(['python3', 'tests/randtest_d.py', '0', '40', '4000'], capture_output=True, text=True, env=env).stdout
    last = out.strip().splitlines()[-1]
    ok = ' 0 mismatching' not in last
    det += ok
    print('detected' if ok else 'NOT DETECTED', '|', a.strip()[:60])
subprocess.run(['iverilog', '-g2005', '-DSIM', '-o', 'build/tbd.vvp', 'tb/tb_dual.v', '../../../src/rsoc8/rtl/rdual.v', '../../../src/rsoc8/rtl/rcore8d.v'], check=True)
print('faults detected', det, 'of', len(MUTS))
