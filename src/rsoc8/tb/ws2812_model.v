// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Independent WS2812 receiver model, included in tb_sys.v. Enabled by +ws. Reads pin 6 (output of the chip).
// Written from the data format of the WS2812 (one wire, return-to-zero): a bit starts with a rising edge; the
// high time is short for a zero (T0H) and long for a one (T1H); the bit period is the same for both. A low
// level of at least the reset time ends the frame. Eight bits make a byte, most significant bit first.
// Limits in clock cycles of the testbench clock (60 MHz): T0H 24, T1H 48 (+-9), bit period 75 (+-9), reset 3000.
// All times are measured between edges of the pin in cycles of 10 ns of simulated time.
reg  w_on = 0;
integer WPIN = 6;                                   // +wpin=
localparam real W_T0H = 24.0, W_T1H = 48.0, W_PER = 75.0, W_TOL = 9.0, W_RESET = 3000.0;
real w_trise = 0, w_tfall = 0, w_tprev = 0;
integer w_bitn = 0, w_nbytes = 0, w_nframes = 0, w_inframe = 0, w_errs = 0, w_have_prev = 0, w_bad_h = 0, w_bad_per = 0, w_partial = 0, w_bits = 0;
reg [7:0] w_sh = 0; reg [7:0] w_b [0:4095]; integer w_fstart [0:63]; integer w_fbytes [0:63];
real w_t0h_min, w_t0h_max, w_t1h_min, w_t1h_max, w_per_min, w_per_max, w_gap_max, w_gap_min, w_low_max_in_byte;
task w_clear; begin
    w_bitn = 0; w_nbytes = 0; w_nframes = 0; w_inframe = 0; w_errs = 0; w_have_prev = 0; w_bad_h = 0; w_bad_per = 0; w_partial = 0; w_bits = 0;
    w_t0h_min = 1e9; w_t0h_max = 0; w_t1h_min = 1e9; w_t1h_max = 0; w_per_min = 1e9; w_per_max = 0; w_gap_max = -1e9; w_gap_min = 1e9;
end endtask
task w_end_frame; begin
    if (w_inframe) begin
        if (w_bitn != 0) w_partial = w_partial + 1;
        if (w_nframes < 64) begin w_fbytes[w_nframes] = w_nbytes - w_fstart[w_nframes]; end
        w_nframes = w_nframes + 1; w_inframe = 0; w_bitn = 0; w_have_prev = 0;
    end
end endtask
initial w_clear;
// a frame that has been low for the reset time ends even if no further edge comes
always @(posedge clk) if (w_on && w_inframe && line[WPIN] === 1'b0 && ($realtime / 10.0 - w_tfall) >= W_RESET) w_end_frame;
always @(line[WPIN]) if (w_on) begin : w_edge
    real t, hi, per, low;
    t = $realtime / 10.0;
    if (line[WPIN] === 1'b1) begin
        if (w_inframe) begin low = t - w_tfall; if (low >= W_RESET) w_end_frame; end
        if (!w_inframe) begin w_inframe = 1; w_have_prev = 0; w_bitn = 0; if (w_nframes < 64) w_fstart[w_nframes] = w_nbytes; end
        if (w_have_prev) begin
            per = t - w_tprev;
            if (w_bitn != 0) begin                                    // inside a byte: the period must be the nominal one
                if (per < w_per_min) w_per_min = per; if (per > w_per_max) w_per_max = per;
                if (per < W_PER - W_TOL || per > W_PER + W_TOL) begin w_bad_per = w_bad_per + 1; w_errs = w_errs + 1; end
            end else begin                                            // first bit of a byte: any extra low time below the reset time is a gap
                if (per - W_PER > w_gap_max) w_gap_max = per - W_PER; if (per - W_PER < w_gap_min) w_gap_min = per - W_PER;
                if (per < W_PER - W_TOL) begin w_bad_per = w_bad_per + 1; w_errs = w_errs + 1; end
            end
        end
        w_trise = t; w_tprev = t; w_have_prev = 1;
    end else begin
        if (w_inframe) begin
            hi = t - w_trise; w_tfall = t; w_bits = w_bits + 1;
            if (hi >= W_T0H - W_TOL && hi <= W_T0H + W_TOL) begin
                w_sh = {w_sh[6:0], 1'b0}; if (hi < w_t0h_min) w_t0h_min = hi; if (hi > w_t0h_max) w_t0h_max = hi;
            end else if (hi >= W_T1H - W_TOL && hi <= W_T1H + W_TOL) begin
                w_sh = {w_sh[6:0], 1'b1}; if (hi < w_t1h_min) w_t1h_min = hi; if (hi > w_t1h_max) w_t1h_max = hi;
            end else begin
                w_sh = {w_sh[6:0], 1'b0}; w_bad_h = w_bad_h + 1; w_errs = w_errs + 1;
            end
            w_bitn = w_bitn + 1;
            if (w_bitn == 8) begin if (w_nbytes < 4096) w_b[w_nbytes] = w_sh; w_nbytes = w_nbytes + 1; w_bitn = 0; end
        end
    end
end
