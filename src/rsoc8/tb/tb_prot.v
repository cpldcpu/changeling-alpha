// Block test of rprot. stimulus (hex): addr[3] we wd host unlock cm0_addr[3] cm1_addr[3] cm0_we cm1_we wo0 wo1 cm_host
// output: rd prot cm0_we_ok cm1_we_ok
`timescale 1ns/1ps
module tb_prot;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg we, host, unl, w0, w1, o0, o1, ch; reg [8:0] addr; reg [7:0] wd; reg [9:0] a0, a1;
    wire [7:0] rd; wire prot, ok0, ok1;
    rprot dut (.clk(clk), .rst_n(rst_n), .io_addr(addr), .io_host(host), .io_we(we), .io_wdata(wd), .io_rdata(rd), .io_unlock(unl),
        .io_prot(prot), .cm0_addr(a0), .cm1_addr(a1), .cm0_we(w0), .cm1_we(w1), .cm0_wother(o0), .cm1_wother(o1), .cm_host(ch),
        .cm0_we_ok(ok0), .cm1_we_ok(ok1));
    integer fi, fo; reg [1023:0] fin, fout;
    reg [15:0] s [0:12];
    initial begin
        if (!$value$plusargs("in=%s", fin)) fin = "build/prot.in";
        if (!$value$plusargs("out=%s", fout)) fout = "build/prot.out";
        fi = $fopen(fin, "r"); fo = $fopen(fout, "w");
        addr = 0; we = 0; wd = 0; host = 0; unl = 0; a0 = 0; a1 = 0; w0 = 0; w1 = 0; o0 = 0; o1 = 0; ch = 0;
        @(negedge clk); rst_n = 1;
        while ($fscanf(fi, "%h %h %h %h %h %h %h %h %h %h %h %h\n", s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11]) == 12) begin
            addr = s[0][8:0]; we = s[1][0]; wd = s[2][7:0]; host = s[3][0]; unl = s[4][0]; a0 = s[5][9:0]; a1 = s[6][9:0];
            w0 = s[7][0]; w1 = s[8][0]; o0 = s[9][0]; o1 = s[10][0]; ch = s[11][0];
            #4 $fdisplay(fo, "%02x %b %b %b", rd, prot, ok0, ok1);
            @(negedge clk);
        end
        $fclose(fo); $finish;
    end
endmodule
