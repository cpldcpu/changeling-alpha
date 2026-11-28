// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Block test of rclk_ctl: one stimulus line per clock cycle, outputs of each cycle to a file.
// stimulus (hex): strap addr[3] re we wd unlock host tglE tglO openO refh refp refevt[2b] smp[2b] acc[2b] txs[2b] ccen[2b] hold
// output (hex): rd prot sel osc_en trim[2] cke ptick trim_evt cko_en cko dbg_en dbg
`timescale 1ns/1ps
module tb_clkctl;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg strap, re, we, unl, host, te, to, oo, rh, rp, hold; reg [8:0] addr; reg [7:0] wd; reg [1:0] rev, smp, acc, txs, ccen;
    wire [7:0] rd, trim; wire prot, sel, osc_en, cke, ptick, trim_evt, cko_en, cko, dbg_en, dbg;
    rclk_ctl dut (.clk(clk), .rst_n(rst_n), .strap(strap), .io_addr(addr), .io_host(host), .io_re(re), .io_we(we), .io_wdata(wd),
        .io_rdata(rd), .io_unlock(unl), .io_prot(prot), .tgl_ext(te), .tgl_osc(to), .open_osc(oo), .sel(sel), .osc_en(osc_en),
        .relax_en(), .trim_sys(trim), .cke(cke), .ptick(ptick), .clk_slow(1'b0), .ref_host(rh), .ref_pin(rp), .ref_evt(rev), .trim_evt(trim_evt),
        .smp_evt(smp), .acc_evt(acc), .tx_strobe(txs), .core_cen(ccen), .bus_hold(hold), .cko_en(cko_en), .cko(cko),
        .dbg_en(dbg_en), .dbg(dbg));
    integer fi, fo; reg [1023:0] fin, fout;
    reg [15:0] a [0:19];
    initial begin
        if (!$value$plusargs("in=%s", fin)) fin = "build/clkctl.in";
        if (!$value$plusargs("out=%s", fout)) fout = "build/clkctl.out";
        fi = $fopen(fin, "r"); fo = $fopen(fout, "w");
        strap = 0; addr = 0; re = 0; we = 0; wd = 0; unl = 0; host = 0; te = 0; to = 0; oo = 0; rh = 0; rp = 0; rev = 0; smp = 0; acc = 0;
        txs = 0; ccen = 0; hold = 0;
        repeat (2) @(negedge clk); rst_n = 1;
        while ($fscanf(fi, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n", a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8],
                       a[9], a[10], a[11], a[12], a[13], a[14], a[15], a[16], a[17]) == 18) begin
            strap = a[0][0]; addr = a[1][8:0]; re = a[2][0]; we = a[3][0]; wd = a[4][7:0]; unl = a[5][0]; host = a[6][0];
            te = a[7][0]; to = a[8][0]; oo = a[9][0]; rh = a[10][0]; rp = a[11][0]; rev = a[12][1:0]; smp = a[13][1:0];
            acc = a[14][1:0]; txs = a[15][1:0]; ccen = a[16][1:0]; hold = a[17][0];
            #4 $fdisplay(fo, "%02x %b %b %b %02x %b %b %b %b %b %b %b", rd, prot, sel, osc_en, trim, cke, ptick, trim_evt, cko_en, cko, dbg_en, dbg);
            @(negedge clk);
        end
        $fclose(fo); $finish;
    end
endmodule
