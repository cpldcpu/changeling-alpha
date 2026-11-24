// rpe_osc - Ring Oscillator A (60 MHz standard-cell tap-selected delay line)
// Matches analog/osc_ring_std/osc_ring_std.sch cell-for-cell.
// Higher trim[7:0] selects a shorter delay chain (higher frequency).
// Reset value 8'h80 selects the midpoint of the chain (<= 60 MHz at fast corner).

module ca_tap_chain_16 (
    input  wire        in,
    input  wire [3:0]  s,
    output wire        out_chain,
    output wire        out_mux
);
    wire [16:0] t;
    assign t[0] = in;

    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : g_dly
            (* keep *) sg13cmos5l_dlygate4sd1_1 u_dly (.A(t[i]), .X(t[i+1]));
        end
    endgenerate
    assign out_chain = t[16];

    // Reversed tap order so s=15 picks t[0] (fastest) and s=0 picks t[15] (slowest)
    wire [7:0] m0;
    wire [3:0] m1;
    wire [1:0] m2;
    generate
        for (i = 0; i < 8; i = i + 1) begin : g_m0
            (* keep *) sg13cmos5l_mux2_1 u_m0 (.A0(t[15 - 2*i]), .A1(t[15 - (2*i + 1)]), .S(s[0]), .X(m0[i]));
        end
        for (i = 0; i < 4; i = i + 1) begin : g_m1
            (* keep *) sg13cmos5l_mux2_1 u_m1 (.A0(m0[2*i]), .A1(m0[2*i+1]), .S(s[1]), .X(m1[i]));
        end
        for (i = 0; i < 2; i = i + 1) begin : g_m2
            (* keep *) sg13cmos5l_mux2_1 u_m2 (.A0(m1[2*i]), .A1(m1[2*i+1]), .S(s[2]), .X(m2[i]));
        end
    endgenerate
    (* keep *) sg13cmos5l_mux2_1 u_m3 (.A0(m2[0]), .A1(m2[1]), .S(s[3]), .X(out_mux));
endmodule

module rpe_osc (
    input  wire       en,
    input  wire [7:0] trim,
    output wire       clk
);
    wire loop_fb, n_nand, clk_pre;
    (* keep *) sg13cmos5l_nand2_2 u_nand (.A(loop_fb), .B(en), .Y(n_nand));
    (* keep *) sg13cmos5l_inv_2   u_oinv (.A(n_nand), .Y(clk_pre));
    (* keep *) sg13cmos5l_buf_4   u_obuf (.A(clk_pre), .X(clk));

    wire [8:0] fix;
    assign fix[0] = n_nand;
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : g_fix
            (* keep *) sg13cmos5l_dlygate4sd3_1 u_fix (.A(fix[i]), .X(fix[i+1]));
        end
    endgenerate

    wire fine_slow, fine_fast, chain_0;
    (* keep *) sg13cmos5l_dlygate4sd1_1 u_fslow (.A(fix[8]), .X(fine_slow));
    (* keep *) sg13cmos5l_buf_1         u_ffast (.A(fix[8]), .X(fine_fast));
    (* keep *) sg13cmos5l_mux2_1        u_fmux  (.A0(fine_slow), .A1(fine_fast), .S(trim[0]), .X(chain_0));

    wire [8:0] chain;
    wire [7:0] smux;
    assign chain[0] = chain_0;
    generate
        for (i = 0; i < 8; i = i + 1) begin : g_sl
            // idx=0 (slice 7) is earliest -> trim[7:5]=7; idx=7 (slice 0) is latest -> trim[7:5]=0
            ca_tap_chain_16 u_slice (
                .in(chain[i]),
                .s(trim[4:1]),
                .out_chain(chain[i+1]),
                .out_mux(smux[7 - i])
            );
        end
    endgenerate

    wire [3:0] fm0;
    wire [1:0] fm1;
    generate
        for (i = 0; i < 4; i = i + 1) begin : g_fm0
            (* keep *) sg13cmos5l_mux2_1 u_fm0 (.A0(smux[2*i]), .A1(smux[2*i+1]), .S(trim[5]), .X(fm0[i]));
        end
        for (i = 0; i < 2; i = i + 1) begin : g_fm1
            (* keep *) sg13cmos5l_mux2_1 u_fm1 (.A0(fm0[2*i]), .A1(fm0[2*i+1]), .S(trim[6]), .X(fm1[i]));
        end
    endgenerate
    (* keep *) sg13cmos5l_mux2_1 u_fm2 (.A0(fm1[0]), .A1(fm1[1]), .S(trim[7]), .X(loop_fb));
endmodule
