#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Fault insertion on a temporary copy of the RTL.  usage: fault_run.py <block> [first_seed last_seed]
Each fault is one textual substitution in a copy of rtl/ (build/mut/); the random test of the block is run
against the copy. A fault counts as detected if the test script returns non-zero."""
import os, shutil, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FAULTS = {
 'ev': ('ev_test.py', [
  ('W1C wins over event (priority swapped)', 'revents.v', "lat  <= (lat & ~ack5 & ~((io_we & a_ifrl) ? w1c[4:0] : 5'd0)) | set5;", "lat  <= ((lat & ~ack5) | set5) & ~((io_we & a_ifrl) ? w1c[4:0] : 5'd0);"),
  ('entry clear wins over event only for ack (ack priority swapped)', 'revents.v', "lat  <= (lat & ~ack5 & ~((io_we & a_ifrl) ? w1c[4:0] : 5'd0)) | set5;", "lat  <= ((lat & ~((io_we & a_ifrl) ? w1c[4:0] : 5'd0)) | set5) & ~ack5;"),
  ('TRIM clear by wrong bit', 'revents.v', "w1c[6])) | trim_evt", "w1c[5])) | trim_evt"),
  ('OVF not clearable by write', 'revents.v', "w1c[4:0] : 5'd0)) | set5", "{1'b0, w1c[3:0]} : 5'd0)) | set5"),
  ('ack of core 1 ignored', 'revents.v', "irq_ack0[5:1] | irq_ack1[5:1]", "irq_ack0[5:1]"),
  ('difference 0 not past', 'revents.v', "wk_past = (wk_d == 16'd0) | wk_d[15]", "wk_past = wk_d[15]"),
  ('difference 0x8000 not past (sign test removed)', 'revents.v', "| wk_d[15] |", "| 1'b0 |"),
  ('same-cycle match at write missing', 'revents.v', "| (ptick & (wk_d == 16'd1));", ";"),
  ('same-cycle match at write for difference 2', 'revents.v', "(ptick & (wk_d == 16'd1))", "(ptick & (wk_d <= 16'd2))"),
  ('wake-up compare uses old time base (off by one)', 'revents.v', "if (ptick & (tb_n == wake0)) dly[0]", "if (ptick & (tbase == wake0)) dly[0]"),
  ('core 1 wake-up write does not set DLY', 'revents.v', "dly[1] <= wk_past; end", "dly[1] <= 1'b0; end"),
  ('high byte latch for writing shared by cores', 'revents.v', "wk_n  = {io_core ? wtmp1 : wtmp0, io_wdata}", "wk_n  = {wtmp0, io_wdata}"),
  ('read latch of core 1 not loaded', 'revents.v', "if (io_core) rtmp1 <= tbase[15:8]; else", "if (io_core) rtmp1 <= rtmp1; else"),
  ('software flag write ignores mask', 'revents.v', "sw <= (sw & ~io_wmask[7:4]) | (io_wdata[7:4] & io_wmask[7:4])", "sw <= io_wdata[7:4]"),
  ('line cell owner view swapped', 'revents.v', "wire [3:0] lc0 = lc_evt & {~lc_own[1], ~lc_own[1], ~lc_own[0], ~lc_own[0]}", "wire [3:0] lc0 = lc_evt & {~lc_own[0], ~lc_own[0], ~lc_own[1], ~lc_own[1]}"),
  ('IER write of core 0 ignores mask', 'revents.v', "else         ier0[7:0] <= (ier0[7:0] & ~io_wmask) | (io_wdata & io_wmask);", "else         ier0[7:0] <= io_wdata;"),
  ('irq of core 1 not masked by IER', 'revents.v', "assign irq1 = ifr1 & ier1;", "assign irq1 = ifr1;"),
  ('time base counts without ptick', 'revents.v', "if (ptick) tbase <= tb_n;", "tbase <= tb_n;"),
 ]),
}
FAULTS['dual'] = ('dual_test.py', [
  ('lock taken although held (free check removed)', 'rdual.v', "if (io_wdata[n] & ~lk_held[n]) begin", "if (io_wdata[n]) begin"),
  ('lock released by any core', 'rdual.v', "if (~io_wdata[n] & lk_held[n] & (lk_own[n] == g1))", "if (~io_wdata[n] & lk_held[n])"),
  ('lock owner recorded wrongly (core 0 always)', 'rdual.v', "lk_own[n] <= g1; end", "lk_own[n] <= 1'b0; end"),
  ('lock write ignores write mask', 'rdual.v', "if (io_wmask[n]) begin\n                        if (io_wdata[n] & ~lk_held", "if (1'b1) begin\n                        if (io_wdata[n] & ~lk_held"),
  ('LOCK view swapped for core 1', 'rdual.v', "wire [3:0] lk_mine  = lk_held & (gs ? lk_own : ~lk_own);", "wire [3:0] lk_mine  = lk_held & (gs ? ~lk_own : lk_own);"),
  ('arbiter: MODE 1 grants core 1', 'rdual.v', "wire prio0 = (arb == 2'd1), prio1 = (arb == 2'd2);", "wire prio0 = (arb == 2'd2), prio1 = (arb == 2'd1);"),
  ('arbiter: alternate grants the same core again', 'rdual.v', "if (req0 & req1) last <= g1;", "if (req0 & req1) last <= ~g1;"),
  ('arbiter: collision history updated on every grant', 'rdual.v', "if (req0 & req1) last <= g1;", "if (req0 | req1) last <= g1;"),
  ('ARB writable without unlock', 'rdual.v', "if (c_we & a_arb & io_unlock) arb <= w_new[1:0];", "if (c_we & a_arb) arb <= w_new[1:0];"),
  ('wait entered although a flag is already set', 'rdual.v', "wire hit0 = (|(m0 & ev0)) | (ie0 & (|irq0));", "wire hit0 = (ie0 & (|irq0));"),
  ('new mask not used for the check at the write', 'rdual.v', "wire hit1 = (|(m1 & ev1)) | (ie1 & (|irq1));", "wire hit1 = (|({mkh1, mkl1} & ev1)) | (ie1 & (|irq1));"),
  ('wake by interrupt ignores I flag', 'rdual.v', "wire wake1 = wt[1] & ((|({mkh1, mkl1} & ev1)) | (ie1 & (|irq1)));", "wire wake1 = wt[1] & ((|({mkh1, mkl1} & ev1)) | ((|irq1)));"),
  ('wake of core 0 uses core 1 flags', 'rdual.v', "wire wake0 = wt[0] & ((|({mkh0, mkl0} & ev0))", "wire wake0 = wt[0] & ((|({mkh0, mkl0} & ev1))"),
  ('start does not clear the wait state', 'rdual.v', "if (start[1]) begin wt[1] <= 1'b0;", "if (start[1]) begin"),
  ('WAITH of core 1 writes mask of core 0', 'rdual.v', "if (c_we & a_wh & g1) mkh1 <= w_new;", "if (c_we & a_wh & g1) mkh0 <= w_new;"),
  ('SLEEP does not wait', 'rdual.v', "wire go1 = (wl_wr & g1) | (cen[1] & sl1);", "wire go1 = (wl_wr & g1);"),
  ('halted core not excluded', 'rdual.v', "((~brkf & ~halt_req) | hrun)", "((~brkf) | hrun)"),
  ('waiting core still requests the bus', 'rdual.v', "wire [1:0] base    = en & ~wt &", "wire [1:0] base    = en &"),
  ('CORECTL write ignores mask', 'rdual.v', "wire [1:0] en_new = (c_we & a_ctl) ? w_new[1:0] : en;", "wire [1:0] en_new = (c_we & a_ctl) ? io_wdata[1:0] : en;"),
  ('CORECTL read: ID bit wrong', 'rdual.v', "wire [7:0] ctl_r = {gs, 1'b0, wt, 2'b00, en};", "wire [7:0] ctl_r = {1'b0, 1'b0, wt, 2'b00, en};"),
  ('hold output missing for core 1', 'rdual.v', "assign bus_hold = (req0 & ~g0) | (req1 & ~g1);", "assign bus_hold = (req0 & ~g0);"),
])

FAULTS['clkctl'] = ('clkctl_test.py', [
  ('protection of CLKCTL and CLKCDIV removed', 'rclock.v', "wire ok = io_unlock | io_host;", "wire ok = 1'b1;"),
  ('host cannot write protected registers', 'rclock.v', "wire ok = io_unlock | io_host;", "wire ok = io_unlock;"),
  ('CLKPDIV protected', 'rclock.v', "io_we & a_pdiv,", "io_we & a_pdiv & ok,"),
  ('early event rule: boundary off by one', 'rclock.v', "({1'b0, cnt} + {1'b0, wspan}) <= {1'b0, tgt}", "({1'b0, cnt} + {1'b0, wspan}) < {1'b0, tgt}"),
  ('early event rule also for pin reference', 'rclock.v', "wire        early    = line &", "wire        early    ="),
  ('window compare not strict', 'rclock.v', "(adiff < wspan)", "(adiff <= wspan)"),
  ('loop steps down when count equals target', 'rclock.v', "& ~diff[16] & (adiff != 16'd0) &", "& ~diff[16] &"),
  ('loop wraps at 255', 'rclock.v', "diff[16] & (r_trim != 8'hFF)", "diff[16]"),
  ('loop step has priority over OSCTRIM write', 'rclock.v', "if (io_we & a_trim) r_trim <= io_wdata;\n            else if (up) r_trim <= r_trim + 8'd1;", "if (up) r_trim <= r_trim + 8'd1;\n            else if (io_we & a_trim) r_trim <= io_wdata;"),
  ('measurement length: one period too many', 'rclock.v', "(line | (per == r_int[6:0]))", "(line | (per == r_int[6:0] + 7'd1))"),
  ('count copied after one more step', 'rclock.v', "trcnt <= cnt; mdone <= 1'b1;", "trcnt <= cnt1; mdone <= 1'b1;"),
  ('count does not saturate', 'rclock.v', "wire [15:0] cnt1     = (cnt == 16'hFFFF) ? cnt : cnt + 16'd1;", "wire [15:0] cnt1     = cnt + 16'd1;"),
  ('MEAS write does not clear MDONE', 'rclock.v', "if (meas_wr) mdone <= 1'b0;", ""),
  ('MEAS busy bit not readable', 'rclock.v', "4'h4: io_rdata = {(st != 2'd0) & ~line, r_int[6:0]};", "4'h4: io_rdata = {1'b0, r_int[6:0]};"),
  ('new divider value takes effect at once', 'rclock.v', "wire [7:0] cc_n = (cc == 8'd0) ? r_cdiv : cc - 8'd1;", "wire [7:0] cc_n = (cc == 8'd0 || cc > r_cdiv) ? r_cdiv : cc - 8'd1;"),
  ('peripheral enable phase shifted', 'rclock.v', "ptick <= (pc_n == 8'd0);", "ptick <= (pc == 8'd0);"),
  ('clock output divider off by one', 'rclock.v', "cko_q <= oc[r_cko[2:0]];", "cko_q <= oc[r_cko[2:0] + 3'd1];"),
  ('debug select 8 and 9 swapped', 'rclock.v', "4'd8:  dsig = core_cen[0];   4'd9:  dsig = core_cen[1];", "4'd8:  dsig = core_cen[1];   4'd9:  dsig = core_cen[0];"),
  ('debug signal not delayed by one cycle', 'rclock.v', "assign dbg    = dbg_q;", "assign dbg    = dsig;"),
  ('presence window one cycle short', 'rclock.v', "if (win == 10'h3FF) begin pres_e", "if (win == 10'h3FE) begin pres_e"),
  ('switch checks the wrong presence bit', 'rclock.v', "(r_src ? pres_o : pres_e)) sel_q <= r_src;", "(r_src ? pres_e : pres_o)) sel_q <= r_src;"),
  ('write to CLKCTL does not end a measurement', 'rclock.v', "if (ctl_wr) st <= 2'd0;", "if (1'b0) st <= 2'd0;"),
  ('TRIM flag without valid', 'rclock.v', "assign trim_evt = done_q & valid;", "assign trim_evt = done_q;"),
  ('MDONE and MVALID swapped in CLKSTAT', 'rclock.v', "{strap, 1'b0, mvalid, mdone, trimd,", "{strap, 1'b0, mdone, mvalid, trimd,"),
  ('TRCNT high latch loaded by the high byte read', 'rclock.v', "if (io_re & a_cntl) cnth_lat", "if (io_re & a_cnth) cnth_lat"),
  ('strap does not set OSCEN at boot', 'rclock.v', "r_src <= strap; r_oscen <= strap;", "r_src <= strap; r_oscen <= 1'b0;"),
  ('reference pin edge on falling edge', 'rclock.v', "(sp[1] & ~sp[2]) : (sh[1] & ~sh[2])", "(~sp[1] & sp[2]) : (sh[1] & ~sh[2])"),
  ('window multiplier 32 instead of 64', 'rclock.v', "wire [15:0] wspan    = {2'b00, r_win, 6'd0};", "wire [15:0] wspan    = {3'b000, r_win, 5'd0};"),
  ('TRIM loop ignores LOOP bit', 'rclock.v', "wire        up = done_q & valid & loop &", "wire        up = done_q & valid &"),
])

FAULTS['prot'] = ('prot_test.py', [
  ('sticky lock ignored for core writes', 'rhost.v', "(cm_host | (~lock & in0 &", "(cm_host | (in0 &"),
  ('limit compare not inclusive (> instead of >=)', 'rhost.v', "wire in0 = (cm0_addr[9:2] >= lim)", "wire in0 = (cm0_addr[9:2] > lim)"),
  ('limit of memory 1 compares word address bit 1 too', 'rhost.v', "in1 = (cm1_addr[9:2] >= lim)", "in1 = (cm1_addr[9:1] >= lim)"),
  ('limit of memory 1 uses address of memory 0', 'rhost.v', "in1 = (cm1_addr[9:2] >= lim)", "in1 = (cm0_addr[9:2] >= lim)"),
  ('own and other enable swapped for memory 0', 'rhost.v', "(cm0_wother ? xwe : pwe)", "(cm0_wother ? pwe : xwe)"),
  ('host writes subject to protection', 'rhost.v', "assign cm1_we_ok = cm1_we & (cm_host | (", "assign cm1_we_ok = cm1_we & ((1'b0) | ("),
  ('lock can be cleared', 'rhost.v', "lock <= lock | io_wdata[7];", "lock <= io_wdata[7];"),
  ('PMCR writable without unlock', 'rhost.v', "if (io_we & a_c & ok)", "if (io_we & a_c)"),
  ('PMLIM not writable by the host', 'rhost.v', "if (io_we & a_l & ok) lim <= io_wdata;", "if (io_we & a_l & io_unlock) lim <= io_wdata;"),
  ('protected flag missing for PMLIM', 'rhost.v', "assign io_prot = a_c | a_l;", "assign io_prot = a_c;"),
  ('XWE and PWE swapped in the read value', 'rhost.v', "io_rdata = {lock, 5'd0, xwe, pwe};", "io_rdata = {lock, 5'd0, pwe, xwe};"),
  ('LOCK read-back missing', 'rhost.v', "io_rdata = {lock, 5'd0, xwe, pwe};", "io_rdata = {1'b0, 5'd0, xwe, pwe};"),
])

FAULTS['host'] = ('host_test.py', [
  ('access allowed only when halted (core reset ignored)', 'rhost.v', "wire       acc_ok  = c_rst | h_quiet;", "wire       acc_ok  = h_quiet;"),
  ('status does not clear the error bit', 'rhost.v', "4'd2: begin tx_next <= st1; err <= 1'b0; end", "4'd2: begin tx_next <= st1; end"),
  ('break flags cleared by every control command', 'rhost.v', "brk_clr <= c_halt & ~rxn[1:0];", "brk_clr <= ~rxn[1:0];"),
  ('mailbox write accepted while RXF set', 'rhost.v', "if (!mb_rxf) begin mb_rx <= rxn;", "if (1'b1) begin mb_rx <= rxn;"),
  ('mailbox read never sets TXE', 'rhost.v', "take <= ~mb_txe; end", "take <= 1'b0; end"),
  ('inject allowed for a waiting core', 'rhost.v', "& ~core_wait[c_core] & ~c_rst", "& ~c_rst"),
  ('inject allowed for a core that is not halted', 'rhost.v', "wire       core_ok = halted[c_core] &", "wire       core_ok = 1'b1 &"),
  ('write address does not increment', 'rhost.v', "if (slot != 4'd3) h_addr <= h_addr + 16'd1;\n                                if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b1;", "if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b1;"),
  ('register read repeats zero instead of the value', 'rhost.v', "end else tx_next <= tx_hold;", "end else tx_next <= 8'd0;"),
  ('control: selected core from bit 3', 'rhost.v', "c_core <= rxn[4];", "c_core <= rxn[3];"),
  ('status: selected core bit inverted', 'rhost.v', "1'b0, c_core, core_en};", "1'b0, ~c_core, core_en};"),
  ('mailbox byte taken by a host read of MBDATA', 'rhost.v', "if (io_re & a_da & ~io_host) mb_rxf", "if (io_re & a_da) mb_rxf"),
  ('inject and execute swapped', 'rhost.v', "inj_cmd <= (cmd == 8'h06) ? 2'd1 : 2'd2;", "inj_cmd <= (cmd == 8'h06) ? 2'd2 : 2'd1;"),
  ('step uses the execute command', 'rhost.v', "inj_cmd <= 2'd3;", "inj_cmd <= 2'd2;"),
  ('status program counter high byte shifted', 'rhost.v', "tx_next <= {5'd0, pcs[10:8]};", "tx_next <= {5'd0, pcs[9:7]};"),
  ('injection failure does not set the error bit', 'rhost.v', "if (inj_fail) err <= 1'b1;", ""),
  ('mailbox write does not store the byte', 'rhost.v', "begin mb_rx <= rxn; mb_rxf <= 1'b1; end", "begin mb_rx <= 8'd0; mb_rxf <= 1'b1; end"),
  ('mbx output follows TXE', 'rhost.v', "assign mbx      = mb_rxf;", "assign mbx      = mb_txe;"),
  ('refused write does not set the error bit', 'rhost.v', "h_wdata <= rxn; end else err <= 1'b1;", "h_wdata <= rxn; end"),
  ('core reset not set after reset', 'rhost.v', "cmd <= 8'd0; c_rst <= 1'b1;", "cmd <= 8'd0; c_rst <= 1'b0;"),
  ('halt requests from bits 2:1', 'rhost.v', "c_halt <= rxn[1:0];", "c_halt <= rxn[2:1];"),
  ('mailbox read returns the status twice', 'rhost.v', "4'd2: begin tx_next <= mb_tx; take", "4'd2: begin tx_next <= {mb_rxf, mb_txe, 6'd0}; take"),
  ('refused read does not set the error bit', 'rhost.v', "if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b0; end else err <= 1'b1;", "if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b0; end"),
  ('firmware write of MBDATA does not clear TXE', 'rhost.v', "begin mb_tx <= io_wdata; mb_txe <= 1'b0; end", "begin mb_tx <= io_wdata; end"),
])

if __name__ == '__main__':
    blk = sys.argv[1]; script, faults = FAULTS[blk]
    seeds = sys.argv[2:4] if len(sys.argv) > 3 else ['0', '100']
    mut = f'{ROOT}/build/mut_{blk}'; det = 0
    for i, (desc, f, old, new) in enumerate(faults):
        shutil.rmtree(mut, ignore_errors=True); shutil.copytree(f'{ROOT}/rtl', mut)
        src = open(f'{mut}/{f}').read()
        if src.count(old) != 1: print(f'F{i + 1:02d} NOT APPLIED ({src.count(old)} matches): {desc}'); continue
        open(f'{mut}/{f}', 'w').write(src.replace(old, new))
        env = dict(os.environ, RTLDIR=mut, TAG=f'mut_{blk}', NODIRECTED='1', FIRST='1')
        r = subprocess.run([sys.executable, f'{ROOT}/tests/{script}', *seeds], env=env, capture_output=True, text=True)
        ok = r.returncode != 0
        det += ok
        first = [l for l in r.stdout.splitlines() if 'seed' in l or l.startswith('   ')][:1]
        print(f'F{i + 1:02d} {"DETECTED " if ok else "MISSED   "} {desc}   {first[0].strip()[:90] if first else ""}')
    print(f'{blk}: {det} of {len(faults)} faults detected')
