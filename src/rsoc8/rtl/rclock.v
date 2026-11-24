// rclock - clock source selection, reset, dividers, trim counter, clock output and debug signal.
//
// Follows the rules K1-K12 of the architecture specification.
//   rclk_src  the part with more than one clock: gates of the two sources, their enable chains,
//             reset synchronisers, presence dividers, trim register on the oscillator clock
//   rclk_ctl  registers and counters on the system clock
//   rclock    both together
//
// Registers:  0x0F  CLKSTAT  STRAP - MVALID MDONE TRIMD EXTP OSCRUN SRC   (read only)
//             0x120 CLKCTL   REFCELL[1:0] REFSEL[1:0] TRIMD LOOP OSCEN SRC   (protected)
//             0x121 OSCTRIM  0x122 CLKCDIV (protected)  0x123 CLKPDIV  0x124 TRINT  MEAS INT[6:0]
//             0x125/126 TRCNT (read only)  0x127/128 TRTGT  0x129 TRWIN  0x12A CLKOUT  EN - - - - DIV[2:0]
//             0x152 DBGSEL   EN - - - SEL[3:0]

// ------------------------------------------------------------------ sources, gates, reset
module rclk_src (
    input            clk_ext,
    input            clk_osc,
    input            rst_n,          // reset pin, asynchronous
    input            sel,            // requested source: 0 external, 1 oscillator
    input      [7:0] trim_sys,       // trim value on the system clock
    output           clk,            // system clock
    output           rst_sys_n,      // reset, released synchronously to clk
    output           tgl_ext,        // external clock divided by 64, for the presence check
    output           tgl_osc,
    output           open_osc,       // gate of the oscillator is open (oscillator clock domain)
    output reg [7:0] osc_trim        // trim inputs of the oscillator macro, change on its rising edge
);
    // reset release per source clock
    reg [1:0] re, ro, rs;
    always @(posedge clk_ext or negedge rst_n) if (!rst_n) re <= 2'b00; else re <= {re[0], 1'b1};
    always @(posedge clk_osc or negedge rst_n) if (!rst_n) ro <= 2'b00; else ro <= {ro[0], 1'b1};

    // enable chains: a source is enabled two rising edges after it is selected and the other gate
    // has closed; its gate opens and closes while the clock is low
    reg e1, e2, eg, o1, o2, og;
    always @(posedge clk_ext or negedge re[1])
        if (!re[1]) begin e1 <= 1'b0; e2 <= 1'b0; end else begin e1 <= ~sel & ~og; e2 <= e1; end
    always @(negedge clk_ext or negedge re[1])
        if (!re[1]) eg <= 1'b0; else eg <= e2;
    always @(posedge clk_osc or negedge ro[1])
        if (!ro[1]) begin o1 <= 1'b0; o2 <= 1'b0; end else begin o1 <= sel & ~eg; o2 <= o1; end
    always @(negedge clk_osc or negedge ro[1])
        if (!ro[1]) og <= 1'b0; else og <= o2;
    wire gext, gosc;
    rlc_cg g_e (.clk(clk_ext), .en(e2), .gclk(gext));
    rlc_cg g_o (.clk(clk_osc), .en(o2), .gclk(gosc));
    assign clk = gext | gosc;
    assign open_osc = og;

    always @(posedge clk or negedge rst_n) if (!rst_n) rs <= 2'b00; else rs <= {rs[0], 1'b1};
    assign rst_sys_n = rs[1];

    // presence dividers
    reg [5:0] de, do_;
    always @(posedge clk_ext or negedge re[1]) if (!re[1]) de  <= 6'd0; else de  <= de  + 6'd1;
    always @(posedge clk_osc or negedge ro[1]) if (!ro[1]) do_ <= 6'd0; else do_ <= do_ + 6'd1;
    assign tgl_ext = de[5];
    assign tgl_osc = do_[5];

    always @(posedge clk_osc or negedge ro[1]) if (!ro[1]) osc_trim <= 8'h80; else osc_trim <= trim_sys;
endmodule

// ------------------------------------------------------------------ registers and counters
module rclk_ctl (
    input            clk,
    input            rst_n,          // rst_sys_n
    input            strap,          // clock source strap pin: 0 external, 1 oscillator

    input      [8:0] io_addr,
    input            io_host,
    input            io_re,
    input            io_we,
    input      [7:0] io_wdata,
    output reg [7:0] io_rdata,
    input            io_unlock,
    output           io_prot,

    input            tgl_ext, tgl_osc, open_osc,
    output           sel,            // to rclk_src
    output           osc_en,         // enable input of the oscillator macro
    output           relax_en,       // enable input of the relaxation oscillator
    output     [7:0] trim_sys,

    output reg       cke,            // core clock enable
    output reg       ptick,          // peripheral clock enable

    input            clk_slow,       // relaxation oscillator (~100 kHz)
    input            ref_host,       // host link clock pin
    input            ref_pin,        // reference pin
    input      [1:0] ref_evt,        // reference events of the receive cells
    output           trim_evt,       // a measurement inside the window has ended

    input      [1:0] smp_evt, acc_evt, tx_strobe, core_cen,   // signals for the debug pin
    input            bus_hold,
    output           cko_en, cko,    // clock output takes over its pin
    output           dbg_en, dbg
);
    // ---------------------------------------------------------------- registers
    wire pg  = (io_addr[8:4] == 5'h12);
    wire [3:0] lo = io_addr[3:0];
    wire a_stat = (io_addr == 9'h00F), a_dbg = (io_addr == 9'h152);
    wire a_ctl = pg & (lo == 4'h0), a_trim = pg & (lo == 4'h1), a_cdiv = pg & (lo == 4'h2), a_pdiv = pg & (lo == 4'h3);
    wire a_int = pg & (lo == 4'h4), a_cntl = pg & (lo == 4'h5), a_cnth = pg & (lo == 4'h6);
    assign io_prot = a_ctl | a_cdiv;
    wire ok = io_unlock | io_host;

    reg        booted, r_src, r_oscen, sel_q, r_relaxen;
    reg  [5:0] r_ctl;                     // REFCELL REFSEL TRIMD LOOP
    reg  [7:0] r_trim, cnth_lat;
    wire [7:0] r_cdiv, r_pdiv, r_int, tgtl, tgth, r_win, r_cko, r_dbg;
    // Reset value 1: the cores run at half the system clock. The timing constraints give the paths from the
    // code memories through the instruction inputs of the cores two clock cycles, which holds for a divider
    // of 2 or more. Divider 1 (value 0) is for a system clock of 33 MHz or less.
    rlc_reg #(8'hFF, 8'h01) u_cdiv (clk, rst_n, io_we & a_cdiv & ok, io_wdata, r_cdiv);
    rlc_reg          u_pdiv (clk, rst_n, io_we & a_pdiv, io_wdata, r_pdiv);
    rlc_reg #(8'h7F) u_int  (clk, rst_n, io_we & a_int, io_wdata, r_int);
    rlc_reg          u_tgtl (clk, rst_n, io_we & pg & (lo == 4'h7), io_wdata, tgtl);
    rlc_reg          u_tgth (clk, rst_n, io_we & pg & (lo == 4'h8), io_wdata, tgth);
    rlc_reg          u_win  (clk, rst_n, io_we & pg & (lo == 4'h9), io_wdata, r_win);
    rlc_reg #(8'h87) u_cko  (clk, rst_n, io_we & pg & (lo == 4'hA), io_wdata, r_cko);
    rlc_reg #(8'h8F) u_dbg  (clk, rst_n, io_we & a_dbg, io_wdata, r_dbg);
    wire       loop = r_ctl[0], trimd = r_ctl[1];
    wire [1:0] refsel = r_ctl[3:2];
    wire       refcell = r_ctl[4];

    // ---------------------------------------------------------------- presence of the two clocks (K2)
    reg  [2:0] se, so;                    // synchronisers and previous value
    reg  [1:0] sa;                        // gate of the oscillator, synchronised
    reg  [9:0] win;
    reg        seen_e, seen_o, pres_e, pres_o;
    wire       te = se[2] ^ se[1], to = so[2] ^ so[1];
    wire       act = sa[1];               // active source

    // ---------------------------------------------------------------- source request (K3, K4)
    assign sel      = booted ? sel_q : strap;
    assign osc_en   = booted ? (r_oscen | r_src | sel_q | act) : strap;      // enabled while requested, selected or active (K1)
    assign relax_en = r_relaxen;
    assign trim_sys = r_trim;

    // ---------------------------------------------------------------- trim counter (K6-K9)
    reg  [2:0]  sh, sp, ss;               // reference pins & clk_slow: synchronisers and previous value
    reg  [1:0]  st;                       // 0 idle, 1 waiting for the first edge, 2 counting
    reg  [15:0] cnt, trcnt;
    reg  [6:0]  per;
    reg         mdone, mvalid, done_q;
    wire        slowref  = (refsel == 2'd3);
    wire        edge_pin = slowref ? (ss[1] & ~ss[2]) : (refsel[0] ? (sp[1] & ~sp[2]) : (sh[1] & ~sh[2]));
    wire        line     = (refsel == 2'd2);
    wire        rev      = line ? ref_evt[refcell] : (edge_pin & (~refsel[1] | slowref));
    wire [15:0] cnt1     = (cnt == 16'hFFFF) ? cnt : cnt + 16'd1;
    wire        ctl_wr   = io_we & a_ctl & ok;
    wire        meas_wr  = io_we & a_int & io_wdata[7];
    wire [15:0] tgt      = {tgth, tgtl};
    wire [15:0] wspan    = {2'b00, r_win, 6'd0};
    // Line reference with a window: an event that comes earlier than the target minus the window is not
    // used and does not restart the count. A periodic event with other events in between (USB keep-alive
    // with packets in the frame) is then measured from one period to the next.
    wire        early    = line & (r_win != 8'd0) & (({1'b0, cnt} + {1'b0, wspan}) <= {1'b0, tgt});
    wire        rev_c    = rev & ~early;
    wire        fin      = (st == 2'd2) & rev_c & (line | (per == r_int[6:0]));
    wire [16:0] diff     = {1'b0, trcnt} - {1'b0, tgt};
    wire [15:0] adiff    = diff[16] ? (~diff[15:0] + 16'd1) : diff[15:0];
    wire        valid    = (r_win == 8'd0) | (adiff < wspan);
    assign trim_evt = done_q & valid;
    wire        up = done_q & valid & loop &  diff[16] & (r_trim != 8'hFF);
    wire        dn = done_q & valid & loop & ~diff[16] & (adiff != 16'd0) & (r_trim != 8'h00);

    // ---------------------------------------------------------------- dividers (K5)
    reg  [7:0] cc, pc;
    wire [7:0] cc_n = (cc == 8'd0) ? r_cdiv : cc - 8'd1;
    wire [7:0] pc_n = (pc == 8'd0) ? r_pdiv : pc - 8'd1;

    // ---------------------------------------------------------------- clock output and debug signal (K11)
    reg  [7:0] oc;
    reg        cko_q, dbg_q;
    reg        dsig;
    always @* begin
        case (r_dbg[3:0])
            4'd0:  dsig = smp_evt[0];    4'd1:  dsig = smp_evt[1];
            4'd2:  dsig = tx_strobe[0];  4'd3:  dsig = tx_strobe[1];
            4'd4:  dsig = acc_evt[0];    4'd5:  dsig = acc_evt[1];
            4'd6:  dsig = ref_evt[0];    4'd7:  dsig = ref_evt[1];
            4'd8:  dsig = core_cen[0];   4'd9:  dsig = core_cen[1];
            4'd10: dsig = bus_hold;      4'd11: dsig = ptick;
            4'd12: dsig = cke;           4'd13: dsig = (st != 2'd0);
            4'd14: dsig = trim_evt;      4'd15: dsig = ss[1];
        endcase
    end
    assign cko_en = r_cko[7];
    assign cko    = cko_q;
    assign dbg_en = r_dbg[7];
    assign dbg    = dbg_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            booted <= 1'b0; r_src <= 1'b0; r_oscen <= 1'b0; sel_q <= 1'b0; r_relaxen <= 1'b0; r_ctl <= 6'd0; r_trim <= 8'h80; cnth_lat <= 8'd0;
            se <= 3'd0; so <= 3'd0; sa <= 2'd0; win <= 10'd0; seen_e <= 1'b0; seen_o <= 1'b0; pres_e <= 1'b0; pres_o <= 1'b0;
            sh <= 3'd0; sp <= 3'd0; ss <= 3'd0; st <= 2'd0; cnt <= 16'd0; trcnt <= 16'd0; per <= 7'd0;
            mdone <= 1'b0; mvalid <= 1'b0; done_q <= 1'b0;
            cc <= 8'd0; pc <= 8'd0; cke <= 1'b1; ptick <= 1'b1; oc <= 8'd0; cko_q <= 1'b0; dbg_q <= 1'b0;
        end else begin
            // ---- start: the strap gives the first source
            if (!booted) begin booted <= 1'b1; r_src <= strap; r_oscen <= strap; sel_q <= strap; end
            else if ((r_src != sel_q) & (r_src ? pres_o : pres_e)) sel_q <= r_src;
            if (ctl_wr) begin r_src <= io_wdata[0]; r_oscen <= io_wdata[1]; r_ctl <= {1'b0, io_wdata[6:2]}; r_relaxen <= io_wdata[7]; end
            // ---- presence
            se <= {se[1:0], tgl_ext}; so <= {so[1:0], tgl_osc}; sa <= {sa[0], open_osc};
            win <= win + 10'd1;
            if (win == 10'h3FF) begin pres_e <= seen_e | te; pres_o <= seen_o | to; seen_e <= 1'b0; seen_o <= 1'b0; end
            else begin if (te) seen_e <= 1'b1; if (to) seen_o <= 1'b1; end
            // ---- dividers
            cc <= cc_n; cke <= (cc_n == 8'd0);
            pc <= pc_n; ptick <= (pc_n == 8'd0);
            // ---- trim counter
            sh <= {sh[1:0], ref_host}; sp <= {sp[1:0], ref_pin}; ss <= {ss[1:0], clk_slow};
            done_q <= fin;
            cnt <= cnt1;
            if (ctl_wr) st <= 2'd0;
            else case (st)
                2'd0: if (line | meas_wr | (loop & ~line)) st <= 2'd1;
                2'd1: if (rev) begin st <= 2'd2; cnt <= 16'd1; per <= 7'd0; end
                default: if (rev_c) begin
                    if (fin) begin
                        trcnt <= cnt; mdone <= 1'b1;
                        if (line) cnt <= 16'd1; else st <= 2'd0;
                    end else per <= per + 7'd1;
                end
            endcase
            if (meas_wr) mdone <= 1'b0;
            if (done_q) mvalid <= valid;
            // ---- trim value: written by the bus, stepped by the loop
            if (io_we & a_trim) r_trim <= io_wdata;
            else if (up) r_trim <= r_trim + 8'd1;
            else if (dn) r_trim <= r_trim - 8'd1;
            if (io_re & a_cntl) cnth_lat <= trcnt[15:8];
            // ---- outputs
            oc <= oc + 8'd1;
            cko_q <= oc[r_cko[2:0]];
            dbg_q <= dsig;
        end
    end

    always @* begin
        io_rdata = 8'h00;
        if (a_stat) io_rdata = {strap, 1'b0, mvalid, mdone, trimd, pres_e, pres_o, act};
        if (a_dbg)  io_rdata = r_dbg;
        if (pg) case (lo)
            4'h0: io_rdata = {r_relaxen, r_ctl[4:0], r_oscen, r_src};
            4'h1: io_rdata = r_trim;
            4'h2: io_rdata = r_cdiv;
            4'h3: io_rdata = r_pdiv;
            4'h4: io_rdata = {(st != 2'd0) & ~line, r_int[6:0]};
            4'h5: io_rdata = trcnt[7:0];
            4'h6: io_rdata = cnth_lat;
            4'h7: io_rdata = tgtl;
            4'h8: io_rdata = tgth;
            4'h9: io_rdata = r_win;
            4'hA: io_rdata = r_cko;
            default: ;
        endcase
    end
endmodule

// ------------------------------------------------------------------ both parts
module rclock (
    input            clk_ext, clk_osc, clk_slow, rst_n, strap,
    output           clk, rst_sys_n,
    output           osc_en, relax_en,
    output     [7:0] osc_trim,
    input      [8:0] io_addr,
    input            io_host, io_re, io_we,
    input      [7:0] io_wdata,
    output     [7:0] io_rdata,
    input            io_unlock,
    output           io_prot,
    output           cke, ptick,
    input            ref_host, ref_pin,
    input      [1:0] ref_evt,
    output           trim_evt,
    input      [1:0] smp_evt, acc_evt, tx_strobe, core_cen,
    input            bus_hold,
    output           cko_en, cko, dbg_en, dbg
);
    wire sel, tgl_ext, tgl_osc, open_osc; wire [7:0] trim_sys;
    rclk_src src (.clk_ext(clk_ext), .clk_osc(clk_osc), .rst_n(rst_n), .sel(sel), .trim_sys(trim_sys), .clk(clk),
        .rst_sys_n(rst_sys_n), .tgl_ext(tgl_ext), .tgl_osc(tgl_osc), .open_osc(open_osc), .osc_trim(osc_trim));
    rclk_ctl ctl (.clk(clk), .rst_n(rst_sys_n), .strap(strap), .io_addr(io_addr), .io_host(io_host), .io_re(io_re),
        .io_we(io_we), .io_wdata(io_wdata), .io_rdata(io_rdata), .io_unlock(io_unlock), .io_prot(io_prot),
        .tgl_ext(tgl_ext), .tgl_osc(tgl_osc), .open_osc(open_osc), .sel(sel), .osc_en(osc_en), .relax_en(relax_en), .trim_sys(trim_sys),
        .cke(cke), .ptick(ptick), .clk_slow(clk_slow), .ref_host(ref_host), .ref_pin(ref_pin), .ref_evt(ref_evt), .trim_evt(trim_evt),
        .smp_evt(smp_evt), .acc_evt(acc_evt), .tx_strobe(tx_strobe), .core_cen(core_cen), .bus_hold(bus_hold),
        .cko_en(cko_en), .cko(cko), .dbg_en(dbg_en), .dbg(dbg));
endmodule
