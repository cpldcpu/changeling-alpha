// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Behavioral simulation model of the hardened analog dual-oscillator macro (rpe_clk_analog).
// Matches post-layout Magic PEX characteristics (tt, 1.20 V, 25 C):
//   - clk:      52.78 MHz at trim=128, 59.92 MHz at trim=155 (~0.2645 MHz/LSB linear around mid-trim)
//   - clk_slow: 98.54 kHz (half-period 5074.2 ns) when en_relax == 1
// Both outputs are held low when their enable input is not 1.
`timescale 1ns/1ps
module rpe_clk_analog (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
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
    output reg  clk,
    output reg  clk_slow
);
    parameter real ERR = 1.0;
    real err0;
    initial if (!$value$plusargs("oscerr=%f", err0)) err0 = ERR;

    wire [7:0] trim = {trim7, trim6, trim5, trim4, trim3, trim2, trim1, trim0};
    real freq_mhz;
    real half_ns;

    initial begin
        clk = 1'b0;
        clk_slow = 1'b0;
    end

    // Ring oscillator (idle low when en_ring != 1)
    always begin
        if (en_ring === 1'b1) begin
            freq_mhz = (52.7764 + 0.264522 * ($itor(trim) - 128.0)) * err0;
            if (freq_mhz < 5.0) freq_mhz = 5.0;
            half_ns = 500.0 / freq_mhz;
            #(half_ns);
            if (en_ring === 1'b1) clk = ~clk; else clk = 1'b0;
        end else begin
            clk = 1'b0;
            #(5.0);
        end
    end

    // Dual-slope relaxation oscillator (98.538 kHz -> half-period 5074.2 ns)
    always begin
        if (en_relax === 1'b1) begin
            #(5074.2);
            if (en_relax === 1'b1) clk_slow = ~clk_slow; else clk_slow = 1'b0;
        end else begin
            clk_slow = 1'b0;
            #(50.0);
        end
    end
endmodule
