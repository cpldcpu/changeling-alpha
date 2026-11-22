// rtimers - 16-bit timer with capture and two compare registers, three PWM channels, CRC unit.
//
// Follows the rules B1-B7 and F1-F7 of the architecture specification.
// Configuration registers are written through gated clocks (rlc_reg in rlinecells.v).
//
// Registers:  fast tier  0x26 TCNTL  0x27 TCNTH  0x28 ICRL  0x29 ICRH  0x2A CRCIN (write)
//             page       0x130 TCR   RUN CTC - - - PS[2:0]         0x131 TCAP  CEDGE CSRC[1:0] - - CPIN[2:0]
//                        0x132/133 OCRA   0x134/135 OCRB
//                        0x138 PWMC  - PPS[2:0] - PEN2 PEN1 PEN0   0x139 PWMTOP   0x13A-13C PWM0..2
//                        0x140 CRCCTL EN RIGHT CSRC[2:0] - BUSY OWNER   0x141 CRCLEN
//                        0x142-145 CRCPOLY   0x146-149 CRCVAL   0x14A-14D CRCREF
//             read of 0x2A (CRCST): EQF EQ BUSY - - - - -

module rtimers (
    input            clk,
    input            rst_n,
    input            ptick,          // peripheral clock enable

    input      [8:0] io_addr,
    input            io_core,
    input            io_host,        // access by the host link: no owner check
    input            io_re,
    input            io_we,
    input      [7:0] io_wdata,
    output reg [7:0] io_rdata,

    input      [7:0] pins_sync,      // synchronised bidirectional pins (capture)
    input      [1:0] acc_evt,        // accepted edges of the receive cells
    input      [1:0] ref_evt,        // reference events of the receive cells
    input      [1:0] rx_strobe, rx_bit, tx_strobe, tx_bit,   // bits of the line cells for the CRC unit
    input      [1:0] rx_frame,       // a frame of a receive cell is complete (same cycle as its last bit)

    output           capt_evt, oca_evt, ocb_evt, ovf_evt,    // pulses to the event flags
    output     [2:0] pwm_en,         // channel takes over its output pin
    output     [2:0] pwm_out
);
    // ---------------------------------------------------------------- address decoding
    wire a_tcntl = (io_addr == 9'h026), a_tcnth = (io_addr == 9'h027);
    wire a_icrl  = (io_addr == 9'h028), a_icrh  = (io_addr == 9'h029);
    wire a_crcin = (io_addr == 9'h02A);
    wire pg3 = (io_addr[8:4] == 5'h13), pg4 = (io_addr[8:4] == 5'h14);
    wire [3:0] lo = io_addr[3:0];
    wire [7:0] tcr, tcap, ocral, ocrah, ocrbl, ocrbh, pwmc, pwmtop, pwm0, pwm1, pwm2;
    wire [7:0] crcctl, crclen, poly0, poly1, poly2, poly3, ref0, ref1, ref2, ref3;

    rlc_reg #(8'hC7) u_tcr   (clk, rst_n, io_we & pg3 & (lo == 4'h0), io_wdata, tcr);
    rlc_reg #(8'hE7) u_tcap  (clk, rst_n, io_we & pg3 & (lo == 4'h1), io_wdata, tcap);
    rlc_reg          u_ocral (clk, rst_n, io_we & pg3 & (lo == 4'h2), io_wdata, ocral);
    rlc_reg          u_ocrah (clk, rst_n, io_we & pg3 & (lo == 4'h3), io_wdata, ocrah);
    rlc_reg          u_ocrbl (clk, rst_n, io_we & pg3 & (lo == 4'h4), io_wdata, ocrbl);
    rlc_reg          u_ocrbh (clk, rst_n, io_we & pg3 & (lo == 4'h5), io_wdata, ocrbh);
    rlc_reg #(8'h77) u_pwmc  (clk, rst_n, io_we & pg3 & (lo == 4'h8), io_wdata, pwmc);
    rlc_reg          u_ptop  (clk, rst_n, io_we & pg3 & (lo == 4'h9), io_wdata, pwmtop);
    rlc_reg          u_pwm0  (clk, rst_n, io_we & pg3 & (lo == 4'hA), io_wdata, pwm0);
    rlc_reg          u_pwm1  (clk, rst_n, io_we & pg3 & (lo == 4'hB), io_wdata, pwm1);
    rlc_reg          u_pwm2  (clk, rst_n, io_we & pg3 & (lo == 4'hC), io_wdata, pwm2);

    // ---------------------------------------------------------------- 16-bit timer (B1-B5)
    wire        run = tcr[7], ctc = tcr[6];
    wire [15:0] ocra = {ocrah, ocral}, ocrb = {ocrbh, ocrbl};
    reg  [15:0] tcnt, icr;
    reg  [6:0]  psc;
    reg  [7:0]  wtmp0, wtmp1, rtmp0, rtmp1;      // high bytes of 16-bit accesses, per core
    reg         cprev;

    wire [6:0]  psm   = (7'd1 << tcr[2:0]) - 7'd1;
    wire        t_wr  = io_we & a_tcntl;
    wire        tstep = ptick & run & ((psc & psm) == psm) & ~t_wr;
    wire        clr   = ctc & (tcnt == ocra);
    wire [15:0] tn    = clr ? 16'd0 : tcnt + 16'd1;
    assign ovf_evt = tstep & (tcnt == 16'hFFFF) & ~clr;
    assign oca_evt = tstep & (tn == ocra);
    assign ocb_evt = tstep & (tn == ocrb);

    wire cpin  = pins_sync[tcap[2:0]];
    wire cedge = tcap[7] ? (cprev & ~cpin) : (~cprev & cpin);
    wire cev   = (tcap[6:5] == 2'd0) ? cedge :
                 (tcap[6:5] == 2'd1) ? acc_evt[tcap[0]] :
                 (tcap[6:5] == 2'd2) ? ref_evt[tcap[0]] : 1'b0;
    assign capt_evt = cev & run;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tcnt <= 0; icr <= 0; psc <= 0; cprev <= 0; wtmp0 <= 0; wtmp1 <= 0; rtmp0 <= 0; rtmp1 <= 0;
        end else begin
            cprev <= cpin;
            if (!run)       psc <= 7'd0;
            else if (ptick) psc <= psc + 7'd1;
            if (t_wr)       tcnt <= {io_core ? wtmp1 : wtmp0, io_wdata};
            else if (tstep) tcnt <= tn;
            if (capt_evt)   icr <= tcnt;
            if (io_we & a_tcnth) begin if (io_core) wtmp1 <= io_wdata; else wtmp0 <= io_wdata; end
            if (io_re & a_tcntl) begin if (io_core) rtmp1 <= tcnt[15:8]; else rtmp0 <= tcnt[15:8]; end
            if (io_re & a_icrl)  begin if (io_core) rtmp1 <= icr[15:8];  else rtmp0 <= icr[15:8];  end
        end
    end

    // ---------------------------------------------------------------- PWM (B6)
    wire [2:0] pen  = pwmc[2:0];
    wire       pany = |pen;
    reg  [6:0] ppsc;
    reg  [7:0] pcnt, atop, ad0, ad1, ad2;        // counter and the values in effect
    wire [6:0] ppm   = (7'd1 << pwmc[6:4]) - 7'd1;
    wire       pstep = ptick & pany & ((ppsc & ppm) == ppm);
    wire       pwrap = (pcnt == atop);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin ppsc <= 0; pcnt <= 0; atop <= 0; ad0 <= 0; ad1 <= 0; ad2 <= 0; end
        else begin
            if (!pany)      ppsc <= 7'd0;
            else if (ptick) ppsc <= ppsc + 7'd1;
            if (!pany)      pcnt <= 8'd0;
            else if (pstep) pcnt <= pwrap ? 8'd0 : pcnt + 8'd1;
            if (!pany | (pstep & pwrap)) begin atop <= pwmtop; ad0 <= pwm0; ad1 <= pwm1; ad2 <= pwm2; end
        end
    end
    assign pwm_en  = pen;
    assign pwm_out = {pen[2] & (pcnt < ad2), pen[1] & (pcnt < ad1), pen[0] & (pcnt < ad0)};

    // ---------------------------------------------------------------- CRC unit (F1-F7)
    wire        c_en = crcctl[7], right = crcctl[6], owner = crcctl[0];
    wire [2:0]  csrc = crcctl[5:3];
    wire        cok  = io_host | (io_core == owner);
    rlc_reg #(8'hF9) u_cctl (clk, rst_n, io_we & pg4 & (lo == 4'h0) & (cok | ~c_en), io_wdata, crcctl);
    rlc_reg #(8'h1F) u_clen (clk, rst_n, io_we & pg4 & (lo == 4'h1) & cok, io_wdata, crclen);
    rlc_reg          u_pl0  (clk, rst_n, io_we & pg4 & (lo == 4'h2) & cok, io_wdata, poly0);
    rlc_reg          u_pl1  (clk, rst_n, io_we & pg4 & (lo == 4'h3) & cok, io_wdata, poly1);
    rlc_reg          u_pl2  (clk, rst_n, io_we & pg4 & (lo == 4'h4) & cok, io_wdata, poly2);
    rlc_reg          u_pl3  (clk, rst_n, io_we & pg4 & (lo == 4'h5) & cok, io_wdata, poly3);
    rlc_reg          u_rf0  (clk, rst_n, io_we & pg4 & (lo == 4'hA) & cok, io_wdata, ref0);
    rlc_reg          u_rf1  (clk, rst_n, io_we & pg4 & (lo == 4'hB) & cok, io_wdata, ref1);
    rlc_reg          u_rf2  (clk, rst_n, io_we & pg4 & (lo == 4'hC) & cok, io_wdata, ref2);
    rlc_reg          u_rf3  (clk, rst_n, io_we & pg4 & (lo == 4'hD) & cok, io_wdata, ref3);
    wire [31:0] poly = {poly3, poly2, poly1, poly0};
    wire [31:0] cref = {ref3, ref2, ref1, ref0};
    reg  [31:0] val;
    reg  [7:0]  sbuf;                 // byte written to CRCIN, two bits are used per cycle
    reg  [2:0]  scnt;                 // cycles left for that byte
    wire        busy = (scnt != 3'd0);

    // one step; all inputs are arguments so that every simulator re-evaluates the callers
    function [31:0] cstep(input [31:0] v, input b, input r, input [4:0] len, input [31:0] p);
        reg fb;
        begin
            fb    = (r ? v[0] : v[len]) ^ b;
            cstep = (r ? {1'b0, v[31:1]} : {v[30:0], 1'b0}) ^ (p & {32{fb}});
        end
    endfunction

    reg lstb, lbit;                   // bit of the selected line cell
    always @* begin
        case (csrc)
            3'd1:    begin lstb = rx_strobe[0]; lbit = rx_bit[0]; end
            3'd2:    begin lstb = tx_strobe[0]; lbit = tx_bit[0]; end
            3'd3:    begin lstb = rx_strobe[1]; lbit = rx_bit[1]; end
            3'd4:    begin lstb = tx_strobe[1]; lbit = tx_bit[1]; end
            default: begin lstb = 1'b0;         lbit = 1'b0;      end
        endcase
    end
    wire        sw    = (csrc == 3'd0);
    wire        e1    = c_en & (sw ? busy : lstb);          // first step of this cycle
    wire        e2    = c_en & sw & busy;                   // second step, only for CRCIN
    wire        b1    = sw ? (right ? sbuf[0] : sbuf[7]) : lbit;
    wire        b2    = right ? sbuf[1] : sbuf[6];
    wire [31:0] v1    = e1 ? cstep(val, b1, right, crclen[4:0], poly) : val;
    wire [31:0] v2    = e2 ? cstep(v1, b2, right, crclen[4:0], poly) : v1;
    wire        in_wr = io_we & a_crcin & cok & c_en & sw;
    // comparison with the reference value. With left shift only the low LEN+1 bits are compared.
    wire [31:0] cmask = right ? 32'hFFFFFFFF : ~(32'hFFFFFFFE << crclen[4:0]);
    wire        eq    = (((val ^ cref) & cmask) == 32'd0);
    // EQF: the comparison at the last frame boundary. The boundary is the last bit of a frame of the
    // selected receive cell, or the last step of a byte written to CRCIN; the value is complete one
    // cycle later.
    wire        fbnd  = c_en & (sw ? (scnt == 3'd1) : (csrc == 3'd1) ? rx_frame[0] : (csrc == 3'd3) ? rx_frame[1] : 1'b0);
    reg         fbnd_q, eqf;
    wire        v_wr  = io_we & pg4 & cok & (lo >= 4'h6) & (lo <= 4'h9);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin val <= 0; sbuf <= 0; scnt <= 0; fbnd_q <= 0; eqf <= 0; end
        else begin
            fbnd_q <= fbnd;
            if (fbnd_q) eqf <= eq;
            val <= v2;
            if (v_wr) case (lo[1:0])
                2'd2: val[7:0]   <= io_wdata;
                2'd3: val[15:8]  <= io_wdata;
                2'd0: val[23:16] <= io_wdata;
                2'd1: val[31:24] <= io_wdata;
            endcase
            if (in_wr)     begin sbuf <= io_wdata; scnt <= 3'd4; end
            else if (busy) begin sbuf <= right ? {2'b00, sbuf[7:2]} : {sbuf[5:0], 2'b00}; scnt <= scnt - 3'd1; end
        end
    end

    // ---------------------------------------------------------------- read multiplexer
    always @* begin
        io_rdata = 8'h00;
        if (a_tcntl) io_rdata = tcnt[7:0];
        if (a_icrl)  io_rdata = icr[7:0];
        if (a_tcnth | a_icrh) io_rdata = io_core ? rtmp1 : rtmp0;
        if (a_crcin & cok) io_rdata = {fbnd_q ? eq : eqf, eq, busy, 5'd0};      // read of CRCIN: status of the CRC unit
        if (pg3) case (lo)
            4'h0: io_rdata = tcr;    4'h1: io_rdata = tcap;
            4'h2: io_rdata = ocral;  4'h3: io_rdata = ocrah;  4'h4: io_rdata = ocrbl;  4'h5: io_rdata = ocrbh;
            4'h8: io_rdata = pwmc;   4'h9: io_rdata = pwmtop;
            4'hA: io_rdata = pwm0;   4'hB: io_rdata = pwm1;   4'hC: io_rdata = pwm2;
            default: ;
        endcase
        if (pg4 & cok) case (lo)
            4'h0: io_rdata = crcctl | {6'd0, busy, 1'b0};
            4'h1: io_rdata = crclen;
            4'h2: io_rdata = poly0;      4'h3: io_rdata = poly1;      4'h4: io_rdata = poly2;       4'h5: io_rdata = poly3;
            4'h6: io_rdata = val[7:0];   4'h7: io_rdata = val[15:8];  4'h8: io_rdata = val[23:16];  4'h9: io_rdata = val[31:24];
            4'hA: io_rdata = ref0;       4'hB: io_rdata = ref1;       4'hC: io_rdata = ref2;        4'hD: io_rdata = ref3;
            default: ;
        endcase
    end
endmodule
