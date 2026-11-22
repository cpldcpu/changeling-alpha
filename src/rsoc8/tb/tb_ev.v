// Testbench of revents: one stimulus line per clock cycle, outputs of each cycle written to a file.
// stimulus (hex): ptick addr[3] core re we wd wm pc capt oca ocb ovf trim mbx lc own ack0[4] ack1[4]
// output (hex):   rdata evt[8] irq0[4] irq1[4]
`timescale 1ns/1ps
module tb_ev;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg ptick, io_core, io_re, io_we, pc, capt, oca, ocb, ovf, trim, mbx; reg [8:0] io_addr; reg [7:0] io_wdata, io_wmask;
    reg [3:0] lc; reg [1:0] own; reg [16:1] ack0, ack1;
    wire [7:0] rd; wire [31:0] evt; wire [16:1] irq0, irq1;
    revents dut (.clk(clk), .rst_n(rst_n), .ptick(ptick), .io_addr(io_addr), .io_core(io_core), .io_re(io_re), .io_we(io_we),
        .io_wdata(io_wdata), .io_wmask(io_wmask), .io_rdata(rd), .pc_evt(pc), .capt_evt(capt), .oca_evt(oca), .ocb_evt(ocb),
        .ovf_evt(ovf), .trim_evt(trim), .mbx(mbx), .lc_evt(lc), .lc_own(own), .evt(evt), .irq0(irq0), .irq1(irq1),
        .irq_ack0(ack0), .irq_ack1(ack1));
    integer fi, fo; reg [1023:0] fin, fout;
    reg [15:0] s_pt, s_addr, s_core, s_re, s_we, s_wd, s_wm, s_pc, s_capt, s_oca, s_ocb, s_ovf, s_trim, s_mbx, s_lc, s_own, s_a0, s_a1;
    initial begin
        if (!$value$plusargs("in=%s", fin)) fin = "build/ev.in";
        if (!$value$plusargs("out=%s", fout)) fout = "build/ev.out";
        fi = $fopen(fin, "r"); fo = $fopen(fout, "w");
        ptick = 0; io_addr = 0; io_core = 0; io_re = 0; io_we = 0; io_wdata = 0; io_wmask = 8'hFF; pc = 0; capt = 0; oca = 0; ocb = 0;
        ovf = 0; trim = 0; mbx = 0; lc = 0; own = 2'b10; ack0 = 0; ack1 = 0;
        @(negedge clk); rst_n = 1;
        while ($fscanf(fi, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n", s_pt, s_addr, s_core, s_re, s_we, s_wd, s_wm,
                       s_pc, s_capt, s_oca, s_ocb, s_ovf, s_trim, s_mbx, s_lc, s_own, s_a0, s_a1) == 18) begin
            ptick = s_pt[0]; io_addr = s_addr[8:0]; io_core = s_core[0]; io_re = s_re[0]; io_we = s_we[0]; io_wdata = s_wd[7:0];
            io_wmask = s_wm[7:0]; pc = s_pc[0]; capt = s_capt[0]; oca = s_oca[0]; ocb = s_ocb[0]; ovf = s_ovf[0]; trim = s_trim[0];
            mbx = s_mbx[0]; lc = s_lc[3:0]; own = s_own[1:0]; ack0 = s_a0; ack1 = s_a1;
            #4 $fdisplay(fo, "%02x %08x %04x %04x", rd, evt, irq0, irq1);
            @(negedge clk);
        end
        $fclose(fo); $finish;
    end
endmodule
