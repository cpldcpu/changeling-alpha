#!/usr/bin/env python3
"""Receive tolerance of the ping firmware against the Ethernet model: for each clock duty cycle find by bisection the
largest bit time error (ppm, both signs) and the largest edge jitter (ps peak, testbench time scale) at which
+ethm=5 passes. usage: eth_sweep.py <tb.vvp> <image.hex> [duty ...]    (run from the rsys directory)"""
import subprocess, sys
vvp, hexf = sys.argv[1], sys.argv[2]
duties = [int(x) for x in sys.argv[3:]] or [50, 45, 55, 40, 60]
def run(duty, ppm, jit, extra=()):
    a = ['vvp', '-n', vvp, '+hex=' + hexf, '+ethm=5', '+ethboot=6000', '+maxcyc=80000', '+duty=%d' % duty,
         '+ethppm=%d' % ppm, '+ethjit=%d' % jit] + list(extra)
    out = subprocess.run(a, capture_output=True, text=True).stdout
    return 'ETHM PASS' in out
def bisect(f, lo, hi, tol):
    """f(lo) is true; find the largest value up to hi for which f is true"""
    if f(hi): return hi
    while hi - lo > tol:
        mid = (lo + hi) // 2
        if f(mid): lo = mid
        else: hi = mid
    return lo
for d in duties:
    if not run(d, 0, 0):
        print('duty %d%%: fails already without error' % d, flush=True); continue
    pos = bisect(lambda x: run(d, x, 0), 0, 600000, 5000)
    neg = -bisect(lambda x: run(d, -x, 0), 0, 600000, 5000)
    jit = bisect(lambda x: run(d, 0, x), 0, 20000, 500)
    print('duty %d%%: bit time error %+d ppm (%+.1f %%) to %+d ppm (%+.1f %%), edge jitter up to %d ps (%.1f %% of a bit) peak'
          % (d, neg, neg / 1e4, pos, pos / 1e4, jit, jit / 600.0), flush=True)
