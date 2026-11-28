// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Block test of rdual with scripted bus users instead of cores (stub_core.v).
// stimulus per cycle (hex): cke evt0[4] evt1[4] irq0[4] irq1[4] halt[2 bits] brk_clr[2 bits]
// output per cycle: cen[2] hold wt[2] en[2] brk[2] rb[8]   (hex fields)
`timescale 1ns/1ps
module tb_dual;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg cke; reg [31:0] evt; reg [15:0] irq0, irq1; reg [1:0] halt, bclr;
    wire [8:0] io_addr; wire io_core, io_re, io_we, io_unlock; wire [7:0] io_wdata, io_wmask;
    wire [1:0] bf, ce, cw, cc; wire bh, idle; wire [10:0] pc0; wire [9:0] pc1;
    wire [7:0] io_rdata = io_addr[7:0] ^ 8'h5A;
    rdual dut (.clk(clk), .rst_n(rst_n), .cke(cke), .cm0_rdata(16'h0), .cm1_rdata(16'h0), .dm_rdata(8'h0),
        .io_rdata(io_rdata), .io_addr(io_addr), .io_core(io_core), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata),
        .io_wmask(io_wmask), .io_unlock(io_unlock), .io_prot(1'b0), .evt(evt), .irq0(irq0), .irq1(irq1),
        .halt_req(halt), .brk_clr(bclr), .brk_flag(bf), .core_en(ce), .core_wait(cw), .core_cen(cc), .bus_hold(bh),
        .dbg_pc0(pc0), .dbg_pc1(pc1), .idle(idle),
        .rst_sys_n(1'b1), .h_acc(1'b0), .h_we(1'b0), .h_core(1'b0), .h_addr(16'h0), .h_wdata(8'h0),
        .inj_cmd(2'b00), .inj_core(1'b0), .inj_word(16'h0));
    integer fi, fo; reg [1023:0] fin, fout;
    reg [31:0] s_cke, s_e0, s_e1, s_i0, s_i1, s_h, s_b;
    initial begin
        if (!$value$plusargs("in=%s", fin)) fin = "build/dual.in";
        if (!$value$plusargs("out=%s", fout)) fout = "build/dual.out";
        fi = $fopen(fin, "r"); fo = $fopen(fout, "w");
        cke = 1; evt = 0; irq0 = 0; irq1 = 0; halt = 0; bclr = 0;
        repeat (2) @(negedge clk); rst_n = 1;
        while ($fscanf(fi, "%h %h %h %h %h %h %h\n", s_cke, s_e0, s_e1, s_i0, s_i1, s_h, s_b) == 7) begin
            cke = s_cke[0]; evt = {s_e1[15:0], s_e0[15:0]}; irq0 = s_i0[15:0]; irq1 = s_i1[15:0]; halt = s_h[1:0]; bclr = s_b[1:0];
            #4 $fdisplay(fo, "%b %b %b %b %b %02x", cc, bh, cw, ce, bf, pc0[7:0]);
            @(negedge clk);
        end
        $fclose(fo); $finish;
    end
endmodule
