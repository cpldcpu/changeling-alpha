#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Timing diagrams of the datasheet, drawn from simulation.
Input: build/wave/w1.txt .. w5.txt of the rsys package (firmware fw/fwwave.c, testbench option +wave=).
Output: figs/wave_1.tex .. wave_5.tex (TikZ). Usage: gen_waves.py <dir with the logs> <output dir>"""
import sys
src, dst = sys.argv[1], sys.argv[2]
SYNC = 2          # clock cycles from a pin to the internal strobes (input synchroniser)

def load(n):
    L = [l.split() for l in open('%s/w%d.txt' % (src, n)) if not l.startswith('#')]
    col = lambda i, f=int: [f(l[i]) for l in L]
    pins = [int(l[1], 16) for l in L]
    d = dict(n=len(L), pins=pins,
             r0acc=col(2), r0smp=col(3), r0stat=[int(l[5], 16) for l in L], t0stat=[int(l[6], 16) for l in L],
             r1acc=col(7), r1smp=col(8), r1stat=[int(l[10], 16) for l in L],
             t0we=col(12), r0re=col(13), r1re=col(15))
    return d
def pin(d, k): return [(p >> k) & 1 for p in d['pins']]
def bit(v, m): return [1 if x & m else 0 for x in v]
def ev(v, shift=0): return [i - shift for i, x in enumerate(v) if x]

class Fig:
    def __init__(s, c0, c1, width=150.0, rowh=5.2, lab=27.0):
        s.c0, s.c1, s.sx, s.rowh, s.lab, s.y, s.o = c0, c1, (width - lab) / (c1 - c0), rowh, lab, 0.0, []
    def x(s, c): return s.lab + (c - s.c0) * s.sx
    def label(s, t, y=None): s.o.append(r'\node[lbl,anchor=east] at (%.2f,%.2f) {%s};' % (s.lab - 2.0, (s.y if y is None else y) + 1.4, t))
    def ruler(s, step=10):
        s.y -= 3.0
        s.o.append(r'\draw[black!55,line width=0.3pt] (%.2f,%.2f) -- (%.2f,%.2f);' % (s.x(s.c0), s.y, s.x(s.c1), s.y))
        c = 0
        while s.c0 + c <= s.c1:
            s.o.append(r'\draw[black!55,line width=0.3pt] (%.2f,%.2f) -- ++(0,-0.9) node[below,inner sep=1pt,font=\tiny\sffamily,text=black!70]{%d};' % (s.x(s.c0 + c), s.y, c)); c += step
        s.o.append(r'\node[lbl,anchor=east,text=black!70] at (%.2f,%.2f) {clock cycles};' % (s.lab - 2.0, s.y - 1.3))
        s.y -= 4.0
    def sig(s, name, v, driven=None, hi=2.8):
        s.y -= s.rowh; s.label(name); y0 = s.y; pts = []; segs = []
        vals = [(v[c] if (driven is None or driven[c]) else None) for c in range(s.c0, s.c1)]
        start = s.c0
        for i in range(1, len(vals) + 1):
            if i == len(vals) or vals[i] != vals[i - 1]:
                segs.append((start, s.c0 + i, vals[i - 1])); start = s.c0 + i
        prev = None
        for a, b, val in segs:
            if val is None:
                s.o.append(r'\draw[black!50,line width=0.4pt,densely dashed] (%.2f,%.2f) -- (%.2f,%.2f);' % (s.x(a), y0 + hi / 2, s.x(b), y0 + hi / 2))
            else:
                yy = y0 + (hi if val else 0)
                if prev is not None and prev != yy: s.o.append(r'\draw[ink,line width=0.6pt] (%.2f,%.2f) -- (%.2f,%.2f);' % (s.x(a), prev, s.x(a), yy))
                s.o.append(r'\draw[ink,line width=0.6pt] (%.2f,%.2f) -- (%.2f,%.2f);' % (s.x(a), yy, s.x(b), yy))
            prev = None if val is None else y0 + (hi if val else 0)
        return y0
    def events(s, name, cyc, style='accent'):
        s.y -= s.rowh - 0.8; s.label(name, s.y - 0.4)
        for c in cyc:
            if s.c0 <= c <= s.c1:
                s.o.append(r'\draw[%s,line width=0.6pt,-{Stealth[length=1.5mm,width=1.2mm]}] (%.2f,%.2f) -- ++(0,2.4);' % (style, s.x(c), s.y))
        return s.y
    def vline(s, c, y1, y2): s.o.append(r'\draw[black!40,line width=0.3pt,densely dotted] (%.2f,%.2f) -- (%.2f,%.2f);' % (s.x(c), y1, s.x(c), y2))
    def dim(s, a, b, y, text):
        s.o.append(r'\draw[accent,line width=0.4pt,{Stealth[length=1.1mm,width=0.9mm]}-{Stealth[length=1.1mm,width=0.9mm]}] (%.2f,%.2f) -- (%.2f,%.2f) node[midway,above,inner sep=0.8pt,font=\tiny\sffamily,text=accent,fill=white]{%s};' % (s.x(a), y, s.x(b), y, text))
    def text(s, c, y, t, anchor='center', col='ink'):
        s.o.append(r'\node[font=\tiny\sffamily,text=%s,inner sep=0.6pt,anchor=%s] at (%.2f,%.2f) {%s};' % (col, anchor, s.x(c), y, t))
    def write(s, n):
        open('%s/wave_%d.tex' % (dst, n), 'w').write('\\begin{tikzpicture}[x=1mm,y=1mm]\n' + '\n'.join(s.o) + '\n\\end{tikzpicture}\n')

def edges(v, c0, c1): return [c for c in range(max(c0, 1), c1) if v[c] != v[c - 1]]

# ---- 1: UART, 8 cycles per bit ----
d = load(1); f = Fig(16, 122); p = pin(d, 0)
st = edges(p, 16, 122)[0]                               # falling edge of the start bit at the pin
f.events(r'write \texttt{LTnDATA}', ev(d['t0we']))
f.sig(r'\texttt{TXE}', bit(d['t0stat'], 0x40)); f.sig(r'\texttt{BUSY}', bit(d['t0stat'], 0x20))
f.y -= 3.2; yp = f.sig('pin', p)
for i, t in enumerate(['start'] + ['%d' % ((0x53 >> k) & 1) for k in range(8)] + ['stop']): f.text(st + 8 * i + 4, yp + 4.3, t)
for i in range(11): f.vline(st + 8 * i, yp - 0.3, yp + 3.3)
f.dim(st + 16, st + 24, yp + 6.4, 'B (transmit) = 8')
smp = ev(d['r0smp'], SYNC); ys = f.events('pin sampled', smp)
f.dim(st, smp[0], ys - 2.2, 'A = 12'); f.dim(smp[0], smp[1], ys - 2.2, 'B = 8')
f.y -= 3.0
f.sig(r'\texttt{RXF}', bit(d['r0stat'], 0x80)); f.events(r'read \texttt{LRnDATA}', ev(d['r0re']))
f.ruler(); f.write(1)

# ---- 2: SPI master ----
d = load(2); f = Fig(16, 106); mo = pin(d, 0); ck = pin(d, 1)
st = edges(mo, 16, 106)[0]
f.events(r'write \texttt{LTnDATA}', ev(d['t0we']))
f.sig(r'\texttt{BUSY}', bit(d['t0stat'], 0x20))
f.y -= 2.4; yc = f.sig('SCK', ck)
f.y -= 2.6; ym = f.sig('MOSI', mo)
for i in range(8): f.text(st + 8 * i + 4, ym + 4.2, '%d' % ((0xA6 >> (7 - i)) & 1))
for i in range(9): f.vline(st + 8 * i, ym - 0.3, yc + 3.2)
smp = ev(d['r0smp'], SYNC); ys = f.events('input sampled', smp)
f.dim(st + 8, st + 12, yc + 4.4, 'B = 4'); f.dim(st + 24, st + 32, yc + 4.4, 'one bit')
re = edges(ck, 16, 106)[2]
f.dim(smp[1], re, ys - 2.2, '4')
f.y -= 3.0
f.sig(r'\texttt{RXF}', bit(d['r0stat'], 0x80)); f.events(r'read \texttt{LRnDATA}', ev(d['r0re']))
f.ruler(); f.write(2)

# ---- 3: compare mode ----
d = load(3); f = Fig(14, 134); p = pin(d, 0)
st = edges(p, 14, 134)[0]
f.events(r'write \texttt{LTnDATA}', ev(d['t0we']))
f.sig(r'\texttt{BUSY}', bit(d['t0stat'], 0x20))
f.y -= 3.0; yp = f.sig('pin', p)
for i in range(6):
    if i < 5: f.text(st + 20 * i + 10, yp + 4.3, '%d' % ((0xB0 >> (7 - i)) & 1)); f.vline(st + 20 * i, yp - 0.3, yp + 3.3)
f.dim(st, st + 12, yp - 2.4, 'A = 12'); f.dim(st + 20, st + 25, yp - 2.4, 'C = 5'); f.dim(st + 40, st + 60, yp - 2.4, 'B = 20')
f.y -= 2.5
f.ruler(); f.write(3)

# ---- 4: Manchester, two phases ----
d = load(4); p = pin(d, 0); busy = bit(d['t0stat'], 0x20)
st = edges(p, 20, 190)[0] - 3                          # start of the first bit: its first half has the idle level
f = Fig(st + 30, st + 164)
f.events(r'write \texttt{LTnDATA}', ev(d['t0we']))
f.sig(r'\texttt{BUSY}', busy)
f.y -= 4.6; yp = f.sig('pin', p, driven=None)
bits = [(b >> k) & 1 for b in (0x55, 0xD5, 0x4B) for k in range(8)]
for i, b in enumerate(bits):
    if i >= 5: f.text(st + 6 * i + 3, yp + 4.2, '%d' % b)
    if i >= 5 and i <= 24: f.vline(st + 6 * i, yp - 0.3, yp + (6.0 if i % 8 == 0 else 3.3))
f.text(st + 39, yp + 6.8, 'preamble'); f.text(st + 72, yp + 6.8, 'match pattern \\texttt{0xD5}'); f.text(st + 120, yp + 6.8, 'data byte \\texttt{0x4B}')
f.dim(st + 60, st + 66, yp - 2.3, '6')
acc = ev(d['r1acc'], SYNC); smp = ev(d['r1smp'], SYNC)
f.y -= 2.2; ya = f.events('edge accepted', acc); ys = f.events('pin sampled', smp)
f.y -= 0.8
f.sig(r'\texttt{MATCH}', bit(d['r1stat'], 0x08)); f.sig(r'\texttt{RXF}', bit(d['r1stat'], 0x80)); f.sig(r'\texttt{IDLE}', bit(d['r1stat'], 0x10))
f.events(r'read \texttt{LRnDATA}', ev(d['r1re']))
f.ruler(); f.write(4)

# ---- 5: NRZI, bit stuffing, end sequence ----
d = load(5); f = Fig(14, 150); dp = pin(d, 0); dm = pin(d, 1); busy = bit(d['t0stat'], 0x20)
st = [c for c in range(1, d['n']) if dp[c] != dp[c - 1]][0]
f.events(r'write \texttt{LTnDATA}', ev(d['t0we']))
f.sig(r'\texttt{BUSY}', busy)
drv = [0] * d['n']
for c in range(d['n']): drv[c] = 1 if st <= c < st + 110 else 0
f.y -= 3.0; y1 = f.sig('true output', dp, driven=drv); f.y -= 0.6; y2 = f.sig('second output', dm, driven=drv)
lab = ['0', '1', '1', '1', '1', '1', '1', 'stuffed 0', '1']
for i, t in enumerate(lab):
    f.text(st + 10 * i + 5, y1 + 4.2, t if t != 'stuffed 0' else '0', col='accent' if t == 'stuffed 0' else 'ink'); f.vline(st + 10 * i, y2 - 0.3, y1 + 3.3)
f.vline(st + 90, y2 - 0.3, y1 + 3.3); f.vline(st + 110, y2 - 0.3, y1 + 3.3)
f.text(st + 75, y1 + 6.4, 'stuffed bit', col='accent')
f.dim(st + 90, st + 110, y2 - 2.4, 'both low, 2 bit times'); f.dim(st + 10, st + 20, y2 - 2.4, 'B = 10')
f.y -= 2.5
f.ruler(); f.write(5)
print("ok")
