#!/usr/bin/env python3
"""Helpers for the stress tests: build images, run the simulation, parse the summary lines.
usage from a script:  import sx; r = sx.run(...)"""
import subprocess, re, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VVP = os.path.join(ROOT, 'build', 'tb_sys.vvp')
_built = {}
def build(src, out, core, defs):
    key = (src, out, core, defs)
    if _built.get(out) == key: return out
    r = subprocess.run(['sh', 'fw/build_x.sh', src, out, str(core), defs], cwd=ROOT, capture_output=True, text=True)
    if r.returncode: raise RuntimeError('build failed %s %s\n%s' % (out, defs, r.stderr[-2000:]))
    _built[out] = key
    return out
def c0(out, defs): return build('fwx_c0', out, 0, defs)
def c1(out, defs): return build('fwx_c1', out, 1, defs)
def sim(args, timeout=300, show=False):
    cmd = ['vvp', '-n', VVP] + args
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return r.stdout
def parse(out):
    d = {'pass': 'STRESS PASS' in out, 'fail': 'STRESS FAIL' in out or 'TIMEOUT' in out or ('STRESS PASS' not in out)}
    m = re.search(r'STRESSMON cycles (\d+), held core0 (\d+) core1 (\d+), bus requests core0 (\d+) core1 (\d+), both in the same cycle (\d+)', out)
    if m: d['cyc'], d['h0'], d['h1'], d['q0'], d['q1'], d['both'] = map(int, m.groups())
    for m in re.finditer(r'STRESSMON service (\w+): n (\d+), min (\d+), mean (\d+\.\d), max (\d+) cycles, held cycles inside the window max (\d+), events before the previous was served (\d+)', out):
        d[m.group(1)] = dict(n=int(m.group(2)), min=int(m.group(3)), mean=float(m.group(4)), max=int(m.group(5)), hw=int(m.group(6)), ovl=int(m.group(7)))
    m = re.search(r'STRESSFW core1: rounds (\d+), first error (\d+), errors (\d+); core0: units (\d+), first error (\d+), errors (\d+)', out)
    if m: d['fw'] = tuple(map(int, m.groups()))
    d['fails'] = re.findall(r'(?:STRESS FAIL: .*|SPISLV FAIL.*|SPIMST FAIL.*|I2CS FAIL.*|I2CM FAIL.*|WS2812.*FAIL.*)', out)[:6]
    d['out'] = out
    return d
def line(d):
    s = 'PASS' if d['pass'] else 'FAIL'
    for k in ('rx0', 'rx1'):
        if k in d: s += ' %s n%d mean%.1f max%d hw%d' % (k, d[k]['n'], d[k]['mean'], d[k]['max'], d[k]['hw'])
    if 'h0' in d: s += ' hold %d/%d' % (d['h0'], d['h1'])
    if 'fw' in d: s += ' fw %s' % (d['fw'],)
    if d['fails'] and not d['pass']: s += ' | ' + ' ; '.join(d['fails'][:2])
    return s
