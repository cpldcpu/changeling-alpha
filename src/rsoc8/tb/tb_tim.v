// Testbench of rtimers: applies one stimulus line per clock cycle and writes the outputs of each cycle.
// stimulus line (hex): ptick addr[3] core host re we wd[2] pins[2] acc ref rxs rxb txs txb rxf
`timescale 1ns/1ps
module tb_tim;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg ptick, io_core, io_host, io_re, io_we; reg [8:0] io_addr; reg [7:0] io_wdata, pins;
    reg [1:0] acc, rf, rxs, rxb, txs, txb, rxf;
    wire [7:0] rd; wire capt, oca, ocb, ovf; wire [2:0] pen, pout;
    rtimers dut (.clk(clk), .rst_n(rst_n), .ptick(ptick), .io_addr(io_addr), .io_core(io_core), .io_host(io_host),
        .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata), .io_rdata(rd), .pins_sync(pins), .acc_evt(acc),
        .ref_evt(rf), .rx_strobe(rxs), .rx_frame(rxf), .rx_bit(rxb), .tx_strobe(txs), .tx_bit(txb),
        .capt_evt(capt), .oca_evt(oca), .ocb_evt(ocb), .ovf_evt(ovf), .pwm_en(pen), .pwm_out(pout));
    integer fi, fo, n; reg [1023:0] fin, fout;
    reg [3:0] s_pt, s_core, s_host, s_re, s_we, s_acc, s_ref, s_rxs, s_rxb, s_txs, s_txb, s_rxf; reg [11:0] s_addr; reg [7:0] s_wd, s_pins;
    initial begin
        if (!$value$plusargs("in=%s", fin)) fin = "build/tim.in";
        if (!$value$plusargs("out=%s", fout)) fout = "build/tim.out";
        fi = $fopen(fin, "r"); fo = $fopen(fout, "w");
        ptick = 0; io_addr = 0; io_core = 0; io_host = 0; io_re = 0; io_we = 0; io_wdata = 0; pins = 8'hFF;
        acc = 0; rf = 0; rxs = 0; rxb = 0; txs = 0; txb = 0; rxf = 0;
        @(negedge clk); rst_n = 1;
        while ($fscanf(fi, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n", s_pt, s_addr, s_core, s_host, s_re, s_we, s_wd, s_pins,
                       s_acc, s_ref, s_rxs, s_rxb, s_txs, s_txb, s_rxf) == 15) begin
            ptick = s_pt[0]; io_addr = s_addr[8:0]; io_core = s_core[0]; io_host = s_host[0]; io_re = s_re[0]; io_we = s_we[0];
            io_wdata = s_wd; pins = s_pins; acc = s_acc[1:0]; rf = s_ref[1:0]; rxs = s_rxs[1:0]; rxb = s_rxb[1:0];
            txs = s_txs[1:0]; txb = s_txb[1:0]; rxf = s_rxf[1:0];
            #4 $fdisplay(fo, "%02x %b %b %b %b %b %b", rd, capt, oca, ocb, ovf, pen, pout);
            @(negedge clk);
        end
        $fclose(fo); $finish;
    end
endmodule
