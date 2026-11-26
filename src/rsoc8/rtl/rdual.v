// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// rdual - two rcore8d cores with private code memories and a shared bus.
//
// Contains: the two cores, the arbiter for the shared bus (data memory and register bus), the
// routing of the code memory ports including access to the other core's code memory, and the
// registers that act on the cores directly:
//   CORECTL 0x00E   LOCK 0x005   WAITL 0x020   WAITH 0x021 (per core)   ARB 0x150 (protected)
//
// The state of this module and of the cores advances only in cycles with cke = 1, with these exceptions:
// the host access state (hk, hb, hio, dirty), the holding registers bclr and jreq, and in the cores
// rd_first, dq_v and dq. The memories and the peripherals are clocked in every cycle.
// Follows the rules U1-U8, M5, H1-H10 and C5-C10 of the architecture specification.

module rdual #(
    parameter NIRQ  = 16,
    parameter HAS_H = 0
) (
    input               clk,
    input               rst_n,
    input               cke,            // core clock enable (core divider); 1 = every cycle

    // code memories: synchronous read (output holds without re), byte write
    output [9:0]        cm0_addr,
    output              cm0_re,
    output              cm0_we,
    output              cm0_wsel,
    output [7:0]        cm0_wdata,
    output              cm0_wother,     // the write comes from the other core
    input  [15:0]       cm0_rdata,
    output [9:0]        cm1_addr,
    output              cm1_re,
    output              cm1_we,
    output              cm1_wsel,
    output [7:0]        cm1_wdata,
    output              cm1_wother,
    input  [15:0]       cm1_rdata,

    // data memory, synchronous read
    output [10:0]       dm_addr,
    output              dm_re,
    output              dm_we,
    output [7:0]        dm_wdata,
    input  [7:0]        dm_rdata,

    // register bus
    output [8:0]        io_addr,
    output              io_core,        // core that performs the access
    output              io_re,
    output              io_we,
    output [7:0]        io_wdata,
    output [7:0]        io_wmask,
    input  [7:0]        io_rdata,
    output              io_unlock,
    input               io_prot,

    input  [31:0]       evt,            // event flags as core 0 (low half) and core 1 see them
    input  [NIRQ:1]     irq0,
    input  [NIRQ:1]     irq1,
    output [NIRQ:1]     irq_ack0,
    output [NIRQ:1]     irq_ack1,

    input  [1:0]        halt_req,
    input  [1:0]        brk_clr,
    output [1:0]        brk_flag,
    output [1:0]        core_en,
    output [1:0]        core_wait,
    output [1:0]        core_cen,       // core advances in this cycle
    output              bus_hold,       // a core is held by the bus arbiter in this cycle
    output [10:0]       dbg_pc0,
    output [9:0]        dbg_pc1,
    output              idle,           // no core can advance

    // host access (host link): memories and register bus while no core can advance
    input               rst_sys_n,      // reset of the host access logic; not the core reset
    input               h_acc,          // one access in this cycle; only with h_quiet or in core reset
    input               h_we,
    input               h_core,         // core whose view of the per-core registers is used
    input  [15:0]       h_addr,         // data address as decoded by the cores
    input  [7:0]        h_wdata,
    output [7:0]        h_rdata,        // valid in the cycle after the access
    output              h_quiet,        // every enabled core is halted and no injection runs
    output              io_host,        // the register bus access comes from the host
    output              cm_host,        // the code memory access comes from the host
    // injection and single step for a halted core
    input  [1:0]        inj_cmd,        // pulse: 1 instruction with return, 2 instruction without return, 3 step
    input               inj_core,
    input  [15:0]       inj_word,
    output              inj_busy,
    output              inj_fail        // pulse: the core could not advance for 63 enabled cycles; injection ended
);
    // ---------------------------------------------------------------- core signals
    wire [10:0] pa0, pa1;               // code port address
    wire        pr0, pr1, pw0, pw1, ps0, ps1, pd0, pd1;
    wire [7:0]  pwd0, pwd1;
    wire [10:0] da0, da1;
    wire        dr0, dr1, dw0, dw1;
    wire [7:0]  dwd0, dwd1;
    wire        rq0, rq1;
    wire [8:0]  ia0, ia1;
    wire        ir0, ir1, iw0, iw1, ul0, ul1;
    wire [7:0]  iwd0, iwd1, iwm0, iwm1;
    wire [NIRQ:1] ak0, ak1;
    wire        ie0, ie1, sl0, sl1, bk0, bk1;
    wire [1:0]  cen;

    // ---------------------------------------------------------------- registers
    reg [1:0]   en, wt, brkf;
    reg [7:0]   mkl0, mkh0, mkl1, mkh1; // wait masks
    reg [1:0]   arb;                    // 0 alternate, 1 core 0 wins, 2 core 1 wins
    reg         last;                   // core granted at the last collision
    reg [3:0]   lk_held, lk_own;        // locks
    reg [1:0]   valid;                  // code memory output holds the owner's last read
    reg [1:0]   src;                    // the core's last read was on the other code memory
    reg [9:0]   last0, last1;           // address of the owner's last read on its own memory

    // ---------------------------------------------------------------- who can advance
    // ---------------------------------------------------------------- host access decode
    wire h_cm  = h_acc & h_addr[14];
    wire h_cm0 = h_cm & ~h_addr[11], h_cm1 = h_cm & h_addr[11];
    wire h_io  = h_acc & ~h_addr[14] & ((&h_addr[13:8]) | (h_addr[13:6] == 8'h00));
    wire h_dm  = h_acc & ~h_addr[14] & ~h_io;
    wire [8:0] h_ioa = (&h_addr[13:8]) ? {1'b1, h_addr[7:0]} : {3'b000, h_addr[5:0]};
    reg  [1:0] dirty;                   // the output of a code memory was changed by the host
    reg  [9:0] lastr0, lastr1;          // address of the last read by a core on each code memory
    wire [1:0] rest = dirty & ~{h_cm1, h_cm0} & {2{cke}};   // read that word again, in an enabled cycle: the
                                                        // next enabled cycle is then a full core period later
    wire       hhold = h_acc | (|dirty);

    // ---------------------------------------------------------------- injection and single step
    localparam J_IDLE = 3'd0, J_ALIGN = 3'd1, J_X = 3'd2, J_X2 = 3'd3, J_R = 3'd4, J_R2 = 3'd5;
    // jst, jmode, jcore and jword change only in cycles with cke = 1 (two-cycle timing exception of the
    // implementation flow; the keep attribute preserves their names for the constraints file).
    (* keep, fsm_encoding = "none" *) reg  [2:0] jst;
    (* keep *) reg  [1:0] jmode;
    (* keep *) reg        jcore;
    (* keep *) reg [15:0] jword;
    reg  [1:0] jreq;                    // inj_cmd is one cycle long; kept until the next enabled cycle
    wire [1:0] jcmd  = inj_cmd | jreq;
    reg  [1:0] bclr;                    // brk_clr is one cycle long; kept until the next enabled cycle
    reg  [5:0] jto;                     // cycles in which the core should advance and does not
    wire [1:0] at;                      // core is at the start of an instruction
    wire       jat   = at[jcore];
    wire       jrun  = ((jst == J_ALIGN) & ~jat) | (jst == J_X) | ((jst == J_X2) & ~jat) | (jst == J_R) | ((jst == J_R2) & ~jat);
    wire       jsub  = jat & (((jst == J_X) & (jmode != 2'd3)) | (jst == J_R));
    wire [15:0] jins = (jst == J_R) ? 16'hCFFE : jword;                 // RJMP .-2 returns to the halted position
    wire [1:0] hrun  = {jrun & jcore, jrun & ~jcore};
    wire [1:0] hsub  = {jsub & jcore, jsub & ~jcore};
    wire [1:0] jmask = {(jst != J_IDLE) & (jmode != 2'd3) & jcore, (jst != J_IDLE) & (jmode != 2'd3) & ~jcore};
    wire       jact  = (jst != J_IDLE);
    assign inj_busy = jact | (|jreq);
    assign inj_fail = jact & (jto == 6'd63) & cke;
    assign h_quiet  = (&(~en | brkf | halt_req)) & ~inj_busy;

    wire [1:0] base    = en & ~wt & ((~brkf & ~halt_req) | hrun) & {2{cke}} & {2{~hhold}};
    wire [1:0] refetch = base & ~valid;                 // read the lost word again; the core is held
    wire [1:0] pre     = base & ~refetch;

    wire use0 = pr0 | pw0, use1 = pr1 | pw1;
    wire fd0  = use0 & pd0 &  pa0[10];                  // core 0: load/store in code memory 1
    wire fd1  = use1 & pd1 & ~pa1[10];                  // core 1: load/store in code memory 0
    wire ff0  = pr0 & ~pd0 & pa0[10];                   // core 0 fetches from code memory 1
    wire prio0 = (arb == 2'd1), prio1 = (arb == 2'd2);

    // access to the other core's code memory: the owner is held if it is running
    // (a core that has just read the other memory cannot be the victim in the next cycle: its own
    // memory is then either idle or in its refetch cycle, see valid)
    wire st0     = pre[0] & fd0 & ~refetch[1] & (~base[1] | ~prio1);
    wire stolen1 = st0 & base[1];
    wire st1     = pre[1] & fd1 & ~refetch[0] & (~base[0] | ~prio0) & ~stolen1;
    wire stolen0 = st1 & base[0];

    wire ok0 = fd0 ? st0 : ff0 ? ~en[1] : 1'b1;
    wire ok1 = fd1 ? st1 : 1'b1;
    wire run0 = pre[0] & ~stolen0 & ok0;
    wire run1 = pre[1] & ~stolen1 & ok1;

    // ---------------------------------------------------------------- shared bus
    wire req0 = run0 & rq0, req1 = run1 & rq1;
    wire g0   = req0 & (~req1 | prio0 | (~prio1 & last));
    wire g1   = req1 & ~g0;
    assign cen = {run1 & (~rq1 | g1), run0 & (~rq0 | g0)};
    assign bus_hold = (req0 & ~g0) | (req1 & ~g1);

    wire gs = h_io ? h_core : g1;       // core whose registers are addressed
    wire c_we = (g0 & iw0) | (g1 & iw1);                // write by a core
    assign dm_addr  = h_dm ? h_addr[10:0] : g1 ? da1 : da0;
    assign dm_re    = (h_dm & ~h_we) | (g0 & dr0) | (g1 & dr1);
    assign dm_we    = (h_dm &  h_we) | (g0 & dw0) | (g1 & dw1);
    assign dm_wdata = h_dm ? h_wdata : g1 ? dwd1 : dwd0;
    assign io_addr  = h_io ? h_ioa : g1 ? ia1 : ia0;
    assign io_core  = gs;
    assign io_re    = (h_io & ~h_we) | (g0 & ir0) | (g1 & ir1);
    assign io_we    = (h_io &  h_we) | c_we;
    assign io_wdata = h_io ? h_wdata : g1 ? iwd1 : iwd0;
    assign io_wmask = h_io ? 8'hFF : g1 ? iwm1 : iwm0;
    assign io_unlock = g1 ? ul1 : ul0;
    assign io_host  = h_io;
    assign cm_host  = h_cm;

    // ---------------------------------------------------------------- registers on the bus
    wire a_ctl  = (io_addr == 9'h00E);
    wire a_lock = (io_addr == 9'h005);
    wire a_wl   = (io_addr == 9'h020);
    wire a_wh   = (io_addr == 9'h021);
    wire a_arb  = (io_addr == 9'h150);
    wire [7:0] mkl_g = gs ? mkl1 : mkl0;
    wire [7:0] mkh_g = gs ? mkh1 : mkh0;
    wire [3:0] lk_mine  = lk_held & (gs ? lk_own : ~lk_own);
    wire [3:0] lk_other = lk_held & (gs ? ~lk_own : lk_own);
    wire [7:0] ctl_r = {gs, 1'b0, wt, 2'b00, en};
    wire [7:0] rb    = a_ctl ? ctl_r : a_lock ? {lk_other, lk_mine} : a_wl ? mkl_g : a_wh ? mkh_g
                     : a_arb ? {6'd0, arb} : io_rdata;
    wire [7:0] w_old = a_ctl ? ctl_r : a_wl ? mkl_g : a_wh ? mkh_g : {6'd0, arb};
    wire [7:0] w_new = (w_old & ~io_wmask) | (io_wdata & io_wmask);
    wire       prot  = a_arb | io_prot;

    wire [1:0] en_new = (c_we & a_ctl) ? w_new[1:0] : en;
    wire [1:0] start  = en_new & ~en;

    // ---------------------------------------------------------------- waiting
    wire [15:0] ev0 = evt[15:0], ev1 = evt[31:16];
    wire wl_wr   = c_we & a_wl;
    wire [15:0] m0 = {mkh0, (wl_wr & g0) ? w_new : mkl0};
    wire [15:0] m1 = {mkh1, (wl_wr & g1) ? w_new : mkl1};
    wire go0 = (wl_wr & g0) | (cen[0] & sl0);
    wire go1 = (wl_wr & g1) | (cen[1] & sl1);
    wire hit0 = (|(m0 & ev0)) | (ie0 & (|irq0));
    wire hit1 = (|(m1 & ev1)) | (ie1 & (|irq1));
    wire wake0 = wt[0] & ((|({mkh0, mkl0} & ev0)) | (ie0 & (|irq0)));
    wire wake1 = wt[1] & ((|({mkh1, mkl1} & ev1)) | (ie1 & (|irq1)));

    // ---------------------------------------------------------------- code memory ports
    // memory 0: refetch for core 0, access by core 1, or core 0 itself
    wire c0_own = cen[0] & ~pa0[10];
    wire c1_in0 = cen[1] & fd1;
    wire cr0 = cke & (refetch[0] | (c1_in0 & pr1) | (c0_own & pr0));    // read by a core
    wire [9:0] ca0 = refetch[0] ? last0 : c1_in0 ? pa1[9:0] : pa0[9:0];
    assign cm0_addr   = h_cm0 ? h_addr[10:1] : rest[0] ? lastr0 : ca0;
    assign cm0_re     = (h_cm0 & ~h_we) | rest[0] | cr0;
    assign cm0_we     = (h_cm0 & h_we) | (~refetch[0] & ((c1_in0 & pw1) | (c0_own & pw0)));
    assign cm0_wsel   = h_cm0 ? h_addr[0] : c1_in0 ? ps1 : ps0;
    assign cm0_wdata  = h_cm0 ? h_wdata : c1_in0 ? pwd1 : pwd0;
    assign cm0_wother = c1_in0;
    // memory 1: refetch for core 1, any access by core 0, or core 1 itself
    wire c1_own = cen[1];
    wire c0_in1 = cen[0] & use0 & pa0[10];
    wire cr1 = cke & (refetch[1] | (c0_in1 & pr0) | (c1_own & pr1 & ~fd1));
    wire [9:0] ca1 = refetch[1] ? last1 : c0_in1 ? pa0[9:0] : pa1[9:0];
    assign cm1_addr   = h_cm1 ? h_addr[10:1] : rest[1] ? lastr1 : ca1;
    assign cm1_re     = (h_cm1 & ~h_we) | rest[1] | cr1;
    assign cm1_we     = (h_cm1 & h_we) | (~refetch[1] & ((c0_in1 & pw0) | (c1_own & pw1 & ~fd1)));
    assign cm1_wsel   = h_cm1 ? h_addr[0] : c0_in1 ? ps0 : ps1;
    assign cm1_wdata  = h_cm1 ? h_wdata : c0_in1 ? pwd0 : pwd1;
    assign cm1_wother = c0_in1;

    // Instruction inputs of the two cores. Everything behind them is taken over only in cycles with cke = 1;
    // the timing constraints of the implementation flow use this (two clock cycles from the code memories).
    wire [15:0] prd0 = hsub[0] ? jins : src[0] ? cm1_rdata : cm0_rdata;
    wire [15:0] prd1 = hsub[1] ? jins : src[1] ? cm0_rdata : cm1_rdata;

    // ---------------------------------------------------------------- host access state
    // These flip-flops are not reset by the core reset, so that the host can load the memories
    // while the cores are held in reset.
    reg  [2:0] hk;                      // kind of the last host access: code 0, code 1 (with byte), data, bus
    reg        hb;
    reg  [7:0] hio;
    assign h_rdata = hk[2] ? hio : hk[1] ? dm_rdata
                   : hk[0] ? (hb ? cm1_rdata[15:8] : cm1_rdata[7:0]) : (hb ? cm0_rdata[15:8] : cm0_rdata[7:0]);
    always @(posedge clk or negedge rst_sys_n) begin
        if (!rst_sys_n) begin hk <= 3'd0; hb <= 1'b0; hio <= 8'h00; end
        else if (h_acc) begin hk <= {h_io, h_dm, h_cm1}; hb <= h_addr[0]; hio <= rb; end
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin dirty <= 2'b00; lastr0 <= 10'd0; lastr1 <= 10'd0; jst <= J_IDLE; jmode <= 2'd0; jcore <= 1'b0; jword <= 16'd0; jto <= 6'd0; bclr <= 2'b00; jreq <= 2'd0; end
        else begin
            dirty <= (dirty & ~rest) | {h_cm1, h_cm0};
            bclr  <= cke ? 2'b00 : (bclr | brk_clr);
            if (cr0 & ~hhold) lastr0 <= ca0;
            if (cr1 & ~hhold) lastr1 <= ca1;
            jreq  <= cke ? 2'd0 : jcmd;
            if (cke) case (jst)
                J_IDLE:  if (jcmd != 2'd0 && en[inj_core] && !wt[inj_core]) begin
                             jst <= J_ALIGN; jmode <= jcmd; jcore <= inj_core; jword <= inj_word;
                         end
                J_ALIGN: if (jat) jst <= J_X;
                J_X:     if (cen[jcore] & jat) jst <= J_X2;
                J_X2:    if (jat) jst <= (jmode == 2'd1) ? J_R : J_IDLE;
                J_R:     if (cen[jcore] & jat) jst <= J_R2;
                default: if (jat) jst <= J_IDLE;
            endcase
            if (!jrun | cen[jcore]) jto <= 6'd0; else if (cke) jto <= jto + 6'd1;
            if (inj_fail) jst <= J_IDLE;        // inj_fail contains cke
        end
    end

    integer n;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            en <= 2'b01; wt <= 2'b00; brkf <= 2'b00;
            mkl0 <= 8'h00; mkh0 <= 8'h00; mkl1 <= 8'h00; mkh1 <= 8'h00;
            arb <= 2'd0; last <= 1'b1; lk_held <= 4'h0; lk_own <= 4'h0;
            valid <= 2'b11; src <= 2'b00; last0 <= 10'd0; last1 <= 10'd0;
        end else if (cke) begin
            // ---- code memory bookkeeping
            if (refetch[0])                   valid[0] <= 1'b1;
            else if (c1_in0)                  valid[0] <= 1'b0;
            if (refetch[1])                   valid[1] <= 1'b1;
            else if (c0_in1)                  valid[1] <= 1'b0;
            if (c0_own & pr0) last0 <= pa0[9:0];
            if (c1_own & pr1 & ~fd1) last1 <= pa1[9:0];
            if (cen[0] & pr0) src[0] <= pa0[10];
            if (cen[1] & pr1) src[1] <= ~pa1[10];

            // ---- arbitration history
            if (req0 & req1) last <= g1;

            // ---- wait, break, enable
            if (wake0) wt[0] <= 1'b0;
            if (wake1) wt[1] <= 1'b0;
            if (go0 & ~hit0) wt[0] <= 1'b1;
            if (go1 & ~hit1) wt[1] <= 1'b1;
            brkf <= (brkf & ~(brk_clr | bclr)) | {cen[1] & bk1, cen[0] & bk0};
            if (c_we & a_wh & g0) mkh0 <= w_new;
            if (c_we & a_wh & g1) mkh1 <= w_new;
            if (wl_wr & g0)        mkl0 <= w_new;
            if (wl_wr & g1)        mkl1 <= w_new;
            if (c_we & a_arb & io_unlock) arb <= w_new[1:0];
            en <= en_new;
            if (start[0]) begin wt[0] <= 1'b0; valid[0] <= 1'b1; src[0] <= 1'b0; end
            if (start[1]) begin wt[1] <= 1'b0; valid[1] <= 1'b1; src[1] <= 1'b0; end

            // ---- locks
            if (c_we & a_lock)
                for (n = 0; n < 4; n = n + 1)
                    if (io_wmask[n]) begin
                        if (io_wdata[n] & ~lk_held[n]) begin lk_held[n] <= 1'b1; lk_own[n] <= g1; end
                        if (~io_wdata[n] & lk_held[n] & (lk_own[n] == g1)) lk_held[n] <= 1'b0;
                    end
        end
    end

    assign irq_ack0  = ak0 & {NIRQ{cen[0]}};
    assign irq_ack1  = ak1 & {NIRQ{cen[1]}};
    assign brk_flag  = brkf;
    assign core_en   = en;
    assign core_wait = wt;
    assign core_cen  = cen;
    assign idle      = ~(|(en & ~wt & ~brkf & ~halt_req));

    rcore8d #(.PC_W(11), .CODE_ID(0), .NIRQ(NIRQ), .HAS_H(HAS_H), .SP_RESET(16'h083F)) core0 (
        .clk(clk), .rst_n(rst_n), .cen(cen[0]), .start(start[0]),
        .pm_addr(pa0), .pm_re(pr0), .pm_we(pw0), .pm_wsel(ps0), .pm_wdata(pwd0), .pm_dacc(pd0), .pm_rdata(prd0),
        .dm_addr(da0), .dm_re(dr0), .dm_we(dw0), .dm_wdata(dwd0), .dm_rdata(dm_rdata),
        .bus_req(rq0),
        .io_addr(ia0), .io_re(ir0), .io_we(iw0), .io_wdata(iwd0), .io_wmask(iwm0), .io_rdata(rb),
        .io_unlock(ul0), .io_prot(prot),
        .irq(irq0 & ~{NIRQ{jmask[0]}}), .irq_ack(ak0), .irq_en(ie0), .sleep(sl0), .brk(bk0), .dbg_pc(dbg_pc0), .inj(jmask[0]), .at_start(at[0]));

    rcore8d #(.PC_W(10), .CODE_ID(1), .NIRQ(NIRQ), .HAS_H(HAS_H), .SP_RESET(16'h043F)) core1 (
        .clk(clk), .rst_n(rst_n), .cen(cen[1]), .start(start[1]),
        .pm_addr(pa1), .pm_re(pr1), .pm_we(pw1), .pm_wsel(ps1), .pm_wdata(pwd1), .pm_dacc(pd1), .pm_rdata(prd1),
        .dm_addr(da1), .dm_re(dr1), .dm_we(dw1), .dm_wdata(dwd1), .dm_rdata(dm_rdata),
        .bus_req(rq1),
        .io_addr(ia1), .io_re(ir1), .io_we(iw1), .io_wdata(iwd1), .io_wmask(iwm1), .io_rdata(rb),
        .io_unlock(ul1), .io_prot(prot),
        .irq(irq1 & ~{NIRQ{jmask[1]}}), .irq_ack(ak1), .irq_en(ie1), .sleep(sl1), .brk(bk1), .dbg_pc(dbg_pc1), .inj(jmask[1]), .at_start(at[1]));
endmodule
