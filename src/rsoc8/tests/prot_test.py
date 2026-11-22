#!/usr/bin/env python3
"""Program protection (rprot): directed checks of the model against the specification, then random comparison of RTL and
model.  usage: prot_test.py [first_seed last_seed]   Environment: RTLDIR, TAG, NODIRECTED, FIRST, COV"""
import os, random, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'model'))
from prot import Prot
from collections import Counter
RTLDIR = os.environ.get('RTLDIR', os.path.join(ROOT, 'rtl')); TAG = os.environ.get('TAG', 'prot')
KEYS = ('addr', 'we', 'wd', 'host', 'unlock', 'a0', 'a1', 'w0', 'w1', 'o0', 'o1', 'ch')
DEF = dict(addr=0, we=0, wd=0, host=0, unlock=0, a0=0, a1=0, w0=0, w1=0, o0=0, o1=0, ch=0)

class Seq:
    def __init__(s): s.m = Prot(); s.stim = []; s.out = []
    def cyc(s, **k):
        d = dict(DEF); d.update(k); s.stim.append(d)
        o = s.m.step(d['addr'], d['we'], d['wd'], d['host'], d['unlock'], (d['a0'], d['a1']), (d['w0'], d['w1']), (d['o0'], d['o1']), d['ch'])
        s.out.append(o); return o
    def wr(s, a, v, **k): return s.cyc(addr=a, we=1, wd=v, **k)
    def rd(s, a, **k): return s.cyc(addr=a, **k)[0]

def build():
    os.makedirs(f'{ROOT}/build', exist_ok=True)
    subprocess.run(['iverilog', '-g2005', '-o', f'{ROOT}/build/tb_{TAG}.vvp', f'{ROOT}/tb/tb_prot.v', f'{RTLDIR}/rhost.v'], check=True)

def run_rtl(seq, name):
    fin, fout = f'{ROOT}/build/{name}.in', f'{ROOT}/build/{name}.out'
    with open(fin, 'w') as f:
        for d in seq.stim: f.write(' '.join('%x' % d[k] for k in KEYS) + '\n')
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_{TAG}.vvp', f'+in={fin}', f'+out={fout}'], check=True, stdout=subprocess.DEVNULL)
    got = [l.split() for l in open(fout)]
    assert len(got) == len(seq.out)
    for i, (g, o) in enumerate(zip(got, seq.out)):
        exp = ['%02x' % o[0], str(o[1]), str(o[2]), str(o[3])]
        if g != exp: return f'cycle {i}: rtl {g} model {exp} stim {seq.stim[i]}'
    return None

def directed():
    errs = []; s = Seq()
    def chk(c, m):
        if not c: errs.append(m)
    chk(s.rd(0x158) == 0 and s.rd(0x159) == 0, 'reset values')
    # no write enable: core writes ignored; with PWE own accepted, other not; XWE other
    o = s.cyc(a0=100, w0=1); chk(o[2] == 0, 'store without PWE ignored')
    s.wr(0x158, 0x01); chk(s.rd(0x158) == 0, 'protected: write without unlock ignored')
    s.wr(0x158, 0x01, unlock=1)
    o = s.cyc(a0=100, w0=1); chk(o[2] == 1, 'PWE: own memory'); o = s.cyc(a0=100, w0=1, o0=1); chk(o[2] == 0, 'PWE does not allow the other core')
    s.wr(0x158, 0x02, unlock=1); o = s.cyc(a1=7, w1=1, o1=1); chk(o[3] == 1, 'XWE: other core'); o = s.cyc(a1=7, w1=1); chk(o[3] == 0, 'XWE does not allow own')
    s.wr(0x158, 0x03, host=1); s.wr(0x159, 10, host=1)
    chk(s.cyc(a0=39, w0=1)[2] == 0 and s.cyc(a0=40, w0=1)[2] == 1, 'PMLIM: below 4*10 words ignored, 40 accepted')
    chk(s.cyc(a1=3, w1=1)[3] == 0 and s.cyc(a1=1023, w1=1)[3] == 1, 'PMLIM in memory 1')
    s.wr(0x158, 0x83, unlock=1); chk(s.rd(0x158) == 0x83, 'LOCK set')
    chk(s.cyc(a0=500, w0=1)[2] == 0, 'LOCK: no program write'); chk(s.cyc(a0=5, w0=1, ch=1)[2] == 1, 'host write unaffected by lock and limit')
    s.wr(0x158, 0x03, unlock=1); chk(s.rd(0x158) == 0x83, 'LOCK cannot be cleared')
    e = run_rtl(s, 'prot_dir')
    if e: errs.append('RTL differs from model: ' + e)
    return errs, len(s.stim)

def rand_seq(seed, n=3000):
    r = random.Random(seed); s = Seq(); m = s.m
    for _ in range(n):
        d = dict(unlock=int(r.random() < 0.5), host=int(r.random() < 0.1), ch=int(r.random() < 0.08))
        d['addr'] = r.choice([0x158, 0x158, 0x159, 0x159, 0x150, 0x157, 0x15A, 0x058, 0x000])
        if r.random() < 0.25:
            v = r.getrandbits(8)
            if d['addr'] == 0x158: v = r.choice([0, 1, 2, 3, 0x80, 0x81, 0x83, 0x03, v]) if r.random() < 0.9 else v
            if d['addr'] == 0x159: v = r.choice([0, 1, 5, 20, 255, 255, v])
            if d['addr'] == 0x158 and (v & 0x80) and r.random() < 0.985: v &= 0x7F       # keep the lock rare so that the other cases occur
            d.update(we=1, wd=v)
        lim4 = m.lim * 4
        for k in (0, 1):
            d['a%d' % k] = r.choice([lim4, lim4 - 1, lim4 + 1, max(0, lim4 - 4), r.randrange(1024), 0, 1023]) & 0x3FF
            d['w%d' % k] = int(r.random() < 0.5); d['o%d' % k] = r.getrandbits(1)
        s.cyc(**d)
    return s

if __name__ == '__main__':
    build()
    errs, n = ([], 0) if os.environ.get('NODIRECTED') else directed()
    print(f'directed: {n} cycles, {len(errs)} errors'); [print('  ', e) for e in errs]
    lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 100)
    bad = 0; cov = Counter(); cyc = 0
    for seed in range(lo, hi):
        q = rand_seq(seed); cyc += len(q.stim); cov.update(q.m.cov)
        e = run_rtl(q, TAG + '_rand')
        if e:
            bad += 1
            if bad <= 3: print('  seed', seed, e[:300])
            if os.environ.get('FIRST'): break
    print(f'random: seeds {lo}..{hi - 1}, {cyc} cycles, {bad} mismatching')
    if os.environ.get('COV'):
        for k in sorted(cov): print('  cov %-44s %d' % (k, cov[k]))
    sys.exit(1 if errs or bad else 0)
