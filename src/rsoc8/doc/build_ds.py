#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Builds the register tables and the instruction table of the datasheet.
Sources: the register map section of rpe_spec.tex (bit tables and field tables), and the lists in this file.
Output: ds_gen/*.tex, included by the chapter files of the datasheet. Run in the directory of the documents."""
import re, os
os.makedirs('ds_gen', exist_ok=True)
spec = open('rpe_spec.tex').read()
m = spec[spec.index("\\section{Register map}"):spec.index("\\section{Behaviour of the other blocks}")]
def tables(s): return re.findall(r'\\begin\{table\}.*?\\end\{table\}', s, flags=re.S)
def rows(t): return [l for l in t.split('\n') if l.rstrip().endswith('\\\\') or l.rstrip().endswith('\\hline')]
def bycap(start):
    for t in tables(m):
        if '\\caption{' + start in t: return t
    raise Exception(start)
def clean(s): return s.replace(" Same positions as in \\texttt{rperiph}", "")

# ---- parse
fast = {}                                   # name -> (addr, access, reset, percore, function)
for l in rows(bycap('Fast I/O tier')):
    c = [x.strip() for x in re.split(r'\s*&\s*', l.rstrip().rstrip('\\').rstrip())]
    if len(c) == 6 and c[0].startswith('\\texttt{0x'):
        for nm in re.findall(r'\\reg\{(\w+)\}', c[1]): fast[nm] = (c[0], c[2], c[3], c[4], c[5], c[1])
bits = {}                                   # register name -> row of a bit table
for cap in ('Bit assignment of the fast', 'Provisional pin positions', 'Clocking registers', 'Timer, PWM and CRC registers', 'System and program protection registers'):
    for l in rows(bycap(cap)):
        mm = re.match(r'\\texttt\{([^}]*)\} & ', l)
        if mm and mm.group(1) != 'Register': bits[mm.group(1)] = l
mean = {}                                   # register -> rows of the fast meaning table
cur = None
for l in rows(bycap('Meaning of the fast')):
    mm = re.match(r'\\reg\{(\w+)\} & ', l)
    if mm: cur = mm.group(1)
    if cur and ' & ' in l and not l.startswith('Register'): mean.setdefault(cur, []).append(clean(l))
def frows(cap): return [l for l in rows(bycap(cap)) if l.startswith('\\reg')]
clk_f, tim_f, sys_f = frows('Clocking fields'), frows('Timer, PWM and CRC fields'), frows('System and program protection fields')

HDR = "\\rowcolor{fillA}\\textbf{Register} & \\textbf{Addr.} & \\textbf{7} & \\textbf{6} & \\textbf{5} & \\textbf{4} & \\textbf{3} & \\textbf{2} & \\textbf{1} & \\textbf{0} \\\\ \\hline"
def bittab(names, page=False):
    o = ["{\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}", "\\begin{tabular}{@{}ll|*{8}{>{\\centering\\arraybackslash}p{12.2mm}|}@{}}", "\\hline", HDR]
    for n in names:
        r = bits[n]
        if page: r = re.sub(r'& \\texttt\{0x([0-9A-F]{2})([^}]*)\}', lambda q: '& \\texttt{0x3F%s%s}' % (q.group(1), q.group(2)), r, count=1)
        o.append(r)
    return '\n'.join(o) + "\n\\end{tabular}\\par}\n"
def reglist(items):
    o = ["{\\small\\begin{tabularx}{\\linewidth}{@{}llllL@{}}", "\\toprule", "Address & Name & Access & Reset & Function \\\\", "\\midrule"]
    for it in items:
        if isinstance(it, str):
            a, acc, rst, pc, fn, nm = fast[it]
            if pc: fn += {'yes': '. One per core', 'view': '. Each core has its own view', 'owner': '. Owner core of the pair only', 'write': '. The written value is per core'}.get(pc, '. Per core: ' + pc)
            o.append("%s & %s & %s & %s & %s \\\\" % (a, nm, acc, rst, fn))
        else: o.append("\\texttt{%s} & \\reg{%s} & %s & %s & %s \\\\" % it)
    return '\n'.join(o) + "\n\\bottomrule\n\\end{tabularx}\\par}\n"
def fieldtab(lines, head="Register & Bits & Meaning", cols="llL"):
    return "{\\small\\begin{tabularx}{\\linewidth}{@{}%s@{}}\n\\toprule\n%s \\\\\n\\midrule\n" % (cols, head) + '\n'.join(lines) + "\n\\bottomrule\n\\end{tabularx}\\par}\n"
def pick(lst, *keys): return [l for l in lst if any(k in l.split(' & ')[0] for k in keys)]
def w(name, s): open('ds_gen/%s.tex' % name, 'w').write(s.replace(' (the RTL treats it like 0)', ''))
V = "\n\\vspace{4pt}\n"

# configuration page registers: (address, name, access, reset, function)
CFG = {
 'clock': [('0x3F20', 'CLKCTL', 'R/W, protected', 'strap', 'Source request, oscillator enables, loop, reference selection'),
           ('0x3F21', 'OSCTRIM', 'R/W', '\\texttt{0x80}', 'Trim value of the oscillator'),
           ('0x3F22', 'CLKCDIV', 'R/W, protected', '\\texttt{0x01}', 'Core clock divider minus one'),
           ('0x3F23', 'CLKPDIV', 'R/W', '\\texttt{0x00}', 'Peripheral clock divider minus one'),
           ('0x3F24', 'TRINT', 'R/W', '\\texttt{0x00}', 'Start of a measurement, reference periods per measurement'),
           ('0x3F25', 'TRCNTL', 'R', '\\texttt{0x00}', 'Count of the last measurement, low byte'),
           ('0x3F26', 'TRCNTH', 'R', '\\texttt{0x00}', 'Count of the last measurement, high byte'),
           ('0x3F27', 'TRTGTL', 'R/W', '\\texttt{0x00}', 'Target count, low byte'),
           ('0x3F28', 'TRTGTH', 'R/W', '\\texttt{0x00}', 'Target count, high byte'),
           ('0x3F29', 'TRWIN', 'R/W', '\\texttt{0x00}', 'Window for a valid measurement, in units of 64 counts'),
           ('0x3F2A', 'CLKOUT', 'R/W', '\\texttt{0x00}', 'Clock output enable and divider')],
 'timer': [('0x3F30', 'TCR', 'R/W', '\\texttt{0x00}', 'Run, restart at compare A, prescaler'),
           ('0x3F31', 'TCAP', 'R/W', '\\texttt{0x00}', 'Capture source and edge'),
           ('0x3F32', 'OCRAL', 'R/W', '\\texttt{0x00}', 'Compare value A, low byte'), ('0x3F33', 'OCRAH', 'R/W', '\\texttt{0x00}', 'Compare value A, high byte'),
           ('0x3F34', 'OCRBL', 'R/W', '\\texttt{0x00}', 'Compare value B, low byte'), ('0x3F35', 'OCRBH', 'R/W', '\\texttt{0x00}', 'Compare value B, high byte')],
 'pwm':   [('0x3F38', 'PWMC', 'R/W', '\\texttt{0x00}', 'Channel enables and prescaler'), ('0x3F39', 'PWMTOP', 'R/W', '\\texttt{0x00}', 'Period minus one'),
           ('0x3F3A', 'PWM0', 'R/W', '\\texttt{0x00}', 'High time of channel 0'), ('0x3F3B', 'PWM1', 'R/W', '\\texttt{0x00}', 'High time of channel 1'), ('0x3F3C', 'PWM2', 'R/W', '\\texttt{0x00}', 'High time of channel 2')],
 'crc':   [('0x3F40', 'CRCCTL', 'R/W', '\\texttt{0x00}', 'Enable, shift direction, bit source, owner'), ('0x3F41', 'CRCLEN', 'R/W', '\\texttt{0x00}', 'Width of the CRC minus one'),
           ('0x3F42--45', 'CRCPOLY0..3', 'R/W', '\\texttt{0x00}', 'Polynomial, low byte first'), ('0x3F46--49', 'CRCVAL0..3', 'R/W', '\\texttt{0x00}', 'CRC value, low byte first'),
           ('0x3F4A--4D', 'CRCREF0..3', 'R/W', '\\texttt{0x00}', 'Reference value, low byte first')],
 'sys':   [('0x3F50', 'ARB', 'R/W, protected', '\\texttt{0x00}', 'Arbiter mode'), ('0x3F51', 'LCOWN', 'R/W, protected', '\\texttt{0x02}', 'Owner core of each pair of line cells'),
           ('0x3F52', 'DBGSEL', 'R/W', '\\texttt{0x00}', 'Debug pin enable and signal selection'), ('0x3F53', 'ODE', 'R/W', '\\texttt{0x00}', 'Open-drain enable per pin of the bidirectional port'),
           ('0x3F54', 'PCMSK', 'R/W', '\\texttt{0x00}', 'Pin-change mask per pin of the bidirectional port'),
           ('0x3F58', 'PMCR', 'R/W, protected', '\\texttt{0x00}', 'Write enables and lock of the code memories'), ('0x3F59', 'PMLIM', 'R/W, protected', '\\texttt{0x00}', 'Write-protected part of the code memories')],
}
def cfg(block, *names): return [r for r in CFG[block] if not names or r[1] in names]

# ---- chapter tables
w('core', reglist(['CCP', 'SPL', 'SPH', 'SREG']) + V + bittab(['SREG']))
w('twocore', reglist(['CORECTL', 'LOCK'] + cfg('sys', 'ARB')) + V + bittab(['CORECTL', 'LOCK']) + V + fieldtab(mean['CORECTL'] + mean['LOCK'] + [r.replace('\\reg{ARB} & \\texttt{0x00} & ', '\\reg{ARB} & \\reg{MODE} (bits 1, 0) & ').replace('\\reg{MODE}: which', 'Which') for r in pick(sys_f, 'ARB')]))
w('mem', reglist(cfg('sys', 'PMCR', 'PMLIM')) + V + bittab(['PMCR', 'PMLIM'], page=True) + V + fieldtab(pick(sys_f, 'PMCR', 'PMLIM'), "Register & Reset & Meaning"))
w('clock', reglist(['CLKSTAT'] + cfg('clock')) + V + bittab(['CLKSTAT']) + V + bittab(['CLKCTL', 'OSCTRIM', 'CLKCDIV', 'CLKPDIV', 'TRINT', 'TRCNTL/H', 'TRTGTL/H', 'TRWIN', 'CLKOUT'], page=True) + V
  + fieldtab([' & '.join([x[1], 'status', x[2]]) for x in ([y.strip() for y in re.split(r'\s&\s', l, maxsplit=2)] for l in mean['CLKSTAT'])] + clk_f, "Field & Reset & Meaning"))
w('ports', reglist(['PINR', 'DDR', 'PORT', 'PINB', 'PORTC'] + cfg('sys', 'ODE', 'PCMSK')) + V + bittab(['PINB', 'PORTC']))
w('events', reglist(['IFRL', 'IFRH', 'IERL', 'IERH', 'WAITL', 'WAITH', 'DLYL', 'DLYH']) + V + bittab(['IFRL', 'IFRH']) + V + fieldtab(mean['IFRL'] + mean['IFRH']))
w('timer', reglist(['TCNTL', 'TCNTH', 'ICRL', 'ICRH'] + cfg('timer')) + V + bittab(['TCR', 'TCAP', 'OCRAL/H', 'OCRBL/H'], page=True) + V + fieldtab(pick(tim_f, 'RUN', 'TCAP'), "Field & Meaning", "lL"))
w('pwm', reglist(cfg('pwm')) + V + bittab(['PWMC', 'PWMTOP', 'PWM0..2'], page=True) + V + fieldtab(pick(tim_f, 'PEN0'), "Field & Meaning", "lL"))
w('crc', reglist(['CRCIN'] + cfg('crc')) + V + bittab(['CRCCTL', 'CRCLEN', 'CRCPOLY0..3', 'CRCVAL0..3', 'CRCREF0..3'], page=True) + V + fieldtab(pick(tim_f, 'CRC'), "Field & Meaning", "lL"))
w('host', reglist(['MBSTAT', 'MBDATA'] + cfg('sys', 'DBGSEL')) + V + bittab(['MBSTAT']) + V + bittab(['DBGSEL'], page=True) + V + fieldtab(mean['MBSTAT'] + [r.replace('\\reg{DBGSEL} & \\texttt{0x00} & ', '\\reg{DBGSEL} & \\reg{EN}, \\reg{SEL} & ') for r in pick(sys_f, 'DBGSEL')]))

# ---- appendix: complete register list of the configuration page and all bit tables
LCN = ['LCCTRL', 'LCPIN', 'LCOUT', 'LCCLK', 'LCTIM', 'LCA', 'LCB', 'LCC', 'LCDEC', 'LCENC', 'LCSH', 'LCMATCH', 'LCRUN', 'LCEVM', 'LCCS']
ap = ["\\begin{longtable}{@{}llllp{0.47\\linewidth}@{}}", "\\caption{Configuration page, all registers.}\\\\", "\\toprule", "Address & Name & Access & Reset & Function \\\\", "\\midrule", "\\endfirsthead",
      "\\toprule", "Address & Name & Access & Reset & Function \\\\", "\\midrule", "\\endhead", "\\bottomrule", "\\endfoot"]
def lcblock(base, cell, kind):
    for i, n in enumerate(LCN):
        if kind == 'R' and n in ('LCOUT', 'LCENC'): continue
        if kind == 'T' and n in ('LCDEC', 'LCMATCH'): continue
        ap.append("\\texttt{0x%04X} & \\texttt{%s} & R/W & \\texttt{0x00} & %s, section~\\ref{sec:lcregs} \\\\" % (base + i, 'LCEC' if (kind == 'R' and n == 'LCC') else n, cell))
    ap.append("\\texttt{0x%04X} & \\texttt{LCX} & R/W & \\texttt{0x00} & %s, section~\\ref{sec:lcregs} \\\\" % (base + 15, cell))
lcblock(0x3F00, 'Receive cell 0', 'R'); ap.append('\\midrule'); lcblock(0x3F10, 'Transmit cell 0', 'T'); ap.append('\\midrule')
for blk in ('clock', 'timer', 'pwm', 'crc', 'sys'):
    for a, n, acc, rst, fn in CFG[blk]:
        if blk == 'sys' and n == 'PMCR':
            ap.append('\\midrule')
        ap.append("\\texttt{%s} & \\texttt{%s} & %s & %s & %s \\\\" % (a, n.replace('_', '\\_'), acc, rst, fn))
    ap.append('\\midrule')
lcblock(0x3F60, 'Receive cell 1', 'R'); ap.append('\\midrule'); lcblock(0x3F70, 'Transmit cell 1', 'T')
ap.append("\\end{longtable}")
order = sorted(range(len(ap)), key=lambda i: i)   # kept in block order; pair 1 follows the system registers by address
w('app_cfg', '\n'.join(ap) + '\n')
ft = bycap('Fast I/O tier').replace('\\begin{table}[H]', '\\begin{table}[H]')
w('app_fast', ft + '\n')
w('app_bits', "\\paragraph{Fast I/O registers.}\n\n" + bittab(['LOCK', 'IFRL', 'IFRH', 'LRnSTAT', 'LTnSTAT', 'MBSTAT', 'CORECTL', 'CLKSTAT', 'SREG', 'PINB', 'PORTC'])
  + "\n\\paragraph{Configuration page} (addresses are offsets from \\texttt{0x3F00}).\n\n" + bittab(['CLKCTL', 'OSCTRIM', 'CLKCDIV', 'CLKPDIV', 'TRINT', 'TRCNTL/H', 'TRTGTL/H', 'TRWIN', 'CLKOUT', 'TCR', 'TCAP', 'OCRAL/H', 'OCRBL/H', 'PWMC', 'PWMTOP', 'PWM0..2', 'CRCCTL', 'CRCLEN', 'CRCPOLY0..3', 'CRCVAL0..3', 'CRCREF0..3', 'ARB', 'LCOWN', 'DBGSEL', 'ODE', 'PCMSK', 'PMCR', 'PMLIM']))

# ---- instruction table
I = []
def grp(t): I.append(('G', t))
def ins(mn, ops, op, fl, enc, cyc): I.append((mn, ops, op, fl, enc, cyc))
grp('Arithmetic and logic')
for mn, op, fl, e in (('ADD', 'Rd $\\leftarrow$ Rd + Rr', 'Z C N V', '0000 1111'), ('ADC', 'Rd $\\leftarrow$ Rd + Rr + C', 'Z C N V', '0001 1111'), ('SUB', 'Rd $\\leftarrow$ Rd $-$ Rr', 'Z C N V', '0001 1011'),
                      ('SBC', 'Rd $\\leftarrow$ Rd $-$ Rr $-$ C', 'Z C N V', '0000 1011'), ('AND', 'Rd $\\leftarrow$ Rd and Rr', 'Z N V', '0010 0011'), ('OR', 'Rd $\\leftarrow$ Rd or Rr', 'Z N V', '0010 1011'),
                      ('EOR', 'Rd $\\leftarrow$ Rd xor Rr', 'Z N V', '0010 0111'), ('CP', 'Rd $-$ Rr', 'Z C N V', '0001 0111'), ('CPC', 'Rd $-$ Rr $-$ C', 'Z C N V', '0000 0111')):
    ins(mn, 'Rd, Rr', op, fl, e + ' dddd rrrr', '1')
for mn, op, fl, e in (('SUBI', 'Rd $\\leftarrow$ Rd $-$ K', 'Z C N V', '0101'), ('SBCI', 'Rd $\\leftarrow$ Rd $-$ K $-$ C', 'Z C N V', '0100'), ('ANDI', 'Rd $\\leftarrow$ Rd and K', 'Z N V', '0111'),
                      ('ORI', 'Rd $\\leftarrow$ Rd or K', 'Z N V', '0110'), ('CPI', 'Rd $-$ K', 'Z C N V', '0011')):
    ins(mn, 'Rd, K', op, fl, e + ' KKKK dddd KKKK', '1')
for mn, op, fl, e in (('COM', 'Rd $\\leftarrow$ not Rd', 'Z C N V', '0000'), ('NEG', 'Rd $\\leftarrow$ 0 $-$ Rd', 'Z C N V', '0001'), ('INC', 'Rd $\\leftarrow$ Rd + 1', 'Z N V', '0011'), ('DEC', 'Rd $\\leftarrow$ Rd $-$ 1', 'Z N V', '1010'),
                      ('LSR', 'shift right, bit 7 $\\leftarrow$ 0, C $\\leftarrow$ bit 0', 'Z C N V', '0110'), ('ROR', 'shift right, bit 7 $\\leftarrow$ C, C $\\leftarrow$ bit 0', 'Z C N V', '0111'),
                      ('ASR', 'shift right, bit 7 kept, C $\\leftarrow$ bit 0', 'Z C N V', '0101'), ('SWAP', 'exchange the two halves of Rd', '--', '0010')):
    ins(mn, 'Rd', op, fl, '1001 0101 dddd ' + e, '1')
grp('Data transfer')
ins('MOV', 'Rd, Rr', 'Rd $\\leftarrow$ Rr', '--', '0010 1111 dddd rrrr', '1')
ins('LDI', 'Rd, K', 'Rd $\\leftarrow$ K', '--', '1110 KKKK dddd KKKK', '1')
for p, e in (('X', '1001 00s1 dddd 1100'), ('X+', '1001 00s1 dddd 1101'), ('$-$X', '1001 00s1 dddd 1110'), ('Y', '1000 00s1 dddd 1000'), ('Y+', '1001 00s1 dddd 1001'), ('$-$Y', '1001 00s1 dddd 1010'),
             ('Z', '1000 00s1 dddd 0000'), ('Z+', '1001 00s1 dddd 0001'), ('$-$Z', '1001 00s1 dddd 0010')):
    ins('LD', 'Rd, ' + p, 'Rd $\\leftarrow$ (%s)' % p, '--', e.replace('s', '0'), '2 \\textsuperscript{a}')
    ins('ST', p + ', Rr', '(%s) $\\leftarrow$ Rr' % p, '--', e.replace('s', '1').replace('dddd', 'rrrr'), '1 \\textsuperscript{b}')
ins('LDS', 'Rd, k', 'Rd $\\leftarrow$ (k), k = \\texttt{0x40} to \\texttt{0xBF}', '--', '1010 0kkk dddd kkkk', '2')
ins('STS', 'k, Rr', '(k) $\\leftarrow$ Rr', '--', '1010 1kkk rrrr kkkk', '1')
ins('IN', 'Rd, A', 'Rd $\\leftarrow$ I/O(A), A = 0 to 63', '--', '1011 0AA1 dddd AAAA', '1')
ins('OUT', 'A, Rr', 'I/O(A) $\\leftarrow$ Rr', '--', '1011 1AA1 rrrr AAAA', '1')
ins('PUSH', 'Rr', '(SP) $\\leftarrow$ Rr, SP $\\leftarrow$ SP $-$ 1', '--', '1001 0011 rrrr 1111', '1')
ins('POP', 'Rd', 'SP $\\leftarrow$ SP + 1, Rd $\\leftarrow$ (SP)', '--', '1001 0001 dddd 1111', '2')
grp('Bits and flags')
ins('SBI', 'A, b', 'I/O(A) bit b $\\leftarrow$ 1, A = 0 to 31', '--', '1001 1010 AAAA Abbb', '1')
ins('CBI', 'A, b', 'I/O(A) bit b $\\leftarrow$ 0', '--', '1001 1000 AAAA Abbb', '1')
ins('BST', 'Rd, b', 'T $\\leftarrow$ Rd bit b', 'T', '1111 1011 dddd 0bbb', '1')
ins('BLD', 'Rd, b', 'Rd bit b $\\leftarrow$ T', '--', '1111 1001 dddd 0bbb', '1')
ins('BSET', 's', 'flag s $\\leftarrow$ 1 (SEC, SEZ, SEN, SEV, SET, SEI)', 'flag s', '1001 0100 0sss 1000', '1')
ins('BCLR', 's', 'flag s $\\leftarrow$ 0 (CLC, CLZ, CLN, CLV, CLT, CLI)', 'flag s', '1001 0100 1sss 1000', '1')
grp('Jumps, calls and skips')
ins('RJMP', 'k', 'PC $\\leftarrow$ PC + 1 + k, k = $-$2048 to 2047', '--', '1100 kkkk kkkk kkkk', '2')
ins('IJMP', '', 'PC $\\leftarrow$ Z', '--', '1001 0100 0000 1001', '2')
ins('RCALL', 'k', 'push PC + 1; PC $\\leftarrow$ PC + 1 + k', '--', '1101 kkkk kkkk kkkk', '2')
ins('ICALL', '', 'push PC + 1; PC $\\leftarrow$ Z', '--', '1001 0101 0000 1001', '2')
ins('RET', '', 'pop PC', '--', '1001 0101 0000 1000', '3')
ins('RETI', '', 'pop PC, I $\\leftarrow$ 1', 'I', '1001 0101 0001 1000', '3')
ins('BRBS', 's, k', 'if flag s = 1: PC $\\leftarrow$ PC + 1 + k, k = $-$64 to 63', '--', '1111 00kk kkkk ksss', '1 / 2')
ins('BRBC', 's, k', 'if flag s = 0: PC $\\leftarrow$ PC + 1 + k', '--', '1111 01kk kkkk ksss', '1 / 2')
ins('CPSE', 'Rd, Rr', 'skip the next instruction if Rd = Rr', '--', '0001 0011 dddd rrrr', '1 / 2')
ins('SBRC', 'Rr, b', 'skip if Rr bit b = 0', '--', '1111 1101 rrrr 0bbb', '1 / 2')
ins('SBRS', 'Rr, b', 'skip if Rr bit b = 1', '--', '1111 1111 rrrr 0bbb', '1 / 2')
ins('SBIC', 'A, b', 'skip if I/O(A) bit b = 0, A = 0 to 31', '--', '1001 1001 AAAA Abbb', '1 / 2')
ins('SBIS', 'A, b', 'skip if I/O(A) bit b = 1', '--', '1001 1011 AAAA Abbb', '1 / 2')
grp('Control')
ins('NOP', '', 'no operation', '--', '0000 0000 0000 0000', '1')
ins('SLEEP', '', 'wait for the events of the wait mask', '--', '1001 0101 1000 1000', '1')
ins('BREAK', '', 'halt the core for the host link', '--', '1001 0101 1001 1000', '1')
o = ["{\\small\\begin{longtable}{@{}llp{0.36\\linewidth}lll@{}}", "\\caption{Instruction set. Rd, Rr: registers r16 to r31, coded as register number minus 16. K: 8-bit constant. Cycles: clock cycles in which the core is enabled; ``1 / 2'': not taken or not skipped / taken or skipped.}\\label{tab:instr}\\\\",
     "\\toprule", "Mnemonic & Operands & Operation & Flags & Code (bit 15 to 0) & Cycles \\\\", "\\midrule", "\\endfirsthead", "\\toprule", "Mnemonic & Operands & Operation & Flags & Code (bit 15 to 0) & Cycles \\\\", "\\midrule", "\\endhead", "\\bottomrule", "\\endfoot"]
for r in I:
    if r[0] == 'G': o.append("\\multicolumn{6}{@{}l}{\\rule{0pt}{2.6ex}\\textbf{%s}} \\\\" % r[1])
    else: o.append("\\texttt{%s} & %s & %s & %s & \\texttt{%s} & %s \\\\" % r)
o.append("\\end{longtable}}")
w('instr', '\n'.join(o) + '\n')
print('instructions:', sum(1 for r in I if r[0] != 'G'))
