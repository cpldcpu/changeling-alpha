#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Tests 2, 4, 5 and the bus hog experiment, and the fault insertions.
usage: python3 -I tests/stress_t4.py extras|hog|host|ws|fwd|faults [args]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sx
def s1(c0defs, c1defs, cdiv, plus, dur=45000, cpb=60, hb=8, spi=True, uart=True, c1src='fwx_c1', name='t4', hexes=None):
    n0 = sx.c0('%s_c0' % name, c0defs)
    if hexes: n1 = hexes
    else: n1 = sx.build(c1src, '%s_c1' % name, 1, c1defs)
    args = ['+hex0=build/%s.hex' % n0, '+hex1=build/%s.hex' % n1, '+stress=1', '+cdiv=%d' % cdiv]
    if uart: args += ['+uart', '+ucpb=%d' % cpb, '+sn=%d' % min(1000, max(60, int(dur / (10 * cpb))))]
    else: args += ['+sxnouart', '+sxtime=%d' % dur]
    if spi: args += ['+spislv', '+spislv_mode=0', '+spislv_gapfree']
    args += list(plus) + ['+maxcyc=%d' % (dur * 4 * cdiv + 300000)]
    return sx.parse(sx.sim(args, timeout=600))
def show(label, d, grep=('STRESSPWM', 'STRESSTIMER', 'STRESS HOST', 'STRESS FAIL', 'STRESSFW')):
    print('%s: %s' % (label, sx.line(d)), flush=True)
    for l in d['out'].splitlines():
        if any(l.startswith(g) for g in grep): print('    ' + l[:260])
    sys.stdout.flush()
if __name__ == '__main__':
    what = sys.argv[1]
    if what == 'extras':
        cds = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1, 2]
        arbs = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [0, 1, 2]
        for c in cds:
            for a in arbs:
                d = s1('-DROLE_ECHO -DTWO -DARBV=%d -DEXTRAS' % a, '-DROLE_SPIM', c, ['+extras'], name='ex')
                show('extras (UART + SPI + PWM + compare A stamps in core 0) cdiv %d ARB %d' % (c, a), d, grep=('STRESSPWM', 'STRESSTIMER', 'STRESS FAIL', 'SPISLV FAIL'))
    elif what == 'extras2':         # compare B served by core 1 as well (an interrupt in the SPI master core)
        cds = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1, 2]
        arbs = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [0, 1, 2]
        for c in cds:
            for a in arbs:
                d = s1('-DROLE_ECHO -DTWO -DARBV=%d -DEXTRAS -DOCBX' % a, '-DROLE_SPIM -DOCB_STAMP', c, ['+extras', '+ocbx'], name='ex2')
                show('extras with compare B stamps in core 1, cdiv %d ARB %d' % (c, a), d, grep=('STRESSPWM', 'STRESSTIMER', 'STRESS FAIL', 'SPISLV FAIL'))
    elif what == 'hog':
        cds = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1, 2]
        for c in cds:
            for a in (0, 1, 2):
                # hog on core 1, UART echo on core 0
                for cpb in (60, 16, 8, 6):
                    d = s1('-DROLE_ECHO -DCPB=%d -DTWO -DARBV=%d' % (cpb, a), '-DROLE_HOG', c, [], cpb=cpb, spi=False, name='hog1')
                    print('hog on core 1, UART core 0, cdiv %d ARB %d cpb %d: %s' % (c, a, cpb, sx.line(d)), flush=True)
                    if not d['pass']: break
                # hog on core 0, SPI master on core 1
                for hb in (8, 6, 4):
                    d = s1('-DROLE_HOG -DTWO -DARBV=%d' % a, '-DROLE_SPIM -DHB=%d' % hb, c, [], hb=hb, uart=False, name='hog0')
                    print('hog on core 0, SPI master core 1, cdiv %d ARB %d hb %d: %s' % (c, a, hb, sx.line(d)), flush=True)
                    if not d['pass']: break
    elif what == 'host':
        cds = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1]
        ks = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [1, 2, 3, 4, 5]
        for c in cds:
            for k in ks:
                d = s1('-DROLE_ECHO -DTWO -DARBV=0', '-DROLE_SPIM', c, ['+sxhost=%d' % k], name='host')
                show('host action %d, cdiv %d' % (k, c), d, grep=('STRESS HOST', 'STRESS FAIL', 'STRESSFW', 'SPISLV FAIL', 'SPISLV PASS'))
    elif what == 'ws':
        cds = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1, 2, 4, 8, 16]
        for c in cds:
            n = sx.build('fwx_ws', 'ws100', 0, '-DNLED=100')
            out = sx.sim(['+hex=build/%s.hex' % n, '+stress=7', '+ws', '+cdiv=%d' % c, '+snfr=2', '+maxcyc=%d' % (900000 * min(c, 4) + 300000)], timeout=900)
            d = sx.parse(out)
            print('WS2812 controller, 100 LEDs (300 bytes), cdiv %d: %s' % (c, 'PASS' if d['pass'] else 'FAIL'), flush=True)
            for l in out.splitlines():
                if l.startswith('STRESS WS') or l.startswith('STRESS FAIL'): print('    ' + l[:330])
            sys.stdout.flush()
    elif what == 'fwd':
        cds = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [1]
        es = [float(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [-10, -5, 0, 5, 10]
        js = [int(x) for x in sys.argv[4].split(',')] if len(sys.argv) > 4 else [0, 3]
        nb = int(sys.argv[5]) if len(sys.argv) > 5 else 100
        for c in cds:
            for j in js:
                for e in es:
                    n = sx.build('fwx_wsfwd', 'wsfwd%d' % nb, 0, '-DNBYTES=%d' % nb)
                    out = sx.sim(['+hex=build/%s.hex' % n, '+stress=8', '+ws', '+wpin=1', '+cdiv=%d' % c, '+snb=%d' % nb, '+snfr=3', '+swe=%s' % e, '+swj=%d' % j, '+swg=3200',
                                  '+maxcyc=%d' % (nb * 3 * 900 + 600000)], timeout=900)
                    d = sx.parse(out)
                    print('WS2812 LED with forwarding, %d bytes per frame, cdiv %d, bit time error %+.0f %%, jitter +-%d: %s' % (nb, c, e, j, 'PASS' if d['pass'] else 'FAIL'), flush=True)
                    for l in out.splitlines():
                        if l.startswith('STRESS WS') or l.startswith('    gap') or l.startswith('STRESS FAIL'): print('    ' + l[:330])
                    sys.stdout.flush()
    elif what == 'faults':
        RTL = "rcore8d.v rdual.v rlinecells.v rlcports.v revents.v rtimers.v rclock.v rhost.v rpe_top.v rpe_osc_stub.v".split()
        mac = " tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"
        def comp(d, out):
            import subprocess
            r = subprocess.run('iverilog -g2005 -DSIM -DFUNCTIONAL -o %s tb/tb_sys.v %s%s' % (out, ' '.join('%s/%s' % (d, f) for f in RTL), mac), shell=True, cwd=sx.ROOT)
            assert r.returncode == 0
        def check(label, d, want_fail=True):
            ok = (not d['pass']) == want_fail
            print('%s %s: %s' % ('ok  ' if ok else 'MISSED', label, sx.line(d)), flush=True)
        # firmware / model faults
        d = s1('-DROLE_ECHO -DCPB=64 -DTWO -DARBV=0', '-DROLE_SPIM', 1, [], name='f1'); check('UART firmware at 64 cycles per bit, model at 60', d)
        d = s1('-DROLE_ECHO -DTWO -DARBV=0', '-DROLE_SPIM -DMODE=2', 1, [], name='f2'); check('SPI master firmware in mode 2, model in mode 0', d)
        d = s1('-DROLE_ECHO -DTWO -DARBV=0', '-DROLE_SPIM -DSPIBAD', 1, ['+sxhost=3'], name='f3'); check('one wrong SPI byte, host halts core 0 (the check "SPI undisturbed" must fire)', d)
        d = s1('-DROLE_ECHO -DTWO -DARBV=0', '-DROLE_SPIM', 1, [], name='f4a'); check('reference run for the faults (must pass)', d, want_fail=False)
        # RTL faults, temporary copies
        comp('build/rtlf_a', 'build/tb_fa.vvp')
        sx.VVP = os.path.join(sx.ROOT, 'build', 'tb_fa.vvp')
        d = s1('-DROLE_ECHO -DTWO -DARBV=0', '-DROLE_SPIM', 1, [], name='f5'); check('RTL copy: core 1 is granted even when core 0 is granted (g1 = req1), ARB 0', d)
        comp('build/rtlf_b', 'build/tb_fb.vvp')
        sx.VVP = os.path.join(sx.ROOT, 'build', 'tb_fb.vvp')
        d = s1('-DROLE_ECHO -DTWO -DARBV=0 -DEXTRAS -DOCBX', '-DROLE_SPIM -DOCB_STAMP', 1, ['+extras', '+ocbx'], name='f6'); check('RTL copy: core 1 reads DLYH from the latch of core 0', d)
