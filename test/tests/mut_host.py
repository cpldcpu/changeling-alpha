#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Fault insertion for the host link, the program protection and the host logic of rdual.
Each fault is one changed line; the three system runs below must give a different result.
Usage: python3 tests/mut_host.py <word address of tick in fwh>   (run tests/run_fw.sh first)"""
import subprocess, sys

brk = sys.argv[1]
RTLDIR = '../src/rsoc8/rtl'
BASE = f'{RTLDIR}/rcore8d.v {RTLDIR}/rlinecells.v {RTLDIR}/rlcports.v {RTLDIR}/revents.v {RTLDIR}/rtimers.v {RTLDIR}/rclock.v '
RUNS = ('+hex=build/fwh.hex +htest=1 +brk=%s +maxcyc=1500000' % brk,
        '+hex0=build/fw2_c0.hex +hex1=build/fw2_c1.hex +spiload +maxcyc=400000',
        '+hex=build/fw8.hex +maxcyc=20000')


def run(files):
    c = subprocess.run(['iverilog', '-g2005', '-DSIM', '-o', 'build/m.vvp', 'tb/tb_sys.v'] + files.split(),
                       capture_output=True, text=True)
    if c.returncode:
        return 'COMPILE ' + (c.stdout + c.stderr)[:80]
    o = ''
    for args in RUNS:
        try:
            r = subprocess.run(['vvp', '-n', 'build/m.vvp'] + args.split(), capture_output=True, text=True, timeout=200).stdout
        except subprocess.TimeoutExpired:
            r = 'HANG'
        o += ' '.join(l for l in r.splitlines() if l.startswith(('EXIT', 'TIMEOUT', 'HOST', 'HANG'))) + '|'
    return o


MUTS = {
 f'{RTLDIR}/rhost.v': [
  ("wire rise = sel & s_ck[1] & ~s_ck[2];", "wire rise = sel & ~s_ck[1] & s_ck[2];"),
  ("if (fall) tx <= (bitn == 3'd0) ? tx_next : {tx[6:0], 1'b0};", "if (fall) tx <= {tx[6:0], 1'b0};"),
  ("wire       acc_ok  = c_rst | h_quiet;", "wire       acc_ok  = 1'b1;"),
  ("                                if (slot != 4'd3) h_addr <= h_addr + 16'd1;\n                                if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b1;",
   "                                if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b1;"),
  ("else if (slot == 4'd3 || !is_reg) begin", "else if (1) begin"),
  ("brk_clr <= c_halt & ~rxn[1:0];", "brk_clr <= 2'b00;"),
  ("4'd2: begin tx_next <= st1; err <= 1'b0; end", "4'd2: begin tx_next <= st1; end"),
  ("if (core_ok) inj_cmd <= (cmd == 8'h06) ? 2'd1 : 2'd2; else err <= 1'b1;", "if (core_ok) inj_cmd <= 2'd1; else err <= 1'b1;"),
  ("if (rxn == 8'h0A) begin if (core_ok) inj_cmd <= 2'd3;", "if (rxn == 8'h0A) begin if (core_ok) inj_cmd <= 2'd2;"),
  ("if (take) begin mb_txe <= 1'b1; take <= 1'b0; end", "if (take) begin take <= 1'b0; end"),
  ("if (io_re & a_da & ~io_host) mb_rxf <= 1'b0;", ""),
  ("wire [10:0] pcs = c_core ? {1'b0, pc1} : pc0;", "wire [10:0] pcs = pc0;"),
  ("wire       core_ok = halted[c_core] & core_en[c_core] &", "wire       core_ok = halted[c_core] &"),
  ("assign cm0_we_ok = cm0_we & (cm_host | (", "assign cm0_we_ok = cm0_we & ((1'b0) | ("),
  ("lock <= lock | io_wdata[7];", "lock <= io_wdata[7];"),
  ("wire in0 = (cm0_addr[9:2] >= lim)", "wire in0 = (1'b1)"),
  ("(cm1_wother ? xwe : pwe)", "(pwe)"),
  ("rst_core_n <= ~c_rst;", "rst_core_n <= 1'b1;"),
 ],
 f'{RTLDIR}/rdual.v': [
  ("    wire       hhold = h_acc | (|dirty);", "    wire       hhold = h_acc;"),
  ("dirty <= (dirty & ~rest) | {h_cm1, h_cm0};", "dirty <= 2'b00;"),
  ("(jst == J_R) ? 16'hCFFE : jword", "(jst == J_R) ? 16'hCFFF : jword"),
  ("wire       jsub  = jat & (((jst == J_X) & (jmode != 2'd3)) | (jst == J_R));", "wire       jsub  = jat & (((jst == J_X)) | (jst == J_R));"),
  ("J_X2:    if (jat) jst <= (jmode == 2'd1) ? J_R : J_IDLE;", "J_X2:    if (jat) jst <= J_R;"),
  ("wire h_dm  = h_acc & ~h_addr[14] & ~h_io;", "wire h_dm  = h_acc & ~h_io;"),
  ("assign io_core  = gs;", "assign io_core  = g1;"),
  ("assign cm0_wsel   = h_cm0 ? h_addr[0] :", "assign cm0_wsel   = h_cm0 ? 1'b0 :"),
  ("assign io_wmask = h_io ? 8'hFF :", "assign io_wmask = h_io ? 8'h0F :"),
  ("((~brkf & ~halt_req) | hrun)", "((~brkf & ~halt_req))"),
  ("hk <= {h_io, h_dm, h_cm1}; hb <= h_addr[0];", "hk <= {h_io, h_dm, h_cm1}; hb <= 1'b0;"),
  ("assign cm1_addr   = h_cm1 ? h_addr[10:1] : rest[1] ? lastr1 : ca1;", "assign cm1_addr   = h_cm1 ? h_addr[10:1] : ca1;"),
 ],
}

ONLY = sys.argv[2:]          # optional: substrings that select faults
good = run(BASE + f'{RTLDIR}/rdual.v {RTLDIR}/rhost.v')
print('reference:', good)
det = tot = 0
for f, ml in MUTS.items():
    src = open(f).read()
    other = f'{RTLDIR}/rdual.v' if f == f'{RTLDIR}/rhost.v' else f'{RTLDIR}/rhost.v'
    for a, b in ml:
        assert src.count(a) == 1, a
        if ONLY and not any(o in a for o in ONLY):
            continue
        open('build/mut.v', 'w').write(src.replace(a, b))
        tot += 1
        if run(BASE + other + ' build/mut.v') != good:
            det += 1
        else:
            print('NOT DETECTED', f, a[:70])
print('faults detected', det, 'of', tot)
