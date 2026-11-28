// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Model of an SPI slave (the chip is the master), included in tb_sys.v. Written from the definition of SPI,
// not from the line cell code. Enabled by +spislv.
// Pins: 0 MOSI (input of the model), 1 SCK, 2 MISO (driven by the model while CS is low), 3 CS (active low).
// Plusargs: +spislv_mode=n   clock mode: CPOL = n[1], CPHA = n[0]; data most significant bit first
//           +spislv_setup=n  smallest allowed time from a change of MOSI to the sampling edge, clock cycles (default 1)
//           +spislv_dly=n    delay of MISO after the shifting edge, clock cycles (default 0)
//           +spislv_gapfree  a pause between two bytes of a transfer is an error (default: only counted)
//           +spislv_xfers=n  number of transfers that must have taken place at the end (default: not checked)
// The model checks: SCK idle level equals CPOL at CS fall and at CS rise; the bytes on MOSI against the sequence
// 0xA5 + 29 i (i = byte number within the transfer); setup of MOSI before the sampling edge; complete bytes only;
// regular clock inside a byte. It returns the sequence 0x3C + 53 i on MISO. It records the time from CS fall to the first
// clock edge, from the last clock edge to CS rise, the half period, pauses between bytes and the smallest hold time.
// All times are in clock cycles of the chip (one cycle = 16.7 ns on the chip, 10 ns in the testbench).
reg ss_on = 0, ss_gapfree = 0, ss_act = 0; reg [1:0] ss_m = 0;
integer ss_setup = 1, ss_dly = 0, ss_xfers_exp = -1;
integer ss_xfer = 0, ss_err = 0, ss_bit = 0, ss_byte = 0, ss_nedge = 0, ss_t_cs = 0, ss_t_mosi = 0, ss_t_samp = 0, ss_t_edge = 0;
integer ss_h = 0, ss_cs2clk = 0, ss_clk2cs = 0, ss_gaps = 0, ss_maxgap = 0, ss_su = 0, ss_hd = 0, ss_mosi_bad = 0, ss_irr = 0, ss_spc = 0;
integer ss_su_all = 1000, ss_hd_all = 1000, ss_h_min = 1000, ss_cs2clk_min = 1000, ss_clk2cs_min = 1000;
reg ss_hold_pend = 0; reg [7:0] ss_sh = 0;
wire ss_mosi = uio_in[0], ss_sck = uio_in[1], ss_cs = uio_in[3];
function [7:0] ss_tx(input integer i); ss_tx = 8'h3C + 53 * i; endfunction
function [7:0] ss_exp(input integer i); ss_exp = 8'hA5 + 29 * i; endfunction
task ss_miso(input b); begin
    if (ss_dly == 0) x_val[2] = b; else x_val[2] <= #(ss_dly * 10) b;
end endtask
initial begin
    #1;
    if ($test$plusargs("spislv")) begin
        ss_on = 1;
        if ($value$plusargs("spislv_mode=%d", ss_m)) ;
        if ($value$plusargs("spislv_setup=%d", ss_setup)) ;
        if ($value$plusargs("spislv_dly=%d", ss_dly)) ;
        if ($value$plusargs("spislv_xfers=%d", ss_xfers_exp)) ;
        if ($test$plusargs("spislv_gapfree")) ss_gapfree = 1;
    end
end
always @(ss_mosi) if (ss_on) begin
    if (ss_hold_pend) begin ss_hd = xcyc - ss_t_samp; if (ss_hd < ss_hd_all) ss_hd_all = ss_hd; ss_hold_pend = 0; end
    ss_t_mosi = xcyc;
end
always @(negedge ss_cs) if (ss_on) begin
    ss_act = 1; ss_t_cs = xcyc; ss_nedge = 0; ss_bit = 0; ss_byte = 0; ss_gaps = 0; ss_maxgap = 0; ss_irr = 0;
    ss_su = 1000; ss_hd = 1000; ss_mosi_bad = 0; ss_h = 0; ss_hold_pend = 0; ss_spc = 0;
    if (ss_sck !== ss_m[1]) begin ss_err = ss_err + 1; $display("SPISLV FAIL: SCK is not at the idle level when CS falls"); end
    x_oe[2] = 1;
    if (!ss_m[0]) ss_miso(ss_tx(0) >> 7); else x_val[2] = 0;         // mode with CPHA = 0: first bit before the first clock edge
end
always @(ss_sck) if (ss_on && ss_act) begin : sckedge
    reg lead, samp; integer sp;
    lead = (ss_sck !== ss_m[1]);
    samp = lead ^ ss_m[0];
    if (ss_nedge == 0) ss_cs2clk = xcyc - ss_t_cs;
    else begin
        sp = xcyc - ss_t_edge;
        if (ss_nedge == 1) ss_h = sp;
        if (ss_nedge % 16 == 0) begin                                 // first edge of a byte
            if (sp > ss_h) begin ss_gaps = ss_gaps + 1; if (sp - ss_h > ss_maxgap) ss_maxgap = sp - ss_h;
                if (ss_gapfree) begin ss_err = ss_err + 1; $display("SPISLV FAIL: pause of %0d cycles before byte %0d", sp - ss_h, ss_nedge / 16); end end
            else if (sp < ss_h) ss_irr = ss_irr + 1;
        end else if (sp != ss_h) ss_irr = ss_irr + 1;
    end
    ss_t_edge = xcyc; ss_nedge = ss_nedge + 1;
    if (samp) begin
        ss_sh = {ss_sh[6:0], ss_mosi};
        if (xcyc - ss_t_mosi < ss_su) ss_su = xcyc - ss_t_mosi;
        ss_t_samp = xcyc; ss_hold_pend = 1;
        ss_bit = ss_bit + 1;
        if (ss_bit == 8) begin
            if (ss_sh !== ss_exp(ss_byte)) begin ss_mosi_bad = ss_mosi_bad + 1; ss_err = ss_err + 1;
                $display("SPISLV FAIL: byte %0d on MOSI is %02x, expected %02x", ss_byte, ss_sh, ss_exp(ss_byte)); end
            ss_byte = ss_byte + 1; ss_bit = 0;
        end
    end else ss_miso(ss_tx(ss_byte) >> (7 - ss_bit));
end
always @(posedge ss_cs) if (ss_on && ss_act) begin
    ss_act = 0; x_oe[2] = 0; ss_xfer = ss_xfer + 1;
    ss_clk2cs = xcyc - ss_t_edge;
    if (ss_sck !== ss_m[1]) begin ss_err = ss_err + 1; $display("SPISLV FAIL: SCK is not at the idle level when CS rises"); end
    if (ss_bit != 0) begin ss_err = ss_err + 1; $display("SPISLV FAIL: transfer ends after %0d bits of a byte", ss_bit); end
    if (ss_su < ss_setup) begin ss_err = ss_err + 1; $display("SPISLV FAIL: setup of MOSI %0d cycles, required %0d", ss_su, ss_setup); end
    if (ss_irr != 0) begin ss_err = ss_err + 1; $display("SPISLV FAIL: irregular clock edges inside a byte: %0d", ss_irr); end
    if (ss_su < ss_su_all) ss_su_all = ss_su; if (ss_h != 0 && ss_h < ss_h_min) ss_h_min = ss_h;
    if (ss_cs2clk < ss_cs2clk_min) ss_cs2clk_min = ss_cs2clk; if (ss_clk2cs < ss_clk2cs_min) ss_clk2cs_min = ss_clk2cs;
    $display("SPISLV mode %0d transfer %0d: %0d bytes, bad %0d, half period %0d, CS to first edge %0d, last edge to CS %0d, pauses %0d (longest %0d), MOSI setup min %0d, hold min %0d cycles",
             ss_m, ss_xfer, ss_byte, ss_mosi_bad, ss_h, ss_cs2clk, ss_clk2cs, ss_gaps, ss_maxgap, ss_su, ss_hd);
end
task spislv_final; begin
    if (ss_on) begin
        if (ss_xfers_exp >= 0 && ss_xfer != ss_xfers_exp) begin ss_err = ss_err + 1; $display("SPISLV FAIL: %0d transfers, expected %0d", ss_xfer, ss_xfers_exp); end
        if (ss_act) begin ss_err = ss_err + 1; $display("SPISLV FAIL: end of the test inside a transfer"); end
        if (ss_err == 0) $display("SPISLV PASS (%0d transfers, setup min %0d, half period min %0d, CS to first edge min %0d, last edge to CS min %0d cycles)", ss_xfer, ss_su_all, ss_h_min, ss_cs2clk_min, ss_clk2cs_min);
        else $display("SPISLV FAIL (%0d errors in %0d transfers)", ss_err, ss_xfer);
    end
end endtask
