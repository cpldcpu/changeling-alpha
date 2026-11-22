// Block test of rhost: SPI transactions, environment changes and firmware accesses to the mailbox registers.
// Input file, one line per item, 32 hex fields: type args...
//   type 0 (env):  h_quiet inj_busy inj_fail brk[2] en[2] wait[2] pc0 pc1
//   type 1 (xact): nbits byte0 byte1 ... (up to 28 bytes)
//   type 2 (fw):   addr re we wdata host
// Output: lines "W addr data", "R addr", "I cmd core word", "B mask" for actions; after each xact "MISO bytes", "ST rst halt core mbx";
//         after each fw access "F rdata mbx".
`timescale 1ns/1ps
module tb_host;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg sck = 0, cs_n = 1, mosi = 0;
    wire miso;
    wire h_acc, h_we, h_core, inj_core, rst_core_n, mbx; wire [15:0] h_addr, inj_word; wire [7:0] h_wdata; wire [1:0] inj_cmd, halt_req, brk_clr;
    reg [7:0] mem [0:65535]; reg [7:0] rdq; wire [7:0] h_rdata = rdq;
    reg quiet = 0, busy = 0, fail = 0; reg [1:0] brk = 0, en = 0, wt = 0; reg [10:0] pc0 = 0; reg [9:0] pc1 = 0;
    reg [8:0] io_addr = 0; reg io_host = 0, io_re = 0, io_we = 0; reg [7:0] io_wdata = 0; wire [7:0] io_rdata;
    rhost dut (.clk(clk), .rst_n(rst_n), .sck(sck), .cs_n(cs_n), .mosi(mosi), .miso(miso), .h_acc(h_acc), .h_we(h_we), .h_core(h_core),
        .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata), .h_quiet(quiet), .inj_cmd(inj_cmd), .inj_core(inj_core), .inj_word(inj_word),
        .inj_busy(busy), .inj_fail(fail), .rst_core_n(rst_core_n), .halt_req(halt_req), .brk_clr(brk_clr), .brk_flag(brk), .core_en(en),
        .core_wait(wt), .pc0(pc0), .pc1(pc1), .io_addr(io_addr), .io_host(io_host), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata),
        .io_rdata(io_rdata), .mbx(mbx));
    integer fi, fo, i, nb, ph; reg [1023:0] fin, fout;
    reg [31:0] a [0:31];
    reg [7:0] got; integer bi; reg [7:0] mb [0:31];
    always @(posedge clk) begin
        if (h_acc) begin
            if (h_we) begin mem[h_addr] <= h_wdata; $fdisplay(fo, "W %04x %02x", h_addr, h_wdata); end
            else $fdisplay(fo, "R %04x", h_addr);
            rdq <= mem[h_addr];
        end
        if (inj_cmd != 0) $fdisplay(fo, "I %0d %0d %04x", inj_cmd, inj_core, inj_word);
        if (brk_clr != 0) $fdisplay(fo, "B %0d", brk_clr);
    end
    task cyc; input integer n; integer j; begin for (j = 0; j < n; j = j + 1) @(negedge clk); end endtask
    task sbit; input b; begin   // one SPI clock period of 2*ph system clock cycles, miso sampled at the end of the low phase
        mosi = b; sck = 0; cyc(ph - 1);
        got = {got[6:0], miso}; cyc(1);
        sck = 1; cyc(ph);
    end endtask
    initial begin
        if (!$value$plusargs("in=%s", fin)) fin = "build/host.in";
        if (!$value$plusargs("out=%s", fout)) fout = "build/host.out";
        if (!$value$plusargs("ph=%d", ph)) ph = 4;
        for (i = 0; i < 65536; i = i + 1) mem[i] = i * 13 + 7;
        fi = $fopen(fin, "r"); fo = $fopen(fout, "w");
        repeat (3) @(negedge clk); rst_n = 1; cyc(5);
        while ($fscanf(fi, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",
               a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9], a[10], a[11], a[12], a[13], a[14], a[15], a[16], a[17], a[18], a[19],
               a[20], a[21], a[22], a[23], a[24], a[25], a[26], a[27], a[28], a[29], a[30], a[31]) == 32) begin
            if (a[0] == 0) begin
                quiet = a[1][0]; busy = a[2][0]; brk = a[4][1:0]; en = a[5][1:0]; wt = a[6][1:0]; pc0 = a[7][10:0]; pc1 = a[8][9:0];
                fail = a[3][0]; cyc(1); fail = 0; cyc(4);
            end else if (a[0] == 1) begin
                cs_n = 0; sck = 0; cyc(4);
                for (i = 0; i < a[1]; i = i + 1) begin
                    sbit(a[2 + i / 8][7 - (i % 8)]);
                    if (i % 8 == 7) mb[i / 8] = got;
                end
                nb = a[1] / 8;
                cs_n = 1; sck = 0; cyc(40);
                $fwrite(fo, "MISO"); for (i = 0; i < nb; i = i + 1) $fwrite(fo, " %02x", mb[i]); $fdisplay(fo, "");
                $fdisplay(fo, "ST %b %b %b %b", rst_core_n, halt_req, h_core, mbx);
            end else begin
                io_addr = a[1][8:0]; io_re = a[2][0]; io_we = a[3][0]; io_wdata = a[4][7:0]; io_host = a[5][0]; #3;
                $fdisplay(fo, "F %02x %b", io_rdata, mbx);
                @(negedge clk); io_re = 0; io_we = 0; io_host = 0; cyc(2);
            end
        end
        $fclose(fo); $finish;
    end
endmodule
