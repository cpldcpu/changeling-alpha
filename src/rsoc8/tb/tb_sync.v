// Pin synchronisers of rlcports: the falling-edge sample given to the line cells must be the one
// taken half a clock period before the rising-edge sample given in the same cycle.
`timescale 1ns/1ps
module tb_sync;
    reg clk = 0, rst_n = 0; always #5 clk = ~clk;
    reg [7:0] uio_in = 0;
    wire [7:0] rd, uo, oe, op, ps; wire [1:0] own, re, ae, se, rs, rb, ts, tb; wire [3:0] le; wire pc, prot;
    rlcports dut (.clk(clk), .rst_n(rst_n), .ptick(1'b1), .io_addr(9'd0), .io_core(1'b0), .io_host(1'b0), .io_re(1'b0),
        .io_we(1'b0), .io_wdata(8'd0), .io_wmask(8'd0), .io_rdata(rd), .io_unlock(1'b0), .io_prot(prot),
        .uio_in(uio_in), .uio_out(uo), .uio_oe(oe), .in_pins(8'd0), .out_pins(op), .ovr_en(8'd0), .ovr_val(8'd0),
        .lc_own(own), .lc_evt(le), .pc_evt(pc), .ref_evt(re), .acc_evt(ae), .smp_evt(se), .rx_strobe(rs), .rx_bit(rb),
        .tx_strobe(ts), .tx_bit(tb), .pins_sync(ps));
    reg [7:0] rq [0:3]; reg [7:0] fq [0:3]; reg [7:0] flast; integer errors = 0, n = 0, seed = 7, k;
    always @(negedge clk) flast <= uio_in;                 // pin at the falling edge
    always @(posedge clk) begin                            // pin at the rising edge, with the falling sample before it
        for (k = 3; k > 0; k = k - 1) begin rq[k] <= rq[k-1]; fq[k] <= fq[k-1]; end
        rq[0] <= uio_in; fq[0] <= flast;
        n <= n + 1;
        if (n > 8 && (dut.p2 !== rq[1] || dut.f3 !== fq[1])) begin
            errors = errors + 1;
            if (errors < 5) $display("FAIL cycle %0d: rising %02x (expected %02x), falling %02x (expected %02x)", n, dut.p2, rq[1], dut.f3, fq[1]);
        end
    end
    initial begin
        repeat (2) @(posedge clk); #1 rst_n = 1;
        repeat (4000) begin #(1 + ($random(seed) & 15)); uio_in = $random(seed); end
        if (errors == 0) $display("PASS: synchroniser order"); else $display("%0d errors", errors);
        $finish;
    end
endmodule
