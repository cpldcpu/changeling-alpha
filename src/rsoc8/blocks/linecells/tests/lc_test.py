#!/usr/bin/env python3
"""Line cells (receive cell, transmit cell) against the behavioural model: protocol cases and random configurations.
usage: lc_test.py [number of random cases]"""
import os, random, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "model"))
from linecell import Cell

def cfg_bytes(c, unit=0):
    """Configuration of the receive cell (15 bytes), one unused byte, and of the transmit cell."""
    g = lambda k, d=0: c.get(k, d)
    rx = [g("RXEN") << 7 | g("RXEN") << 6 | unit << 4,                                # LCCTRL
          0x00, 0x00,                                                                  # LCPIN: pin 0
          1 << 5 | g("CPHA") << 1 | g("BLEN"),                                         # LCCLK: second pin = pin 1
          g("EDGE") << 6 | g("ACC") << 5 | g("STOP") << 3 | g("TWOPH") << 2 | g("TRIG"),
          g("A", 1) & 255, g("B", 1) & 255, 0, g("DEC", 0xF0), 0,
          g("LEN", 7) << 5 | g("LSBF") << 4 | g("MEN") << 1,
          g("MATCH"), g("LIM") << 5 | g("RMODE") << 4 | g("REF"), 0x00, 0x00, g("PAR")]
    tx = [g("TXEN") << 7 | g("TXEN") << 5, 0x00, 0x00, g("CPOL") << 2 | g("CPHA") << 1,
          g("TWOPH") << 2, g("A", 1) & 255, g("B", 1) & 255, g("C", 1) & 255, 0, g("ENC", 0xF0),
          g("LEN", 7) << 5 | g("LSBF") << 4 | g("CMP") << 2 | g("SS"), 0,
          g("LIM") << 5 | g("RMODE") << 4 | g("LOW2") << 3 | g("IDLE") << 2, 0x00, 0x00, g("PAR")]
    return rx + tx

def rtl(c, stim, txq=(), stimf=None, unit=0, tag="t"):
    p = "build/lc_%s" % tag
    open(p + ".cfg", "w").write("\n".join("%02x" % b for b in cfg_bytes(c, unit)) + "\n")
    open(p + ".stim", "w").write("\n".join("%02x" % b for b in stim) + "\n")
    args = ["vvp", "-n", "build/tb_lc.vvp", "+cfg=%s.cfg" % p, "+stim=%s.stim" % p, "+log=%s.log" % p, "+n=%d" % len(stim)]
    if stimf is not None:
        open(p + ".stimf", "w").write("\n".join("%02x" % b for b in stimf) + "\n"); args.append("+stimf=%s.stimf" % p)
    if txq:
        open(p + ".txq", "w").write("\n".join("%03x" % b for b in txq) + "\n"); args += ["+txq=%s.txq" % p, "+ntx=%d" % len(txq)]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
    r = {"R": [], "S": [], "E": [], "F": [], "W": [], "T": [], "X": []}
    for l in open(p + ".log"):
        f = l.split()
        if f[0] == "STAT": r["STAT"] = int(f[1], 16)
        elif f[0] == "R": r["R"].append((int(f[1]), int(f[2], 16)))
        elif f[0] == "W": r["W"].append((int(f[2]), int(f[3])))
        elif f[0] == "T": r["T"].append(int(f[2]))
        else: r[f[0]].append(int(f[1]))
    return r

# ---------------------------------------------------------------- transmit: waveform equal to the model
def model_tx(c, data, n):
    m = Cell(**{k: v for k, v in c.items() if k != "REF"})
    q = list(data); w = []
    for _ in range(n):
        if q and m.TXE: m.write(q.pop(0))
        w.append(m.step())
    return w

def check_tx(name, c, data, n):
    w = model_tx(c, data, n)
    r = rtl(c, [0] * n, data, tag="tx")
    for sh in (2, 1, 3, 0):
        if all(r["W"][k + sh] == w[k] for k in range(n - sh)):
            return (True, "%s: waveform equal, delay %d cycles" % (name, sh))
    k = next(k for k in range(n - 2) if r["W"][k + 2] != w[k])
    return (False, "%s: waveform differs at unit %d: model %s rtl %s" % (name, k, w[k:k + 6], r["W"][k + 2:k + 8]))

# ---------------------------------------------------------------- receive: frames, sample points, flags
def check_rx(name, c, x, x2=None, unit=0):
    m = Cell(**{k: v for k, v in c.items() if k != "REF"})
    frames = []
    x2 = x2 or [1] * len(x)
    if unit:                                            # the pins are stable in the first clock cycle
        x = [x[0]] + list(x[:-1]) if x[0] != x[1] else x
        x2 = [x2[0]] + list(x2[:-1]) if x2[0] != x2[1] else x2
    m.bothl = 1 if (c.get("BLEN") and x[0] == 0 and x2[0] == 0) else 0    # the cell follows the pins before it is enabled
    for k in range(len(x)):
        m.step(x[k], x2[k])
        while m.fifo: frames.append((k, m.read()))
    ref = [t for (t, kind, q) in m.refev if c.get("REF") == 2 or (c.get("REF") == 3 and q)] if c.get("REF", 0) >= 2 else \
          (m.edges if c.get("REF") == 1 else [])
    if unit:                                            # two model units per clock cycle
        n = len(x) // 2
        stimf = [x[2 * k] | x2[2 * k] << 1 for k in range(n)]; stim = [x[2 * k + 1] | x2[2 * k + 1] << 1 for k in range(n)]
        r = rtl(c, stim, stimf=stimf, unit=1, tag="rx")
        div = 2
    else:
        r = rtl(c, [a | b << 1 for a, b in zip(x, x2)], tag="rx")
        div = 1
    exp_fr = [(k // div + 1, v) for k, v in frames if k // div + 1 < len(r["W"])]
    exp_s = sorted(set(t // div for t in m.samples))
    exp_stat = m.FERR << 6 | m.EOPF << 5 | m.IDLEF << 4 | m.MATCHF << 3 | m.OVR << 2 | m.STUFF << 1
    bad = []
    if [v for _, v in r["R"]] != [v for _, v in exp_fr]: bad.append("frames %s / %s" % ([hex(v) for _, v in r["R"]][:12], [hex(v) for _, v in exp_fr][:12]))
    elif r["R"] != exp_fr: bad.append("frame times")
    if r["S"] != exp_s: bad.append("sample points (%d / %d)" % (len(r["S"]), len(exp_s)))
    if sorted(set(t // div for t in m.edges)) != r["E"]: bad.append("accepted edges")
    if r["STAT"] & 0x7E != exp_stat: bad.append("status %02x / %02x" % (r["STAT"] & 0x7E, exp_stat))
    if sorted(set(t // div for t in ref)) != r["F"]: bad.append("reference events")
    return (not bad, "%s: %s" % (name, "equal (%d frames, %d sample points)" % (len(frames), len(exp_s)) if not bad else "; ".join(bad)))

def resample(w, e, ph=0.0):
    n = int(len(w) * (1 + e)); return [w[min(len(w) - 1, int((k + ph) / (1 + e)))] for k in range(n)]

def protocol_cases():
    out = []
    data = [0x4B, 0x00, 0xFF, 0x55, 0xA5]
    # UART
    c = dict(TXEN=1, B=16, SS=1, LSBF=1, IDLE=1, ENC=0xF0)
    out.append(check_tx("UART transmit", c, data, 1000))
    w = [1] * 20 + [o for o, _ in model_tx(c, data, 900)]
    for e in (0, -0.03, 0.04):
        out.append(check_rx("UART receive, clock offset %+d %%" % round(100 * e), dict(RXEN=1, EDGE=2, ACC=1, STOP=2, A=24, B=16, DEC=0xF0, LSBF=1), resample(w, e, 0.5)))
    # UART with parity and with a ninth data bit (C7)
    for par, nm in ((2, "even parity"), (1, "odd parity"), (3, "ninth data bit")):
        d9 = [0x14B, 0x000, 0x1FF, 0x055, 0x1A5] if par == 3 else data
        c = dict(TXEN=1, B=16, SS=1, LSBF=1, IDLE=1, ENC=0xF0, PAR=par)
        out.append(check_tx("UART transmit, 8 data bits, %s" % nm, c, d9, 1100))
        nt = len(rtl(c, [0] * 1100, d9, tag="tx")["T"])
        out.append((nt == 8 * len(d9), "UART transmit, %s: %d strobes of data bits for %d frames (rule N4: none for the additional bit)" % (nm, nt, len(d9))))
        w = [1] * 20 + [o for o, _ in model_tx(c, d9, 1000)]
        rc = dict(RXEN=1, EDGE=2, ACC=1, STOP=2, A=24, B=16, DEC=0xF0, LSBF=1, PAR=par)
        for e in (0, -0.03, 0.04):
            out.append(check_rx("UART receive, %s, clock offset %+d %%" % (nm, round(100 * e)), rc, resample(w, e, 0.5)))
        nx = len(rtl(dict(rc), [a | 2 for a in w], tag="rx")["X"])
        out.append((nx == 8 * len(d9), "UART receive, %s: %d bit strobes for %d frames (rule N4)" % (nm, nx, len(d9))))
        if par != 3:
            w2 = list(w); k = 20 + 16 * (11 + 9) + 8; w2[k - 8:k + 8] = [1 - w2[k]] * 16      # parity bit of the second character inverted
            ok, msg = check_rx("UART receive, %s, parity bit of character 2 inverted" % nm, rc, w2)
            m = Cell(**rc)
            for x in w2: m.step(x, 1)
            out.append((ok and m.FERR == 1, msg + ("; FERR set" if m.FERR else "; FERR NOT set")))
    # USB low-speed
    pkt = [0x80, 0xC3, 0x00, 0xFF, 0xFF, 0x7E, 0x3F, 0xAA, 0x01]
    for upb in (10, 40):
        c = dict(TXEN=1, B=upb, LSBF=1, IDLE=0, ENC=0xA5, LIM=6)
        out.append(check_tx("USB transmit, %d units per bit" % upb, c, pkt, upb * 90))
        m = Cell(**c); q = list(pkt); body = []
        while q or not m.TXE or m.busy or not body:
            if q and m.TXE: m.write(q.pop(0))
            body.append(m.step())
        body = body[:-1]
        dp = [0] * (3 * upb) + [o for o, _ in body] + [0] * (14 * upb)
        dm = [1] * (3 * upb) + [n for _, n in body] + [0] * (2 * upb) + [1] * (12 * upb)
        rc = dict(RXEN=1, EDGE=3, ACC=0, STOP=0, A=upb // 2, B=upb, DEC=0xC3, LSBF=1, LIM=6, MEN=1, MATCH=0x80, BLEN=1, REF=2)
        for e in (0, -0.04, 0.05):
            out.append(check_rx("USB receive, %d units per bit, clock offset %+d %%" % (upb, round(100 * e)), rc, resample(dp, e, 0.25), resample(dm, e, 0.25)))
    rc = dict(RXEN=1, EDGE=3, ACC=0, STOP=0, A=5, B=10, DEC=0xC3, LSBF=1, LIM=6, MEN=1, MATCH=0x80, BLEN=1, REF=3)
    out.append(check_rx("USB keep-alive as reference event", rc, [0] * 420, [1] * 200 + [0] * 20 + [1] * 200))
    # 10BASE-T
    frame = [0x55] * 7 + [0xD5] + [0x00, 0xFF, 0x12, 0x34, 0xA5, 0x5A, 0x80, 0x01]
    for half in (6, 3):
        c = dict(TXEN=1, B=half, TWOPH=1, LSBF=1, IDLE=0, ENC=0xC3)
        out.append(check_tx("10BASE-T transmit, %d units per bit" % (2 * half), c, frame, 2 * half * 8 * 17 + 40))
        w = [0] * (4 * half) + [o for o, _ in model_tx(c, frame, 2 * half * 8 * 16 + 12 * half)]
        rc = dict(RXEN=1, EDGE=3, ACC=1, STOP=1, A=(3 * half) // 2, B=4 * half, DEC=0x0F, LSBF=1, MEN=1, MATCH=0xD5)
        for e in (0, -0.1, 0.1):
            ww = resample(w, e, 0.5)
            out.append(check_rx("10BASE-T receive, %d units per bit, clock offset %+d %%" % (2 * half, round(100 * e)), rc, ww))
            if half == 6:
                out.append(check_rx("10BASE-T receive on both clock edges, clock offset %+d %%" % round(100 * e), rc, ww[:len(ww) & ~1], unit=1))
    # WS2812
    px = [0xFF, 0x00, 0xA5, 0x3C]
    c = dict(TXEN=1, CMP=1, B=75, A=48, C=24, LSBF=0)
    out.append(check_tx("WS2812 transmit", c, px, 75 * 34))
    w = [0] * 100 + [o for o, _ in model_tx(c, px, 75 * 32 + 400)]
    for e in (0, -0.15, 0.2):
        out.append(check_rx("WS2812 receive, clock offset %+d %%" % round(100 * e), dict(RXEN=1, EDGE=1, ACC=1, STOP=1, A=36, B=150, DEC=0xF0, LSBF=0), resample(w, e, 0.5)))
    return out

def random_rx(seed):
    rnd = random.Random(seed)
    unit = seed % 3 == 0
    lo = 2 if unit else 1
    c = dict(RXEN=1, EDGE=rnd.choice([1, 2, 3, 3]), ACC=rnd.randrange(2), STOP=rnd.randrange(3), TWOPH=rnd.randrange(2),
             CPHA=rnd.randrange(2), A=rnd.randrange(lo, 30), B=rnd.randrange(lo, 30), DEC=rnd.choice([0xF0, 0x0F, 0xC3, rnd.randrange(256)]),
             LEN=rnd.choice([7, 7, rnd.randrange(8)]), LSBF=rnd.randrange(2), LIM=rnd.choice([0, 0, rnd.randrange(1, 8)]),
             RMODE=rnd.randrange(2), BLEN=rnd.randrange(2), REF=rnd.randrange(4))
    c["PAR"] = random.Random(seed + 5 * 10**6).choice([0, 0, 1, 2, 3])
    if rnd.random() < 0.4:
        c.update(MEN=1, MATCH=rnd.choice([0x00, 0xFF, 0x55, 0xAA, 0x80, rnd.randrange(256)]))
    n = 3000
    def wave(p_long):
        w = []; lvl = rnd.randrange(2)
        while len(w) < n:
            w += [lvl] * (rnd.randrange(1, 200) if rnd.random() < p_long else rnd.randrange(1, 2 * c["B"] + 3)); lvl ^= 1
        return w[:n]
    x = wave(0.05)
    x2 = wave(0.3) if c["BLEN"] else None
    return check_rx("random receive %d%s" % (seed, " (both clock edges)" if unit else ""), c, x, x2, unit=1 if unit else 0)

def random_tx(seed):
    rnd = random.Random(seed + 10**6)
    c = dict(TXEN=1, B=rnd.randrange(1, 12), A=rnd.randrange(1, 12), C=rnd.randrange(1, 12), LEN=rnd.choice([7, 7, rnd.randrange(8)]),
             LSBF=rnd.randrange(2), SS=rnd.randrange(2), IDLE=rnd.randrange(2), LIM=rnd.choice([0, 0, rnd.randrange(1, 8)]),
             RMODE=rnd.randrange(2), ENC=rnd.choice([0xF0, 0xA5, 0xC3, rnd.randrange(256)]), CPOL=rnd.randrange(2))
    if rnd.random() < 0.3: c["CMP"] = 1
    else: c["TWOPH"] = rnd.randrange(2)
    if rnd.random() < 0.1: c["LOW2"] = 1
    data = [rnd.choice([0x00, 0xFF, rnd.randrange(256)]) & ((2 << c["LEN"]) - 1) for _ in range(rnd.randrange(1, 7))]
    r2 = random.Random(seed + 6 * 10**6); c["PAR"] = r2.choice([0, 0, 1, 2, 3])
    if c["PAR"] == 3: data = [d | r2.randrange(2) << 8 for d in data]
    n = len(data) * (c["LEN"] + 5) * c["B"] * 2 * 2 + 60
    return check_tx("random transmit %d" % seed, c, data, n)

def main():
    nrand = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    os.makedirs("build", exist_ok=True)
    res = protocol_cases()
    for ok, msg in res: print(("ok   " if ok else "FAIL ") + msg)
    bad = sum(1 for ok, _ in res if not ok)
    rb = tb = 0
    for s in range(nrand):
        ok, msg = random_rx(s)
        if not ok:
            rb += 1
            if rb <= 5: print("FAIL " + msg)
        ok, msg = random_tx(s)
        if not ok:
            tb += 1
            if tb <= 5: print("FAIL " + msg)
    print("random configurations: %d receive cases, %d differ; %d transmit cases, %d differ" % (nrand, rb, nrand, tb))
    return bad + rb + tb

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
