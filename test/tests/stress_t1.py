#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Test 1 (a): core 0 UART echo + core 1 SPI master. Sweeps of the rates with ARB and core divider.
usage: python3 -I tests/stress_t1.py alone|together|base [cdivs] [arbs]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sx
CPBS = [60, 30, 16, 10, 8, 6, 5, 4, 3, 2]
HBS  = [8, 6, 5, 4, 3]
def run(cdiv, arb, cpb=60, hb=8, uart=True, spi=True, extras=False, mode=0, nxg=None, plus=(), sn=None, dur=45000, host=None):
    tag = 'c%d_a%d_%d_%d_%s%s' % (cdiv, arb, cpb, hb, 'u' if uart else '', 's' if spi else '')
    ex = ' -DEXTRAS' if extras else ''
    if uart:
        c0 = sx.c0('s1_c0_' + tag + ('e' if extras else ''), '-DROLE_ECHO -DCPB=%d -DARBV=%d%s%s' % (cpb, arb, ' -DTWO' if spi else '', ex))
    else:
        c0 = sx.c0('s1_c0_idle_' + tag + ('e' if extras else ''), '-DROLE_IDLE -DTWO -DARBV=%d%s' % (arb, ex))
    args = ['+hex0=build/%s.hex' % c0, '+stress=1', '+cdiv=%d' % cdiv]
    if spi:
        c1 = sx.c1('s1_c1_' + tag, '-DROLE_SPIM -DHB=%d -DMODE=%d' % (hb, mode))
        args += ['+hex1=build/%s.hex' % c1, '+spislv', '+spislv_mode=%d' % mode, '+spislv_gapfree']
    if uart:
        n = min(1000, sn or max(60, int(dur / (10 * cpb))))
        args += ['+uart', '+ucpb=%d' % cpb, '+sn=%d' % n]
    else:
        args += ['+sxnouart', '+sxtime=%d' % dur]
    if extras: args += ['+extras']
    args += list(plus)
    args += ['+maxcyc=%d' % (dur * 4 * cdiv + 200000)]
    return sx.parse(sx.sim(args))
def sweep(name, vals, f):
    last = None
    for v in vals:
        d = f(v)
        print('  %s=%s %s' % (name, v, sx.line(d)), flush=True)
        if d['pass']: last = v
        else: break
    return last
if __name__ == '__main__':
    what = sys.argv[1]
    cdivs = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1, 2]
    arbs = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [0, 1, 2]
    if what == 'alone':
        for c in cdivs:
            print('cdiv %d: UART echo alone' % c)
            u = sweep('cpb', CPBS, lambda v: run(c, 0, cpb=v, spi=False))
            print('cdiv %d: SPI master alone' % c)
            s = sweep('hb', HBS, lambda v: run(c, 0, hb=v, uart=False))
            print('RESULT alone cdiv %d: UART min CPB %s, SPI min bit time %s cycles' % (c, u, None if s is None else 2 * s))
    elif what == 'base':
        for c in cdivs:
            for a in arbs:
                d = run(c, a)
                print('base cdiv %d arb %d: %s' % (c, a, sx.line(d)), flush=True)
    elif what == 'together':
        for c in cdivs:
            for a in arbs:
                print('cdiv %d ARB %d: UART rate limit with SPI at 16 cycles per bit' % (c, a))
                u = sweep('cpb', CPBS, lambda v: run(c, a, cpb=v, hb=8))
                print('cdiv %d ARB %d: SPI rate limit with UART at 1 Mbaud' % (c, a))
                s = sweep('hb', HBS, lambda v: run(c, a, cpb=60, hb=v))
                print('RESULT together cdiv %d ARB %d: UART min CPB %s (SPI 16), SPI min bit time %s cycles (UART 60)' % (c, a, u, None if s is None else 2 * s), flush=True)
    elif what == 'limits':          # both protocols at the limit that each reached alone
        lim = {1: (3, 4), 2: (6, 4)}
        for c in cdivs:
            for a in arbs:
                cpb, hb = lim[c]
                d = run(c, a, cpb=cpb, hb=hb)
                print('both at their alone limits: cdiv %d ARB %d cpb %d hb %d: %s' % (c, a, cpb, hb, sx.line(d)), flush=True)
