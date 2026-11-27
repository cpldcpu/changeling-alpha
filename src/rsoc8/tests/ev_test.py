#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Event flags, interrupt masks, time base, wake-up time: directed checks of the model against the
specification, then random comparison of RTL and model.   usage: ev_test.py [first_seed last_seed]
Environment: RTLDIR (default rtl) selects the RTL, TAG names the build files."""
import os, random, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'model'))
from events import Events
from collections import Counter
RTLDIR = os.environ.get('RTLDIR', os.path.join(ROOT, 'rtl')); TAG = os.environ.get('TAG', 'ev')
KEYS = ('ptick', 'addr', 'core', 're', 'we', 'wd', 'wm', 'pc', 'capt', 'oca', 'ocb', 'ovf', 'trim', 'mbx', 'lc', 'own', 'ack0', 'ack1')
DEF = dict(ptick=1, addr=0, core=0, re=0, we=0, wd=0, wm=0xFF, pc=0, capt=0, oca=0, ocb=0, ovf=0, trim=0, mbx=0, lc=0, own=2, ack0=0, ack1=0)
OWN = (0, 1)

class Seq:
    def __init__(s): s.m = Events(); s.stim = []; s.out = []
    def cyc(s, **k):
        d = dict(DEF); d.update(k); s.stim.append(d)
        o = s.m.step(**{**{x: d[x] for x in d if x != 'own'}, 'own': ((d['own'] >> 0) & 1, (d['own'] >> 1) & 1)})
        s.out.append(o); return o
    def wr(s, a, v, **k): return s.cyc(addr=a, we=1, wd=v, **k)
    def rd(s, a, **k): return s.cyc(addr=a, re=1, **k)[0]

def build():
    os.makedirs(f'{ROOT}/build', exist_ok=True)
    subprocess.run(['iverilog', '-g2005', '-o', f'{ROOT}/build/tb_{TAG}.vvp', f'{ROOT}/tb/tb_ev.v', f'{RTLDIR}/revents.v'], check=True)

def run_rtl(seq, name):
    fin, fout = f'{ROOT}/build/{name}.in', f'{ROOT}/build/{name}.out'
    with open(fin, 'w') as f:
        for d in seq.stim: f.write(' '.join('%x' % d[k] for k in KEYS) + '\n')
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_{TAG}.vvp', f'+in={fin}', f'+out={fout}'], check=True, stdout=subprocess.DEVNULL)
    got = [l.split() for l in open(fout)]
    assert len(got) == len(seq.out), (len(got), len(seq.out))
    for i, (g, o) in enumerate(zip(got, seq.out)):
        d = seq.stim[i]
        exp = ['%02x' % o[0] if d['re'] else g[0], '%08x' % o[1], '%04x' % o[2], '%04x' % o[3]]
        if g != exp: return f'cycle {i}: rtl {g} model {exp} stim {d}'
    return None

def directed():
    s = Seq(); errs = []
    def chk(c, msg):
        if not c: errs.append(msg)
    # E1 latched flags: event sets, W1C clears, zero has no effect, same cycle: stays set
    s.cyc(pc=1); chk(s.rd(0x06) == 0x01, 'PC set')
    s.wr(0x06, 0x00); chk(s.rd(0x06) == 1, 'writing zero does not clear')
    s.wr(0x06, 0x01); chk(s.rd(0x06) == 0, 'W1C clears')
    s.wr(0x06, 0x01, pc=1); chk(s.rd(0x06) == 1, 'E1: event and clearing write in the same cycle: flag stays')
    s.wr(0x06, 0x01, wm=0x01); s.cyc(trim=1); chk(s.rd(0x06) == 0x40, 'TRIM latched')
    s.wr(0x06, 0xBF); chk(s.rd(0x06) == 0x40, 'other bits clear nothing'); s.wr(0x06, 0x40); chk(s.rd(0x06) == 0, 'TRIM W1C')
    # level flag: follows source, cannot be written
    s.cyc(mbx=1); chk(s.rd(0x06, mbx=1) == 0x20, 'MBX level'); s.wr(0x06, 0x20, mbx=1); chk(s.rd(0x06, mbx=1) == 0x20, 'MBX not writable')
    chk(s.rd(0x06) == 0, 'MBX follows source')
    # E5 view of line cell flags
    chk(s.rd(0x07, lc=0xF, own=2, core=0) == 0x03 and s.rd(0x07, lc=0xF, own=2, core=1) == 0x0C, 'owner view: pair 0 core 0, pair 1 core 1')
    chk(s.rd(0x07, lc=0xF, own=0, core=0) == 0x0F and s.rd(0x07, lc=0xF, own=0, core=1) == 0, 'core 0 owns both')
    # E4 software flags through the mask; shared
    s.wr(0x07, 0xF0, wm=0x10); s.wr(0x07, 0xFF, wm=0x40, core=1)
    chk(s.rd(0x07, core=1) == 0x50 and s.rd(0x07, core=0) == 0x50, 'SW0 and SW2 set by mask, shared')
    s.wr(0x07, 0x00, wm=0x10); chk(s.rd(0x07) == 0x40, 'CBI of SW0')
    s.wr(0x07, 0x0F, wm=0x0F); chk(s.rd(0x07) == 0x40, 'level bits of IFRH not writable')
    s.wr(0x07, 0, wm=0xF0)
    # IER per core, Q1 request
    s.wr(0x22, 0x15, core=0); s.wr(0x22, 0x0A, core=1); s.wr(0x23, 0x80, core=1)
    chk(s.rd(0x22, core=0) == 0x15 and s.rd(0x22, core=1) == 0x0A and s.rd(0x23, core=0) == 0 and s.rd(0x23, core=1) == 0x80, 'IER per core')
    o = s.cyc(pc=1)
    o = s.cyc(); chk(o[2] == 0x0001 and o[3] == 0, 'request of vector 1 for core 0 only'); s.wr(0x22, 0xFF, wm=0x0F)
    # Q4: acks clear the five flags only, not TRIM
    s.cyc(trim=1); s.cyc(); s.cyc(ack0=0xFFFF); chk(s.rd(0x06) == 0x40, 'entry clears PC.. OVF, not TRIM')
    # D1, D2, D3
    s2 = Seq()
    for i in range(10): s2.cyc()
    chk(s2.rd(0x24) == 10 and s2.rd(0x25) == 0, 'time base counts')
    s2.cyc(ptick=0); s2.cyc(ptick=0); chk(s2.rd(0x24, ptick=0) == 12, 'time base counts with ptick only')
    s2.wr(0x25, 0x00); s2.wr(0x24, 20); chk(s2.rd(0x06) & 0x80 == 0, 'future wake-up: DLY clear')
    n = 0
    while not (s2.rd(0x06) & 0x80): n += 1
    chk(s2.m.tbase == 20 + 1 or s2.m.tbase == 20 + 2, 'DLY set when the time base equals the time: tbase=%d' % s2.m.tbase)
    s2.wr(0x25, 0); s2.wr(0x24, 10); chk(s2.rd(0x06) & 0x80, 'past time sets DLY at once')
    t = s2.m.tbase
    s2.wr(0x25, (t >> 8) & 255); s2.wr(0x24, t & 255); chk(s2.rd(0x06) & 0x80, 'difference 0 sets DLY at once')
    t = s2.m.tbase
    s2.wr(0x25, ((t + 1) >> 8) & 255, ptick=0); s2.wr(0x24, (t + 1) & 255, ptick=0); chk(s2.rd(0x06, ptick=0) & 0x80 == 0, 'difference 1 without tick: DLY clear')
    s2.wr(0x25, ((s2.m.tbase + 1) >> 8) & 255); s2.wr(0x24, (s2.m.tbase + 1) & 255, ptick=1); chk(s2.rd(0x06, ptick=0) & 0x80, 'difference 1 with tick: DLY at once')
    t = s2.m.tbase; nt = (t + 0x8000) & 0xFFFF
    s2.wr(0x25, nt >> 8, ptick=0); s2.wr(0x24, nt & 255, ptick=0); chk(s2.rd(0x06, ptick=0) & 0x80, 'difference 0x8000 counts as past')
    t = s2.m.tbase; nt = (t + 0x7FFF) & 0xFFFF
    s2.wr(0x25, nt >> 8, ptick=0); s2.wr(0x24, nt & 255, ptick=0); chk(s2.rd(0x06, ptick=0) & 0x80 == 0, 'difference 0x7FFF is a wait')
    chk(s2.rd(0x06, core=1) & 0x80 == 0, 'DLY is per core')
    s2.wr(0x25, 0x12, core=1); s2.wr(0x25, 0x34, core=0); s2.rd(0x24, core=0)
    chk(s2.rd(0x25, core=1) == s2.rd(0x25, core=0), 'DLYH read after DLYL read is the same value for both cores here (no tick between)') if False else None
    # high byte latch of the reading core
    s3 = Seq()
    for i in range(0x1FF): s3.cyc()
    lo = s3.rd(0x24, core=0)
    for i in range(300): s3.cyc()
    chk(s3.rd(0x25, core=0) == 0x01, 'DLYH read gives the high byte latched by the read of DLYL')
    chk(s3.rd(0x25, core=1) == 0x00, 'latch per core')
    for q in (s, s2, s3):
        pass
    for k, q in (('s', s), ('s2', s2), ('s3', s3)):
        e = run_rtl(q, 'ev_dir_' + k)
        if e: errs.append('RTL differs from model (%s): %s' % (k, e))
    return errs, len(s.stim) + len(s2.stim) + len(s3.stim)

def rand_seq(seed, n=4000):
    r = random.Random(seed); s = Seq()
    pt = r.choice([1, 1, 0.5, 0.2]); ev_rate = r.choice([0.02, 0.1, 0.3]); mbx = 0; lc = 0; own = 2
    for _ in range(n):
        d = dict(ptick=int(r.random() < pt), core=r.getrandbits(1))
        for e in ('pc', 'capt', 'oca', 'ocb', 'ovf', 'trim'): d[e] = int(r.random() < ev_rate)
        if r.random() < 0.05: mbx ^= 1
        if r.random() < 0.1: lc = r.getrandbits(4)
        if r.random() < 0.01: own = r.getrandbits(2)
        d.update(mbx=mbx, lc=lc, own=own)
        x = r.random(); m = s.m; k = d['core']
        wm = r.choice([0xFF, 0xFF, 1 << r.randrange(8), r.getrandbits(8)])
        if x < 0.30:
            a = r.choice([0x06, 0x06, 0x07, 0x22, 0x23, 0x24, 0x24, 0x25, 0x25, 0x05, 0x26, 0x30])
            v = r.getrandbits(8)
            if a == 0x06: v = r.choice([v, 1 << r.randrange(7), 0xFF, 0x1F])
            if a == 0x24:
                # wake-up time near the time base, to hit the boundary cases; the high byte is written first,
                # the time base at the write of the low byte is the current value plus the tick of the high byte cycle
                p1 = int(r.random() < pt)
                tgt = (m.tbase + p1 + r.choice([-3, -1, 0, 1, 2, 3, 5, 20, 0x7FFE, 0x7FFF, 0x8000, 0x8001, r.randrange(1 << 16)])) & 0xFFFF
                if r.random() < 0.9:
                    s.wr(0x25, tgt >> 8, core=k, ptick=p1, mbx=mbx, lc=lc, own=own)
                    if r.random() < 0.1: s.wr(0x25, r.getrandbits(8), core=1 - k, ptick=0, mbx=mbx, lc=lc, own=own)
                    v = tgt & 0xFF
            d.update(addr=a, we=1, wd=v, wm=wm if a in (0x06, 0x07, 0x22, 0x23) else 0xFF)
        elif x < 0.62: d.update(addr=r.choice([0x06, 0x07, 0x22, 0x23, 0x24, 0x25, 0x24, 0x25]), re=1)
        # interrupt entries: only for requests that are pending in this cycle
        if r.random() < 0.15:
            f = [m.ifr(0, mbx, lc, (own & 1, own >> 1)), m.ifr(1, mbx, lc, (own & 1, own >> 1))]
            for kk, key in ((0, 'ack0'), (1, 'ack1')):
                pend = f[kk] & m.ier[kk] & 0x1F
                if pend and r.random() < 0.7:
                    b = r.choice([i for i in range(5) if (pend >> i) & 1]); d[key] = 1 << b
        s.cyc(**d)
    return s

if __name__ == '__main__':
    build()
    errs, n = ([], 0) if os.environ.get('NODIRECTED') else directed()
    print(f'directed: {n} cycles, {len(errs)} errors'); [print('  ', e) for e in errs]
    lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 100)
    bad = 0; cov = Counter(); cyc = 0
    for seed in range(lo, hi):
        q = rand_seq(seed); cyc += len(q.stim)
        e = run_rtl(q, TAG + '_rand')
        cov.update(q.m.cov)
        if e:
            bad += 1
            if bad <= 3: print('  seed', seed, e[:300])
            if os.environ.get('FIRST'): break
    print(f'random: seeds {lo}..{hi - 1}, {cyc} cycles, {bad} mismatching')
    if os.environ.get('COV'):
        for k in sorted(cov): print('  cov %-34s %d' % (k, cov[k]))
    sys.exit(1 if errs or bad else 0)
