// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Blackbox stub for unified custom analog clock macro (rpe_clk_analog)
(* blackbox *)
module rpe_clk_analog (
    inout  wire VDD,
    inout  wire VSS,
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
