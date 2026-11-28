#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Host link (rhost): SPI bytes in, bus and control actions out. Directed checks of the model, then random comparison of
RTL and model.  usage: host_test.py [first_seed last_seed]
Environment: RTLDIR, TAG, NODIRECTED, FIRST, COV; LITERAL=1 selects the literal text of the specification for the
refusal rule of inject, execute and step (GAP-H1) and for the data returned by a refused read (finding H1)."""
import os, random, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'model'))
from host import Host
from collections import Counter
RTLDIR = os.environ.get('RTLDIR', os.path.join(ROOT, '..', 'src', 'rsoc8', 'rtl')); TAG = os.environ.get('TAG', 'host')
LIT = os.environ.get('LITERAL', '')       # '1': both, 'hold': refused-read data only, 'inj': inject refusal rule only
if LIT not in ('1', 'inj'): Host.GAP_REST_BUSY = True
# a refused read leaves zero in the following bytes since the RTL fix of draft 0.32 (Host.STALE_HOLD stays False)

class Run:
    def __init__(s): s.m = Host(); s.lines = []; s.exp = []      # exp: list of ('X', miso, acts, state) or ('F', rdata, mbx)
    def env(s, quiet=0, busy=0, fail=0, brk=0, en=0, wait=0, pc0=0, pc1=0):
        s.m.set_env(quiet, busy, fail, brk, en, wait, pc0, pc1)
        s.lines.append([0, quiet, busy, fail, brk, en, wait, pc0, pc1])
    def x(s, data, nbits=None):
        nbits = 8 * len(data) if nbits is None else nbits
        data = list(data) + [0] * (((nbits + 7) // 8) - len(data))
        miso, acts, st = s.m.xact(nbits, data)
        s.lines.append([1, nbits] + data[:28]); s.exp.append(('X', miso, acts, st)); return miso, acts
    def fw(s, addr, re=0, we=0, wd=0, host=0):
        pre = s.m.mb_rxf
        rd = s.m.fw(addr, we, re, wd, host)
        s.lines.append([2, addr, re, we, wd, host]); s.exp.append(('F', rd, pre)); return rd

def build():
    os.makedirs(f'{ROOT}/build', exist_ok=True)
    subprocess.run(['iverilog', '-g2005', '-o', f'{ROOT}/build/tb_{TAG}.vvp', f'{ROOT}/tb/tb_host.v', f'{RTLDIR}/rhost.v'], check=True)

def run_rtl(r, name, ph=4):
    fin, fout = f'{ROOT}/build/{name}.in', f'{ROOT}/build/{name}.out'
    with open(fin, 'w') as f:
        for l in r.lines: f.write(' '.join('%x' % v for v in (l + [0] * 32)[:32]) + '\n')
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_{TAG}.vvp', f'+in={fin}', f'+out={fout}', f'+ph={ph}'], check=True, stdout=subprocess.DEVNULL)
    recs = []; acts = []
    for l in open(fout):
        w = l.split()
        if not w: continue
        if w[0] == 'W': acts.append(('W', int(w[1], 16), int(w[2], 16)))
        elif w[0] == 'R': acts.append(('R', int(w[1], 16)))
        elif w[0] == 'I': acts.append(('I', int(w[1]), int(w[2]), int(w[3], 16) if int(w[1]) != 3 else None))
        elif w[0] == 'B': acts.append(('B', int(w[1])))
        elif w[0] == 'MISO': miso = [int(x, 16) for x in w[1:]]
        elif w[0] == 'ST': recs.append(('X', miso, acts, (int(w[1]), int(w[2], 2), int(w[3]), int(w[4])))); acts = []
        elif w[0] == 'F': recs.append(('F', int(w[1], 16), int(w[2])))
    if len(recs) != len(r.exp): return f'record count rtl {len(recs)} model {len(r.exp)}'
    xi = 0
    for i, (g, e) in enumerate(zip(recs, r.exp)):
        if g[0] == 'X': e = ('X', e[1], e[2], e[3])
        if g != e:
            # find the stimulus line of this record
            idx = [j for j, l in enumerate(r.lines) if l[0] in (1, 2)][i]
            return f'item {i} (line {idx}: {r.lines[idx][:12]}): rtl {g} model {e}'
    return None

def randx(rng, m):
    cmds = [2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 7, 8, 8, 9, 10, 10, 0, 1, 11, 0xFF]
    cmd = rng.choice(cmds)
    reg = rng.choice([0x0C, 0x0D, 0x3F20, 0x3F50, 0x0001, 0x003F, 0x3EFF, 0x3FFF])
    mem = rng.choice([0x0040, 0x0100, 0x083F, 0x4000, 0x47FE, 0x4800, 0x4FFF, 0x1234, 0xFFFF])
    ad = rng.choice([reg, mem, mem, rng.getrandbits(15)])      # bit 15 set: not defined by the specification (GAP-H3), only 0xFFFF is used
    nb = rng.choice([4, 5, 6, 8, 12])
    if cmd == 2: data = [2, ad >> 8, ad & 255] + [rng.getrandbits(8) for _ in range(rng.choice([1, 1, 2, 4, 9]))]
    elif cmd == 3: data = [3, ad >> 8, ad & 255, 0] + [0] * rng.choice([1, 2, 3, 6, 9])
    elif cmd == 4: data = [4, rng.choice([0, 0x80, 0x10, 0x01, 0x02, 0x03, 0x13, 0x90, rng.getrandbits(8)])]
    elif cmd == 5: data = [5, 0, 0, 0, 0] + [0] * rng.choice([0, 0, 2])
    elif cmd in (6, 9): data = [cmd, rng.getrandbits(8), rng.getrandbits(8)]
    elif cmd == 7: data = [7, rng.getrandbits(8)]
    elif cmd == 8: data = [8, 0, 0, 0, 0]
    elif cmd == 10: data = [10]
    else: data = [cmd] + [rng.getrandbits(8) for _ in range(rng.randrange(0, 4))]
    nbits = 8 * len(data)
    if rng.random() < 0.12: nbits = rng.randrange(1, nbits + 1)       # chip select released early, also inside a byte
    return data, nbits

def rand_run(seed, n=120):
    rng = random.Random(seed); r = Run()
    q = 0
    for _ in range(n):
        x = rng.random()
        if x < 0.25:
            q = rng.choice([0, 1, 1]); r.env(quiet=q, busy=int(rng.random() < 0.1), fail=int(rng.random() < 0.05), brk=rng.getrandbits(2), en=rng.choice([3, 3, 1, 2, 0]),
                                             wait=rng.choice([0, 0, 0, 1, 2, 3]), pc0=rng.getrandbits(11), pc1=rng.getrandbits(10))
        elif x < 0.37:
            r.fw(rng.choice([0x0C, 0x0D, 0x0D, 0x0C, 0x20]), re=rng.getrandbits(1), we=rng.getrandbits(1) if False else 0, host=int(rng.random() < 0.1))
            if rng.random() < 0.5: r.fw(0x0D, we=1, wd=rng.getrandbits(8), host=int(rng.random() < 0.1))
        else:
            d, nb = randx(rng, r.m); r.x(d, nb)
    return r

def directed():
    errs = []; r = Run()
    def chk(c, msg):
        if not c: errs.append(msg)
    r.env(quiet=0, en=3)
    # L3, L4: after reset the core reset is set: access allowed; a status command shows it
    miso, a = r.x([5, 0, 0, 0, 0]); chk(miso[2] == 0x80 and miso[3] == 0x43 - 0 * 1 or miso[3] & 0x40, 'status after reset: access allowed, core reset set %r' % miso)
    # write and read back
    r.x([2, 0x01, 0x00, 0xAA, 0xBB]); miso, a = r.x([3, 0x01, 0x00, 0, 0, 0]); chk(miso[4:6] == [0xAA, 0xBB], 'write then read: %r' % miso)
    # control: release reset; with the cores running access is refused with the error bit
    r.x([4, 0x00]); r.env(quiet=0, en=3)
    miso, a = r.x([2, 0x01, 0x00, 0x11]); chk(a == [], 'write refused while a core runs')
    miso, a = r.x([5, 0, 0, 0, 0]); chk(miso[3] & 0x80 == 0x80 and miso[2] == 0x00, 'status: no access allowed, error bit set by the refused write: %r' % miso)
    miso, a = r.x([5, 0, 0, 0, 0]); chk(miso[3] & 0x80 == 0, 'error bit cleared by the previous status command')
    # mailbox
    r.x([7, 0x5A]); chk(r.fw(0x0C, re=1) == 0x80 | 0x40, 'RXF set'); chk(r.fw(0x0D, re=1) == 0x5A, 'MBDATA'); chk(r.fw(0x0C, re=1) == 0x40, 'RXF cleared by the read')
    r.fw(0x0D, we=1, wd=0x77); chk(r.fw(0x0C, re=1) == 0, 'TXE cleared by the write')
    miso, a = r.x([8, 0, 0, 0, 0]); chk(miso[3] == 0x77 and miso[2] == 0x00, 'mailbox read: %r' % miso); chk(r.fw(0x0C, re=1) == 0x40, 'TXE set by clocking the second byte')
    e = run_rtl(r, 'host_dir')
    if e: errs.append('RTL differs from model: ' + e)
    return errs, len(r.lines)

if __name__ == '__main__':
    build()
    errs, n = ([], 0) if os.environ.get('NODIRECTED') else directed()
    print(f'directed: {n} items, {len(errs)} errors'); [print('  ', e) for e in errs]
    lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 100)
    bad = 0; cov = Counter(); cyc = 0
    for seed in range(lo, hi):
        q = rand_run(seed); cyc += len(q.lines); cov.update(q.m.cov)
        e = run_rtl(q, TAG + '_rand')
        if e:
            bad += 1
            if bad <= 3: print('  seed', seed, e[:500])
            if os.environ.get('FIRST'): break
    print(f'random: seeds {lo}..{hi - 1}, {cyc} items, {bad} mismatching')
    if os.environ.get('COV'):
        for k in sorted(cov): print('  cov %-34s %d' % (k, cov[k]))
    sys.exit(1 if errs or bad else 0)
