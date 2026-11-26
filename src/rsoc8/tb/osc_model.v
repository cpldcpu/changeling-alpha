// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Behavioural model of the oscillator macro for simulation (compile in place of rtl/rpe_osc_stub.v).
// 15 MHz at trim 128 times ERR, 0.5 % per trim step. The output is low while en is low.
`timescale 1ns/1ps
module rpe_osc (
    input  wire       en,
    input  wire       en_relax,
    input  wire [7:0] trim,
    output reg        clk,
    output wire       clk_slow
);
    assign clk_slow = 1'b0;
    parameter real ERR = 0.85;
    real err0; initial if (!$value$plusargs("oscerr=%f", err0)) err0 = ERR;
    real half; real drift = 1.0;         // drift: factor on the frequency, changed by the testbench
    initial clk = 0;
    always begin
        half = 33.3333 / (err0 * drift * (1.0 + 0.005 * ($itor(trim) - 128.0)));
        #(half); if (en === 1'b1) clk = ~clk; else clk = 0;
    end
endmodule
