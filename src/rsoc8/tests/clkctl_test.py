#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""rclk_ctl (control part of the clocking block): directed checks of the model against the specification and
random comparison of RTL and model.  usage: clkctl_test.py [first_seed last_seed]
Environment: RTLDIR, TAG, NODIRECTED, FIRST, COV; SKIP=name,name excludes stimulus of known deviations
(bit7 = CLKCTL bit 7, osc = SRC without OSCEN)"""
import os, random, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'model'))
from clkctl import *
from collections import Counter
LITERAL = bool(os.environ.get('LITERAL'))   # LITERAL=1: model and stimulus follow the specification text literally (finds the three deviations)
if not LITERAL: ClkCtl.EARLY_LE = True
RTLDIR = os.environ.get('RTLDIR', os.path.join(ROOT, 'rtl')); TAG = os.environ.get('TAG', 'clkctl')
SKIP = set(filter(None, os.environ.get('SKIP', '').split(',')))
# bit 7 of CLKCTL and the oscillator enable follow the specification since the RTL fix of draft 0.32
KEYS = ('strap', 'addr', 're', 'we', 'wd', 'unlock', 'host', 'tgl_ext', 'tgl_osc', 'open_osc', 'ref_host', 'ref_pin', 'ref_evt', 'smp', 'acc', 'txs', 'ccen', 'hold')
DEF = dict(strap=0, addr=0, re=0, we=0, wd=0, unlock=0, host=0, tgl_ext=0, tgl_osc=0, open_osc=0, ref_host=0, ref_pin=0,
           ref_evt=(0, 0), smp=(0, 0), acc=(0, 0), txs=(0, 0), ccen=(0, 0), hold=0)

def pk(v): return v[0] | v[1] << 1 if isinstance(v, tuple) else v

class Seq:
    def __init__(s): s.m = ClkCtl(); s.stim = []; s.out = []
    def cyc(s, **k):
        d = dict(DEF); d.update(k); s.stim.append(d); o = s.m.step(**d); s.out.append(o); return o
    def wr(s, a, v, **k): return s.cyc(addr=a, we=1, wd=v, **k)
    def rd(s, a, **k): return s.cyc(addr=a, re=1, **k)[0]
    def idle(s, n, **k): return [s.cyc(**k) for _ in range(n)]

def build():
    os.makedirs(f'{ROOT}/build', exist_ok=True)
    subprocess.run(['iverilog', '-g2005', '-o', f'{ROOT}/build/tb_{TAG}.vvp', f'{ROOT}/tb/tb_clkctl.v', f'{RTLDIR}/rclock.v',
                    f'{ROOT}/rtl/rlinecells.v'], check=True)

NAMES = ('rd', 'prot', 'sel', 'osc_en', 'trim', 'cke', 'ptick', 'trim_evt', 'cko_en', 'cko', 'dbg_en', 'dbg')
def run_rtl(seq, name):
    fin, fout = f'{ROOT}/build/{name}.in', f'{ROOT}/build/{name}.out'
    with open(fin, 'w') as f:
        for d in seq.stim: f.write(' '.join('%x' % pk(d[k]) for k in KEYS) + '\n')
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_{TAG}.vvp', f'+in={fin}', f'+out={fout}'], check=True, stdout=subprocess.DEVNULL)
    got = [l.split() for l in open(fout)]
    assert len(got) == len(seq.out), (len(got), len(seq.out))
    for i, (g, o) in enumerate(zip(got, seq.out)):
        exp = ['%02x' % o[0] if seq.stim[i]['re'] else g[0]] + ['%d' % o[1], '%d' % o[2], '%d' % o[3], '%02x' % o[4]] + ['%d' % x for x in o[5:]]
        if g != exp:
            bad = [NAMES[j] for j in range(len(exp)) if g[j] != exp[j]]
            return f'cycle {i}: differ in {bad}: rtl {g} model {exp} stim {({k: v for k, v in seq.stim[i].items() if v and k in ("addr","we","re","wd","unlock","host")})}'
    return None

def rtl_out(seq, name):
    fin, fout = f'{ROOT}/build/{name}.in', f'{ROOT}/build/{name}.out'
    with open(fin, 'w') as f:
        for d in seq.stim: f.write(' '.join('%x' % pk(d[k]) for k in KEYS) + '\n')
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_{TAG}.vvp', f'+in={fin}', f'+out={fout}'], check=True, stdout=subprocess.DEVNULL)
    return [l.split() for l in open(fout)]

def findings():
    """Places where the RTL differs from the literal text of the specification. Each is a short sequence checked on the
    RTL output directly; returns a list of (id, text, ok)."""
    res = []
    # F1: bit 7 of CLKCTL is RELAXEN and reads back as written
    s = Seq(); s.idle(3); s.wr(CLKCTL, 0x80, unlock=1); s.rd(CLKCTL)
    g = rtl_out(s, TAG + '_f1'); res.append(('F1', 'CLKCTL bit 7 (RELAXEN) stores and reads back 80', g[-1][0] == '80', 'reads ' + g[-1][0]))
    # D2: K1 oscillator enable follows the requested source: SRC=1, OSCEN=0
    s = Seq(); s.idle(3); s.wr(CLKCTL, 0x01, unlock=1); s.idle(10)
    g = rtl_out(s, TAG + '_f2'); res.append(('F2', 'K1: SRC=1 with OSCEN=0 enables the oscillator macro (osc_en=1)', g[-1][3] == '1', 'osc_en=' + g[-1][3]))
    # D3: K7 event exactly at target - 64*TRWIN is not "earlier" and is used
    s = Seq(); s.idle(3)
    s.wr(CLKCTL, 0x24, unlock=1)   # LOOP=1? no: REFSEL=2
    s.wr(CLKCTL, 0x20, unlock=1); s.wr(TGTL, 100); s.wr(TGTH, 0); s.wr(TRWIN, 1)
    s.idle(5); s.cyc(ref_evt=(1, 0)); s.idle(35); s.cyc(ref_evt=(1, 0)); s.idle(3); s.wr(TRINT, 0, wd=0) if False else None
    s.rd(TRCNTL); s.rd(CLKSTAT)
    g = rtl_out(s, TAG + '_f3'); res.append(('F3', 'K7: event 36 cycles after the last one with target 100 and window 64 is used (count 36)', g[-2][0] == '24', 'TRCNTL=' + g[-2][0] + ' MDONE ' + str((int(g[-1][0], 16) >> 4) & 1)))
    return res

def directed():
    errs = []; 
    def chk(c, msg):
        if not c: errs.append(msg)
    s = Seq(); N = lambda n, **k: s.idle(n, **k)
    # K4: strap low: external clock, oscillator off; reset values
    s.idle(3, strap=0)
    chk(s.rd(OSCTRIM) == 0x80 and s.rd(CDIV) == 1 and s.rd(TRINT) == 0 and s.rd(CLKCTL) == 0, 'reset values')
    # reserved bits read as zero: CLKCTL bit 7, CLKOUT, DBGSEL
    s.wr(CLKOUT, 0xFF); chk(s.rd(CLKOUT) == 0x87, 'CLKOUT writable bits')
    s.wr(DBGSEL, 0xFF); chk(s.rd(DBGSEL) == 0x8F, 'DBGSEL writable bits')
    # protected registers
    s.wr(CDIV, 5); chk(s.rd(CDIV) == 1, 'CLKCDIV write without unlock ignored'); s.wr(CDIV, 5, unlock=1); chk(s.rd(CDIV) == 5, 'with unlock')
    s.wr(CDIV, 0, host=1); chk(s.rd(CDIV) == 0, 'host writes without unlock'); s.wr(PDIV, 3); chk(s.rd(PDIV) == 3, 'CLKPDIV not protected')
    # K5: dividers
    s.wr(CDIV, 3, unlock=1); s.idle(8); o = s.idle(16)
    chk(sum(x[5] for x in o) == 4 and sum(x[6] for x in o) == 4, 'one enable in 4 cycles for divider values 3: %d %d' % (sum(x[5] for x in o), sum(x[6] for x in o)))
    # K2: presence from toggling inputs; EXTP/OSCRUN
    for i in range(1100): s.cyc(tgl_ext=(i // 5) & 1)
    st = s.rd(CLKSTAT); chk(st & 6 == 4, 'EXTP set and OSCRUN clear: %02x' % st)
    # strap in the status register
    chk(s.rd(CLKSTAT, strap=1) >> 7 == 1, 'STRAP')
    # K3: request for a missing clock stays pending, then switches when it is present
    s.wr(CLKCTL, 0x03, unlock=1); s.idle(2000)
    chk(s.m.sel == 0, 'request for the absent oscillator pending'); 
    for i in range(2200): s.cyc(tgl_ext=(i // 5) & 1, tgl_osc=(i // 3) & 1)
    chk(s.m.sel == 1, 'switch when the oscillator is present')
    # K6: the count stops at 0xFFFF (line reference, interval of 70 000 cycles)
    s2 = Seq(); s2.idle(3); s2.wr(CLKCTL, 0x20, unlock=1); s2.idle(5); s2.cyc(ref_evt=(1, 0)); s2.idle(70000); s2.cyc(ref_evt=(1, 0)); s2.idle(3)
    chk(s2.rd(TRCNTL) == 0xFF and s2.rd(TRCNTH) == 0xFF, 'count stops at 0xFFFF')
    e = run_rtl(s2, 'clkctl_dir2')
    if e: errs.append('RTL differs from model (saturation): ' + e)
    e = run_rtl(s, 'clkctl_dir1')
    if e: errs.append('RTL differs from model: ' + e)
    return errs, len(s.stim) + len(s2.stim)

def rand_case(seed, n=6000):
    r = random.Random(seed); s = Seq(); m = s.m
    strap = r.getrandbits(1)
    # clocks: segments in which each source runs with a period or is stopped
    seg = {'e': [0, 0, 0], 'o': [0, 0, 0]}     # [end cycle, period, phase]
    ref = dict(h=[0, 40], p=[0, 40], ev=[0, 100], extra=0)
    ev_period = r.choice([20, 70, 150, 300]); tgt_hint = ev_period
    lag = r.choice([1, 2, 4]); opq = [0] * 8
    ctr = dict(e=0, o=0); lvl = dict(e=0, o=0)
    wp = r.choice([0.02, 0.05, 0.1])
    for i in range(n):
        d = dict(strap=strap, unlock=int(r.random() < 0.6), host=int(r.random() < 0.04))
        # presence inputs
        for k, key in (('e', 'tgl_ext'), ('o', 'tgl_osc')):
            if i >= seg[k][0]: seg[k] = [i + r.randrange(300, 2500), r.choice([0, 0, 2, 3, 5, 17, 64, 200]), 0]
            p = seg[k][1]
            if p:
                ctr[k] += 1
                if ctr[k] >= p: ctr[k] = 0; lvl[k] ^= 1
            d[key] = lvl[k]
        # the gate follows the selection with a lag
        opq = [m.sel] + opq[:-1]; d['open_osc'] = opq[lag]
        # references
        for k, key in (('h', 'ref_host'), ('p', 'ref_pin')):
            if i >= ref[k][0] and r.random() < 0.002: ref[k] = [i + r.randrange(200, 2000), r.choice([0, 6, 8, 20, 40, 77])]
            ref.setdefault(k + 'c', 0); ref.setdefault(k + 'l', 0)
            if ref[k][1] and i < ref[k][0]:
                ref[k + 'c'] += 1
                if ref[k + 'c'] >= ref[k][1] // 2 + (r.random() < 0.02): ref[k + 'c'] = 0; ref[k + 'l'] ^= 1
            d[key] = ref[k + 'l']
        evs = [0, 0]
        for c in (0, 1):
            if r.random() < 0.3 and False: pass
        ref['t'] = ref.get('t', 0) + 1
        wspan = m.win_r * 64
        if ref['t'] >= ev_period + r.choice([0, 0, 0, 1, -1, 3]) and r.random() < 0.9:
            ref['t'] = 0; evs[m.refcell() if r.random() < 0.8 else 1 - m.refcell()] = 1
        # an extra early event near the window boundary relative to the current count
        elif wspan and r.random() < 0.15 and m.st == 2:
            want = m.tgt - wspan + r.choice([-2, -1, 0, 1, 2])
            if m.cnt == want: evs[m.refcell()] = 1; ref['t'] = ref['t'] if r.random() < 0.5 else 0
        elif r.random() < 0.01: evs[r.getrandbits(1)] = 1
        d['ref_evt'] = tuple(evs)
        for key in ('smp', 'acc', 'txs', 'ccen'): d[key] = (r.getrandbits(1), r.getrandbits(1))
        d['hold'] = r.getrandbits(1)
        # bus
        x = r.random()
        if x < wp:
            a = r.choice([CLKCTL, CLKCTL, OSCTRIM, CDIV, PDIV, TRINT, TRINT, TGTL, TGTH, TRWIN, TRWIN, CLKOUT, DBGSEL, DBGSEL])
            v = r.getrandbits(8)
            if a == CLKCTL:
                v = r.getrandbits(1) | (r.getrandbits(1) << 1) | (int(r.random() < 0.5) << 2) | (r.getrandbits(1) << 3) | (r.choice([0, 1, 2, 2]) << 4) | (r.getrandbits(1) << 6)
                if 'osc' in SKIP and v & 1: v |= 2
                if 'bit7' not in SKIP: v |= r.getrandbits(1) << 7
                if r.random() < 0.3: v = (v & ~3) | (strap and 3 or 0)
            elif a == CDIV: v = r.choice([0, 0, 1, 2, 3, 5, v])
            elif a == PDIV: v = r.choice([0, 0, 1, 2, 4, v])
            elif a == TRINT: v = (r.getrandbits(1) << 7) | r.choice([0, 0, 1, 3, 7, r.getrandbits(7)])
            elif a == TGTL: v = (ev_period + r.choice([-70, -2, -1, 0, 1, 2, 70, 0, 0])) & 0xFF
            elif a == TGTH: v = ((ev_period + r.choice([-70, -2, -1, 0, 1, 2, 70, 0, 0])) >> 8) & 0xFF
            elif a == TRWIN: v = r.choice([0, 0, 1, 1, 2, 4, r.getrandbits(8)])
            elif a == DBGSEL: v = r.choice([0x80 | r.randrange(16), 0x80 | r.randrange(16), v])
            d.update(addr=a, we=1, wd=v)
            if a == TGTL and r.random() < 0.7:
                s.cyc(**d); d.update(addr=TGTH, we=1, wd=(ev_period >> 8) & 0xFF)
        elif x < wp + 0.15:
            d.update(addr=r.choice([CLKSTAT, CLKCTL, OSCTRIM, CDIV, PDIV, TRINT, TRCNTL, TRCNTH, TRCNTL, TRCNTH, TGTL, TGTH, TRWIN, CLKOUT, DBGSEL, 0x00F, 0x121, 0x12B]), re=1)
        s.cyc(**d)
    return s

if __name__ == '__main__':
    build()
    errs, n = ([], 0) if os.environ.get('NODIRECTED') else directed()
    print(f'directed: {n} cycles, {len(errs)} errors'); [print('  ', e) for e in errs]
    if not os.environ.get('NODIRECTED'):
        for fid, text, ok, info in findings(): print('  %s %s: %s (%s)' % (fid, 'ok     ' if ok else 'DEVIATES', text, info))
    lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 100)
    bad = 0; cov = Counter(); cyc = 0
    for seed in range(lo, hi):
        q = rand_case(seed); cyc += len(q.stim); cov.update(q.m.cov)
        e = run_rtl(q, TAG + '_rand')
        if e:
            bad += 1
            if bad <= 3: print('  seed', seed, e[:420])
            if os.environ.get('FIRST'): break
    print(f'random: seeds {lo}..{hi - 1}, {cyc} cycles, {bad} mismatching')
    if os.environ.get('COV'):
        for k in sorted(cov): print('  cov %-40s %d' % (k, cov[k]))
    sys.exit(1 if errs or bad else 0)
