// rlcports - pins and line cells on the register bus.
//
// Contains the two pairs of line cells, the bidirectional port, the input and output pins, the pin
// synchronisers, the pin multiplexer with its output registers, and the owner check of the cells.
// Follows the rules A1-A6 and O1-O4 of the architecture specification.
//
// Registers:  fast tier  0x00 PINR  0x01 DDR  0x02 PORT  0x03 PINB  0x04 PORTC
//                        0x08 LR0STAT 0x09 LR0DATA 0x0A LT0STAT 0x0B LT0DATA   0x10..0x13 pair 1
//             page       0x100 receive cell 0, 0x110 transmit cell 0, 0x160 receive cell 1,
//                        0x170 transmit cell 1,  0x151 LCOWN (protected)  0x153 ODE  0x154 PCMSK

module rlcports (
    input            clk,
    input            rst_n,          // reset of the cores and the peripherals
    input            rst_sys_n,      // system reset: the output register of the dedicated outputs works during the core reset
    input            ptick,          // peripheral clock enable

    // register bus
    input      [8:0] io_addr,
    input            io_core,        // core that performs the access
    input            io_host,        // access by the host link: no owner check
    input            io_re,
    input            io_we,
    input      [7:0] io_wdata,
    input      [7:0] io_wmask,
    output reg [7:0] io_rdata,       // zero if no register of this block is addressed
    input            io_unlock,
    output           io_prot,        // the addressed register of this block is protected

    // pins
    input      [7:0] uio_in,
    output reg [7:0] uio_out,
    output reg [7:0] uio_oe,
    input      [7:0] in_pins,        // input-only pins
    output reg [7:0] out_pins,       // output-only pins
    input      [7:0] ovr_en,         // other blocks take over an output pin (host link, clock, debug, PWM)
    input      [7:0] ovr_val,

    // to the event flags, timer, trim counter, CRC unit and debug
    output     [1:0] lc_own,         // owner core of pair 0 and 1
    output     [3:0] lc_evt,         // event flags: receive 0, transmit 0, receive 1, transmit 1
    output           pc_evt,         // pin change on a pin selected in PCMSK
    output     [1:0] ref_evt,        // reference events of the receive cells
    output     [1:0] acc_evt,        // accepted edges of the receive cells
    output     [1:0] smp_evt,        // sample points of the receive cells
    output     [1:0] rx_strobe,      // received bits behind the match pattern (for the CRC unit)
    output     [1:0] rx_frame,       // a received frame is complete (for the CRC unit)
    output     [1:0] rx_bit,
    output     [1:0] tx_strobe,      // transmitted data bits
    output     [1:0] tx_bit,
    output     [7:0] pins_sync       // synchronised levels of the bidirectional pins
);
    // ---------------------------------------------------------------- synchronisers (rule A1)
    reg [7:0] p1, p2, pprev;         // rising-edge samples
    reg [7:0] n1, f2, f3;            // falling-edge samples; f3 is half a period older than p2
    reg [7:0] i1, i2;                // input pins
    always @(negedge clk or negedge rst_n)
        if (!rst_n) n1 <= 8'h00; else n1 <= uio_in;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin p1 <= 0; p2 <= 0; pprev <= 0; f2 <= 0; f3 <= 0; i1 <= 0; i2 <= 0; end
        else begin p1 <= uio_in; p2 <= p1; pprev <= p2; f2 <= n1; f3 <= f2; i1 <= in_pins; i2 <= i1; end
    end
    assign pins_sync = p2;

    // ---------------------------------------------------------------- port registers
    reg [7:0] r_ddr, r_port, r_portc, r_ode, r_pcmsk;
    reg [1:0] r_own;
    wire fast   = (io_addr[8:6] == 3'b000);
    wire a_pinr = (io_addr == 9'h000), a_ddr = (io_addr == 9'h001), a_port = (io_addr == 9'h002);
    wire a_pinb = (io_addr == 9'h003), a_portc = (io_addr == 9'h004);
    wire a_own  = (io_addr == 9'h151), a_ode = (io_addr == 9'h153), a_pcm = (io_addr == 9'h154);
    function [7:0] mw; input [7:0] old; mw = (old & ~io_wmask) | (io_wdata & io_wmask); endfunction
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin r_ddr <= 0; r_port <= 0; r_portc <= 0; r_ode <= 0; r_pcmsk <= 0; r_own <= 2'b10; end
        else if (io_we) begin
            if (a_ddr)   r_ddr   <= mw(r_ddr);
            if (a_port)  r_port  <= mw(r_port);
            if (a_portc) r_portc <= mw(r_portc);
            if (a_ode)   r_ode   <= io_wdata;
            if (a_pcm)   r_pcmsk <= io_wdata;
            if (a_own & (io_unlock | io_host)) r_own <= io_wdata[1:0];
        end
    end
    assign io_prot = a_own;
    assign lc_own  = r_own;
    assign pc_evt  = |((p2 ^ pprev) & r_pcmsk);

    // ---------------------------------------------------------------- line cells and owner check
    // cell index: 0 receive 0, 1 transmit 0, 2 receive 1, 3 transmit 1
    wire [3:0] f_sel = {fast & (io_addr[5:1] == 5'b01001), fast & (io_addr[5:1] == 5'b01000),
                        fast & (io_addr[5:1] == 5'b00101), fast & (io_addr[5:1] == 5'b00100)};
    wire [3:0] c_sel = {io_addr[8:4] == 5'h17, io_addr[8:4] == 5'h16, io_addr[8:4] == 5'h11, io_addr[8:4] == 5'h10};
    wire [1:0] p_ok  = {io_host | (io_core == r_own[1]), io_host | (io_core == r_own[0])};
    wire [3:0] ok    = {p_ok[1], p_ok[1], p_ok[0], p_ok[0]};
    wire [3:0] f_st  = f_sel & ok & {4{~io_addr[0]}};      // status register
    wire [3:0] f_da  = f_sel & ok & {4{io_addr[0]}};       // data register
    wire [3:0] c_ok  = c_sel & ok;

    wire [7:0] rstat0, rstat1, tstat0, tstat1, rdat0, rdat1, rcfg0, rcfg1, tcfg0, tcfg1;
    wire [1:0] mid, o_t, o_n, o_ct, o_cn, o_dr, o_dd, nbs;
    wire [2:0] tsel0, tsel1, nsel0, nsel1;
    wire [7:0] w_stat = io_wdata & io_wmask;

    rlc_rx r0 (.clk(clk), .rst_n(rst_n), .ptick(ptick), .pins_r(p2), .pins_f(f3),
        .cfg_we(io_we & c_ok[0]), .cfg_a(io_addr[3:0]), .cfg_wdata(io_wdata), .cfg_rdata(rcfg0),
        .stat(rstat0), .stat_we(io_we & f_st[0]), .stat_wdata(w_stat), .rdata(rdat0), .data_re(io_re & f_da[0]),
        .nb_mid(mid[0]), .rx_strobe(nbs[0]), .crc_strobe(rx_strobe[0]), .rx_frame(rx_frame[0]), .rx_bit(rx_bit[0]), .evt(lc_evt[0]), .ref_evt(ref_evt[0]),
        .dbg_smp(smp_evt[0]), .dbg_acc(acc_evt[0]));
    rlc_tx t0 (.clk(clk), .rst_n(rst_n), .ptick(ptick), .pins_r(p2),
        .cfg_we(io_we & c_ok[1]), .cfg_a(io_addr[3:0]), .cfg_wdata(io_wdata), .cfg_rdata(tcfg0),
        .stat(tstat0), .data_we(io_we & f_da[1]), .data_wdata(io_wdata),
        .nb_strobe(nbs[0]), .nb_bit(rx_bit[0]), .tx_mid(mid[0]), .tx_strobe(tx_strobe[0]), .tx_bit(tx_bit[0]),
        .o_true(o_t[0]), .o_second(o_n[0]), .o_claim_t(o_ct[0]), .o_claim_n(o_cn[0]), .o_tsel(tsel0), .o_nsel(nsel0),
        .o_drive(o_dr[0]), .o_ddr(o_dd[0]), .evt(lc_evt[1]));
    rlc_rx r1 (.clk(clk), .rst_n(rst_n), .ptick(ptick), .pins_r(p2), .pins_f(f3),
        .cfg_we(io_we & c_ok[2]), .cfg_a(io_addr[3:0]), .cfg_wdata(io_wdata), .cfg_rdata(rcfg1),
        .stat(rstat1), .stat_we(io_we & f_st[2]), .stat_wdata(w_stat), .rdata(rdat1), .data_re(io_re & f_da[2]),
        .nb_mid(mid[1]), .rx_strobe(nbs[1]), .crc_strobe(rx_strobe[1]), .rx_frame(rx_frame[1]), .rx_bit(rx_bit[1]), .evt(lc_evt[2]), .ref_evt(ref_evt[1]),
        .dbg_smp(smp_evt[1]), .dbg_acc(acc_evt[1]));
    rlc_tx t1 (.clk(clk), .rst_n(rst_n), .ptick(ptick), .pins_r(p2),
        .cfg_we(io_we & c_ok[3]), .cfg_a(io_addr[3:0]), .cfg_wdata(io_wdata), .cfg_rdata(tcfg1),
        .stat(tstat1), .data_we(io_we & f_da[3]), .data_wdata(io_wdata),
        .nb_strobe(nbs[1]), .nb_bit(rx_bit[1]), .tx_mid(mid[1]), .tx_strobe(tx_strobe[1]), .tx_bit(tx_bit[1]),
        .o_true(o_t[1]), .o_second(o_n[1]), .o_claim_t(o_ct[1]), .o_claim_n(o_cn[1]), .o_tsel(tsel1), .o_nsel(nsel1),
        .o_drive(o_dr[1]), .o_ddr(o_dd[1]), .evt(lc_evt[3]));

    // ---------------------------------------------------------------- read multiplexer
    always @* begin
        io_rdata = 8'h00;
        if (a_pinr)  io_rdata = p2;
        if (a_ddr)   io_rdata = r_ddr;
        if (a_port)  io_rdata = r_port;
        if (a_pinb)  io_rdata = i2;
        if (a_portc) io_rdata = r_portc;
        if (a_own)   io_rdata = {6'd0, r_own};
        if (a_ode)   io_rdata = r_ode;
        if (a_pcm)   io_rdata = r_pcmsk;
        if (f_st[0]) io_rdata = rstat0;
        if (f_da[0]) io_rdata = rdat0;
        if (f_st[1]) io_rdata = tstat0;
        if (f_st[2]) io_rdata = rstat1;
        if (f_da[2]) io_rdata = rdat1;
        if (f_st[3]) io_rdata = tstat1;
        if (c_ok[0]) io_rdata = rcfg0;
        if (c_ok[1]) io_rdata = tcfg0;
        if (c_ok[2]) io_rdata = rcfg1;
        if (c_ok[3]) io_rdata = tcfg1;
    end

    // ---------------------------------------------------------------- pin multiplexer (rules A2, A3, O1-O4)
    // priority: transmit cell 0 true output, its second output, transmit cell 1 true, second, port
    reg [7:0] pv, pe;
    integer i;
    always @* begin
        for (i = 0; i < 8; i = i + 1) begin
            pv[i] = r_port[i];
            pe[i] = r_ddr[i];
            if (o_cn[1] && nsel1 == i) begin pv[i] = o_n[1]; pe[i] = o_dr[1] | (o_dd[1] & r_ddr[i]); end
            if (o_ct[1] && tsel1 == i) begin pv[i] = o_t[1]; pe[i] = o_dr[1] | (o_dd[1] & r_ddr[i]); end
            if (o_cn[0] && nsel0 == i) begin pv[i] = o_n[0]; pe[i] = o_dr[0] | (o_dd[0] & r_ddr[i]); end
            if (o_ct[0] && tsel0 == i) begin pv[i] = o_t[0]; pe[i] = o_dr[0] | (o_dd[0] & r_ddr[i]); end
            if (r_ode[i] & pv[i]) pe[i] = 1'b0;             // open drain: only driven low
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin uio_out <= 8'h00; uio_oe <= 8'h00; end
        else begin
            uio_out  <= pv;
            uio_oe   <= pe;
        end
    end
    // The dedicated outputs carry the data output of the host link (pin 0). The host may read status and
    // memory while the core reset is set, so this register is reset by the system reset only. During the
    // core reset PORTC and the enables of clock output, debug signal and PWM are zero.
    always @(posedge clk or negedge rst_sys_n) begin
        if (!rst_sys_n) out_pins <= 8'h00;
        else            out_pins <= (r_portc & ~ovr_en) | (ovr_val & ovr_en);
    end
endmodule
