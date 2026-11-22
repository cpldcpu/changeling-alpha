#!/usr/bin/env python3
"""Tests 1 (b) and 1 (c).
 b: core 0 UART echo (pins 2/3) + core 1 I2C firmware master against the stretching slave model
 c: core 0 SPI slave (master model drives it) + core 1 WS2812 frames
usage: python3 -I tests/stress_t2.py b|c alone|together|base [cdivs] [arbs]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sx
CPBS = [60, 16, 8, 6, 5, 4, 3]
QS   = [60, 30, 15, 8, 4]
HPS  = [8, 7, 6, 5, 4, 3, 2]
STR  = ['+i2cs_str=300', '+i2cs_strp=30']
def run_b(cdiv, arb, cpb=60, q=60, uart=True, i2c=True, dur=100000, plus=()):
    tag = 'c%d_a%d_%d_%d_%s%s' % (cdiv, arb, cpb, q, 'u' if uart else '', 'i' if i2c else '')
    if uart:
        c0 = sx.c0('s2_c0_' + tag, '-DROLE_ECHO -DCPB=%d -DARBV=%d -DRXP=2 -DTXP=3%s' % (cpb, arb, ' -DTWO' if i2c else ''))
    else:
        c0 = sx.c0('s2_c0i_' + tag, '-DROLE_IDLE -DTWO -DARBV=%d' % arb)
    args = ['+hex0=build/%s.hex' % c0, '+stress=2', '+cdiv=%d' % cdiv, '+urx=2', '+utx=3']
    if i2c:
        c1 = sx.c1('s2_c1_' + tag, '-DROLE_I2CM -DI2C_Q=%d' % q)
        args += ['+hex1=build/%s.hex' % c1, '+i2cs'] + STR
    if uart:
        n = min(1000, max(60, int(dur / (10 * cpb))))
        args += ['+uart', '+ucpb=%d' % cpb, '+sn=%d' % n, '+sxrep=%d' % max(1, -(-dur // (n * 10 * cpb)))]
    else:
        args += ['+sxnouart', '+sxtime=%d' % dur]
    args += list(plus) + ['+maxcyc=%d' % (dur * 4 * cdiv + 400000)]
    return sx.parse(sx.sim(args, timeout=600))
def run_c(cdiv, arb, hp=8, ws=True, spi=True, nx=40, nbs=4, plus=()):
    tag = 'c%d_a%d_%d_%s%s' % (cdiv, arb, hp, 's' if spi else '', 'w' if ws else '')
    if spi:
        c0 = sx.c0('s3_c0_' + tag, '-DROLE_SPIS -DARBV=%d -DNBS=%d%s' % (arb, nbs, ' -DTWO' if ws else ''))
    else:
        c0 = sx.c0('s3_c0i_' + tag, '-DROLE_IDLE -DTWO -DARBV=%d' % arb)
    args = ['+hex0=build/%s.hex' % c0, '+stress=3', '+cdiv=%d' % cdiv, '+spimst', '+spimst_mode=0', '+spimst_hp=%d' % hp,
            '+spimst_n=%d' % nbs, '+spimst_xfers=%d' % nx, '+spimst_idle=300', '+pd=10', '+ws']
    if ws:
        c1 = sx.c1('s3_c1_' + tag, '-DROLE_WSC -DNLED=8')
        args += ['+hex1=build/%s.hex' % c1]
    else:
        args += ['+sxnows']
    args += list(plus) + ['+maxcyc=%d' % (nx * 3000 * cdiv + 400000)]
    return sx.parse(sx.sim(args, timeout=600))
def sweep(name, vals, f):
    last = None
    for v in vals:
        d = f(v)
        print('  %s=%s %s' % (name, v, sx.line(d)), flush=True)
        if d['pass']: last = v
        else: break
    return last
if __name__ == '__main__':
    t, what = sys.argv[1], sys.argv[2]
    cdivs = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [1, 2]
    arbs = [int(x) for x in sys.argv[4].split(',')] if len(sys.argv) > 4 else [0, 1, 2]
    if t == 'b':
        if what == 'alone':
            for c in cdivs:
                print('cdiv %d: I2C master alone (stretching slave)' % c)
                q = sweep('q', QS, lambda v: run_b(c, 0, q=v, uart=False))
                print('RESULT b alone cdiv %d: I2C min Q %s (UART alone limit: see test 1a, same firmware)' % (c, q), flush=True)
        elif what == 'base':
            for c in cdivs:
                for a in arbs:
                    print('b base cdiv %d arb %d: %s' % (c, a, sx.line(run_b(c, a))), flush=True)
        else:
            for c in cdivs:
                for a in arbs:
                    print('cdiv %d ARB %d: UART rate limit with I2C at Q 60' % (c, a))
                    u = sweep('cpb', CPBS, lambda v: run_b(c, a, cpb=v))
                    print('cdiv %d ARB %d: I2C rate limit with UART at 1 Mbaud' % (c, a))
                    q = sweep('q', QS, lambda v: run_b(c, a, q=v))
                    print('RESULT b together cdiv %d ARB %d: UART min CPB %s (I2C Q 60), I2C min Q %s (UART 60)' % (c, a, u, q), flush=True)
    else:
        if what == 'alone':
            for c in cdivs:
                print('cdiv %d: SPI slave alone' % c)
                h = sweep('hp', HPS, lambda v: run_c(c, 0, hp=v, ws=False))
                print('RESULT c alone cdiv %d: SPI slave min bit time %s cycles' % (c, None if h is None else 2 * h), flush=True)
        elif what == 'base':
            for c in cdivs:
                for a in arbs:
                    print('c base cdiv %d arb %d: %s' % (c, a, sx.line(run_c(c, a))), flush=True)
        else:
            hpm = {1: int(sys.argv[5]) if len(sys.argv) > 5 else 6, 2: int(sys.argv[6]) if len(sys.argv) > 6 else 8}
            for c in cdivs:
                for a in arbs:
                    print('cdiv %d ARB %d: SPI slave rate limit with WS2812 frames on core 1' % (c, a))
                    h = sweep('hp', HPS, lambda v: run_c(c, a, hp=v))
                    print('RESULT c together cdiv %d ARB %d: SPI slave min bit time %s cycles' % (c, a, None if h is None else 2 * h), flush=True)
