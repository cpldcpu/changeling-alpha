// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// revents - event flags, interrupt enable masks, time base and wake-up times.
//
// Follows the rules D1-D4 and E1-E5 of the architecture specification, and Q4 for the flags that
// are cleared when their interrupt is taken.
//
// Registers:  0x06 IFRL  DLY TRIM MBX OVF OCB OCA CAPT PC       0x22 IERL  0x23 IERH (per core)
//             0x07 IFRH  SW3 SW2 SW1 SW0 LT1 LR1 LT0 LR0        0x24 DLYL  0x25 DLYH (per core)
// A core sees the flag of a line cell only if it owns the pair, and its own DLY.

module revents (
    input            clk,
    input            rst_n,
    input            ptick,

    input      [8:0] io_addr,
    input            io_core,
    input            io_re,
    input            io_we,
    input      [7:0] io_wdata,
    input      [7:0] io_wmask,
    output reg [7:0] io_rdata,

    input            pc_evt, capt_evt, oca_evt, ocb_evt, ovf_evt, trim_evt,   // pulses
    input            mbx,                // level
    input      [3:0] lc_evt,             // levels: receive 0, transmit 0, receive 1, transmit 1
    input      [1:0] lc_own,

    output    [31:0] evt,                // flags as core 0 (low half) and core 1 see them
    output    [16:1] irq0,
    output    [16:1] irq1,
    input     [16:1] irq_ack0,
    input     [16:1] irq_ack1
);
    reg [4:0]  lat;                      // PC, CAPT, OCA, OCB, OVF
    reg        trim;
    reg [3:0]  sw;
    reg [1:0]  dly;
    reg [15:0] ier0, ier1, wake0, wake1, tbase;
    reg [7:0]  wtmp0, wtmp1, rtmp0, rtmp1;      // high bytes of 16-bit accesses, per core

    wire [3:0] lc0 = lc_evt & {~lc_own[1], ~lc_own[1], ~lc_own[0], ~lc_own[0]};
    wire [3:0] lc1 = lc_evt & { lc_own[1],  lc_own[1],  lc_own[0],  lc_own[0]};
    wire [15:0] ifr0 = {sw, lc0, dly[0], trim, mbx, lat};
    wire [15:0] ifr1 = {sw, lc1, dly[1], trim, mbx, lat};
    assign evt  = {ifr1, ifr0};
    assign irq0 = ifr0 & ier0;
    assign irq1 = ifr1 & ier1;

    wire a_ifrl = (io_addr == 9'h006), a_ifrh = (io_addr == 9'h007);
    wire a_ierl = (io_addr == 9'h022), a_ierh = (io_addr == 9'h023);
    wire a_dlyl = (io_addr == 9'h024), a_dlyh = (io_addr == 9'h025);
    wire [15:0] ifr_c = io_core ? ifr1 : ifr0;
    wire [15:0] ier_c = io_core ? ier1 : ier0;
    always @* begin
        io_rdata = 8'h00;
        if (a_ifrl) io_rdata = ifr_c[7:0];
        if (a_ifrh) io_rdata = ifr_c[15:8];
        if (a_ierl) io_rdata = ier_c[7:0];
        if (a_ierh) io_rdata = ier_c[15:8];
        if (a_dlyl) io_rdata = tbase[7:0];
        if (a_dlyh) io_rdata = io_core ? rtmp1 : rtmp0;
    end

    wire [7:0]  w1c   = io_wdata & io_wmask;
    wire [15:0] wk_n  = {io_core ? wtmp1 : wtmp0, io_wdata};       // new wake-up time
    wire [15:0] wk_d  = wk_n - tbase;
    wire        wk_past = (wk_d == 16'd0) | wk_d[15] | (ptick & (wk_d == 16'd1));   // reached in this cycle counts as past
    wire        wk_wr = io_we & a_dlyl;
    wire [15:0] tb_n  = tbase + 16'd1;
    wire [4:0]  set5  = {ovf_evt, ocb_evt, oca_evt, capt_evt, pc_evt};
    wire [4:0]  ack5  = irq_ack0[5:1] | irq_ack1[5:1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lat <= 0; trim <= 0; sw <= 0; dly <= 0; ier0 <= 0; ier1 <= 0; wake0 <= 0; wake1 <= 0; tbase <= 0;
            wtmp0 <= 0; wtmp1 <= 0; rtmp0 <= 0; rtmp1 <= 0;
        end else begin
            // ---- latched flags: an event in the same cycle wins over clearing
            lat  <= (lat & ~ack5 & ~((io_we & a_ifrl) ? w1c[4:0] : 5'd0)) | set5;
            trim <= (trim & ~(io_we & a_ifrl & w1c[6])) | trim_evt;
            // ---- software flags: masked write
            if (io_we & a_ifrh) sw <= (sw & ~io_wmask[7:4]) | (io_wdata[7:4] & io_wmask[7:4]);
            // ---- interrupt enable masks
            if (io_we & a_ierl) begin
                if (io_core) ier1[7:0] <= (ier1[7:0] & ~io_wmask) | (io_wdata & io_wmask);
                else         ier0[7:0] <= (ier0[7:0] & ~io_wmask) | (io_wdata & io_wmask);
            end
            if (io_we & a_ierh) begin
                if (io_core) ier1[15:8] <= (ier1[15:8] & ~io_wmask) | (io_wdata & io_wmask);
                else         ier0[15:8] <= (ier0[15:8] & ~io_wmask) | (io_wdata & io_wmask);
            end
            // ---- time base and wake-up times
            if (ptick) tbase <= tb_n;
            if (ptick & (tb_n == wake0)) dly[0] <= 1'b1;
            if (ptick & (tb_n == wake1)) dly[1] <= 1'b1;
            if (io_re & a_dlyl) begin if (io_core) rtmp1 <= tbase[15:8]; else rtmp0 <= tbase[15:8]; end
            if (io_we & a_dlyh) begin if (io_core) wtmp1 <= io_wdata; else wtmp0 <= io_wdata; end
            if (wk_wr) begin
                if (io_core) begin wake1 <= wk_n; dly[1] <= wk_past; end
                else         begin wake0 <= wk_n; dly[0] <= wk_past; end
            end
        end
    end
endmodule
