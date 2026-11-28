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
RSV = "\\textcolor{black!45}{--}"

def bitstrip(bit_rows):
    """Render an 8-bit register bit strip. bit_rows is [(label, [(span, text), ...]), ...].
    text None renders a grey reserved '--' field."""
    o = [
        "{\\centering\\footnotesize\\setlength{\\tabcolsep}{2pt}%",
        "\\begin{tabular}{@{}|>{\\centering\\arraybackslash}p{12mm}|*{8}{>{\\centering\\arraybackslash}p{16.9mm}|}@{}}",
        "\\hline",
        "\\rowcolor{fillD}\\textbf{Bit} & \\textbf{7} & \\textbf{6} & \\textbf{5} & \\textbf{4} & \\textbf{3} & \\textbf{2} & \\textbf{1} & \\textbf{0} \\\\ \\hline",
    ]
    for lbl, spans in bit_rows:
        assert sum(s for s, _ in spans) == 8, (lbl, spans)
        cells = []
        for s, txt in spans:
            inner = RSV if txt is None else f"\\texttt{{{txt}}}"
            cells.append(inner if s == 1 else f"\\multicolumn{{{s}}}{{c|}}{{{inner}}}")
        o.append(f"{lbl} & " + " & ".join(cells) + " \\\\ \\hline")
    o.append("\\end{tabular}\\par}")
    return "\n".join(o)

def regblock(name, addr, access, reset, bit_rows, fields, extra=None):
    """Render a self-contained register card: header bar + 8-bit strip + bit-field table."""
    lines = [
        "\\par\\vspace{5pt}\\noindent\\begin{minipage}{\\linewidth}",
        f"\\reghead{{{name}}}{{{addr}}}{{{access}}}{{{reset}}}",
    ]
    if bit_rows:
        lines += ["\\vspace{2pt}", bitstrip(bit_rows)]
    if fields:
        lines += [
            "\\vspace{2pt}",
            "{\\small\\begin{tabularx}{\\linewidth}{@{}llL@{}}",
            "\\toprule",
            "Bits & Field & Description \\\\",
            "\\midrule",
        ]
        for b, fld, desc in fields:
            fcol = f"\\reg{{{fld}}}" if fld else RSV
            lines.append(f"\\texttt{{{b}}} & {fcol} & {desc} \\\\")
        lines += ["\\bottomrule", "\\end{tabularx}\\par}"]
    if extra:
        lines.append(extra)
    lines.append("\\end{minipage}\\par")
    return "\n".join(lines)

def simple_reg(name, addr, access, reset, desc):
    """Render a compact whole-byte or multi-byte register card without a redundant bit box."""
    return "\n".join([
        "\\par\\vspace{5pt}\\noindent\\begin{minipage}{\\linewidth}",
        f"\\reghead{{{name}}}{{{addr}}}{{{access}}}{{{reset}}}",
        "\\vspace{2pt}",
        f"{{\\small\\noindent {desc}\\par}}",
        "\\end{minipage}\\par",
    ])

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

# ---- chapter tables (per-register cards: bit strips + field descriptions for bitfields, compact cards for whole-byte registers)
w('core', "\n\n".join([
    simple_reg('CCP', '0x3C', 'W, per core', '--',
               'Signature for protected writes: writing \\texttt{0xD8} allows a core to write a protected register within the next four instructions'),
    simple_reg('SPL', '0x3D', 'R/W, per core', '\\texttt{0x00}',
               'Stack pointer, low byte (bits 7 to 0)'),
    regblock('SPH', '0x3E', 'R/W, per core', '\\texttt{0x00}',
             [("\\textbf{Field}", [(4, None), (4, "SP[11:8]")])],
             [("3:0", "SPH", "Stack pointer, high bits (bits 11 to 8)")]),
    regblock('SREG', '0x3F', 'R/W, per core', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"I"),(1,"T"),(1,"H"),(1,"S"),(1,"V"),(1,"N"),(1,"Z"),(1,"C")])],
             [
                 ("7", "I", "Global interrupt enable (set by \\texttt{SEI}/\\texttt{RETI}, cleared on interrupt entry or \\texttt{CLI})"),
                 ("6", "T", "Bit copy storage (used by \\texttt{BST} and \\texttt{BLD})"),
                 ("5", "H", "Half-carry flag"),
                 ("4", "S", "Sign flag ($N \\oplus V$)"),
                 ("3", "V", "Two's complement overflow flag"),
                 ("2", "N", "Negative flag"),
                 ("1", "Z", "Zero flag"),
                 ("0", "C", "Carry flag"),
             ]),
]))

w('twocore', "\n\n".join([
    regblock('CORECTL', '0x0E', 'R/W (bit 7 per core)', '\\texttt{0x01}',
             [("\\textbf{Field}", [(1,"ID"),(1,None),(1,"WAIT1"),(1,"WAIT0"),(2,None),(1,"EN1"),(1,"EN0")])],
             [
                 ("7", "ID", "Number of the core that reads the register (0 or 1). Read only"),
                 ("5:4", "WAIT1, WAIT0", "The core is waiting (1 while executing \\texttt{SLEEP}). Read only"),
                 ("1:0", "EN1, EN0", "Core enable. Setting a bit starts that core at word 0 of its code memory; clearing it stops the core"),
             ]),
    regblock('LOCK', '0x05', 'R/W (per-core view)', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"OTH3"),(1,"OTH2"),(1,"OTH1"),(1,"OTH0"),(1,"LK3"),(1,"LK2"),(1,"LK1"),(1,"LK0")])],
             [
                 ("7:4", "OTH3..OTH0", "Read only: 1 when the other core holds lock $n$ ($n=0..3$)"),
                 ("3:0", "LK3..LK0", "Read: 1 when the reading core holds lock $n$. Write 1 to take the lock if free; write 0 to release it if held by the writing core"),
             ]),
    regblock('ARB', '0x3F50', 'R/W, protected', '\\texttt{0x00}',
             [("\\textbf{Field}", [(6,None),(2,"MODE")])],
             [
                 ("1:0", "MODE", "Bus arbitration when both cores request the shared bus: 0 alternating (first collision after reset goes to core 0), 1 always core 0, 2 always core 1, 3 reserved"),
             ]),
]))

w('mem', "\n\n".join([
    regblock('PMCR', '0x3F58', 'R/W, protected', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"LOCK"),(5,None),(1,"XWE"),(1,"PWE")])],
             [
                 ("7", "LOCK", "Blocks all program writes by the cores until the next reset; can be set but not cleared. Host link writes are unaffected"),
                 ("1", "XWE", "Stores by a core to the other core's code memory are accepted"),
                 ("0", "PWE", "Stores by a core to its own code memory are accepted"),
             ]),
    simple_reg('PMLIM', '0x3F59', 'R/W, protected', '\\texttt{0x00}',
               'Stores to word addresses below $4 \\times \\mathtt{PMLIM}$, in either code memory, are ignored'),
]))

w('clock', "\n\n".join([
    regblock('CLKSTAT', '0x0F', 'R', '--',
             [("\\textbf{Field}", [(1,"STRAP"),(1,None),(1,"MVALID"),(1,"MDONE"),(1,"TRIMD"),(1,"EXTP"),(1,"OSCRUN"),(1,"SRC")])],
             [
                 ("7", "STRAP", "Level of the clock source strap pin"),
                 ("5", "MVALID", "The last completed measurement fell inside the target window"),
                 ("4", "MDONE", "The last trim measurement is complete"),
                 ("3", "TRIMD", "Copy of \\reg{CLKCTL.TRIMD}, set by whoever trimmed the oscillator"),
                 ("2", "EXTP", "Edges were seen on the external clock pin"),
                 ("1", "OSCRUN", "The internal ring oscillator is running"),
                 ("0", "SRC", "Active system clock source: 0 external clock, 1 internal ring oscillator"),
             ]),
    regblock('CLKCTL', '0x3F20', 'R/W, protected', 'strap',
             [("\\textbf{Field}", [(1,"RELAXEN"),(1,"REFCELL"),(2,"REFSEL"),(1,"TRIMD"),(1,"LOOP"),(1,"OSCEN"),(1,"SRC")])],
             [
                 ("7", "RELAXEN", "Enables the internal $\\sim$100\\,kHz relaxation oscillator (reset 0)"),
                 ("6", "REFCELL", "Receive cell supplying the line-cell reference event (0 or 1; reset 0)"),
                 ("5:4", "REFSEL", "Trim reference: 0 host link clock, 1 reference pin, 2 line cell reference event, 3 relaxation oscillator (reset 0)"),
                 ("3", "TRIMD", "Free status flag set by firmware/host once the oscillator has been trimmed (reset 0)"),
                 ("2", "LOOP", "Closed trim loop enable: after each valid measurement \\reg{OSCTRIM} steps by 1 towards \\reg{TRTGT} (reset 0)"),
                 ("1", "OSCEN", "Enables the internal ring oscillator (reset = strap). Also forced on while it is the active or requested source"),
                 ("0", "SRC", "Requested clock source: 0 external, 1 internal ring (reset = strap). Switchover executes once target edges are seen"),
             ]),
    simple_reg('OSCTRIM', '0x3F21', 'R/W', '\\texttt{0x80}',
               '8-bit trim value of the internal ring oscillator. A higher value gives a higher frequency'),
    simple_reg('CLKCDIV', '0x3F22', 'R/W, protected', '\\texttt{0x01}',
               'Core clock divider minus one: cores advance in 1 of every $\\mathtt{CDIV}+1$ source cycles (1 to 256). Value 0 is allowed only for a source clock of 30\\,MHz or less'),
    simple_reg('CLKPDIV', '0x3F23', 'R/W', '\\texttt{0x00}',
               'Peripheral clock divider minus one: peripherals advance in 1 of every $\\mathtt{PDIV}+1$ source cycles (1 to 256)'),
    regblock('TRINT', '0x3F24', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"MEAS"),(7,"INT")])],
             [
                 ("7", "MEAS", "Write 1 to start a single measurement against host link or reference pin and clear \\reg{MDONE}. Reads 1 while waiting/running; reads 0 for line-cell reference"),
                 ("6:0", "INT", "Reference periods per measurement, minus one (1 to 128). Not used with a line-cell reference, which runs from one event to the next"),
             ]),
    simple_reg('TRCNTL, TRCNTH', '0x3F25, 0x3F26', 'R', '\\texttt{0x00}',
               'Source clock cycles counted in the last measurement; saturates at \\texttt{0xFFFF}. Reading \\reg{TRCNTL} latches \\reg{TRCNTH} (one shared latch)'),
    simple_reg('TRTGTL, TRTGTH', '0x3F27, 0x3F28', 'R/W', '\\texttt{0x00}',
               '16-bit target count corresponding to the nominal clock frequency'),
    simple_reg('TRWIN', '0x3F29', 'R/W', '\\texttt{0x00}',
               'Validity window in units of 64 counts ($|\\mathtt{TRCNT}-\\mathtt{TRTGT}| < 64\\times\\mathtt{TRWIN}$); 0 accepts every measurement. With a line-cell ref $>0$, events before target$-$window are ignored'),
    regblock('CLKOUT', '0x3F2A', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"EN"),(4,None),(3,"DIV")])],
             [
                 ("7", "EN", "Enable the divided source clock output on pin \\reg{CKO}"),
                 ("2:0", "DIV", "Clock output divider: source clock divided by $2^{\\mathtt{DIV}+1}$ (2 to 256)"),
             ]),
]))

w('ports', "\n\n".join([
    simple_reg('PINR, DDR, PORT', '0x00, 0x01, 0x02', 'R / R/W', '-- / \\texttt{0x00}',
               'Bit $k$ corresponds to bidirectional pin $k$. \\reg{PINR}: synchronised pin input levels (R). \\reg{DDR}: direction, 1 = output. \\reg{PORT}: output value (when not overridden by a line cell or PWM)'),
    regblock('PINB', '0x03', 'R', '--',
             [("\\textbf{Field}", [(1,"IN7"),(1,"IN6"),(1,"IN5"),(1,"REF"),(1,"STRAP"),(1,"HMOSI"),(1,"HCS"),(1,"HSCK")])],
             [
                 ("7:5", "IN7..IN5", "Synchronised levels of dedicated input pins \\texttt{ui\\_in[7:5]}"),
                 ("4", "REF", "Reference clock input pin (\\texttt{ui\\_in[4]})"),
                 ("3", "STRAP", "Clock source strap input pin (\\texttt{ui\\_in[3]})"),
                 ("2:0", "HMOSI, HCS, HSCK", "Host link data in, chip select and clock pins (\\texttt{ui\\_in[2:0]})"),
             ]),
    regblock('PORTC', '0x04', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"OUT7"),(1,"OUT6"),(1,"OUT5"),(1,"OUT4"),(1,"OUT3"),(1,"DBG"),(1,"CKO"),(1,None)])],
             [
                 ("7:3", "OUT7..OUT3", "Dedicated output pins \\texttt{uo\\_out[7:3]} (overridden when PWM is enabled on \\texttt{OUT5..7})"),
                 ("2", "DBG", "Debug pin \\texttt{uo\\_out[2]} when \\reg{DBGSEL.EN} = 0"),
                 ("1", "CKO", "Clock output pin \\texttt{uo\\_out[1]} when \\reg{CLKOUT.EN} = 0"),
                 ("0", "", "Reserved (driven by host link MISO \\texttt{uo\\_out[0]})"),
             ]),
    simple_reg('ODE, PCMSK', '0x3F53, 0x3F54', 'R/W', '\\texttt{0x00}',
               '\\reg{ODE}: open-drain enable per pin (bit $k=1$: driven low only, high releases the pin). \\reg{PCMSK}: pin-change mask (edges on unmasked pins set \\reg{IFRL.PC})'),
]))

w('events', "\n\n".join([
    regblock('IFRL (and IERL, WAITL)', '0x06 (0x22, 0x20)', 'W1C / R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"DLY"),(1,"TRIM"),(1,"MBX"),(1,"OVF"),(1,"OCB"),(1,"OCA"),(1,"CAPT"),(1,"PC")])],
             [
                 ("7", "DLY", "Shared time base reached the reading core's wake-up time (per core). Cleared by writing a new wake-up time to \\reg{DLYL/H}"),
                 ("6", "TRIM", "Trim counter completed a measurement inside the target window. Latched, W1C"),
                 ("5", "MBX", "Host mailbox holds an unread byte from the host. Level, follows \\reg{MBSTAT.RXF}"),
                 ("4", "OVF", "16-bit timer overflow. Latched, W1C"),
                 ("3:2", "OCB, OCA", "16-bit timer compare B and compare A match. Latched, W1C"),
                 ("1", "CAPT", "16-bit timer input capture. Latched, W1C"),
                 ("0", "PC", "Pin change on an unmasked bidirectional pin (\\reg{PCMSK}). Latched, W1C"),
             ],
             extra="\\noindent{\\footnotesize\\reg{IERL} (\\texttt{0x22}) enables interrupts and \\reg{WAITL} (\\texttt{0x20}) sets the wait mask for the same bit positions (one register per core); writing \\reg{WAITL} starts the wait.}"),
    regblock('IFRH (and IERH, WAITH)', '0x07 (0x23, 0x21)', 'mixed / R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"SW3"),(1,"SW2"),(1,"SW1"),(1,"SW0"),(1,"LT1"),(1,"LR1"),(1,"LT0"),(1,"LR0")])],
             [
                 ("7:4", "SW3..SW0", "Software flags shared by both cores (R/W; set with \\texttt{SBI}, cleared with \\texttt{CBI})"),
                 ("3:0", "LT1..LR0", "Line-cell event flags (a status bit selected in \\reg{LCEVM} is set). Level; visible only to the pair's owner core (\\reg{LCOWN})"),
             ],
             extra="\\noindent{\\footnotesize\\reg{IERH} (\\texttt{0x23}) and \\reg{WAITH} (\\texttt{0x21}) use the same bit positions per core.}"),
    simple_reg('DLYL, DLYH', '0x24, 0x25', 'R / W (per core)', '\\texttt{0x00}',
               "Read returns the shared 16-bit free-running peripheral time base. Write sets this core's wake-up time and clears \\reg{IFRL.DLY}"),
]))

w('timer', "\n\n".join([
    simple_reg('TCNTL, TCNTH', '0x26, 0x27', 'R/W', '\\texttt{0x00}',
               '16-bit timer counter. Counts peripheral clock cycles divided by $2^{\\mathtt{PS}}$ while \\reg{TCR.RUN} = 1'),
    simple_reg('ICRL, ICRH', '0x28, 0x29', 'R', '\\texttt{0x00}',
               'Input capture value: receives a copy of \\reg{TCNT} and sets \\reg{IFRL.CAPT} on the edge configured in \\reg{TCAP}'),
    regblock('TCR', '0x3F30', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"RUN"),(1,"CTC"),(3,None),(3,"PS")])],
             [
                 ("7", "RUN", "Timer enable: 1 counter runs, 0 counter stops (retains value)"),
                 ("6", "CTC", "Clear timer on compare A: count resets to 0 after matching \\reg{OCRA} (period = \\reg{OCRA}+1)"),
                 ("2:0", "PS", "Clock prescaler: divides the peripheral clock by $2^{\\mathtt{PS}}$ (1 to 128)"),
             ]),
    regblock('TCAP', '0x3F31', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"CEDGE"),(2,"CSRC"),(2,None),(3,"CPIN")])],
             [
                 ("7", "CEDGE", "Pin capture edge when \\reg{CSRC} = 0: 0 rising edge, 1 falling edge"),
                 ("6:5", "CSRC", "Capture source: 0 bidirectional pin \\reg{CPIN}, 1 accepted edge of receive cell \\reg{CPIN} (0 or 1), 2 reference event of receive cell \\reg{CPIN}, 3 off"),
                 ("2:0", "CPIN", "Bidirectional pin (0 to 7) when \\reg{CSRC} = 0, or receive cell number (0 or 1) when \\reg{CSRC} = 1 or 2"),
             ]),
    simple_reg('OCRAL/H, OCRBL/H', '0x3F32/33, 0x3F34/35', 'R/W', '\\texttt{0x00}',
               '16-bit compare registers. Matching \\reg{TCNT} sets \\reg{IFRL.OCA} or \\reg{IFRL.OCB}'),
]))

w('pwm', "\n\n".join([
    regblock('PWMC', '0x3F38', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,None),(3,"PPS"),(1,None),(1,"PEN2"),(1,"PEN1"),(1,"PEN0")])],
             [
                 ("6:4", "PPS", "PWM prescaler: divides the peripheral clock by $2^{\\mathtt{PPS}}$ (1 to 128)"),
                 ("2:0", "PEN2..PEN0", "Channel enables for PWM0, PWM1, PWM2 on dedicated outputs \\reg{OUT5}, \\reg{OUT6}, \\reg{OUT7}"),
             ]),
    simple_reg('PWMTOP', '0x3F39', 'R/W', '\\texttt{0x00}',
               'Common period minus one: shared counter wraps from \\reg{PWMTOP} to 0 (period = $\\mathtt{PWMTOP}+1$ ticks)'),
    simple_reg('PWM0..PWM2', '0x3F3A--3C', 'R/W', '\\texttt{0x00}',
               'High time of channels 0 to 2 in timer ticks (output is high while counter $<$ \\reg{PWMn})'),
]))

w('crc', "\n\n".join([
    regblock('CRCIN (W) / CRCST (R)', '0x2A', 'W (IN) / R (ST)', '\\texttt{0x00}',
             [("\\texttt{Write}", [(8,"data byte")]), ("\\texttt{Read}", [(1,"EQF"),(1,"EQ"),(1,"BUSY"),(5,None)])],
             [
                 ("7:0 (W)", "CRCIN", "Write one data byte to feed the CRC unit (processes over 4 cycles); only accepted from owner core"),
                 ("7 (R)", "EQF", "Latched equality comparison at last frame boundary (\\reg{CRCVAL} == \\reg{CRCREF} at last receive frame bit or last step of \\reg{CRCIN})"),
                 ("6 (R)", "EQ", "\\reg{CRCVAL} equals \\reg{CRCREF} now (with left shift, compares the low \\reg{CRCLEN}+1 bits)"),
                 ("5 (R)", "BUSY", "1 while a byte written to \\reg{CRCIN} is being processed (4 clock cycles). Read only"),
             ]),
    regblock('CRCCTL', '0x3F40', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"EN"),(1,"RIGHT"),(3,"CSRC"),(1,None),(1,"BUSY"),(1,"OWNER")])],
             [
                 ("7", "EN", "CRC unit enabled"),
                 ("6", "RIGHT", "Shift direction: 0 left (towards MSB), 1 right (towards LSB)"),
                 ("5:3", "CSRC", "Bit source: 0 \\reg{CRCIN}, 1 receive cell 0, 2 transmit cell 0, 3 receive cell 1, 4 transmit cell 1 (stuffed bits excluded)"),
                 ("1", "BUSY", "Same busy flag as \\reg{CRCST.BUSY} (1 during 4-cycle \\reg{CRCIN} byte processing). Read only"),
                 ("0", "OWNER", "Core that owns the CRC unit (0 or 1); the other core reads 0 and its writes are ignored"),
             ]),
    regblock('CRCLEN', '0x3F41', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(3,None),(5,"width minus one")])],
             [
                 ("4:0", "CRCLEN", "CRC width minus one (0 to 31, giving widths of 1 to 32 bits)"),
             ]),
    simple_reg('CRCPOLY0..3, CRCVAL0..3, CRCREF0..3', '0x3F42--4D', 'R/W', '\\texttt{0x00}',
               '\\reg{CRCPOLY} (\\texttt{0x3F42..45}): generator polynomial. \\reg{CRCVAL} (\\texttt{0x3F46..49}): initial/current CRC state. \\reg{CRCREF} (\\texttt{0x3F4A..4D}): expected residual compared against \\reg{CRCVAL} for \\reg{EQ}/\\reg{EQF}'),
]))

w('host', "\n\n".join([
    regblock('MBSTAT', '0x0C', 'R', '\\texttt{0x40}',
             [("\\textbf{Field}", [(1,"RXF"),(1,"TXE"),(6,None)])],
             [
                 ("7", "RXF", "1 while an unread byte from the host is waiting in \\reg{MBDATA}"),
                 ("6", "TXE", "1 when the outgoing mailbox is empty (host has read the last byte written by a core)"),
             ]),
    simple_reg('MBDATA', '0x0D', 'R/W', '--',
               'Read: receives a byte written by the host (clears \\reg{RXF}). Write: sends a byte to the host (clears \\reg{TXE})'),
    regblock('DBGSEL', '0x3F52', 'R/W', '\\texttt{0x00}',
             [("\\textbf{Field}", [(1,"EN"),(3,None),(4,"SEL")])],
             [
                 ("7", "EN", "Enables routing the selected internal debug signal to pin \\reg{DBG} (\\texttt{uo\\_out[2]}, one clock cycle latency)"),
                 ("3:0", "SEL", "Debug signal: 0/1 sample point R0/R1, 2/3 TX bit T0/T1, 4/5 accepted edge R0/R1, 6/7 ref event R0/R1, 8/9 core 0/1 enable, 10 \\texttt{bus\\_hold}, 11 peripheral CKE, 12 core CKE, 13 trim measurement active, 14 valid measurement, 15 synchronised relaxation oscillator"),
             ]),
]))

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
