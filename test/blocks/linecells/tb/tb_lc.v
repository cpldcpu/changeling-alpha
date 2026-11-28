// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// (LCX at offset 15: lines 15 and 31; +txq holds 9-bit words, bit 8 is the ninth data bit of the frame)
// Testbench for one pair of line cells (receive cell and transmit cell), driven from files written by tests/lc_test.py.
//   +cfg=file    configuration: lines 0..14 receive cell, 16..30 transmit cell (LCCTRL first)
//   +stim=file   one byte per clock cycle: pin levels sampled on the rising edge
//   +stimf=file  optional: pin levels sampled on the preceding falling edge (UNIT = 1)
//   +txq=file    bytes to transmit; +ntx=n their number
//   +log=file    output
`timescale 1ns/1ps
module tb_lc;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;
    reg [7:0] pins_r = 0, pins_f = 0;
    reg cfg_we = 0, sel_t = 0; reg [3:0] cfg_a = 0; reg [7:0] cfg_wdata = 0;
    reg stat_we = 0; reg [7:0] stat_wdata = 0; reg data_re = 0, data_we = 0; reg [7:0] data_wdata = 0;
    wire [7:0] cfg_rdata, stat, rdata;
    wire rx_strobe, rx_bit, tx_strobe, tx_bit, o_true, o_second, o_claim_t, o_claim_n, o_drive, o_ddr, evt, ref_evt, dbg_smp, dbg_acc;
    wire [2:0] o_tsel, o_nsel;
    wire tx_mid;
    rlc_rx rx (.clk(clk), .rst_n(rst_n), .ptick(1'b1), .pins_r(pins_r), .pins_f(pins_f),
        .cfg_we(cfg_we & ~sel_t), .cfg_a(cfg_a), .cfg_wdata(cfg_wdata), .cfg_rdata(cfg_rdata),
        .stat(stat), .stat_we(stat_we), .stat_wdata(stat_wdata), .rdata(rdata), .data_re(data_re),
        .nb_mid(tx_mid), .rx_strobe(rx_strobe), .rx_bit(rx_bit), .evt(evt), .ref_evt(ref_evt),
        .dbg_smp(dbg_smp), .dbg_acc(dbg_acc));
    wire [7:0] tstat, tcfg_rdata; wire tevt;
    rlc_tx tx (.clk(clk), .rst_n(rst_n), .ptick(1'b1), .pins_r(pins_r),
        .cfg_we(cfg_we & sel_t), .cfg_a(cfg_a), .cfg_wdata(cfg_wdata), .cfg_rdata(tcfg_rdata),
        .stat(tstat), .data_we(data_we), .data_wdata(data_wdata),
        .nb_strobe(rx_strobe), .nb_bit(rx_bit), .tx_mid(tx_mid), .tx_strobe(tx_strobe), .tx_bit(tx_bit),
        .o_true(o_true), .o_second(o_second), .o_claim_t(o_claim_t), .o_claim_n(o_claim_n), .o_tsel(o_tsel),
        .o_nsel(o_nsel), .o_drive(o_drive), .o_ddr(o_ddr), .evt(tevt));

    reg [7:0] cfg [0:31];          // 0..14 receive cell, 16..30 transmit cell
    reg [7:0] stim [0:65535];
    reg [7:0] stimf [0:65535];
    reg [8:0] txq [0:255];
    reg [1023:0] f_cfg, f_stim, f_stimf, f_txq, f_log;
    integer i, n, ntx, txi, fd, k, hasf;

    task wr(input t, input [3:0] a, input [7:0] v); begin
        @(negedge clk); sel_t = t; cfg_we = 1; cfg_a = a; cfg_wdata = v; @(negedge clk); cfg_we = 0;
    end endtask

    initial begin
        ntx = 0; n = 0; hasf = 0;
        if (!$value$plusargs("cfg=%s", f_cfg) || !$value$plusargs("stim=%s", f_stim) || !$value$plusargs("log=%s", f_log)) begin
            $display("missing arguments"); $finish;
        end
        if (!$value$plusargs("n=%d", n)) begin $display("missing +n"); $finish; end
        $readmemh(f_cfg, cfg); $readmemh(f_stim, stim);
        if ($value$plusargs("stimf=%s", f_stimf)) begin $readmemh(f_stimf, stimf); hasf = 1; end
        if ($value$plusargs("txq=%s", f_txq)) begin $readmemh(f_txq, txq); if ($value$plusargs("ntx=%d", ntx)) ; end
        fd = $fopen(f_log, "w");
        pins_r = stim[0]; pins_f = hasf ? stimf[0] : stim[0];
        repeat (3) @(posedge clk); #1 rst_n = 1;
        repeat (4) @(posedge clk);                       // the cell follows the pins while disabled
        for (i = 1; i < 15; i = i + 1) begin wr(0, i[3:0], cfg[i]); wr(1, i[3:0], cfg[16 + i]); end
        wr(0, 4'd15, cfg[15]); wr(1, 4'd15, {txq[0][8], cfg[31][6:0]});   // ninth data bit of the first frame
        wr(0, 4'd0, cfg[0] & 8'h7F);
        wr(1, 4'd0, cfg[16]);                            // the transmit cell is enabled one cycle earlier
        @(negedge clk); sel_t = 0; cfg_we = 1; cfg_a = 0; cfg_wdata = cfg[0];   // EN of the receive cell at the next rising edge
        txi = 0;
        for (k = 0; k < n; k = k + 1) begin
            @(negedge clk);
            cfg_we = 0; sel_t = 0; cfg_a = 4'd15;      // LCX of the receive cell is read with every frame
            pins_r = stim[k]; pins_f = hasf ? stimf[k] : stim[k];
            data_we = 0; data_re = 0;
            #1;
            if (txi < ntx && tstat[6]) begin
                data_we = 1; data_wdata = txq[txi][7:0]; txi = txi + 1;
                sel_t = 1; cfg_we = 1; cfg_wdata = {txq[txi][8], cfg[31][6:0]};   // ninth data bit of the next frame
            end
            if (stat[7]) begin data_re = 1; $fwrite(fd, "R %0d %03x\n", k, {cfg[15][1:0] != 0 ? rx.h0x : 1'b0, rdata}); end
            #1;
            if (dbg_smp) $fwrite(fd, "S %0d\n", k);
            if (dbg_acc) $fwrite(fd, "E %0d\n", k);
            if (ref_evt) $fwrite(fd, "F %0d\n", k);
            if (tx_strobe) $fwrite(fd, "T %0d %0d\n", k, tx_bit);
            if (rx_strobe) $fwrite(fd, "X %0d\n", k);
            $fwrite(fd, "W %0d %0d %0d %0d\n", k, o_true, o_second, tstat[5]);
        end
        @(negedge clk); data_we = 0; data_re = 0;
        $fwrite(fd, "STAT %02x\n", stat);
        $fclose(fd); $finish;
    end
endmodule
