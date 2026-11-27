#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""rdual register side (locks, wait masks, core enable, ARB, bus arbiter) with scripted bus users:
directed checks of the model against the specification, then random comparison of RTL and model.
usage: dual_test.py [first_seed last_seed]    Environment: RTLDIR, TAG, NODIRECTED, FIRST, COV"""
import os, random, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'model'))
from dual import *
from collections import Counter
RTLDIR = os.environ.get('RTLDIR', os.path.join(ROOT, 'rtl')); TAG = os.environ.get('TAG', 'dual')

def enc(op):
    k, a, d, m, u = op
    return (k << 26) | (u << 25) | (a << 16) | (d << 8) | m

def build():
    os.makedirs(f'{ROOT}/build', exist_ok=True)
    subprocess.run(['iverilog', '-g2005', '-o', f'{ROOT}/build/tb_{TAG}.vvp', f'{ROOT}/tb/tb_dual.v', f'{ROOT}/tb/stub_core.v',
                    f'{RTLDIR}/rdual.v'], check=True)

def run_rtl(ops, env, outs, name):
    f0, f1, fin, fout = (f'{ROOT}/build/{name}.{x}' for x in ('ops0', 'ops1', 'in', 'out'))
    for f, o in ((f0, ops[0]), (f1, ops[1])):
        open(f, 'w').write('\n'.join('%08x' % enc(x) for x in o) + '\n')
    with open(fin, 'w') as f:
        for e in env: f.write('%x %x %x %x %x %x %x\n' % (e['cke'], e['evt'][0], e['evt'][1], e['irq'][0], e['irq'][1],
                                                    e['halt'][0] | e['halt'][1] << 1, e['bclr'][0] | e['bclr'][1] << 1))
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_{TAG}.vvp', f'+in={fin}', f'+out={fout}', f'+ops0={f0}', f'+ops1={f1}'],
                   check=True, stdout=subprocess.DEVNULL)
    got = [l.split() for l in open(fout)]
    assert len(got) == len(outs), (len(got), len(outs))
    for i, (g, o) in enumerate(zip(got, outs)):
        exp = ['%d%d' % (o[1], o[0]), str(o[2]), '%d%d' % (o[4], o[3]), '%d%d' % (o[6], o[5]), '%d%d' % (o[8], o[7])]
        if o[9] is not None: exp.append('%02x' % o[9])
        else: exp.append(g[5])
        if g != exp: return f'cycle {i}: rtl {g} model {exp} env {env[i]}'
    return None

E0 = dict(cke=1, evt=(0, 0), irq=(0, 0), halt=(0, 0), bclr=(0, 0))

def run_model(ops, env_fn, n):
    m = Dual(ops); env = []; outs = []
    for i in range(n):
        e = env_fn(m, i); env.append(e)
        outs.append(m.step(e['cke'], e['evt'], e['irq'], e['halt'], e['bclr']))
    return m, env, outs

def W(a, d, m=0xFF, u=0): return (WRITE, a, d, m, u)
def R(a): return (READ, a, 0, 0, 0)

N = (NOP, 0, 0, 0, 0)

def directed():
    errs = []
    def chk(c, msg):
        if not c: errs.append(msg)
    def go(ops, n, envf=lambda m, i: E0, name='x'):
        m, env, outs = run_model(ops, envf, n)
        e = run_rtl(ops, env, outs, 'dual_' + name)
        if e: errs.append('RTL differs from model (%s): %s' % (name, e))
        return [o[9] for o in outs if o[9] is not None], outs
    # A: one core, C5-C8
    v, _ = go([[W(5, 0x05), R(5), W(5, 0x02, 0x02), R(5), W(5, 0, 0x01), R(5), W(5, 0, 0x08), R(5), W(5, 0xF0), R(5)], []], 20, name='lockA')
    chk(v == [0x05, 0x07, 0x06, 0x06, 0x00], 'single core lock sequence %r' % v)
    # B: lock held by core 0 is seen by core 1 in bits 7:4; core 1 can neither take nor release it
    c0 = [W(5, 0x01), W(0x0E, 0x03)] + [N] * 14 + [R(5), W(5, 0, 1), R(5)]
    c1 = [R(5), W(5, 0x01), R(5), W(5, 0, 1), R(5), W(5, 0x02), R(5)]
    v, outs = go([c0, c1], 30, name='lockB')
    print('lockB reads', [hex(x) for x in v])
    chk(v[:3] == [0x10, 0x10, 0x10], 'lock held by the other core: %r' % v)
    # C: wait ends in the cycle after the flag; flag already set: no wait; WAITL read back
    ops0 = [W(0x21, 0x00), W(0x20, 0x04), R(0x0E), R(0x0E), W(0x20, 0x04), R(0x20), W(0x21, 0x80), R(0x21)]
    def envf(m, i): return dict(E0, evt=((0x0004 if 12 <= i < 20 else 0, 0)))
    v, outs = go([ops0, []], 40, envf, 'waitC')
    wt = [o[3] for o in outs]
    chk(wt[12] == 1 and wt[13] == 0, 'wait ends in the cycle after the flag is set: %r' % wt[:16])
    # D: arbitration, both cores read the same register at the same time
    ops = [[W(0x0E, 3)] + [R(5)] * 8, [R(5)] * 8]
    for mode in (0, 1, 2):
        ops0 = [W(0x150, mode, 0xFF, 1)] + ops[0]
        go([ops0, ops[1]], 30, name='arb%d' % mode)
    return errs, 190

def gen_ops(r, c, n):
    ops = []
    for _ in range(n):
        x = r.random()
        if x < 0.20:
            wm = r.choice([0x0F, 0x0F, 1 << r.randrange(4), r.getrandbits(8), 0xFF]); ops.append(W(5, r.getrandbits(8), wm))
        elif x < 0.28: ops.append(R(5))
        elif x < 0.38:
            a = r.choice([0x20, 0x21]); d = r.choice([0, 0, 1 << r.randrange(8), r.getrandbits(8)])
            ops.append(W(a, d, r.choice([0xFF, 0xFF, 0xFF, r.getrandbits(8)])))
        elif x < 0.41: ops.append(R(r.choice([0x20, 0x21])))
        elif x < 0.47: ops.append((SLEEP, 0, 0, 0, 0))
        elif x < 0.50: ops.append((r.choice([SETI, SETI, CLRI]), 0, 0, 0, 0))
        elif x < 0.54: ops.append(R(0x0E))
        elif x < 0.58:
            ops.append(r.choice([W(0x0E, 0x03, 0x03), W(0x0E, 3, 3), W(0x0E, 1 << c, 3), W(0x0E, 1 << c, 3), W(0x0E, 0x02 >> c, 0x03) if r.random() < 0.1 else W(0x0E, 3, 3)]))
        elif x < 0.595:
            b = r.randrange(2); ops.append(W(0x0E, r.choice([0xFF, 0xFF, 0x00 if b != c or r.random() < 0.05 else 0xFF]), 1 << b))
        elif x < 0.61: ops.append(R(0x150))
        elif x < 0.66: ops.append(W(0x150, r.choice([0, 1, 2]), 0xFF, r.getrandbits(1)))
        elif x < 0.675: ops.append((BREAK, 0, 0, 0, 0))
        elif x < 0.72: ops.append(R(r.choice([0x00, 0x06, 0x24, 0x3C])))
        else: ops.append((NOP, 0, 0, 0, 0))
    return ops

def rand_case(seed, n=3000):
    r = random.Random(seed)
    ops = [gen_ops(r, 0, n // 2), gen_ops(r, 1, n // 2)]
    ev = [0, 0]; pe = r.choice([0.02, 0.1, 0.3]); pk = r.choice([1, 1, 0.7, 0.3]); hd = [0, 0]
    def env_fn(m, i):
        for c in (0, 1):
            if r.random() < pe: ev[c] ^= 1 << r.randrange(16)
            if r.random() < 0.02: ev[c] = 0
        irq = tuple((1 << r.randrange(16)) if r.random() < 0.1 else 0 for _ in (0, 1))
        cke = int(r.random() < pk)
        for c in (0, 1):
            if hd[c]: hd[c] -= 1
            elif r.random() < 0.01: hd[c] = r.randrange(1, 4)
        bclr = tuple(int(cke and m.brk[c] and r.random() < 0.2) for c in (0, 1))
        return dict(cke=cke, evt=tuple(ev), irq=irq, halt=(int(hd[0] > 0), int(hd[1] > 0)), bclr=bclr)
    m, env, outs = run_model(ops, env_fn, n)
    return ops, env, outs, m

if __name__ == '__main__':
    build()
    errs, n = ([], 0) if os.environ.get('NODIRECTED') else directed()
    print(f'directed: {n} cycles, {len(errs)} errors'); [print('  ', e) for e in errs]
    lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 100)
    bad = 0; cov = Counter(); cyc = 0
    for seed in range(lo, hi):
        ops, env, outs, m = rand_case(seed); cyc += len(env); cov.update(m.cov)
        e = run_rtl(ops, env, outs, TAG + '_rand')
        if e:
            bad += 1
            if bad <= 3: print('  seed', seed, e[:400])
            if os.environ.get('FIRST'): break
    print(f'random: seeds {lo}..{hi - 1}, {cyc} cycles, {bad} mismatching')
    if os.environ.get('COV'):
        for k in sorted(cov): print('  cov %-40s %d' % (k, cov[k]))
    sys.exit(1 if errs or bad else 0)
