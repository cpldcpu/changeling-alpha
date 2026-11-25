#!/usr/bin/env python3
"""Builds the formal check of the two-cycle timing exception for rdual with both cores.

Input:  a flattened Verilog netlist of rdual written by Yosys (flat.ys), in which every flip-flop is
        `always @(posedge clk) <reg> <= <expr>;`.
Output: rdual_comb.v  the same logic with every flip-flop cut open: the register value is an input, the
                      next value is an output (<reg>_d);
        exc_top.v     a wrapper that holds the registers, evaluates rdual_comb once with the real values (A)
                      and once per case with the values of the timing start points replaced by free values,
                      and asserts that nothing that is captured in that cycle differs.
"""
import re, sys

src = open(sys.argv[1]).read()
outdir = sys.argv[2]

# ------------------------------------------------------------------ cut the flip-flops open
hdr = re.search(r"module rdual\((.*?)\);", src, re.S)
ports = [p.strip() for p in hdr.group(1).replace("\n", " ").split(",")]
pdecl = {}
for m in re.finditer(r"^  (input|output) (\[\d+:\d+\] )?(\S+);", src, re.M):
    pdecl[m.group(3)] = (m.group(1), m.group(2) or "")
ffs = re.findall(r"^  always @\(posedge clk\)\n    (\\\S+ |\w+) ?<= (.*?);\n", src, re.M)   # escaped names end with a blank
assert len(ffs) == len(re.findall(r"always @", src)), "unexpected always block"
regs = {}
for name, expr in ffs:
    m = re.search(r"^  reg (\[\d+:\d+\] )?%s ?(= [^;]*)?;" % re.escape(name), src, re.M)        # an initial value is dropped: any start value
    assert m, name
    regs[name] = (m.group(1) or "", expr)

def width(rng):
    if not rng: return 1
    a, b = re.match(r"\[(\d+):(\d+)\]", rng).groups()
    return int(a) - int(b) + 1

# name of each register in the RTL: `assign \x = rst ? _reg_ : const;` (asynchronous reset moved behind the
# flip-flop by async2sync) or the register itself
rtlname = {}
for name in regs:
    m = re.search(r"^  assign (\S+)\s+= rst\w*_n \? %s : " % re.escape(name), src, re.M)
    rtlname[name] = (m.group(1) if m else name).lstrip("\\").strip()

comb = src
comb = re.sub(r"^  always @\(posedge clk\)\n    (\\\S+ |\w+) ?<= .*?;\n", "", comb, flags=re.M)
idx = {}
extra_ports, extra_decl = [], []
for i, (name, (rng, expr)) in enumerate(regs.items()):
    idx[name] = i
    comb = re.sub(r"^  reg (\[\d+:\d+\] )?%s ?(= [^;]*)?;" % re.escape(name), lambda m: "  wire %s%s;\n  assign %s = q%d;" % (rng, name, name, i), comb, flags=re.M)
    extra_ports += ["q%d" % i, "d%d" % i]
    extra_decl += ["  input %sq%d;" % (rng, i), "  output %sd%d;" % (rng, i), "  assign d%d = %s;" % (i, expr)]
comb = comb.replace(hdr.group(0), "module rdual_comb(" + ", ".join(ports + extra_ports) + ");\n" + "\n".join(extra_decl), 1)
assert "always" not in comb and not re.search(r"^  reg ", comb, re.M)
open(outdir + "/rdual_comb.v", "w").write(comb)

# ------------------------------------------------------------------ groups of registers
def group(pred): return [n for n in regs if pred(rtlname[n])]
START = group(lambda r: re.fullmatch(r"core[01]\.(state|ir)|jst|jmode|jcore|jword", r))
DQ    = group(lambda r: re.fullmatch(r"core[01]\.dq", r))
nbits = lambda g: sum(width(regs[n][0]) for n in g)
assert nbits(START) == 62, (nbits(START), [rtlname[n] for n in START])
assert nbits(DQ) == 16
print("registers: %d (%d bit); timing start points: %d bit; dq: %d bit" % (len(regs), nbits(regs), nbits(START), nbits(DQ)))

ins  = [p for p in ports if pdecl[p][0] == "input" and p not in ("clk",)]
outs = [p for p in ports if pdecl[p][0] == "output"]
MEMS = {"cm0": "cm0_rdata", "cm1": "cm1_rdata", "dm": "dm_rdata"}
FREE_IN = [p for p in ins if p not in ("rst_n", "rst_sys_n") and p not in MEMS.values()]

# outputs that something outside rdual captures in every clock cycle: (enable or None, signals)
STRICT = ["cm0_re", "cm0_we", "cm1_re", "cm1_we", "dm_re", "dm_we", "io_re", "io_we", "io_unlock", "irq_ack0", "irq_ack1",
          "brk_flag", "core_en", "core_wait", "core_cen", "bus_hold", "dbg_pc0", "dbg_pc1", "idle", "io_host",
          "cm_host", "inj_fail"]
COND = [("cm0_re | cm0_we", ["cm0_addr"]), ("cm0_we", ["cm0_wsel", "cm0_wdata", "cm0_wother"]),
        ("cm1_re | cm1_we", ["cm1_addr"]), ("cm1_we", ["cm1_wsel", "cm1_wdata", "cm1_wother"]),
        ("dm_re | dm_we", ["dm_addr"]), ("dm_we", ["dm_wdata"]),
        ("io_re | io_we", ["io_addr", "io_core"]), ("io_we", ["io_wdata", "io_wmask"])]
# Outputs that only the host link (rhost.v) uses. Its registers are constrained to one clock cycle from every
# start point (timing.sdc), so these outputs are outside the exception. With HOSTSTRICT=1 in the environment
# the status outputs are checked like the others, which shows why that constraint is needed.
import os
HOSTDATA   = ["h_rdata"]                # read data, captured one cycle after a host access
HOSTSTATUS = ["h_quiet", "inj_busy"]    # sampled when a command byte is complete, at any time
if os.environ.get("HOSTSTRICT"): STRICT += HOSTSTATUS; HOSTSTATUS = []
assert set(STRICT + [s for _, l in COND for s in l] + HOSTDATA + HOSTSTATUS) == set(outs)

# ------------------------------------------------------------------ wrapper
L = []
A = L.append
CHK = []                                                    # (expression that is true on a violation, description)
A("// Generated by gen_exc.py. Do not edit.")
A("module exc_top(input clk")
for p in FREE_IN: A("  , input %s%s" % (pdecl[p][1], p))
for m, sig in MEMS.items():
    A("  , input %snew_%s      // value a memory puts out after an access" % (pdecl[sig][1], sig))
    A("  , input %salt_%s      // any other value: the output is not settled yet" % (pdecl[sig][1], sig))
for n in START: A("  , input %salt_q%d       // %s: any other value for the bits that changed" % (regs[n][0], idx[n], rtlname[n]))
A(");")
A("  `include \"exc_mask.vh\"")
A("  reg [1:0] step = 2'd0;                 // 0: reset, then 1, 2, 3, 3, ...")
A("  always @(posedge clk) if (step != 2'd3) step <= step + 2'd1;")
A("  wire rst_n = (step != 2'd0), rst_sys_n = rst_n;")
for n, (rng, _) in regs.items(): A("  reg %sq%d; wire %sdA%d;   // %s" % (rng, idx[n], rng, idx[n], rtlname[n]))
for n in START:
    A("  reg %spq%d;   // value of %s one cycle earlier" % (regs[n][0], idx[n], rtlname[n]))
    A("  wire %ssq%d = q%d ^ ((alt_q%d ^ q%d) & (q%d ^ pq%d));" % (regs[n][0], idx[n], idx[n], idx[n], idx[n], idx[n], idx[n]))
for m, sig in MEMS.items(): A("  reg %s%s; reg fresh_%s = 1'b0;" % (pdecl[sig][1], sig, m))
A("  reg prev_cke = 1'b0;")

def inst(tag, qsub, msub):
    for o in outs: A("  wire %s%s_%s;" % (pdecl[o][1], tag, o))
    if tag != "A":
        for n, (rng, _) in regs.items(): A("  wire %sd%s%d;" % (rng, tag, idx[n]))
    c = [".clk(clk)", ".rst_n(rst_n)", ".rst_sys_n(rst_sys_n)"]
    c += [".%s(%s)" % (p, p) for p in FREE_IN]
    c += [".%s(%s)" % (sig, msub.get(sig, sig)) for sig in MEMS.values()]
    c += [".%s(%s_%s)" % (o, tag, o) for o in outs]
    for n in regs:
        c += [".q%d(%s)" % (idx[n], qsub.get(n, "q%d" % idx[n])), ".d%d(d%s%d)" % (idx[n], tag, idx[n])]
    A("  rdual_comb u%s (%s);" % (tag, ", ".join(c)))

CASE = os.environ.get("CASE", "all")                        # one case per run keeps the problem small: S, cm0, cm1, dm
inst("A", {}, {})
if CASE in ("all", "S"): inst("S", {n: "sq%d" % idx[n] for n in START}, {})
for m, sig in MEMS.items():
    if CASE in ("all", m): inst("M" + m, {}, {sig: "alt_" + sig})

A("  wire acc_cm0 = A_cm0_re | A_cm0_we, acc_cm1 = A_cm1_re | A_cm1_we, acc_dm = A_dm_re | A_dm_we;")
A("  wire hevent = h_acc | (inj_cmd != 2'd0) | (brk_clr != 2'd0) | (halt_req != prev_halt_req);")
A("  reg prev_quiet = 1'b0, prev_busy = 1'b0; reg [1:0] prev_halted = 2'b00, prev_halt_req = 2'b00; reg [2:0] hgap = 3'd0;")
A("  reg [1:0] cgap = 2'd0;                  // cycles without core clock enable since the last one, saturating at 3")
A("  always @(posedge clk) begin")
for n in regs: A("    q%d <= dA%d;" % (idx[n], idx[n]))
for n in START: A("    pq%d <= q%d;" % (idx[n], idx[n]))
for m, sig in MEMS.items():
    A("    fresh_%s <= acc_%s; if (acc_%s) %s <= new_%s;" % (m, m, m, sig, sig))
A("    prev_cke <= cke; prev_quiet <= A_h_quiet; prev_busy <= A_inj_busy; prev_halt_req <= halt_req;")
A("    prev_halted <= (A_brk_flag | halt_req) & A_core_en & ~A_core_wait;")
A("    hgap <= hevent ? 3'd0 : (hgap != 3'd7) ? hgap + 3'd1 : hgap;")
A("    cgap <= cke ? 2'd0 : (cgap != 2'd3) ? cgap + 2'd1 : cgap;")
A("  end")

def diffs(tag, skip_regs, skip_out, what):
    t = [("d%s%d != dA%d" % (tag, idx[n], idx[n]), "register %s" % rtlname[n]) for n in regs if n not in skip_regs]
    t += [("%s_%s != A_%s" % (tag, o, o), "output %s" % o) for o in STRICT + [h for h in HOSTDATA + HOSTSTATUS if h not in skip_out]]
    for en, sigs in COND:
        aen = re.sub(r"(\w+)", r"A_\1", en)
        t += [("(%s) && %s_%s != A_%s" % (aen, tag, s, s), "output %s while %s" % (s, en)) for s in sigs]
    return [(e, "%s depends on %s" % (d, what)) for e, d in t]

if CASE in ("all", "S"):
    for n in START: CHK.append(("!cke && dA%d != q%d" % (idx[n], idx[n]), "P1: %s changes in a cycle without core clock enable" % rtlname[n]))
    CHK += [(e, "P2: " + d) for e, d in diffs("S", START, HOSTSTATUS, "a start register that changed at the last clock edge")]
for m in MEMS:
    if CASE in ("all", m): CHK += [("fresh_%s && (%s)" % (m, e), "P3: " + d) for e, d in diffs("M" + m, DQ if m == "dm" else [], HOSTDATA + HOSTSTATUS, "the output of memory %s one cycle after an access" % m)]
REG = dict((rtlname[n], n) for n in regs)
dirty = REG["dirty"]
CHK.append(("q%d != 2'd0 && hgap > {1'b0, cgap}" % idx[dirty], "I2: a restore read is pending although a cycle with core clock enable has passed since the host access"))
CHK.append(("q%d != 2'd0 && hgap > {1'b0, cgap}" % idx[REG["bclr"]], "I3: a break clear is pending although a cycle with core clock enable has passed since the host command"))
for c in ("core0", "core1"):       # S_RET2 = 3, S_RET3 = 4, S_LD2 = 5 take a byte from the data memory (rcore8d.v)
    st, rf, dv = idx[REG[c + ".state"]], idx[REG[c + ".rd_first"]], idx[REG[c + ".dq_v"]]
    CHK.append(("(q%d == 4'd3 || q%d == 4'd4 || q%d == 4'd5) && !q%d && !q%d" % (st, st, st, rf, dv),
                "I4: %s waits for a byte from the data memory and neither its read is one cycle old nor dq holds the byte" % c))
# Known violations, see README.md in this folder. They are reported and do not fail the run.
WAIVED = ["P2: register jto depends on"]
K = len(CHK)
A("  wire [%d:0] viol;" % (K - 1))
for k, (e, d) in enumerate(CHK): A("  assign viol[%d] = (step == 2'd3) && (%s);   // %s" % (k, e, d))
A("  wire [%d:0] fail_vec = viol & ~MASK;" % (K - 1))
A("  (* keep *) wire fail_any = |fail_vec;")
A("  always @(*) begin          // not clocked: every assumption and the assertion apply to the cycle they are evaluated in")
A("    // ---- assumptions about the surroundings")
A("    assume (!(cke && prev_cke));                                   // core divider of 2 or more")
A("    assume (cke || cgap != 2'd3);                                  // and of 4 or less: at most 3 cycles without core clock enable")
A("    if (step != 2'd3) assume (!h_acc && inj_cmd == 2'd0 && brk_clr == 2'd0 && halt_req == 2'd0 && !cke);")
A("    assume (!hevent || step != 2'd3 || hgap == 3'd7);              // rhost.v: one event per received byte, 8 cycles apart or more")
A("    assume (!h_acc || prev_quiet);                                 // rhost.v: h_acc is registered from acc_ok = h_quiet (no core reset here)")
A("    assume (inj_cmd == 2'd0 || (!prev_busy && prev_halted[inj_core] && !h_acc));   // rhost.v: inj_cmd is registered from core_ok")
A("    assume (!h_acc || (halt_req == prev_halt_req && brk_clr == 2'd0));              // rhost.v: one action per received byte")
A("    assume (inj_cmd == 2'd0 || (halt_req == prev_halt_req && brk_clr == 2'd0));")
A("    assert (fail_vec == %d'd0);" % K)
A("  end")
A("endmodule")
open(outdir + "/exc_top.v", "w").write("\n".join(L) + "\n")
open(outdir + "/exc_checks.txt", "w").write("".join("%d\t%s%s\n" % (k, "WAIVED " if any(d.startswith(w) for w in WAIVED) else "", d) for k, (e, d) in enumerate(CHK)))
open(outdir + "/exc_mask.vh", "w").write("localparam [%d:0] MASK = %d'd0;\n" % (K - 1, K))
print("checks: %d" % K)
