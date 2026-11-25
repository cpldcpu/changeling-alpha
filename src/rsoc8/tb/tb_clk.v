// Testbench of rclock: two unrelated source clocks, an oscillator model with trim, register bus tasks.
// Self-checking; prints PASS or the failed checks.
`timescale 1ps/1ps
module tb_clk;
    // ---------------------------------------------------------------- sources
    reg clk_ext = 0, ext_on = 1; real ext_half = 8333.0;
    always begin #(ext_half); if (ext_on) clk_ext = ~clk_ext; end
    wire osc_en; wire [7:0] osc_trim;
    reg clk_osc = 0, osc_dead = 0; real osc_err = 0.85;          // untrimmed: 15 % slow
    real osc_half;
    always begin
        osc_half = 33333.0 / (osc_err * (1.0 + 0.005 * ($itor(osc_trim) - 128.0)));
        #(osc_half); if (osc_en && !osc_dead) clk_osc = ~clk_osc; else clk_osc = 0;
    end
    // ---------------------------------------------------------------- device
    reg rst_n = 1, strap = 0; initial #10 rst_n = 0;
    reg [8:0] io_addr = 0; reg io_host = 0, io_re = 0, io_we = 0, io_unlock = 0; reg [7:0] io_wdata = 0;
    wire [7:0] io_rdata; wire io_prot, clk, rst_sys_n, cke, ptick, trim_evt, cko_en, cko, dbg_en, dbg;
    reg ref_host = 0, ref_pin = 0; reg [1:0] ref_evt = 0;
    // relaxation oscillator model: 98.54 kHz (value after extraction, typical corner) while enabled
    wire relax_en; reg clk_slow = 0; real slow_half = 5074200.0;
    always begin #(slow_half); if (relax_en) clk_slow = ~clk_slow; else clk_slow = 0; end
    rclock dut (.clk_ext(clk_ext), .clk_osc(clk_osc), .clk_slow(clk_slow), .rst_n(rst_n), .strap(strap), .clk(clk), .rst_sys_n(rst_sys_n),
        .osc_en(osc_en), .relax_en(relax_en), .osc_trim(osc_trim), .io_addr(io_addr), .io_host(io_host), .io_re(io_re), .io_we(io_we),
        .io_wdata(io_wdata), .io_rdata(io_rdata), .io_unlock(io_unlock), .io_prot(io_prot), .cke(cke), .ptick(ptick),
        .ref_host(ref_host), .ref_pin(ref_pin), .ref_evt(ref_evt), .trim_evt(trim_evt),
        .smp_evt(2'b00), .acc_evt(2'b00), .tx_strobe(2'b00), .core_cen(2'b00), .bus_hold(1'b0),
        .cko_en(cko_en), .cko(cko), .dbg_en(dbg_en), .dbg(dbg));

    // ---------------------------------------------------------------- monitors
    integer errors = 0, n_clk = 0, n_cke = 0, n_pt = 0, n_tev = 0, n_cko = 0, n_short = 0;
    real t_rise = 0, t_fall = 0, t_prev_rise = 0, period = 0, min_hi = 1e9, min_lo = 1e9, t_osc_rise = 0;
    task fail(input [479:0] msg); begin errors = errors + 1; $display("FAIL at %0t: %0s", $time, msg); end endtask
    always @(posedge clk) begin
        if (t_fall > 0 && $realtime - t_fall < min_lo) min_lo = $realtime - t_fall;
        period = $realtime - t_prev_rise; t_prev_rise = $realtime; t_rise = $realtime;
        n_clk = n_clk + 1; n_cke = n_cke + cke; n_pt = n_pt + ptick; n_tev = n_tev + trim_evt;
    end
    always @(negedge clk) begin
        if (t_rise > 0 && $realtime - t_rise < min_hi) min_hi = $realtime - t_rise;
        t_fall = $realtime;
    end
    always @(posedge cko) n_cko = n_cko + 1;
    always @(posedge clk_osc) t_osc_rise = $realtime;
    always @(osc_trim) if (rst_n && $realtime - t_osc_rise > 1.0) fail("trim input changed away from a rising edge of the oscillator");
    reg dbg_exp; always @(posedge clk) begin if (dbg_en && n_clk > 10 && dbg !== dbg_exp && chk_dbg) fail("debug signal"); dbg_exp <= cke; end
    reg chk_dbg = 0;

    // ---------------------------------------------------------------- bus
    reg [7:0] rdv;
    task wr(input [8:0] a, input [7:0] d, input ul); begin
        @(negedge clk); io_addr = a; io_wdata = d; io_we = 1; io_unlock = ul; @(negedge clk); io_we = 0; io_unlock = 0;
    end endtask
    task rd(input [8:0] a); begin
        @(negedge clk); io_addr = a; io_re = 1; #100 rdv = io_rdata; @(negedge clk); io_re = 0;
    end endtask
    task cycles(input integer n); begin repeat (n) @(posedge clk); end endtask
    task expect_rd(input [8:0] a, input [7:0] mask, input [7:0] v, input [479:0] msg); begin
        rd(a); if ((rdv & mask) !== v) begin errors = errors + 1; $display("FAIL at %0t: %0s (read %02x)", $time, msg, rdv); end
    end endtask
    reg [15:0] cntv;
    task rd_cnt; begin rd(9'h125); cntv[7:0] = rdv; rd(9'h126); cntv[15:8] = rdv; end endtask
    task wait_done; integer k; begin
        k = 0; rd(9'h00F);
        while (!(rdv & 8'h10) && k < 4000) begin cycles(20); rd(9'h00F); k = k + 1; end
        if (k >= 4000) fail("measurement did not end");
    end endtask
    // reference generators
    real refp_half = 5000000.0; reg refp_on = 0;
    always begin #(refp_half); if (refp_on) ref_pin = ~ref_pin; end
    real refh_half = 500000.0; reg refh_on = 0;
    always begin #(refh_half); if (refh_on) ref_host = ~ref_host; end
    integer ev_per = 0, ev_cnt = 0, ev_cell = 1, ev_extra = 0;
    always @(negedge clk) begin
        ref_evt = 0;
        if (ev_per > 0) begin ev_cnt = ev_cnt + 1; if (ev_cnt >= ev_per) begin ev_cnt = 0; ref_evt[ev_cell] = 1; end if (ev_extra > 0 && ev_cnt == ev_extra) ref_evt[ev_cell] = 1; end
    end

    integer i, n0, c0, p0, t0, seed = 1; real f, tp; reg [7:0] trim0;
    initial begin
        // ---- 1. start on the external clock
        #100000 rst_n = 1;
        cycles(20);
        expect_rd(9'h00F, 8'h81, 8'h00, "starts on the external clock");
        expect_rd(9'h120, 8'hFF, 8'h00, "CLKCTL after reset with the strap low");
        if (osc_en !== 0) fail("oscillator enabled with the strap low");
        if (period < 16600 || period > 16700) fail("system clock is not the external clock");
        cycles(2200);
        expect_rd(9'h00F, 8'h06, 8'h04, "external clock present, oscillator not");
        // ---- 2. dividers; protected write
        wr(9'h122, 8'd2, 0); expect_rd(9'h122, 8'hFF, 8'h01, "CLKCDIV needs the unlock");
        wr(9'h122, 8'd2, 1); wr(9'h123, 8'd3, 0); cycles(20);
        n0 = n_clk; c0 = n_cke; p0 = n_pt; cycles(1200);
        if (n_cke - c0 != 400 || n_pt - p0 != 300) fail("divider ratios");
        wr(9'h122, 8'd0, 1); wr(9'h123, 8'd0, 0); cycles(8);
        c0 = n_cke; p0 = n_pt; cycles(100); if (n_cke - c0 != 100 || n_pt - p0 != 100) fail("dividers back to 1");
        // ---- 3. request for a clock that is not there: nothing happens. The request alone enables the oscillator
        //         (rule K1), so the oscillator is held dead for this case; then it runs and the switch follows.
        wr(9'h120, 8'h01, 0); expect_rd(9'h120, 8'hFF, 8'h00, "CLKCTL needs the unlock");
        osc_dead = 1; wr(9'h120, 8'h01, 1); cycles(3000);
        if (osc_en !== 1) fail("the requested oscillator is not enabled");
        expect_rd(9'h00F, 8'h01, 8'h00, "no switch to a stopped oscillator");
        osc_dead = 0; cycles(3000);
        expect_rd(9'h00F, 8'h07, 8'h07, "switch after the requested oscillator started, OSCEN not written");
        wr(9'h120, 8'h03, 1); cycles(3000);
        expect_rd(9'h00F, 8'h07, 8'h07, "runs from the oscillator, both clocks present");
        tp = 66667.0 / 0.85; if (period < tp * 0.99 || period > tp * 1.01) fail("system clock is not the oscillator");
        wr(9'h120, 8'h01, 1); cycles(50); if (osc_en !== 1) fail("the active oscillator must not be stopped");
        wr(9'h120, 8'h03, 1);
        // ---- 4. measurement against the reference pin: 4 periods of 10 us
        refp_on = 1;
        wr(9'h120, 8'h13, 1);                       // REFSEL = 1
        wr(9'h124, 8'h83, 0); expect_rd(9'h124, 8'hFF, 8'h83, "MEAS reads 1 while the measurement runs");
        wait_done; rd_cnt;
        f = 40000000.0 / tp;
        if (cntv < f - 1.5 || cntv > f + 1.5) begin fail("count against the reference pin"); $display("  count %0d expected %0f", cntv, f); end
        expect_rd(9'h124, 8'h80, 8'h00, "MEAS reads 0 afterwards");
        expect_rd(9'h00F, 8'h30, 8'h30, "MDONE and MVALID");
        // ---- 5. window: a target far away makes the measurement invalid, the loop does not step
        wr(9'h127, 8'hE8, 0); wr(9'h128, 8'h03, 0); wr(9'h129, 8'd1, 0);        // target 1000, window 64
        t0 = n_tev; wr(9'h120, 8'h17, 1); cycles(8000);
        expect_rd(9'h00F, 8'h30, 8'h10, "measurement outside the window is not valid");
        expect_rd(9'h121, 8'hFF, 8'h80, "no trim step outside the window");
        if (n_tev != t0) fail("event for a measurement outside the window");
        // ---- 6. loop: target 600 = 15 MHz, window 128; the oscillator model starts 15 % slow
        wr(9'h120, 8'h13, 1); wr(9'h127, 8'h58, 0); wr(9'h128, 8'h02, 0); wr(9'h129, 8'd2, 0);
        t0 = n_tev; wr(9'h120, 8'h17, 1);
        cycles(60000);
        rd_cnt; rd(9'h121); trim0 = rdv;
        if (cntv < 597 || cntv > 603) begin fail("loop did not reach the target"); $display("  count %0d trim %0d", cntv, trim0); end
        if (trim0 < 8'd158 || trim0 > 8'd170) begin fail("trim value after the loop"); $display("  trim %0d", trim0); end
        if (n_tev - t0 < 30) fail("events of valid measurements");
        if (period < 66667.0 * 0.993 || period > 66667.0 * 1.007) fail("oscillator period after the loop");
        wr(9'h120, 8'h1B, 1);                       // loop off, TRIMD set
        expect_rd(9'h00F, 8'h08, 8'h08, "TRIMD in the status");
        refp_on = 0;
        // ---- 7. line cell reference: every interval is a measurement
        ev_cell = 1; ev_per = 1500; wr(9'h129, 8'd0, 0);
        wr(9'h120, 8'h6B, 1); t0 = n_tev; cycles(7000); rd_cnt;
        if (cntv != 1500) begin fail("interval between line cell events"); $display("  count %0d", cntv); end
        if (n_tev - t0 < 3 || n_tev - t0 > 4) fail("one event per interval");
        expect_rd(9'h124, 8'h80, 8'h00, "MEAS is 0 with a line cell reference");
        ev_cell = 0; cycles(4000); t0 = n_tev; cycles(4000); if (n_tev != t0) fail("events of the other cell are not used");
        ev_per = 0;
        // ---- 7b. line cell reference with a window: events earlier than target - window are not used
        wr(9'h127, 8'hDC, 0); wr(9'h128, 8'h05, 0); wr(9'h129, 8'd1, 0);        // target 1500, window 64
        ev_cell = 1; ev_per = 1500; ev_extra = 400;                             // a second event 400 cycles after each
        wr(9'h120, 8'h6B, 1); cycles(400); t0 = n_tev; cycles(9000); rd_cnt;
        if (cntv != 1500) begin fail("interval with events in between"); $display("  count %0d", cntv); end
        if (n_tev - t0 < 5 || n_tev - t0 > 7) begin fail("one valid measurement per period with events in between"); $display("  events %0d", n_tev - t0); end
        expect_rd(9'h00F, 8'h20, 8'h20, "measurement with events in between is valid");
        ev_per = 1700; cycles(6000); rd_cnt;                                    // period outside the window: not valid, count restarts
        expect_rd(9'h00F, 8'h20, 8'h00, "interval longer than target + window is not valid");
        ev_extra = 0; ev_per = 0; wr(9'h129, 8'd0, 0);
        // ---- 8. count stops at 0xFFFF
        ev_cell = 1; ev_per = 70000; cycles(150000); rd_cnt; if (cntv != 16'hFFFF) fail("count stops at 0xFFFF"); ev_per = 0;
        // ---- 9. clock output and debug signal
        wr(9'h12A, 8'h81, 0); cycles(10); n0 = n_cko; cycles(400);
        if (n_cko - n0 != 100 || cko_en !== 1) fail("clock output divided by 4");
        wr(9'h12A, 8'h00, 0);
        wr(9'h122, 8'd4, 1); wr(9'h152, 8'h8C, 0); cycles(10); chk_dbg = 1; cycles(200); chk_dbg = 0;
        wr(9'h122, 8'd0, 1); wr(9'h152, 8'h00, 0);
        // ---- 10. back to the external clock; reference: host link clock, 8 periods of 1 us
        wr(9'h120, 8'h0A, 1); cycles(300);
        expect_rd(9'h00F, 8'h01, 8'h00, "back on the external clock");
        if (period < 16600 || period > 16700) fail("system clock is not the external clock again");
        refh_on = 1; wr(9'h124, 8'h87, 0); wait_done; rd_cnt; refh_on = 0;
        if (cntv < 479 || cntv > 481) begin fail("count against the host link clock"); $display("  count %0d", cntv); end
        // ---- 11. random switching with a changing oscillator frequency
        for (i = 0; i < 60; i = i + 1) begin
            wr(9'h121, 8'd60 + ($random(seed) & 8'h7F), 0);
            wr(9'h120, 8'h02 | (i & 1 ? 8'h00 : 8'h01), 1);
            #(2000000 + ($random(seed) & 32'hFFFFF));
            rd(9'h00F); if (rdv[0] !== ~i[0]) fail("switch not carried out");
        end
        // ---- 12. the external clock stops while the chip runs from the oscillator: no switch back
        wr(9'h120, 8'h03, 1); cycles(300); ext_on = 0; cycles(2500);
        expect_rd(9'h00F, 8'h04, 8'h00, "external clock absent");
        wr(9'h120, 8'h02, 1); cycles(3000);
        expect_rd(9'h00F, 8'h01, 8'h01, "no switch to a stopped external clock");
        ext_on = 1; cycles(3000);
        expect_rd(9'h00F, 8'h01, 8'h00, "switch once the external clock is back");
        // ---- 13. start with the strap high
        rst_n = 0; strap = 1; #200000 rst_n = 1; #2000000;
        expect_rd(9'h00F, 8'h81, 8'h81, "starts on the oscillator with the strap high");
        expect_rd(9'h120, 8'hFF, 8'h03, "CLKCTL after reset with the strap high");
        // ---- 14. strap high and no oscillator: no clock, and no pulse
        rst_n = 0; osc_dead = 1; #200000 rst_n = 1; n0 = n_clk; #3000000;
        if (n_clk != n0) fail("clock without a source");
        rst_n = 0; osc_dead = 0; strap = 0; #200000 rst_n = 1; cycles(50);
        expect_rd(9'h00F, 8'h81, 8'h00, "restart on the external clock");
        // ---- 15. loop with the relaxation oscillator as reference (REFSEL = 3)
        // 4 periods of 98.54 kHz are 40.59 us; the oscillator model has 15 MHz at the right trim: target 609.
        if (relax_en !== 0) fail("relaxation oscillator enabled after reset");
        wr(9'h120, 8'h03, 1); cycles(3000);         // run from the oscillator (model starts 15 % slow)
        expect_rd(9'h00F, 8'h01, 8'h01, "runs from the oscillator before the slow reference test");
        wr(9'h121, 8'h80, 0);
        wr(9'h124, 8'h03, 0); wr(9'h127, 8'h61, 0); wr(9'h128, 8'h02, 0); wr(9'h129, 8'd2, 0);     // 4 periods, target 609, window 128
        t0 = n_tev; wr(9'h120, 8'h37, 1);           // REFSEL = 3, LOOP, RELAXEN = 0: no reference edges
        cycles(8000);
        expect_rd(9'h121, 8'hFF, 8'h80, "no trim step while the relaxation oscillator is off");
        if (n_tev != t0) fail("measurement event without a slow reference");
        wr(9'h120, 8'hB3, 1);                       // RELAXEN = 1, loop off: one measurement over 4 periods
        wr(9'h124, 8'h83, 0); wait_done; rd_cnt;
        f = 4.0 * 2.0 * slow_half / (66667.0 / 0.85);
        if (cntv < f - 1.5 || cntv > f + 1.5) begin fail("count against the relaxation oscillator"); $display("  count %0d expected %0f", cntv, f); end
        expect_rd(9'h121, 8'hFF, 8'h80, "a single measurement does not change the trim value");
        wr(9'h120, 8'hB7, 1);                       // LOOP
        expect_rd(9'h120, 8'hFF, 8'hB7, "CLKCTL reads RELAXEN, REFSEL = 3, LOOP, OSCEN, SRC");
        if (relax_en !== 1) fail("RELAXEN does not enable the relaxation oscillator");
        cycles(80000);
        rd_cnt; rd(9'h121); trim0 = rdv;
        if (cntv < 606 || cntv > 612) begin fail("loop with the slow reference did not reach the target"); $display("  count %0d trim %0d", cntv, trim0); end
        if (trim0 < 8'd158 || trim0 > 8'd170) begin fail("trim value after the loop with the slow reference"); $display("  trim %0d", trim0); end
        if (n_tev - t0 < 30) fail("events of valid measurements with the slow reference");
        if (period < 66667.0 * 0.99 || period > 66667.0 * 1.01) fail("oscillator period after the loop with the slow reference");
        slow_half = 5074200.0 / 1.05; cycles(80000);                            // reference 5 % faster: the loop follows
        if (period < 66667.0 / 1.05 * 0.99 || period > 66667.0 / 1.05 * 1.01) fail("loop does not follow the slow reference");
        wr(9'h120, 8'h03, 1); cycles(50);
        if (relax_en !== 0) fail("RELAXEN cleared, relaxation oscillator still enabled");
        wr(9'h120, 8'h00, 1); cycles(3000);
        expect_rd(9'h00F, 8'h01, 8'h00, "back on the external clock");
        // ---- shortest phases of the system clock over the whole run
        $display("shortest high phase %0.0f ps, shortest low phase %0.0f ps, %0d clock cycles", min_hi, min_lo, n_clk);
        if (min_hi < 8300 || min_lo < 8300) fail("short pulse on the system clock");
        if (errors == 0) $display("PASS"); else $display("%0d errors", errors);
        $finish;
    end
    initial begin #(64'd200000000000); $display("TIMEOUT"); $finish; end
endmodule
