/*
 * Copyright (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// Blackbox declaration of the custom analog dual-oscillator macro (rpe_clk_analog)
// and structural wrapper rpe_osc instantiated by rpe_top.
// Hard macro GDS/LEF/LIB come from analog/clk_macro/layout via src/config.json.
`ifndef SIM
/* verilator lint_off UNDRIVEN */
/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module rpe_clk_analog (
    input  wire en_ring,
    input  wire en_relax,
    input  wire trim0,
    input  wire trim1,
    input  wire trim2,
    input  wire trim3,
    input  wire trim4,
    input  wire trim5,
    input  wire trim6,
    input  wire trim7,
    output wire clk,
    output wire clk_slow
);
endmodule
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on UNDRIVEN */
`endif

module rpe_osc (
    input  wire       en,
    input  wire       en_relax,
    input  wire [7:0] trim,
    output wire       clk,
    output wire       clk_slow
);
    rpe_clk_analog u_analog (
        .en_ring  (en),
        .en_relax (en_relax),
        .trim0    (trim[0]),
        .trim1    (trim[1]),
        .trim2    (trim[2]),
        .trim3    (trim[3]),
        .trim4    (trim[4]),
        .trim5    (trim[5]),
        .trim6    (trim[6]),
        .trim7    (trim[7]),
        .clk      (clk),
        .clk_slow (clk_slow)
    );
endmodule

`default_nettype wire
