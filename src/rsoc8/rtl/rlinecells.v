// Line cells of the rcore8 protocol emulator: receive cell rlc_rx, transmit cell rlc_tx.
//
// The cells follow the rules of the architecture specification (section "Line cell behaviour").
// A receive cell and a transmit cell form a pair and are linked: the transmit cell can send one bit
// per received bit (WS2812 forwarding), the receive cell can sample in the middle of each
// transmitted bit (SPI master). Pin synchronisers, pin multiplexer and output registers are outside.
//
// Configuration registers are written through a gated clock, one gate per register.

// ------------------------------------------------------------------ clock gate for a register
module rlc_cg (input clk, input en, output gclk);
`ifdef IHP_CELLS                               // library clock gate; IHP_SG13G2 selects the SG13G2 library, default is SG13CMOS5L
`ifdef IHP_SG13G2
    sg13g2_lgcp_1 g (.CLK(clk), .GATE(en), .GCLK(gclk));
`else
    sg13cmos5l_lgcp_1 g (.CLK(clk), .GATE(en), .GCLK(gclk));
`endif
`else
    reg q;
    always @(clk or en) if (!clk) q = en;       // transparent while the clock is low
    assign gclk = clk & q;
`endif
endmodule

// ------------------------------------------------------------------ 8-bit configuration register
module rlc_reg #(parameter [7:0] MASK = 8'hFF, parameter [7:0] RST = 8'h00) (
    input clk, input rst_n, input we, input [7:0] d, output [7:0] q);
    wire gclk;
    reg [7:0] r;
    rlc_cg cg (.clk(clk), .en(we), .gclk(gclk));
    always @(posedge gclk or negedge rst_n)
        if (!rst_n) r <= RST; else r <= d & MASK;
    assign q = r;
endmodule

// ------------------------------------------------------------------ one base unit of receive timing
module rlc_step (
    input            act,        // this base unit is processed
    input            en,         // receiver enabled (EN, RXEN, chip select)
    input            een,        // edge detector enabled (EN, chip select)
    input            ut,         // the timer counts in this base unit
    input            x,          // data input after the filter
    input            xc,         // clock / second input after the filter
    input            rxt,        // the timer belongs to the receiver
    input      [1:0] EDGE,
    input            ACC,
    input      [1:0] STOP,
    input            TWOPH, CPHA, CEN, BLEN,
    input      [1:0] TRIG,
    input      [7:0] A, B,
    input            wait_pred,  // a sample in this unit completes a frame
    input            run_i, ph_i, armed_i, quiet_i, last_i, lastc_i, prev_i, bothl_i,
    input      [7:0] T_i,
    input      [2:0] q_i,
    output reg       run_o, ph_o, armed_o, quiet_o, prev_o,
    output           last_o, lastc_o, bothl_o,
    output reg [7:0] T_o,
    output reg [2:0] q_o,
    output           acc,        // accepted edge
    output           opp,        // edge of the opposite direction
    output reg       smp,        // sample point
    output reg       smp_ph,     // phase input of the decode table
    output           smp_prev,   // previous sample for the decode table
    output reg       rst,        // receiver reset
    output reg       idle,       // the line became idle
    output           bl_start,   // start of both-low
    output           bl_quiet    // ... while the line was idle
);
    wire bl    = BLEN & ~x & ~xc;
    assign bl_start = act & en & bl & ~bothl_i;
    assign bl_quiet = quiet_i;
    wire es    = CEN ? xc : x;
    wire el    = CEN ? lastc_i : last_i;
    wire rise  = es & ~el, fall = ~es & el;
    wire dirok = (rise & EDGE[0]) | (fall & EDGE[1]);
    wire run1  = run_i & ~bl_start;
    assign acc = act & en & dirok & ~bl & (~ACC | ~run1);
    assign opp = act & een & (rise | fall) & ~dirok & (EDGE[0] ^ EDGE[1]) & ~bl;
    wire expy  = (T_i == 8'd1);
    assign smp_prev = prev_i;
    assign last_o  = act ? x  : last_i;
    assign lastc_o = act ? xc : lastc_i;
    assign bothl_o = act ? bl : bothl_i;

    always @* begin
        run_o = run1; T_o = T_i; ph_o = ph_i; armed_o = armed_i & ~bl_start; q_o = q_i;
        quiet_o = quiet_i; prev_o = prev_i;
        smp = 1'b0; smp_ph = 1'b0; rst = bl_start; idle = 1'b0;
        if (!act) begin
            run_o = run_i; armed_o = armed_i;
        end else if (!en) begin
            run_o = 1'b0; armed_o = 1'b0; q_o = 3'd0; rst = 1'b1;
        end else if (TRIG == 2'd1) begin                    // the pin edge is the sample point
            if (acc) begin smp = 1'b1; prev_o = x; quiet_o = 1'b0; end
        end else if (rxt) begin
            if (acc) begin
                if (!run1) prev_o = last_i;
                T_o = A; run_o = 1'b1; ph_o = 1'b0; quiet_o = 1'b0; q_o = 3'd0;
            end else if (run1 & ut) begin
                T_o = T_i - 8'd1;
                if (expy) begin
                    if (STOP == 2'd0 && q_i == 3'd7) begin   // eighth expiry without an edge
                        idle = 1'b1; quiet_o = 1'b1; run_o = 1'b0; rst = 1'b1; q_o = 3'd0;
                    end else begin
                        if (STOP == 2'd0) q_o = q_i + 3'd1;
                        ph_o   = ph_i ^ TWOPH;
                        smp    = TWOPH ? (ph_i == CPHA) : 1'b1;
                        smp_ph = ph_i;
                        if (smp) prev_o = x;
                        T_o = B;
                        if ((STOP == 2'd1 && smp) || (STOP == 2'd2 && smp && wait_pred)) begin
                            run_o = 1'b0; armed_o = 1'b1;
                        end
                    end
                end
            end else if (!run1 & armed_i & ~bl_start & (STOP != 2'd0) & ut) begin
                T_o = T_i - 8'd1;
                if (expy) begin idle = 1'b1; quiet_o = 1'b1; rst = 1'b1; armed_o = 1'b0; end
            end
        end
    end
endmodule

// ------------------------------------------------------------------ receive cell
// Registers (offset):  0 LCCTRL  EN RXEN - UNIT - PRE[2:0]      8 LCDEC   decode table
//                      1 LCPIN   INSEL[2:0] INV FILT[1:0] - -  10 LCSH    LEN[2:0] LSBF - - MEN -
//                      3 LCCLK   CSEL[2:0] CEN - - CPHA BLEN   11 LCMATCH pattern
//                      4 LCTIM   EDGE[1:0] ACC STOP[1:0] TWOPH TRIG[1:0]
//                      5 LCA   6 LCB                           12 LCRUN   LIM[2:0] RMODE - - REF[1:0]
//                     13 LCEVM  14 LCCS  SSEL[2:0] SSEN SSPOL
//                      7 LCEC   - - - - EC[3:0]               15 LCX     X9 ECF STA STP BEV BCD PAR[1:0]
// PAR: 0 no additional bit, 1 odd parity, 2 even parity, 3 ninth data bit (read in X9 with the oldest frame)
// BCD: an edge of the data input while the clock input is high sets STA (falling) or STP (rising) and resets
//      the receiver. EC: falling data edges while the clock input is low are counted; ECF when the count is EC.
// TRIG: 0 timer started by an edge, 1 pin edge, 2 middle of the bit of the transmit cell of the pair
// Status: RXF FERR EOP IDLE MATCH OVR STUFF BOTHL   (FERR: wrong parity)
module rlc_rx (
    input            clk,
    input            rst_n,
    input            ptick,      // peripheral clock enable
    input      [7:0] pins_r,     // synchronised pin levels, sampled on rising clock edges
    input      [7:0] pins_f,     // sampled on the falling edge half a period earlier (UNIT = 1)
    input            cfg_we,
    input      [3:0] cfg_a,
    input      [7:0] cfg_wdata,
    output reg [7:0] cfg_rdata,
    output     [7:0] stat,
    input            stat_we,    // write one to clear
    input      [7:0] stat_wdata, // already masked
    output     [7:0] rdata,      // oldest received frame
    input            data_re,    // remove it
    input            nb_mid,     // middle of a bit of the transmit cell
    output           rx_strobe,  // a received bit that is not discarded (to the transmit cell of the pair)
    output           crc_strobe, // the same, without the bits before the match pattern (to the CRC unit)
    output           rx_frame,   // a frame is complete in this cycle (to the CRC unit)
    output           rx_bit,
    output           evt,
    output           ref_evt,    // reference event for the trim counter
    output           dbg_smp,
    output           dbg_acc
);
    wire [7:0] r_ctrl, r_pin, r_clk, r_tim, r_a, r_b, r_dec, r_sh, r_match, r_run, r_evm, r_cs, r_ec, r_x;
    rlc_reg #(8'h0F) g7  (clk, rst_n, cfg_we & (cfg_a == 4'd7),  cfg_wdata, r_ec);
    rlc_reg #(8'h0F) g15 (clk, rst_n, cfg_we & (cfg_a == 4'd15), cfg_wdata, r_x);
    rlc_reg #(8'hD7) g0  (clk, rst_n, cfg_we & (cfg_a == 4'd0),  cfg_wdata, r_ctrl);
    rlc_reg #(8'hFC) g1  (clk, rst_n, cfg_we & (cfg_a == 4'd1),  cfg_wdata, r_pin);
    rlc_reg #(8'hF3) g3  (clk, rst_n, cfg_we & (cfg_a == 4'd3),  cfg_wdata, r_clk);
    rlc_reg          g4  (clk, rst_n, cfg_we & (cfg_a == 4'd4),  cfg_wdata, r_tim);
    rlc_reg          g5  (clk, rst_n, cfg_we & (cfg_a == 4'd5),  cfg_wdata, r_a);
    rlc_reg          g6  (clk, rst_n, cfg_we & (cfg_a == 4'd6),  cfg_wdata, r_b);
    rlc_reg          g8  (clk, rst_n, cfg_we & (cfg_a == 4'd8),  cfg_wdata, r_dec);
    rlc_reg #(8'hF2) g10 (clk, rst_n, cfg_we & (cfg_a == 4'd10), cfg_wdata, r_sh);
    rlc_reg          g11 (clk, rst_n, cfg_we & (cfg_a == 4'd11), cfg_wdata, r_match);
    rlc_reg #(8'hF3) g12 (clk, rst_n, cfg_we & (cfg_a == 4'd12), cfg_wdata, r_run);
    rlc_reg          g13 (clk, rst_n, cfg_we & (cfg_a == 4'd13), cfg_wdata, r_evm);
    rlc_reg #(8'hF8) g14 (clk, rst_n, cfg_we & (cfg_a == 4'd14), cfg_wdata, r_cs);
    always @* case (cfg_a)
        4'd0: cfg_rdata = r_ctrl;   4'd1: cfg_rdata = r_pin;    4'd3: cfg_rdata = r_clk;   4'd4: cfg_rdata = r_tim;
        4'd5: cfg_rdata = r_a;      4'd6: cfg_rdata = r_b;      4'd8: cfg_rdata = r_dec;   4'd10: cfg_rdata = r_sh;
        4'd11: cfg_rdata = r_match; 4'd12: cfg_rdata = r_run;   4'd13: cfg_rdata = r_evm;  4'd14: cfg_rdata = r_cs;
        4'd7: cfg_rdata = r_ec;     4'd15: cfg_rdata = {h0x, s_ecf, s_sta, s_stp, r_x[3:0]};
        default: cfg_rdata = 8'h00;
    endcase
    wire       EN = r_ctrl[7], RXEN = r_ctrl[6], UNIT = r_ctrl[4];
    wire [2:0] PRE = r_ctrl[2:0];
    wire [2:0] INSEL = r_pin[7:5];  wire INV = r_pin[4];  wire [1:0] FILT = r_pin[3:2];
    wire [2:0] CSEL = r_clk[7:5];   wire CEN = r_clk[4], CPHA = r_clk[1], BLEN = r_clk[0];
    wire [1:0] EDGE = r_tim[7:6];   wire ACC = r_tim[5];  wire [1:0] STOP = r_tim[4:3];  wire TWOPH = r_tim[2];
    wire [1:0] TRIG = r_tim[1:0];
    wire [2:0] LEN = r_sh[7:5];     wire LSBF = r_sh[4], MEN = r_sh[1];
    wire [2:0] LIM = r_run[7:5];    wire RMODE = r_run[4];  wire [1:0] REF = r_run[1:0];
    wire [2:0] SSEL = r_cs[7:5];    wire SSEN = r_cs[4], SSPOL = r_cs[3];
    wire [1:0] PAR = r_x[1:0];      wire BCD = r_x[2], BEV = r_x[3];
    wire       PARON = (PAR != 2'd0);

    // ---------------------------------------------------------------- state
    reg       ext, h0x, h1x, s_ferr, s_sta, s_stp, s_ecf;   // additional bit pending, ninth bits, flags
    reg [3:0] ecnt;                                        // edge count
    reg       run, ph, armed, quiet, last, lastc, prev, bothl;      // receive timing
    reg [7:0] T;
    reg [2:0] qc;
    reg [1:0] fd, fc;            // filter history of data and clock input
    reg       xd, xcl;           // filter outputs
    reg [6:0] pcnt;              // prescaler
    reg [7:0] win;               // last eight decoded bits
    reg [2:0] nbit, rrun;        // bit counter, run length
    reg [3:0] hcnt;              // decoded bits since the receiver reset, saturating at 8
    reg       rlast, rlast_v, skip, hunt;
    reg [7:0] h0, h1;            // holding register
    reg [1:0] hn;
    reg       s_idle, s_match, s_ovr, s_stuff, s_eop;

    // ---------------------------------------------------------------- inputs and filter
    wire cs_ok = ~SSEN | (pins_r[SSEL] == SSPOL);
    function [2:0] filt;         // {output, history}
        input x; input [1:0] h; input o; input [1:0] mode;
        begin
            case (mode)
            2'd1:    filt = {(x == h[0]) ? x : o, h[0], x};
            2'd2:    filt = {(x & h[0]) | (x & h[1]) | (h[0] & h[1]), h[0], x};
            default: filt = {x, h[0], x};
            endcase
        end
    endfunction
    wire        a1   = UNIT;                         // first half-unit, only with UNIT = 1
    wire        a2   = UNIT | ptick;
    wire [2:0]  fd1  = a1 ? filt(pins_f[INSEL] ^ INV, fd, xd, FILT) : {xd, fd};
    wire [2:0]  fc1  = a1 ? filt(pins_f[CSEL], fc, xcl, FILT)       : {xcl, fc};
    wire [2:0]  fd2  = a2 ? filt(pins_r[INSEL] ^ INV, fd1[1:0], fd1[2], FILT) : fd1;
    wire [2:0]  fc2  = a2 ? filt(pins_r[CSEL], fc1[1:0], fc1[2], FILT)        : fc1;

    // ---------------------------------------------------------------- time unit
    wire [6:0] pmax   = (7'd1 << PRE) - 7'd1;
    wire       ut_pre = (pcnt == pmax);
    wire       ut     = UNIT | ut_pre;

    // ---------------------------------------------------------------- receive timing, two half-units
    wire rx_en   = EN & RXEN & cs_ok;
    wire rxt     = (TRIG == 2'd0) & (EDGE != 2'd0);
    wire wait_pred = ~skip & ~hunt & (PARON ? ext : (nbit == LEN));
    wire wait_pred2 = PARON ? (smp1 ? (~skip & ~hunt & ~ext & (nbit == LEN)) : wait_pred) : (wait_pred & ~smp1);

    wire       run1, ph1, armed1, quiet1, prev1, last1, lastc1, bothl1;
    wire [7:0] T1;  wire [2:0] q1;
    wire       acc1, opp1, smp1, sph1, spv1, rst1, idle1, bls1, blq1;
    rlc_step s1 (.act(a1), .en(rx_en), .een(1'b0), .ut(1'b1), .x(fd1[2]), .xc(fc1[2]), .rxt(rxt),
        .EDGE(EDGE), .ACC(ACC), .STOP(STOP), .TWOPH(TWOPH), .CPHA(CPHA), .CEN(CEN), .BLEN(BLEN), .TRIG(TRIG),
        .A(r_a), .B(r_b), .wait_pred(wait_pred),
        .run_i(run), .ph_i(ph), .armed_i(armed), .quiet_i(quiet), .last_i(last), .lastc_i(lastc), .prev_i(prev),
        .bothl_i(bothl), .T_i(T), .q_i(qc),
        .run_o(run1), .ph_o(ph1), .armed_o(armed1), .quiet_o(quiet1), .prev_o(prev1), .last_o(last1),
        .lastc_o(lastc1), .bothl_o(bothl1), .T_o(T1), .q_o(q1),
        .acc(acc1), .opp(opp1), .smp(smp1), .smp_ph(sph1), .smp_prev(spv1), .rst(rst1), .idle(idle1),
        .bl_start(bls1), .bl_quiet(blq1));
    wire       run2, ph2, armed2, quiet2, prev2, last2, lastc2, bothl2;
    wire [7:0] T2;  wire [2:0] q2;
    wire       acc2, opp2, smp2, sph2, spv2, rst2, idle2, bls2, blq2;
    rlc_step s2 (.act(a2), .en(rx_en), .een(1'b0), .ut(ut), .x(fd2[2]), .xc(fc2[2]), .rxt(rxt),
        .EDGE(EDGE), .ACC(ACC), .STOP(STOP), .TWOPH(TWOPH), .CPHA(CPHA), .CEN(CEN), .BLEN(BLEN), .TRIG(TRIG),
        .A(r_a), .B(r_b), .wait_pred(wait_pred2),
        .run_i(run1), .ph_i(ph1), .armed_i(armed1), .quiet_i(quiet1), .last_i(last1), .lastc_i(lastc1), .prev_i(prev1),
        .bothl_i(bothl1), .T_i(T1), .q_i(q1),
        .run_o(run2), .ph_o(ph2), .armed_o(armed2), .quiet_o(quiet2), .prev_o(prev2), .last_o(last2),
        .lastc_o(lastc2), .bothl_o(bothl2), .T_o(T2), .q_o(q2),
        .acc(acc2), .opp(opp2), .smp(smp2), .smp_ph(sph2), .smp_prev(spv2), .rst(rst2), .idle(idle2),
        .bl_start(bls2), .bl_quiet(blq2));
    wire acc_any = acc1 | acc2;
    // the transmit cell of the pair gives the sample point
    wire smp_x = rx_en & (TRIG == 2'd2) & nb_mid;

    // ---------------------------------------------------------------- sample: decode, unstuff, shift
    wire s_v   = smp1 | smp2 | smp_x;
    wire s_lvl = smp1 ? fd1[2] : fd2[2];
    wire s_ph  = smp1 ? sph1 : smp2 ? sph2 : 1'b0;
    wire s_pv  = smp1 ? spv1 : smp2 ? spv2 : prev;
    wire d     = r_dec[{s_lvl, s_pv, s_ph}];
    wire lim_on = (LIM != 3'd0);
    wire discard = lim_on & skip;
    wire stuff_err = discard & (RMODE ? (rlast_v & (d == rlast)) : d);
    wire [2:0] rrun_inc = (rrun == 3'd7) ? 3'd7 : rrun + 3'd1;         // saturating
    wire [2:0] rrun_n = discard ? {2'b00, RMODE}
                      : RMODE ? ((rlast_v & (d == rlast)) ? rrun_inc : 3'd1)
                              : (d ? rrun_inc : 3'd0);
    wire skip_n = ~discard & lim_on & (rrun_n == LIM);
    wire shift  = s_v & ~discard;
    wire sdata  = shift & ~ext;                      // a data bit; the additional bit does not enter the window
    wire [7:0] win_n = LSBF ? {d, win[7:1]} : {win[6:0], d};
    wire [3:0] hcnt_n = hcnt[3] ? hcnt : hcnt + 4'd1;
    wire matched = sdata & hunt & hcnt_n[3] & (win_n == r_match);
    wire dlast  = sdata & ~hunt & (nbit == LEN);     // last data bit of a frame
    wire frame  = PARON ? (shift & ext) : dlast;
    wire [7:0] wsel = ext ? win : win_n;
    wire [7:0] fval = LSBF ? (wsel >> (3'd7 - LEN)) : (wsel & (8'hFF >> (3'd7 - LEN)));
    wire perr   = frame & PARON & (PAR != 2'd3) & ((^fval ^ d) != (PAR == 2'd1));
    wire x9     = PARON & d;
    wire push   = frame & (hn != 2'd2 | data_re);
    wire ovr    = frame & ~(hn != 2'd2 | data_re);
    // bus conditions: the levels at the end of this cycle against those of the cycle before
    wire dn = fd2[2], cn = fc2[2];
    wire bc_on  = EN & BCD & CEN & cs_ok & xcl & cn;
    wire bc_sta = bc_on & xd & ~dn;
    wire bc_stp = bc_on & ~xd & dn;
    wire ec_hit = EN & cs_ok & (r_ec[3:0] != 4'd0) & ~xcl & ~cn & xd & ~dn;
    wire ec_set = ec_hit & (ecnt + 4'd1 == r_ec[3:0]);
    wire x_we   = cfg_we & (cfg_a == 4'd15);
    wire rx_rst = rst1 | rst2 | bc_sta | bc_stp;

    assign rx_strobe  = sdata;
    assign crc_strobe = sdata & ~hunt;
    assign rx_frame   = frame;
    assign rx_bit    = d;
    assign stat  = {hn != 2'd0, s_ferr, s_eop, s_idle, s_match, s_ovr, s_stuff, bothl & EN};
    assign rdata = h0;
    assign evt   = (|(stat & r_evm)) | (BEV & (s_sta | s_stp | s_ecf));
    assign ref_evt = (REF == 2'd1) ? acc_any
                   : (REF == 2'd2) ? (bls1 | bls2)
                   : (REF == 2'd3) ? ((bls1 & blq1) | (bls2 & blq2)) : 1'b0;
    assign dbg_smp = s_v;
    assign dbg_acc = acc_any;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run <= 0; ph <= 0; armed <= 0; quiet <= 1; last <= 0; lastc <= 0; prev <= 0; bothl <= 0;
            T <= 0; qc <= 0; fd <= 0; fc <= 0; xd <= 0; xcl <= 0; pcnt <= 0;
            win <= 0; nbit <= 0; rrun <= 0; hcnt <= 0; rlast <= 0; rlast_v <= 0; skip <= 0; hunt <= 0;
            h0 <= 0; h1 <= 0; hn <= 0; s_idle <= 0; s_match <= 0; s_ovr <= 0; s_stuff <= 0; s_eop <= 0;
            ext <= 0; h0x <= 0; h1x <= 0; s_ferr <= 0; s_sta <= 0; s_stp <= 0; s_ecf <= 0; ecnt <= 0;
        end else begin
            // ---- inputs: followed also while the cell is disabled
            {xd, fd}  <= fd2;
            {xcl, fc} <= fc2;
            last <= last2; lastc <= lastc2; bothl <= bothl2;

            // ---- prescaler: restarts on an accepted edge
            if (acc_any)        pcnt <= 7'd0;
            else if (ptick)     pcnt <= ut_pre ? 7'd0 : pcnt + 7'd1;

            // ---- timer and phase
            run <= run2; armed <= armed2; quiet <= quiet2; prev <= prev2; qc <= q2;
            if (smp_x) prev <= fd2[2];
            T <= T2; ph <= ph2;

            // ---- receive data path
            if (s_v) begin
                if (lim_on) begin
                    rrun <= rrun_n; skip <= skip_n;
                    if (RMODE) begin rlast <= d; rlast_v <= 1'b1; end
                    if (stuff_err) s_stuff <= 1'b1;
                end
                if (sdata) begin
                    win <= win_n; hcnt <= hcnt_n;
                    nbit <= (matched | dlast) ? 3'd0 : nbit + 3'd1;
                    if (matched) begin hunt <= 1'b0; s_match <= 1'b1; end
                    if (dlast & PARON) ext <= 1'b1;
                end
                if (shift & ext) ext <= 1'b0;
            end
            if (rx_rst) begin
                ext <= 1'b0;
                nbit <= 3'd0; rrun <= 3'd0; rlast_v <= 1'b0; skip <= 1'b0; hunt <= MEN; hcnt <= 4'd0;
            end
            if (idle1 | idle2) s_idle <= 1'b1;
            if (ovr)           s_ovr  <= 1'b1;
            if (bls1 | bls2)   s_eop  <= 1'b1;      // both pins have gone low; stays until cleared
            if (perr)          s_ferr <= 1'b1;

            // ---- bus conditions and edge count; flags: write one to clear, a new event wins
            if (x_we) begin
                if (cfg_wdata[4]) s_stp <= 1'b0;
                if (cfg_wdata[5]) s_sta <= 1'b0;
                if (cfg_wdata[6]) s_ecf <= 1'b0;
            end
            if (bc_stp) s_stp <= 1'b1;
            if (bc_sta) s_sta <= 1'b1;
            if (ec_set) s_ecf <= 1'b1;
            if (cn != xcl)   ecnt <= 4'd0;
            else if (ec_hit) ecnt <= (ecnt == 4'd15) ? ecnt : ecnt + 4'd1;

            // ---- holding register
            case ({push, data_re & (hn != 2'd0)})
            2'b10: begin if (hn == 2'd0) begin h0 <= fval; h0x <= x9; end else begin h1 <= fval; h1x <= x9; end hn <= hn + 2'd1; end
            2'b01: begin h0 <= h1; h0x <= h1x; hn <= hn - 2'd1; end
            2'b11: begin if (hn == 2'd1) begin h0 <= fval; h0x <= x9; end else begin h0 <= h1; h0x <= h1x; h1 <= fval; h1x <= x9; end end
            default: ;
            endcase

            // ---- status: write one to clear; a new event in the same cycle wins
            if (stat_we) begin
                if (stat_wdata[6] & ~perr)            s_ferr  <= 1'b0;
                if (stat_wdata[5] & ~(bls1 | bls2))   s_eop   <= 1'b0;
                if (stat_wdata[4] & ~(idle1 | idle2)) s_idle  <= 1'b0;
                if (stat_wdata[3] & ~matched)         s_match <= 1'b0;
                if (stat_wdata[2] & ~ovr)             s_ovr   <= 1'b0;
                if (stat_wdata[1] & ~(s_v & stuff_err)) s_stuff <= 1'b0;
            end

            // ---- disabled: reset state (configuration is kept)
            if (!EN) begin
                run <= 0; armed <= 0; quiet <= 1; qc <= 0; ph <= 0;
                nbit <= 0; rrun <= 0; rlast_v <= 0; skip <= 0; hunt <= MEN; hcnt <= 0; hn <= 0;
                s_idle <= 0; s_match <= 0; s_ovr <= 0; s_stuff <= 0; s_eop <= 0;
                ext <= 0; s_ferr <= 0; s_sta <= 0; s_stp <= 0; s_ecf <= 0; ecnt <= 0;
            end
        end
    end
endmodule

// ------------------------------------------------------------------ transmit cell
// Registers (offset):  0 LCCTRL  EN - TXEN - - PRE[2:0]          9 LCENC   encode table
//                      1 LCPIN   - - - - - - OEM[1:0]           10 LCSH    LEN[2:0] LSBF SRC CMP - SS
//                      2 LCOUT   OUTSEL[2:0] OUTEN NSEL[2:0] NEN
//                      3 LCCLK   CSEL[2:0] - NFN CPOL CPHA -    12 LCRUN   LIM[2:0] RMODE LOW2 IDLE - -
//                      4 LCTIM   EDGE[1:0] - - - TWOPH TRIG[1:0]
//                      5 LCA   6 LCB   7 LCC                    13 LCEVM  14 LCCS  SSEL[2:0] SSEN SSPOL
//                     15 LCX    X9 - - - - ESTR PAR[1:0]
// PAR: 0 no additional bit, 1 odd parity, 2 even parity, 3 ninth data bit (X9 at the write of the frame)
// ESTR: with TRIG = 1 the first bit of a frame is put out at the first shift edge after the write
// TRIG: 0 timer, 1 edge on pin CSEL (EDGE = the edge at which the other side samples),
//       2 one bit per received bit of the receive cell of the pair
// Status: - TXE BUSY - - - - -
module rlc_tx (
    input            clk,
    input            rst_n,
    input            ptick,
    input      [7:0] pins_r,
    input            cfg_we,
    input      [3:0] cfg_a,
    input      [7:0] cfg_wdata,
    output reg [7:0] cfg_rdata,
    output     [7:0] stat,
    input            data_we,
    input      [7:0] data_wdata,
    input            nb_strobe,  // a received bit of the receive cell
    input            nb_bit,
    output           tx_mid,     // middle of a bit (sample point for the receive cell)
    output           tx_strobe,  // a transmitted data bit
    output           tx_bit,
    output           o_true,
    output           o_second,
    output           o_claim_t,  // the cell uses pin OUTSEL
    output           o_claim_n,  // the cell uses pin NSEL
    output     [2:0] o_tsel,
    output     [2:0] o_nsel,
    output           o_drive,    // drive regardless of DDR
    output           o_ddr,      // drive if DDR is set
    output           evt
);
    wire [7:0] r_ctrl, r_pin, r_out, r_clk, r_tim, r_a, r_b, r_c, r_enc, r_sh, r_run, r_evm, r_cs, r_x;
    rlc_reg #(8'h87) g15 (clk, rst_n, cfg_we & (cfg_a == 4'd15), cfg_wdata, r_x);
    rlc_reg #(8'hA7) g0  (clk, rst_n, cfg_we & (cfg_a == 4'd0),  cfg_wdata, r_ctrl);
    rlc_reg #(8'h03) g1  (clk, rst_n, cfg_we & (cfg_a == 4'd1),  cfg_wdata, r_pin);
    rlc_reg          g2  (clk, rst_n, cfg_we & (cfg_a == 4'd2),  cfg_wdata, r_out);
    rlc_reg #(8'hEE) g3  (clk, rst_n, cfg_we & (cfg_a == 4'd3),  cfg_wdata, r_clk);
    rlc_reg #(8'hC7) g4  (clk, rst_n, cfg_we & (cfg_a == 4'd4),  cfg_wdata, r_tim);
    rlc_reg          g5  (clk, rst_n, cfg_we & (cfg_a == 4'd5),  cfg_wdata, r_a);
    rlc_reg          g6  (clk, rst_n, cfg_we & (cfg_a == 4'd6),  cfg_wdata, r_b);
    rlc_reg          g7  (clk, rst_n, cfg_we & (cfg_a == 4'd7),  cfg_wdata, r_c);
    rlc_reg          g9  (clk, rst_n, cfg_we & (cfg_a == 4'd9),  cfg_wdata, r_enc);
    rlc_reg #(8'hFD) g10 (clk, rst_n, cfg_we & (cfg_a == 4'd10), cfg_wdata, r_sh);
    rlc_reg #(8'hFE) g12 (clk, rst_n, cfg_we & (cfg_a == 4'd12), cfg_wdata, r_run);
    rlc_reg #(8'h60) g13 (clk, rst_n, cfg_we & (cfg_a == 4'd13), cfg_wdata, r_evm);
    rlc_reg #(8'hF8) g14 (clk, rst_n, cfg_we & (cfg_a == 4'd14), cfg_wdata, r_cs);
    always @* case (cfg_a)
        4'd0: cfg_rdata = r_ctrl;   4'd1: cfg_rdata = r_pin;   4'd2: cfg_rdata = r_out;  4'd3: cfg_rdata = r_clk;
        4'd4: cfg_rdata = r_tim;    4'd5: cfg_rdata = r_a;     4'd6: cfg_rdata = r_b;    4'd7: cfg_rdata = r_c;
        4'd9: cfg_rdata = r_enc;    4'd10: cfg_rdata = r_sh;   4'd12: cfg_rdata = r_run; 4'd13: cfg_rdata = r_evm;
        4'd14: cfg_rdata = r_cs;    4'd15: cfg_rdata = r_x;    default: cfg_rdata = 8'h00;
    endcase
    wire       EN = r_ctrl[7], TXEN = r_ctrl[5];
    wire [2:0] PRE = r_ctrl[2:0];
    wire [1:0] OEM = r_pin[1:0];
    wire [2:0] CSEL = r_clk[7:5];   wire NFN = r_clk[3], CPOL = r_clk[2], CPHA = r_clk[1];
    wire [1:0] EDGE = r_tim[7:6];   wire TWOPH = r_tim[2];  wire [1:0] TRIG = r_tim[1:0];
    wire [2:0] LEN = r_sh[7:5];     wire LSBF = r_sh[4], SRC = r_sh[3], CMP = r_sh[2], SS = r_sh[0];
    wire [2:0] LIM = r_run[7:5];    wire RMODE = r_run[4], LOW2 = r_run[3], IDLE = r_run[2], EOP = r_run[1];
    wire [2:0] SSEL = r_cs[7:5];    wire SSEN = r_cs[4], SSPOL = r_cs[3];
    wire [1:0] PAR = r_x[1:0];      wire ESTR = r_x[2], X9 = r_x[7];
    wire       PARON = (PAR != 2'd0);

    reg       tbuf9, tsr9;          // ninth data bit of the frame in the buffer and of the frame being sent
    reg [7:0] T, tbuf, tsr;
    reg [6:0] pcnt;
    reg       ph, lastc;
    reg       tbuf_full, tbusy, tout, tcur, tlast, tlast_v, tfirst;
    reg [2:0] tstage;             // 0 start bit, 1 data bits, 2 stop bit, 3 nothing left, 4 additional bit
    reg [2:0] tcnt, trun;
    reg [1:0] eopc;                 // bit periods left of the end of packet

    wire cs_ok = ~SSEN | (pins_r[SSEL] == SSPOL);
    wire [6:0] pmax   = (7'd1 << PRE) - 7'd1;
    wire       ut_pre = (pcnt == pmax);

    // clock pin: an edge of the direction opposite to EDGE advances the transmitter
    wire xc   = pins_r[CSEL];
    wire rise = xc & ~lastc, fall = ~xc & lastc;
    wire opp  = EN & cs_ok & (EDGE[0] ^ EDGE[1]) & ((rise & ~EDGE[0]) | (fall & ~EDGE[1]));

    // ---------------------------------------------------------------- next symbol
    wire tx_en   = EN & TXEN & cs_ok;
    wire [2:0] trun_e  = tbusy ? trun : 3'd0;
    wire       tlv_e   = tbusy & tlast_v;
    wire [2:0] tst_e   = tbusy ? tstage : 3'd3;
    wire       stuff   = (LIM != 3'd0) & (trun_e == LIM);
    wire       exhaust = (tst_e == 3'd3);
    wire       load    = ~stuff & exhaust & tbuf_full;
    wire       sym_v   = stuff | ~exhaust | tbuf_full;
    wire [7:0] fr      = load ? tbuf : tsr;
    wire [2:0] st0     = load ? (SS ? 3'd0 : 3'd1) : tst_e;
    wire [2:0] cn0     = load ? 3'd0 : tcnt;
    wire [2:0] bidx    = LSBF ? cn0 : (LEN - cn0);
    wire       dbit    = fr[bidx];
    wire       sym_d8  = ~stuff & (st0 == 3'd1);                       // one of the data bits
    wire       sym_data = ~stuff & ((st0 == 3'd1) | (st0 == 3'd4));    // counted for stuffing
    wire       nin     = (PAR == 2'd3) ? tsr9 : (^(tsr & (8'hFF >> (3'd7 - LEN))) ^ (PAR == 2'd1));
    wire       sym     = stuff ? (RMODE ? ~tlast : 1'b0) : (st0 == 3'd0) ? ~IDLE : (st0 == 3'd1) ? dbit
                       : (st0 == 3'd4) ? nin : IDLE;
    wire [2:0] st_end  = SS ? 3'd2 : 3'd3;
    wire [2:0] st_n    = (st0 == 3'd0) ? 3'd1 : (st0 == 3'd1) ? ((cn0 == LEN) ? (PARON ? 3'd4 : st_end) : 3'd1)
                       : (st0 == 3'd4) ? st_end : 3'd3;
    wire [2:0] trun_inc = (trun_e == 3'd7) ? 3'd7 : trun_e + 3'd1;     // saturating
    wire [2:0] trun_n  = stuff ? {2'b00, RMODE}
                       : (sym_data & (LIM != 3'd0)) ? (RMODE ? ((tlv_e & (sym == tlast)) ? trun_inc : 3'd1)
                                                             : (sym ? trun_inc : 3'd0))
                       : trun_e;

    // ---------------------------------------------------------------- timing
    wire texp     = (T == 8'd1);
    wire t0_start = tx_en & (TRIG == 2'd0) & ~tbusy & tbuf_full & ptick;
    wire t0_exp   = tx_en & (TRIG == 2'd0) & tbusy & ptick & ut_pre & texp;
    wire t0_adv   = t0_exp & ~(TWOPH & ~ph);
    wire t1_start = tx_en & (TRIG == 2'd1) & ~tbusy & tbuf_full & (~ESTR | opp);
    wire t1_adv   = tx_en & (TRIG == 2'd1) & tbusy & opp & ~(CPHA & tfirst);
    wire t2_start = tx_en & (TRIG == 2'd2) & nb_strobe;
    wire t2_exp   = tx_en & (TRIG == 2'd2) & tbusy & ptick & ut_pre & texp & ~nb_strobe;
    wire take     = t0_start | t0_adv | t1_start | t1_adv | (t2_start & ~SRC);  // a symbol is requested
    wire got      = take & sym_v;
    // end of packet: with EOP set, two more bit periods follow the last symbol with both outputs low
    wire eop_on   = EOP & (TRIG == 2'd0);
    wire last_tk  = take & ~sym_v;
    wire eop_end  = last_tk & eop_on & (eopc == 2'd1);
    wire tend     = (last_tk & ~eop_on) | eop_end | (t2_exp & (~TWOPH | ph));
    wire tstart   = t0_start | t1_start | t2_start;
    wire tcur_n   = (t2_start & SRC) ? nb_bit : sym;
    wire newsym   = got | (t2_start & SRC);
    wire tph_n    = tstart ? 1'b0 : (t0_exp | t2_exp) ? (TWOPH & ~ph) : ph;
    wire tbusy_n  = tx_en & ((tbusy & ~tend) | newsym);
    wire enc_now  = newsym | ((t0_exp | t2_exp) & tbusy_n);
    wire tcur_e   = newsym ? tcur_n : tcur;
    wire tout_n   = r_enc[{tcur_e, tph_n, tout}];
    assign tx_mid    = t0_exp & (TWOPH ? ~ph : 1'b1);
    assign tx_strobe = got & sym_d8;
    assign tx_bit    = sym;

    // ---------------------------------------------------------------- status and outputs
    assign stat = {1'b0, ~tbuf_full, tbusy, 5'b00000};
    assign evt  = |(stat & r_evm);
    wire [8:0] b9   = {r_b == 8'd0, r_b};
    wire [7:0] thr  = tcur ? r_a : r_c;
    wire [8:0] thr9 = {thr == 8'd0, thr};
    wire [8:0] t9   = {T == 8'd0, T};
    wire       cmp_hi = ((b9 - t9) < thr9);
    wire       lvl  = CMP ? cmp_hi : tout;
    wire       low2 = LOW2 | (eopc != 2'd0);
    assign o_true    = low2 ? 1'b0 : tbusy ? lvl : IDLE;
    assign o_second  = low2 ? 1'b0 : tbusy ? (NFN ? (CPOL ^ ph ^ CPHA) : ~lvl) : (NFN ? CPOL : IDLE);
    assign o_claim_t = EN & r_out[4];
    assign o_claim_n = EN & r_out[0];
    assign o_tsel    = r_out[7:5];
    assign o_nsel    = r_out[3:1];
    assign o_drive   = cs_ok & ((OEM == 2'd1) | ((OEM == 2'd2) & (tbusy | LOW2)));
    assign o_ddr     = cs_ok & (OEM == 2'd0);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            T <= 0; pcnt <= 0; ph <= 0; lastc <= 0;
            tbuf <= 0; tsr <= 0; tbuf_full <= 0; tbusy <= 0; tout <= 0; tcur <= 0; tlast <= 0; tlast_v <= 0;
            tfirst <= 0; tstage <= 3'd3; tcnt <= 0; trun <= 0; eopc <= 0; tbuf9 <= 0; tsr9 <= 0;
        end else begin
            lastc <= xc;
            // ---- prescaler: restarts at the start of a frame
            if (tstart)         pcnt <= 7'd0;
            else if (ptick)     pcnt <= ut_pre ? 7'd0 : pcnt + 7'd1;
            // ---- timer and phase
            if (tstart | t0_exp | t2_exp)                       T <= r_b;
            else if (tbusy & ptick & ut_pre & (TRIG != 2'd1))   T <= T - 8'd1;
            ph <= tph_n;
            // ---- frame buffer and symbol sequence
            if (data_we & ~tbuf_full) begin tbuf <= data_wdata; tbuf9 <= X9; tbuf_full <= 1'b1; end
            if (got) begin
                if (load) begin tsr <= tbuf; tsr9 <= tbuf9; tbuf_full <= 1'b0; end
                if (~stuff) begin tstage <= st_n; tcnt <= (st0 == 3'd1) ? cn0 + 3'd1 : cn0; end
                trun <= trun_n;
                if (stuff | sym_data) begin tlast <= sym; tlast_v <= 1'b1; end
            end
            if (newsym) tcur <= tcur_n;
            if (tstart & ~tbusy) tfirst <= ~ESTR;
            else if (opp)        tfirst <= 1'b0;
            tbusy <= tbusy_n;
            if (!tbusy_n)                 eopc <= 2'd0;
            else if (last_tk & eop_on)    eopc <= (eopc == 2'd0) ? 2'd2 : eopc - 2'd1;
            if (!tbusy_n) begin tstage <= 3'd3; tout <= IDLE; end
            else if (enc_now) tout <= tout_n;
            // ---- disabled: reset state (configuration is kept)
            if (!EN) begin
                ph <= 0; tbuf_full <= 0; tbusy <= 0; tstage <= 3'd3; tout <= IDLE; tlast_v <= 0; trun <= 0; eopc <= 0;
            end
        end
    end
endmodule
