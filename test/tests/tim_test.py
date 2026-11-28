#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Tests of the timer, PWM and CRC unit: known answers on the model, then model against RTL."""
import os, random, subprocess, sys, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'model'))
from timers import Timers
ROOT = os.path.join(os.path.dirname(__file__), '..')
RTLDIR = os.environ.get('RTLDIR', os.path.join(ROOT, '..', 'src', 'rsoc8', 'rtl'))
KEYS = ('ptick', 'addr', 'core', 'host', 're', 'we', 'wd', 'pins', 'acc', 'ref', 'rxs', 'rxb', 'txs', 'txb', 'rxf')
DEF = dict(ptick=1, addr=0, core=0, host=0, re=0, we=0, wd=0, pins=0xFF, acc=0, ref=0, rxs=0, rxb=0, txs=0, txb=0, rxf=0)

class Seq:
    """Stimulus sequence, applied to the model while it is built."""
    def __init__(s): s.m = Timers(); s.stim = []; s.out = []
    def cyc(s, **k):
        d = dict(DEF); d.update(k); s.stim.append(d); o = s.m.step(**d); s.out.append(o); return o
    def wr(s, a, v, **k): return s.cyc(addr=a, we=1, wd=v, **k)
    def rd(s, a, **k): return s.cyc(addr=a, re=1, **k)[0]
    def idle(s, n, **k):
        r = []
        for _ in range(n): r.append(s.cyc(**k))
        return r
    def rd16(s, a, **k): lo = s.rd(a, **k); return lo | (s.rd(a + 1, **k) << 8)
    def crcval(s, **k): return sum(s.rd(0x146 + i, **k) << (8 * i) for i in range(4))
    def crcset(s, poly, init, ln, right, src=0, owner=0, **k):
        s.wr(0x140, owner, **k)
        s.wr(0x141, ln, **k)
        for i in range(4): s.wr(0x142 + i, (poly >> (8 * i)) & 255, **k); s.wr(0x146 + i, (init >> (8 * i)) & 255, **k)
        s.wr(0x140, 0x80 | (right << 6) | (src << 3) | owner, **k)
    def setref(s, v, **k):
        for i in range(4): s.wr(0x14A + i, (v >> (8 * i)) & 255, **k)
    def feed(s, data, gap=4, **k):
        for b in data: s.wr(0x2A, b, **k); s.idle(gap, **k)

def run_rtl(seq, name):
    fin, fout = f'{ROOT}/build/{name}.in', f'{ROOT}/build/{name}.out'
    with open(fin, 'w') as f:
        for d in seq.stim: f.write(' '.join('%x' % d[k] for k in KEYS) + '\n')
    subprocess.run(['vvp', '-n', f'{ROOT}/build/tb_tim.vvp', f'+in={fin}', f'+out={fout}'], check=True, stdout=subprocess.DEVNULL)
    got = [l.split() for l in open(fout)]
    assert len(got) == len(seq.out), (len(got), len(seq.out))
    for i, (g, o) in enumerate(zip(got, seq.out)):
        exp = ['%02x' % o[0], str(o[1]), str(o[2]), str(o[3]), str(o[4]), format(o[5], '03b'), format(o[6], '03b')]
        if g != exp: return f'cycle {i}: rtl {g} model {exp} stim {seq.stim[i]}'
    return None

def crc_ref(data, width, poly, init, refl):
    """Bitwise reference, independent of the model."""
    v = init
    for b in data:
        for i in range(8):
            if refl:
                bit = (b >> i) & 1; fb = (v & 1) ^ bit; v >>= 1
                if fb: v ^= poly
            else:
                bit = (b >> (7 - i)) & 1; fb = ((v >> (width - 1)) & 1) ^ bit; v = (v << 1) & ((1 << width) - 1)
                if fb: v ^= poly
    return v

def directed():
    s = Seq(); errs = []
    def chk(c, msg):
        if not c: errs.append(msg)
    msg = b'123456789'
    # ---- CRC known answers (catalogue check values)
    s.crcset(0xEDB88320, 0xFFFFFFFF, 31, 1); s.feed(msg)
    chk(s.crcval() ^ 0xFFFFFFFF == 0xCBF43926 == zlib.crc32(msg), 'CRC-32')
    s.wr(0x140, 0); s.crcset(0xA001, 0xFFFF, 15, 1); s.feed(msg)
    chk((s.crcval() ^ 0xFFFF) & 0xFFFF == 0xB4C8, 'CRC-16/USB')
    s.wr(0x140, 0); s.crcset(0x1021, 0xFFFF, 15, 0); s.feed(msg)
    chk(s.crcval() & 0xFFFF == 0x29B1, 'CRC-16/CCITT-FALSE, left shift')
    s.wr(0x140, 0); s.crcset(0x8C, 0, 7, 1); s.feed(msg)
    chk(s.crcval() & 0xFF == 0xA1, 'CRC-8/MAXIM (1-Wire)')
    s.wr(0x140, 0); s.crcset(0x4599, 0, 14, 0); s.feed(msg)
    chk(s.crcval() & 0x7FFF == 0x059E, 'CRC-15/CAN')
    s.wr(0x140, 0); s.crcset(0x04C11DB7, 0xFFFFFFFF, 31, 0); s.feed(msg)
    chk(s.crcval() == 0x0376E6E7, 'CRC-32/MPEG-2, left shift')
    s.wr(0x140, 0); s.crcset(0x14, 0x1F, 4, 1); s.feed(msg)
    chk((s.crcval() ^ 0x1F) & 0x1F == 0x19, 'CRC-5/USB')
    # ---- USB token: 11 bits from receive cell 0, then the 5 CRC bits give the residual 0x06 (reflected 0x0C)
    s.wr(0x140, 0); s.crcset(0x14, 0x1F, 4, 1, src=1)
    bits = [(0x15 >> i) & 1 for i in range(7)] + [(0xE >> i) & 1 for i in range(4)]
    v = 0x1F
    for b in bits:
        fb = (v & 1) ^ b; v >>= 1
        if fb: v ^= 0x14
    for b in bits: s.cyc(rxs=1, rxb=b); s.cyc(rxs=2, rxb=1); s.cyc(txs=3, txb=3)
    chk(s.crcval() & 0x1F == v, 'CRC5 from receive cell 0')
    for i in range(5): s.cyc(rxs=1, rxb=((v ^ 0x1F) >> i) & 1)
    chk(s.crcval() & 0x1F == 0x06, 'CRC5 residual %02x' % (s.crcval() & 0x1F))
    for src, kw in ((2, 'tx0'), (3, 'rx1'), (4, 'tx1')):
        s.wr(0x140, 0); s.crcset(0xEDB88320, 0xFFFFFFFF, 31, 1, src=src)
        for b in msg:
            for i in range(8):
                bit = (b >> i) & 1
                s.cyc(**{'tx0': dict(txs=1, txb=bit, rxs=3, rxb=3), 'rx1': dict(rxs=2, rxb=bit << 1, txs=3),
                         'tx1': dict(txs=2, txb=bit << 1, rxs=3)}[kw])
        chk(s.crcval() ^ 0xFFFFFFFF == 0xCBF43926, 'CRC-32 from ' + kw)
    # ---- reference value: EQ is the comparison now, EQF the comparison at the last frame boundary
    fcs = zlib.crc32(msg)
    frame = msg + bytes([(fcs >> (8 * i)) & 0xFF for i in range(4)])
    s.wr(0x140, 0); s.setref(0xDEBB20E3); s.crcset(0xEDB88320, 0xFFFFFFFF, 31, 1); s.feed(frame)
    chk(s.rd(0x2A) == 0xC0, 'CRC-32 residual 0xDEBB20E3 after a frame with its check sequence: EQ and EQF')
    s.wr(0x140, 0); s.crcset(0xEDB88320, 0xFFFFFFFF, 31, 1); s.feed(frame[:3] + b'\x00' + frame[4:])
    chk(s.rd(0x2A) == 0x00, 'frame with a wrong byte: neither EQ nor EQF')
    # the same from receive cell 1, with three more bits after the last byte: EQF stays, EQ does not
    s.wr(0x140, 0); s.crcset(0xEDB88320, 0xFFFFFFFF, 31, 1, src=3)
    for b in frame:
        for i in range(8): s.cyc(rxs=2, rxb=((b >> i) & 1) << 1, rxf=2 if i == 7 else 0); s.cyc(rxs=1, rxb=1, rxf=1)
    chk(s.rd(0x2A) == 0xC0, 'frame from receive cell 1: EQ and EQF')
    for i in range(3): s.cyc(rxs=2, rxb=0); s.cyc()
    chk(s.rd(0x2A) == 0x80, 'bits behind the last frame boundary: EQF stays set, EQ is cleared')
    # USB CRC-16 residual 0xB001, CAN CRC-15 residual 0 with left shift (bits above the width are ignored)
    c16 = crc_ref(msg, 16, 0xA001, 0xFFFF, True) ^ 0xFFFF
    s.wr(0x140, 0); s.setref(0xB001); s.crcset(0xA001, 0xFFFF, 15, 1); s.feed(msg + bytes([c16 & 255, c16 >> 8]))
    chk(s.rd(0x2A) == 0xC0, 'CRC-16 residual 0xB001')
    c15 = crc_ref(msg, 15, 0x4599, 0, False)
    s.wr(0x140, 0); s.setref(0); s.crcset(0x4599, 0, 14, 0); s.feed(msg)
    for i in range(14, -1, -1): s.cyc(); 
    s.wr(0x140, 0); s.crcset(0x4599, 0, 14, 0, src=1)
    bits = [(b >> (7 - i)) & 1 for b in msg for i in range(8)] + [(c15 >> i) & 1 for i in range(14, -1, -1)]
    for k, b in enumerate(bits): s.cyc(rxs=1, rxb=b, rxf=int(k == len(bits) - 1))
    s.cyc()
    chk(s.rd(0x2A) == 0xC0, 'CRC-15 of CAN: residual 0 in the low 15 bits')
    chk(s.crcval() >> 15 != 0, 'CRC-15: bits above the width are not zero, as assumed by this check')
    chk(s.rd(0x2A, core=1) == 0, 'status is zero for the core that does not own the unit')
    s.wr(0x140, 0); s.crcset(0xEDB88320, 0x12345678, 31, 1)
    # ---- owner: core 1 reads zero and cannot write; either core can claim the disabled unit
    v0 = s.crcval()
    chk(s.crcval(core=1) == 0 and s.rd(0x140, core=1) == 0, 'non-owner reads zero')
    s.wr(0x146, 0x55, core=1); s.wr(0x140, 0x81, core=1); s.wr(0x2A, 1, core=1); s.idle(5)
    chk(s.crcval() == v0, 'non-owner cannot write')
    chk(s.crcval(core=1, host=1) == v0, 'host reads without owner check')
    s.wr(0x140, 0x00); s.wr(0x140, 0x81, core=1)
    chk(s.rd(0x140, core=1) == 0x81 and s.rd(0x140) == 0, 'claim by core 1')
    s.wr(0x140, 0x01, core=1)
    # ---- busy flag and timing of CRCIN
    s.crcset(0xEDB88320, 0, 31, 1); s.wr(0x2A, 0xA5)
    b = [s.rd(0x140) & 2 for _ in range(5)]
    chk(b == [2, 2, 2, 2, 0], 'BUSY for four cycles: %r' % b)
    chk(s.crcval() == crc_ref(b'\xA5', 32, 0xEDB88320, 0, True), 'value after four cycles')
    # ---- disabling the unit stops the steps of a byte in progress
    s.wr(0x140, 0); s.crcset(0xEDB88320, 0, 31, 1); s.wr(0x2A, 0xFF); s.wr(0x140, 0x40); s.idle(6)
    v = 0
    for _ in range(2): v = (v >> 1) ^ (0xEDB88320 if (v ^ 1) & 1 else 0)
    chk(s.crcval() == v, 'steps stop when EN is cleared')
    s.wr(0x140, 0)
    # ---- timer: free running, prescaler, compare, overflow
    s.wr(0x132, 0x10); s.wr(0x133, 0x00); s.wr(0x134, 0x05); s.wr(0x135, 0x00)
    s.wr(0x130, 0x80)
    o = s.idle(40)
    chk([i for i, x in enumerate(o) if x[2]] == [15] and [i for i, x in enumerate(o) if x[3]] == [4], 'compare A at count 16, B at 5')
    chk(s.rd16(0x26) == 40, 'count after 40 cycles'); s.rd(0x27)
    s.wr(0x130, 0x00); s.wr(0x27, 0xFF); s.wr(0x26, 0xFC); s.wr(0x130, 0x82)
    o = s.idle(24)
    chk([i for i, x in enumerate(o) if x[4]] == [15], 'overflow after 4 steps of 4 cycles: %r' % [i for i, x in enumerate(o) if x[4]])
    # ---- CTC: period OCRA + 1
    s.wr(0x130, 0x00); s.wr(0x27, 0); s.wr(0x26, 0); s.wr(0x132, 9); s.wr(0x130, 0xC0)
    o = s.idle(50); t = [i for i, x in enumerate(o) if x[2]]
    chk(all(b - a == 10 for a, b in zip(t, t[1:])) and len(t) == 5 and not any(x[4] for x in o), 'CTC period 10: %r' % t)
    # ---- CTC with OCRA = 0xFFFF: the count is cleared, no overflow event
    s.wr(0x130, 0x00); s.wr(0x132, 0xFF); s.wr(0x133, 0xFF); s.wr(0x27, 0xFF); s.wr(0x26, 0xFD); s.wr(0x130, 0xC0)
    o = s.idle(8); chk(not any(x[4] for x in o) and sum(x[2] for x in o) == 1 and s.rd16(0x26) == 5, 'CTC at 0xFFFF')
    s.wr(0x132, 9); s.wr(0x133, 0)
    # ---- ptick: counts only in peripheral clock cycles
    s.wr(0x130, 0x00); s.wr(0x27, 0); s.wr(0x26, 0); s.wr(0x130, 0x80)
    for i in range(30): s.cyc(ptick=int(i % 3 == 0))
    chk(s.rd16(0x26) == 10, 'peripheral clock enable')
    # ---- capture: pin edge, falling edge, cell events, not while stopped
    s.wr(0x130, 0x00); s.wr(0x27, 0); s.wr(0x26, 0); s.wr(0x131, 0x03)
    s.idle(3, pins=0xF7); s.wr(0x130, 0x80, pins=0xF7); s.idle(6, pins=0xF7)
    o = s.idle(1, pins=0xFF); c = s.rd16(0x28)
    chk(o[0][1] == 1 and c == 6, 'capture on rising edge of pin 3: %d' % c)
    s.wr(0x131, 0x83); s.idle(2); o = s.idle(1, pins=0xF7)
    chk(o[0][1] == 1, 'capture on falling edge')
    s.wr(0x131, 0x21); o = s.idle(1, acc=1) + s.idle(1, acc=2) + s.idle(1, ref=2)
    chk([x[1] for x in o] == [0, 1, 0], 'capture on accepted edge of receive cell 1')
    s.wr(0x131, 0x40); o = s.idle(1, ref=1) + s.idle(1, ref=2) + s.idle(1, acc=1)
    chk([x[1] for x in o] == [1, 0, 0], 'capture on reference event of receive cell 0')
    s.wr(0x130, 0x00); o = s.idle(1, ref=1); chk(o[0][1] == 0, 'no capture while stopped')
    # ---- high byte latches per core
    s.wr(0x27, 0x12, core=0); s.wr(0x27, 0x34, core=1); s.wr(0x26, 0x56, core=0)
    chk(s.rd(0x26, core=1) == 0x56 and s.rd(0x26, core=0) == 0x56, 'low byte')
    s.wr(0x27, 0x77, core=1); s.wr(0x26, 0x01, core=1); s.rd(0x26, core=1)
    chk(s.rd(0x27, core=0) == 0x12 and s.rd(0x27, core=1) == 0x77, 'high byte latch per core')
    # ---- PWM: period TOP + 1, duty, update at the restart only
    s.wr(0x139, 9); s.wr(0x13A, 3); s.wr(0x13B, 0); s.wr(0x13C, 200); s.wr(0x138, 0x07)
    o = s.idle(40)
    chk(sum(x[6] & 1 for x in o) == 12 and sum((x[6] >> 1) & 1 for x in o) == 0 and sum((x[6] >> 2) & 1 for x in o) == 40, 'PWM duty')
    hi = [i for i, x in enumerate(o) if x[6] & 1]
    chk(hi == [0, 1, 2, 10, 11, 12, 20, 21, 22, 30, 31, 32], 'PWM period 10: %r' % hi)
    s.idle(3); s.wr(0x13A, 7); o = s.idle(20); hi = [x[6] & 1 for x in o]
    k = hi.index(1)
    chk(k >= 3 and hi[k:k + 10] == [1] * 7 + [0] * 3, 'new duty takes effect at the restart: %r' % hi)
    s.wr(0x138, 0x15); o = s.idle(40)
    chk(all(x[5] == 5 for x in o) and sum(x[6] & 1 for x in o) == 28, 'PWM prescaler 2')
    s.wr(0x138, 0); o = s.idle(2); chk(o[1][5] == 0 and o[1][6] == 0, 'PWM off')
    e = run_rtl(s, 'tim_dir')
    if e: errs.append('RTL differs from model: ' + e)
    return errs, len(s.stim)

def rand_seq(seed, n=3000):
    r = random.Random(seed); s = Seq()
    regs = [0x130, 0x131, 0x132, 0x133, 0x134, 0x135, 0x138, 0x139, 0x13A, 0x13B, 0x13C, 0x140, 0x141, 0x142, 0x143,
            0x144, 0x145, 0x146, 0x147, 0x148, 0x149, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x136, 0x14A, 0x14B, 0x14C, 0x14D, 0x14E, 0x25]
    pt = r.choice([1, 1, 0.5, 0.25]); pins = 0xFF
    for _ in range(n):
        d = dict(ptick=int(r.random() < pt), core=r.getrandbits(1), host=int(r.random() < 0.05))
        if r.random() < 0.1: pins ^= 1 << r.randrange(8)
        d['pins'] = pins
        d.update(acc=r.choice([0, 0, 0, 1, 2, 3]), ref=r.choice([0, 0, 0, 1, 2, 3]), rxs=r.choice([0, 0, 1, 2, 3]),
                 rxb=r.getrandbits(2), txs=r.choice([0, 0, 1, 2, 3]), txb=r.getrandbits(2), rxf=r.choice([0, 0, 0, 1, 2, 3]))
        x = r.random()
        if x < 0.25:
            a = r.choice(regs); v = r.getrandbits(8)
            if a == 0x130: v = r.choice([0x80, 0xC0, 0x81, 0xC2, 0x00, v])
            if a in (0x133, 0x135, 0x27) and r.random() < 0.8: v = r.choice([0, 0, 0xFF])
            if a in (0x132, 0x134) and r.random() < 0.5: v = r.randrange(16)
            if a in (0x142, 0x143, 0x144, 0x145, 0x146, 0x147, 0x148, 0x149, 0x14A, 0x14B, 0x14C, 0x14D) and r.random() < 0.85: v = 0     # so that EQ occurs
            if a == 0x138: v = r.choice([0, 1, 7, 0x13, 0x25, v])
            if a == 0x139 and r.random() < 0.7: v = r.randrange(1, 12)
            if a == 0x140: v = r.choice([0x80, 0xC0, 0x81, 0xC1, 0x88, 0xD0, 0x98, 0xE0, 0x00, 0x01, v])
            d.update(addr=a, we=1, wd=v)
        elif x < 0.5: d.update(addr=r.choice(regs), re=1)
        s.cyc(**d)
    return s

if __name__ == '__main__':
    os.makedirs(f'{ROOT}/build', exist_ok=True)
    subprocess.run(['iverilog', '-g2005', '-o', f'{ROOT}/build/tb_tim.vvp', f'{ROOT}/tb/tb_tim.v', f'{RTLDIR}/rtimers.v',
                    f'{RTLDIR}/rlinecells.v'], check=True)
    errs, n = directed()
    print(f'directed: {n} cycles, {len(errs)} errors'); [print('  ', e) for e in errs]
    lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 100)
    bad = 0
    for seed in range(lo, hi):
        e = run_rtl(rand_seq(seed), 'tim_rand')
        if e:
            bad += 1
            if bad <= 3: print('  seed', seed, e[:160])
    print(f'random: seeds {lo}..{hi - 1}, {bad} mismatching')
    sys.exit(1 if errs or bad else 0)
