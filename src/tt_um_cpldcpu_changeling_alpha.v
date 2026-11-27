/*
 * Copyright (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// Tiny Tapeout top module of Changeling-alpha. It only connects the pins of the Tiny Tapeout
// template to the chip level rpe_chip in rsoc8/rtl/rpe_top.v. Everything specific to Tiny Tapeout
// is in this file, sram_bb.v, config.json and pdn_cfg.tcl; the folder rsoc8 does not depend on it.
//
// The instance names below are part of the hierarchical names of the three SRAM macros
// (chip.u.m_code0.u_mem, chip.u.m_code1.u_mem, chip.u.m_data.u_mem), which config.json uses.
module tt_um_cpldcpu_changeling_alpha (
    input  wire [7:0] ui_in,    // dedicated inputs
    output wire [7:0] uo_out,   // dedicated outputs
    input  wire [7:0] uio_in,   // bidirectional pins: input path
    output wire [7:0] uio_out,  // bidirectional pins: output path
    output wire [7:0] uio_oe,   // bidirectional pins: output enable (1 = output)
    input  wire       ena,      // high while the design is selected
    input  wire       clk,      // clock, 60 MHz
    input  wire       rst_n     // reset, active low
);
    rpe_chip chip (.ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
                   .ena(ena), .clk(clk), .rst_n(rst_n));
endmodule

`default_nettype wire
