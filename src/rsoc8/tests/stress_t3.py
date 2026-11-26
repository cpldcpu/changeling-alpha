#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Test 3: one core serves UART echo (pair 0, pins 6/7) and an SPI slave (pair 1, pins 0-4) in one loop (fw/fwx_one.c).
For each UART bit time the smallest SPI half period without any loss, at core dividers 1 and 2.
usage: python3 -I tests/stress_t3.py [cdivs] [cpbs]    (cpb 0 = no UART, hp 0 = no SPI)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sx
HPS = [8, 6, 5, 4, 3, 2]
HPS2 = [24, 20, 16, 14, 12, 10, 8]   # for core divider 2 (half speed)
def run(cdiv, cpb, hp, dur=40000, nbs=4, mode=0, plus=(), busy=0):
    tag = 'c%d_%d_%d_%d' % (cdiv, cpb, nbs, busy)
    img = sx.build('fwx_one', 's6_' + tag, 0, '-DCPB=%d -DNBS=%d -DSMODE=%d%s' % (cpb, nbs, mode, (' -DBUSY=%d' % busy) if busy else ''))
    nx = max(4, dur // (450 + 16 * nbs * hp))
    n = min(1000, max(20, dur // (10 * cpb)))
    args = ['+hex=build/%s.hex' % img, '+stress=6', '+cdiv=%d' % cdiv, '+uart', '+ucpb=%d' % cpb, '+sn=%d' % n, '+urx=6', '+utx=7',
            '+spimst', '+spimst_mode=%d' % mode, '+spimst_hp=%d' % hp, '+spimst_n=%d' % nbs, '+spimst_xfers=%d' % nx, '+spimst_idle=300', '+pd=10']
    args += list(plus) + ['+maxcyc=%d' % (dur * 4 * cdiv + 400000)]
    return sx.parse(sx.sim(args, timeout=600))
if __name__ == '__main__':
    cdivs = [int(x) for x in sys.argv[1].split(',')] if len(sys.argv) > 1 else [1, 2]
    cpbs = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [60, 30, 16, 12, 10, 8, 6]
    for c in cdivs:
        for cpb in cpbs:
            last = None
            for hp in (HPS if c == 1 else HPS2):
                d = run(c, cpb, hp)
                print('cdiv %d cpb %d hp %d: %s' % (c, cpb, hp, sx.line(d)), flush=True)
                if d['pass']: last = hp
                else: break
            print('RESULT one core cdiv %d, UART %d cycles per bit: SPI slave smallest bit time without loss %s cycles' % (c, cpb, None if last is None else 2 * last), flush=True)
