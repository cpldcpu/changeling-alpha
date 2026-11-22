#!/usr/bin/env python3
"""Register settings of the configuration examples of the datasheet, read from the simulation recordings
(comment lines '# R0 ...', '# T0 ...' written by the testbench option +wave=). Output: figs/lcex_<n>.tex.
Usage: gen_lcex.py <dir with w1.txt..w5.txt> <output dir>"""
import sys
src, dst = sys.argv[1], sys.argv[2]
NAMES = ['LCCTRL', 'LCPIN', 'LCOUT', 'LCCLK', 'LCTIM', 'LCA', 'LCB', 'LCC', 'LCDEC', 'LCENC', 'LCSH', 'LCMATCH', 'LCRUN', 'LCEVM', 'LCCS']
EDGE = ['no edge', 'rising edge', 'falling edge', 'both edges']
def rx(i, v, reg):
    t = []
    if i == 0:
        t += ['enabled' if v & 0x80 else 'off']; t += ['receiver on'] if v & 0x40 else []
        t += ['time unit half a clock cycle'] if v & 0x10 else []; t += ['prescaler %d' % (1 << (v & 7))] if v & 7 else []
    elif i == 1:
        t += ['input pin %d' % (v >> 5)]; t += ['inverted'] if v & 0x10 else []
        t += [['', 'filter: two equal samples', 'filter: majority of three', ''][(v >> 2) & 3]] if (v >> 2) & 3 else []
    elif i == 3:
        t += ['clock or second pin %d' % (v >> 5)] if v & 0x11 else []; t += ['edges from the clock pin'] if v & 0x10 else []
        t += ['second clock edge'] if v & 2 else []; t += ['both-low detector on'] if v & 1 else []
    elif i == 4:
        trig = v & 3
        if trig == 0:
            t += [EDGE[v >> 6]]; t += ['accepted only while waiting'] if v & 0x20 else ['accepted always']
            t += [['timer keeps running', 'wait after each sample', 'wait after each frame'][(v >> 3) & 3]]
        elif trig == 1: t += ['sample on the %s of the clock pin' % EDGE[v >> 6]]
        else: t += ['sample in the middle of each bit of the transmit cell']
        t += ['two periods per bit'] if v & 4 else []
    elif i == 5: t += ['%d time units from the edge to the first sample' % v] if (reg[4] & 3) == 0 else []
    elif i == 6: t += ['%d time units between samples, and idle timeout' % v] if (reg[4] & 3) == 0 else []
    elif i == 8: t += [{0xF0: 'level', 0x0F: 'inverted level', 0xC3: 'NRZI'}.get(v, 'table')]
    elif i == 10:
        t += ['%d bits' % ((v >> 5) + 1), 'LSB first' if v & 0x10 else 'MSB first']; t += ['search for the match pattern'] if v & 2 else []
    elif i == 11: t += ['pattern'] if reg[10] & 2 else []
    elif i == 12:
        t += ['drop the bit after %d ones' % (v >> 5)] if v >> 5 else []
        t += [['', 'reference event: accepted edge', 'reference event: both pins low', 'reference event: both low after idle'][v & 3]] if v & 3 else []
    elif i == 13:
        n = [('RXF', 0x80), ('EOP', 0x20), ('IDLE', 0x10), ('MATCH', 0x08), ('OVR', 4), ('STUFF', 2), ('BOTHL', 1)]
        t += ['event flag on ' + ', '.join(r'\texttt{%s}' % a for a, m in n if v & m)] if v else []
    return t
def tx(i, v, reg):
    t = []
    if i == 0:
        t += ['enabled' if v & 0x80 else 'off']; t += ['transmitter on'] if v & 0x20 else []; t += ['prescaler %d' % (1 << (v & 7))] if v & 7 else []
    elif i == 1: t += [['driven as the direction register says', 'pins always driven', 'pins driven while busy', ''][v & 3]]
    elif i == 2:
        t += ['true output on pin %d' % (v >> 5)] if v & 0x10 else []; t += ['second output on pin %d' % ((v >> 1) & 7)] if v & 1 else []
    elif i == 3:
        t += ['second output is the bit clock'] if v & 8 else []; t += ['clock idles high'] if v & 4 else []; t += ['second clock edge'] if v & 2 else []
    elif i == 4:
        t += [['next bit from the timer', 'next bit on an edge of the clock pin', 'next bit with each received bit', ''][v & 3]]
        t += ['two periods per bit'] if v & 4 else []
    elif i == 5: t += ['high time for a one: %d' % v] if reg[10] & 4 else []
    elif i == 6: t += ['%d time units per %s' % (v, 'period' if reg[4] & 4 else 'bit')]
    elif i == 7: t += ['high time for a zero: %d' % v] if reg[10] & 4 else []
    elif i == 9: t += [] if reg[10] & 4 else [{0xF0: 'NRZ', 0xA5: 'NRZI', 0xC3: 'Manchester'}.get(v, 'table')]
    elif i == 10:
        t += ['%d bits' % ((v >> 5) + 1), 'LSB first' if v & 0x10 else 'MSB first']
        t += ['compare mode'] if v & 4 else []; t += ['bits from the receive cell'] if v & 8 else []; t += ['start and stop bit'] if v & 1 else []
    elif i == 12:
        t += ['insert a zero after %d ones' % (v >> 5)] if v >> 5 else []; t += ['idle level high'] if v & 4 else []
        t += ['both outputs low for two bit times after the last bit'] if v & 2 else []
    elif i == 13: t += [r'event flag on \texttt{TXE}'] if v & 0x40 else []
    return t
def table(n, tcell, rcell):
    cfg = {}
    for l in open('%s/w%d.txt' % (src, n)):
        if l.startswith('#'):
            p = l.split(); cfg[p[1]] = [int(x, 16) for x in p[2:]]
    o = [r'\begin{tabularx}{\linewidth}{@{}l l L l L@{}}', r'\toprule',
         r' & \multicolumn{2}{l}{Transmit cell} & \multicolumn{2}{l}{Receive cell} \\', r'\midrule']
    T = cfg[tcell]; R = cfg[rcell] if rcell else None
    for i, nm in enumerate(NAMES):
        tv = T[i] if nm not in ('LCDEC', 'LCMATCH') else None
        rv = R[i] if R and nm not in ('LCOUT', 'LCC', 'LCENC') else None
        tt = tx(i, tv, T) if tv is not None else []; rt = rx(i, rv, R) if rv is not None else []
        if not (tv or rv) and not tt and not rt: continue
        if not tt and not rt and not ((tv or 0) | (rv or 0)): continue
        dec = nm in ('LCA', 'LCB', 'LCC')
        f = lambda v, txt: ('' if v is None or (v == 0 and not txt) else (r'\texttt{%d}' % v if dec else r'\texttt{0x%02X}' % v))
        if f(tv, tt) == '' and f(rv, rt) == '': continue
        nu = lambda v, txt: '; '.join(txt) if txt else ('not used' if v else '')
        o.append(r'\texttt{%s} & %s & %s & %s & %s \\' % (nm, f(tv, tt), nu(tv, tt), f(rv, rt), nu(rv, rt)))
    o += [r'\bottomrule', r'\end{tabularx}']
    open('%s/lcex_%d.tex' % (dst, n), 'w').write('\n'.join(o) + '\n')
table(1, 'T0', 'R0'); table(2, 'T0', 'R0'); table(3, 'T0', None); table(4, 'T0', 'R1'); table(5, 'T0', None)
print('ok')
