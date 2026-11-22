// Stress tests: two protocols at once, monitors for bus holds and service times, PWM and timer checks.
// Included in tb_sys.v. Enabled by +stress=<scenario>; see tests/stress.sh for the command lines.
//   scenarios  1 UART echo (core 0, models on pins 4/5) + SPI master (core 1, slave model on pins 0-3)
//              2 UART echo (core 0, pins +urx/+utx) + I2C firmware master (core 1) with the stretching slave model (+i2cs)
//              3 SPI slave (core 0, master model +spimst) + WS2812 controller frames (core 1, +ws)
//              6 one core: UART echo on pair 0 + SPI slave on pair 1 (both models)
//              7 WS2812 controller, long chain (+ws)       8 WS2812 LED with forwarding, sender in the testbench
//   +sn=<n>     number of UART characters (default 60)   +sxstart=<cycles> wait before the stream (default 3000)
//   +sxhost=<k> host link actions during the run (scenario 1), see sx_host
// All times in clock cycles of the testbench (10 ns each, 16.7 ns on the chip).
integer sx_hk = 0, sx_scen = 0, sx_n = 60, sx_time = 40000; reg sx_nouart = 0;   // +sxnouart: no UART stream, run +sxtime=<cycles>
reg sx_en = 0;
// ------------------------------------------------------------------ monitors
wire sx_h0 = top.u.cores.req0 & ~top.u.cores.g0;           // core 0 is held by the arbiter in this cycle
wire sx_h1 = top.u.cores.req1 & ~top.u.cores.g1;
wire sx_q0 = top.u.cores.req0, sx_q1 = top.u.cores.req1;
integer sx_hold0 = 0, sx_hold1 = 0, sx_req0 = 0, sx_req1 = 0, sx_cyc = 0, sx_both = 0;
// service times: index 0 receive cell 0 (rxf pulse to read of LR0DATA), 1 receive cell 1, 2 transmit cell 0 (buffer
// emptied to write of LT0DATA), 3 transmit cell 1
integer sx_n_a [0:3], sx_sum_a [0:3], sx_max_a [0:3], sx_hw_a [0:3], sx_hwmax_a [0:3], sx_t_a [0:3], sx_ovl_a [0:3], sx_min_a [0:3];
reg sx_pd_a [0:3];
integer sxi;
initial for (sxi = 0; sxi < 4; sxi = sxi + 1) begin sx_n_a[sxi] = 0; sx_sum_a[sxi] = 0; sx_max_a[sxi] = 0; sx_hw_a[sxi] = 0; sx_hwmax_a[sxi] = 0; sx_t_a[sxi] = 0; sx_ovl_a[sxi] = 0; sx_pd_a[sxi] = 0; sx_min_a[sxi] = 1000000; end
reg sx_tf0 = 0, sx_tf1 = 0;
task sx_begin(input integer i); begin
    if (sx_pd_a[i]) sx_ovl_a[i] = sx_ovl_a[i] + 1;      // the previous event has not been served yet
    sx_pd_a[i] = 1; sx_t_a[i] = xcyc; sx_hw_a[i] = 0;
end endtask
task sx_end(input integer i); integer l; begin
    if (sx_pd_a[i]) begin
        l = xcyc - sx_t_a[i];
        sx_n_a[i] = sx_n_a[i] + 1; sx_sum_a[i] = sx_sum_a[i] + l;
        if (l > sx_max_a[i]) sx_max_a[i] = l; if (l < sx_min_a[i]) sx_min_a[i] = l;
        if (sx_hw_a[i] > sx_hwmax_a[i]) sx_hwmax_a[i] = sx_hw_a[i];
        sx_pd_a[i] = 0;
    end
end endtask
always @(posedge clk) if (sx_en) begin
    sx_cyc = sx_cyc + 1;
    sx_hold0 = sx_hold0 + sx_h0; sx_hold1 = sx_hold1 + sx_h1; sx_req0 = sx_req0 + sx_q0; sx_req1 = sx_req1 + sx_q1;
    sx_both = sx_both + (sx_q0 & sx_q1);
    // the held cycles of the core that owns the pair count in the window of that pair
    for (sxi = 0; sxi < 4; sxi = sxi + 1)
        if (sx_pd_a[sxi]) sx_hw_a[sxi] = sx_hw_a[sxi] + (top.u.lc_own[sxi % 2] ? sx_h1 : sx_h0);
    if (top.u.rxf[0]) sx_begin(0);
    if (top.u.rxf[1]) sx_begin(1);
    if (sx_tf0 && !top.u.ports.t0.tbuf_full) sx_begin(2);
    if (sx_tf1 && !top.u.ports.t1.tbuf_full) sx_begin(3);
    sx_tf0 = top.u.ports.t0.tbuf_full; sx_tf1 = top.u.ports.t1.tbuf_full;
    if (top.u.io_re && !io_host && io_addr == 9'h009) sx_end(0);
    if (top.u.io_re && !io_host && io_addr == 9'h011) sx_end(1);
    if (io_we && !io_host && io_addr == 9'h00B) sx_end(2);
    if (io_we && !io_host && io_addr == 9'h013) sx_end(3);
end
// PWM pins (output-only pins 5, 6, 7): period between rising edges and high time, in clock cycles. Event driven: the time of
// the edge is taken from $realtime (10 ns per cycle), not from a sample at the clock edge.
integer pw_np [0:2], pw_pmin [0:2], pw_pmax [0:2], pw_hmin [0:2], pw_hmax [0:2], pw_edges [0:2], pwi;
real pw_tr [0:2];
reg [2:0] pw_prev = 3'b000;
initial for (pwi = 0; pwi < 3; pwi = pwi + 1) begin pw_tr[pwi] = -1.0; pw_np[pwi] = 0; pw_pmin[pwi] = 1000000; pw_pmax[pwi] = 0; pw_hmin[pwi] = 1000000; pw_hmax[pwi] = 0; pw_edges[pwi] = 0; end
always @(out_pins[7:5]) if (sx_en) begin : pwm_edge
    integer ii, per, hi; real t;
    t = $realtime / 10.0;
    for (ii = 0; ii < 3; ii = ii + 1) begin
        if (out_pins[5 + ii] === 1'b1 && !pw_prev[ii]) begin
            if (pw_tr[ii] >= 0.0) begin
                per = t - pw_tr[ii]; pw_np[ii] = pw_np[ii] + 1;
                if (per < pw_pmin[ii]) pw_pmin[ii] = per; if (per > pw_pmax[ii]) pw_pmax[ii] = per;
            end
            pw_tr[ii] = t;
        end
        if (out_pins[5 + ii] === 1'b0 && pw_prev[ii] && pw_tr[ii] >= 0.0) begin
            hi = t - pw_tr[ii];
            if (pw_np[ii] > 0) begin if (hi < pw_hmin[ii]) pw_hmin[ii] = hi; if (hi > pw_hmax[ii]) pw_hmax[ii] = hi; end
            pw_edges[ii] = pw_edges[ii] + 1;
        end
        pw_prev[ii] = out_pins[5 + ii];
    end
end
// compare A and B events of the timer (event driven), and the spacing of the A events
integer oc_n = 0, oc_min = 1000000, oc_max = 0, ob_n = 0; real oc_t = -1.0;
always @(posedge top.u.oca_evt) if (sx_en) begin : oca_edge
    real t; integer d; t = $realtime / 10.0;
    oc_n = oc_n + 1;
    if (oc_t >= 0.0) begin d = t - oc_t; if (d < oc_min) oc_min = d; if (d > oc_max) oc_max = d; end
    oc_t = t;
end
always @(posedge top.u.ocb_evt) if (sx_en) ob_n = ob_n + 1;
function integer sx_mean(input integer i); begin sx_mean = sx_n_a[i] ? (10 * sx_sum_a[i]) / sx_n_a[i] : 0; end endfunction   // in tenths of a cycle
task sx_monitor_report; integer i; begin
    $display("STRESSMON cycles %0d, held core0 %0d core1 %0d, bus requests core0 %0d core1 %0d, both in the same cycle %0d, cdiv %0d", sx_cyc, sx_hold0, sx_hold1, sx_req0, sx_req1, sx_both, cdiv);
    for (i = 0; i < 4; i = i + 1)
        if (sx_n_a[i] > 0 || sx_ovl_a[i] > 0)
            $display("STRESSMON service %0s: n %0d, min %0d, mean %0d.%0d, max %0d cycles, held cycles inside the window max %0d, events before the previous was served %0d",
                     i == 0 ? "rx0" : i == 1 ? "rx1" : i == 2 ? "tx0" : "tx1", sx_n_a[i], sx_min_a[i], sx_mean(i) / 10, sx_mean(i) % 10, sx_max_a[i], sx_hwmax_a[i], sx_ovl_a[i]);
end endtask
// ------------------------------------------------------------------ helpers
integer sx_fails = 0;
task sx_fail(input [511:0] msg); begin sx_fails = sx_fails + 1; $display("STRESS FAIL: %0s", msg); end endtask
function [7:0] sx_ram(input [10:0] a); begin sx_ram = ram8(a); end endfunction
function [15:0] sx_ram16(input [10:0] a); begin sx_ram16 = {ram8(a + 11'd1), ram8(a)}; end endfunction
task sx_fwreport; begin
    $display("STRESSFW core1: rounds %0d, first error %0d, errors %0d; core0: units %0d, first error %0d, errors %0d",
             sx_ram16(11'h710), sx_ram(11'h712), sx_ram(11'h713), sx_ram16(11'h716), sx_ram(11'h714), sx_ram(11'h715));
end endtask
// the UART stream: n characters back to back at the bit time of the model, echo checked at the end (u_chk)
integer sx_t_s0 = 0;
integer sx_rep = 1;      // +sxrep=k: the stream of n characters is repeated k times (blocks of at most 1000 characters)
task sx_uart_stream(input integer n); integer k, rep, allok, tot; reg [7:0] d; begin
    allok = 1; tot = 0; sx_t_s0 = xcyc;
    for (rep = 0; rep < sx_rep; rep = rep + 1) begin
        u_clear; u_idle(rep == 0 ? 12 : 2);
        for (k = 0; k < n; k = k + 1) begin d = u_pat(k + 3); u_send(d, 0, 0); u_expect(d & u_mask(u_nd), 0, 0); end
        u_waitn(n, 80); u_idle(30);
        u_chk; tot = tot + r_n;
        if (!u_ok) allok = 0;
    end
    $display("STRESS UART: %0d characters back to back (%0d block(s) of %0d), bit time %0f cycles, model offset %0f%%: %0s (received %0d)", n * sx_rep, sx_rep, n, u_cyc, u_offt, allok ? "all echoed correctly" : "DIFFERENT", tot);
    if (!allok) sx_fail("UART echo differs");
end endtask
// loss analysis of the echo: the received characters (without '#') are matched against the sent ones in order; a sent
// character that is not matched is lost. Returns the number of lost characters and the first and last lost index.
integer sx_lost, sx_lost_first, sx_lost_last, sx_marks, sx_wrong;
task sx_uart_loss(input integer n); integer k, p; reg [7:0] d; begin
    sx_lost = 0; sx_lost_first = -1; sx_lost_last = -1; sx_marks = 0; sx_wrong = 0; p = 0;
    for (k = 0; k < n; k = k + 1) begin
        d = mb_pat(k);
        while (p < r_n && r_d[p] == 8'h23 && d != 8'h23) begin sx_marks = sx_marks + 1; p = p + 1; end
        if (p < r_n && r_d[p] == d && !r_fe[p] && !r_pe[p]) p = p + 1;
        else begin sx_lost = sx_lost + 1; if (sx_lost_first < 0) sx_lost_first = k; sx_lost_last = k; end
    end
    while (p < r_n) begin if (r_d[p] == 8'h23) sx_marks = sx_marks + 1; else sx_wrong = sx_wrong + 1; p = p + 1; end
end endtask
task sx_pwm_report; integer i; begin
    for (i = 0; i < 3; i = i + 1)
        $display("STRESSPWM pin %0d: %0d periods, period min %0d max %0d, high min %0d max %0d cycles", 5 + i, pw_np[i], pw_pmin[i], pw_pmax[i], pw_hmin[i], pw_hmax[i]);
    $display("STRESSTIMER compare A events %0d, spacing min %0d max %0d; stamps served by the firmware %0d, spacing errors %0d, largest deviation %0d cycles",
             oc_n, oc_min, oc_max, sx_ram16(11'h718), sx_ram16(11'h71A), sx_ram16(11'h71C));
end endtask
// the checks of the extras (PWM period 100, duty 25/50/75, compare event period OCA_PERIOD)
integer sx_ocap = 997;
task sx_extras_check; integer i, ex; begin
    sx_pwm_report;
    for (i = 0; i < 3; i = i + 1) begin
        if (pw_np[i] < 10) sx_fail("PWM: too few periods");
        if (pw_pmin[i] != 100 || pw_pmax[i] != 100) sx_fail("PWM period is not 100");
        if (pw_hmin[i] != 25 * (i + 1) || pw_hmax[i] != 25 * (i + 1)) sx_fail("PWM duty is not 25/50/75");
    end
    if ($test$plusargs("ocbx")) begin
        $display("STRESSTIMER compare B events %0d; stamps served by core 1 %0d, spacing errors %0d, largest deviation %0d cycles", ob_n, sx_ram16(11'h724), sx_ram16(11'h726), sx_ram16(11'h728));
        if (ob_n - sx_ram16(11'h724) < 0 || ob_n - sx_ram16(11'h724) > 1) sx_fail("compare B events lost");
        if (sx_ram16(11'h726) != 0) sx_fail("compare B stamps with a wrong spacing");
    end
    if (oc_min != sx_ocap || oc_max != sx_ocap) sx_fail("compare A spacing is not the period");
    ex = oc_n - sx_ram16(11'h718);
    if (ex < 0 || ex > 1) sx_fail("compare events lost (count of the firmware differs from the count of the testbench)");
    if (sx_ram16(11'h71A) != 0) sx_fail("time stamps with a wrong spacing");
end endtask
task sx_final(input integer wantfw1, input integer wantfw0); begin
    sx_monitor_report; sx_fwreport;
    spislv_final; spimst_final; i2cs_final; i2cm_final;
    if (wantfw1 && sx_ram(11'h712) != 0) sx_fail("core 1 reports an error");
    if (wantfw0 && sx_ram(11'h714) != 0) sx_fail("core 0 reports an error");
    if (ss_on && ss_err != 0) sx_fail("SPI slave model reports errors");
    if (sm_on && sm_err != 0) sx_fail("SPI master model reports errors");
    if (i2cs_on && i2cs_err != 0) sx_fail("I2C slave model reports errors");
    if (sx_fails == 0) $display("STRESS PASS scenario %0d", sx_scen); else $display("STRESS FAIL scenario %0d (%0d failures)", sx_scen, sx_fails);
    $finish;
end endtask
// checks all frames of the WS2812 receiver model: every frame has nb bytes, the data are ws_pat(0..nb-1), no timing error
task sx_ws_check(input integer nb); integer f, k, bad, fb; begin
    bad = 0;
    for (f = 0; f < w_nframes && f < 64; f = f + 1) begin
        if (w_fbytes[f] != nb) begin bad = bad + 1; $display("STRESS WS frame %0d has %0d bytes, expected %0d", f, w_fbytes[f], nb); end
        for (k = 0; k < nb; k = k + 1) if (w_b[w_fstart[f] + k] !== ws_pat(k)) bad = bad + 1;
    end
    $display("STRESS WS: %0d bits, %0d frames, %0d bytes, %0d bad bytes or frames, %0d bad high times, %0d bad periods, %0d partial; T0H %0f..%0f T1H %0f..%0f period %0f..%0f extra low between bytes %0f..%0f cycles",
             w_bits, w_nframes, w_nbytes, bad, w_bad_h, w_bad_per, w_partial, w_t0h_min, w_t0h_max, w_t1h_min, w_t1h_max, w_per_min, w_per_max, w_gap_min, w_gap_max);
    if (w_nframes < 1 || bad != 0 || w_errs != 0 || w_partial != 0) sx_fail("WS2812 frames wrong");
end endtask
// WS2812 sender (testbench): bit period 75 (1 + e) cycles, T0H 24 (1 + e), T1H 48 (1 + e), every edge moved by a random value
// in -jit .. +jit cycles. Sends nb bytes ws_pat(0 ...), most significant bit first, on pin ws_in (x_oe / x_val).
integer ws_in = 0, ws_seed = 7;
function integer wsx_j(input integer jj); integer r; begin r = $random(ws_seed); if (r < 0) r = -r; if (r < 0) r = 0; wsx_j = (r % (2 * jj + 1)) - jj; end endfunction
task wsx_frame(input integer nb, input real e, input integer jit); integer k, i, j; real per, th, tb0, tr, tf; reg b; begin
    per = 75.0 * (1.0 + e); tb0 = $realtime; k = 0;
    for (j = 0; j < nb; j = j + 1)
        for (i = 7; i >= 0; i = i - 1) begin
            b = ws_pat(j) >> i;
            th = (b ? 48.0 : 24.0) * (1.0 + e);
            tr = tb0 + 10.0 * (k * per + (jit ? wsx_j(jit) : 0));
            tf = tb0 + 10.0 * (k * per + th + (jit ? wsx_j(jit) : 0));
            if (tr > $realtime) #(tr - $realtime);
            x_val[ws_in] = 1;
            if (tf > $realtime) #(tf - $realtime);
            x_val[ws_in] = 0;
            k = k + 1;
        end
end endtask
// low times above 500 cycles on the output pin of the WS2812 receiver model (the gaps between frames)
integer wg [0:7], wg_n = 0; real wg_t = 0;
always @(line[WPIN]) if (w_on) begin
    if (line[WPIN] === 1'b0) wg_t = $realtime / 10.0;
    else if (wg_t > 0 && ($realtime / 10.0 - wg_t) > 500.0) begin if (wg_n < 8) wg[wg_n] = $realtime / 10.0 - wg_t; wg_n = wg_n + 1; wg_t = 0; end
end
// the UART stream during host actions: no check at the end; the analysis follows in sx_host_analysis
task sx_uart_stream_h(input integer n); integer k; reg [7:0] d; begin
    u_clear; u_idle(12); sx_t_s0 = xcyc;
    for (k = 0; k < n; k = k + 1) begin d = mb_pat(k); u_send(d, 0, 0); u_expect(d & u_mask(u_nd), 0, 0); end
    u_waitn(n, 80); u_idle(30);
end endtask
task sx_host_analysis(input integer k, input integer n); integer w0, w1, kk; begin
    sx_uart_loss(n);
    w0 = sx_host_t0 - sx_t_s0; w1 = sx_host_t1 - sx_t_s0;
    $display("STRESS HOST UART: %0d sent, %0d received, %0d lost (first %0d last %0d; characters start every %0f cycles), overrun markers %0d, wrong characters %0d; disturbance from cycle %0d to %0d (%0d cycles = %0f characters)",
             n, r_n, sx_lost, sx_lost_first, sx_lost_last, 10.0 * u_cyc, sx_marks, sx_wrong, w0, w1, w1 - w0, (w1 - w0) / (10.0 * u_cyc));
    if (sx_lost > 0) begin
        $write("STRESS HOST UART received (as k = index of the sent pattern): ");
        for (kk = 0; kk < r_n && kk < 90; kk = kk + 1) $write(" %02x", r_d[kk]);
        $write("\n");
    end
    if (sx_lost_first >= 0) $display("STRESS HOST UART: first lost character started at cycle %0f, last at %0f (disturbance %0d..%0d)", 12 * u_cyc + sx_lost_first * 10.0 * u_cyc, 12 * u_cyc + sx_lost_last * 10.0 * u_cyc, w0, w1);
    // expectation: with core 0 not halted (k = 1, 2) the UART is clean; with core 0 halted (3, 4, 5) the lost characters are inside the window
    if (k == 1 || k == 2) begin if (sx_lost != 0 || sx_marks != 0 || sx_wrong != 0) sx_fail("UART disturbed although core 0 was not halted"); end
    else begin if (sx_wrong != 0) sx_fail("wrong characters after the halt"); end
    // SPI: with core 1 not halted (k = 1, 3, 5) the SPI transfers must all be clean
    if ((k == 1 || k == 3 || k == 5) && (ss_err != 0 || sx_ram(11'h712) != 0)) sx_fail("SPI disturbed although core 1 was not halted");
end endtask
// ------------------------------------------------------------------ host link actions during a run (+sxhost=k, scenario 1)
//   1 status and mailbox commands and a refused memory read while both cores run; no halt
//   2 halt core 1 for sx_hlen cycles, resume          3 halt core 0, resume
//   4 halt both cores, read and write memory and registers, resume
//   5 halt core 0, inject instructions (core 1 keeps running), a memory read is refused, resume
integer sx_host_t0 = 0, sx_host_t1 = 0, sx_hlen = 4000, sx_hostt = 12000, sx_host_ok = 1;
reg [7:0] sx_c1a, sx_c1b; reg [7:0] sx_r16;
task sx_hchk(input c, input [255:0] msg); begin
    if (!c) begin sx_host_ok = 0; $display("STRESS HOST CHECK FAILED: %0s (hv %02x %02x status %02x %02x)", msg, hv, hv2, hs0, hs1); end
end endtask
task sx_host(input integer k); integer i; reg [15:0] a, b; begin
    repeat (sx_hostt) @(posedge clk);
    case (k)
    1: begin
        sx_host_t0 = xcyc;
        for (i = 0; i < 20; i = i + 1) begin h_status; sx_hchk(hs0[1:0] == 2'b00 && hs1[1:0] == 2'b11, "status while both cores run"); end
        spi_start; spi_byte(8'h07); spi_byte(8'h5A); spi_stop;                  // mailbox write
        h_status; sx_hchk(hs1[7] == 0, "mailbox write accepted");
        spi_start; spi_byte(8'h08); spi_byte(0); spi_byte(0); spi_stop;         // mailbox status
        h_rd(16'h0700); h_status; sx_hchk(hs1[7] == 1, "memory read while the cores run is refused (error bit)");
        h_wr(16'h0700, 8'h55); h_status; sx_hchk(hs1[7] == 1, "memory write while the cores run is refused");
        sx_host_t1 = xcyc;
    end
    2, 3: begin
        h_ctrl(k == 2 ? 8'h02 : 8'h01); sx_host_t0 = xcyc;
        repeat (sx_hlen) @(posedge clk);
        h_status; sx_hchk(k == 2 ? hs0[1:0] == 2'b10 : hs0[1:0] == 2'b01, "status shows the halted core");
        h_rd(16'h0700); h_status; sx_hchk(hs1[7] == 1, "memory read refused: the other core runs");
        h_ctrl(8'h00); sx_host_t1 = xcyc;
    end
    4: begin
        h_ctrl(8'h03); sx_host_t0 = xcyc;
        repeat (3000) @(posedge clk);
        h_status; sx_hchk(hs0[1:0] == 2'b11 && hs0[7], "both halted, access allowed");
        h_rd(16'h0716); sx_c1a = hv; h_rd(16'h0717); sx_c1b = hv;
        h_rd(16'h0710); a[7:0] = hv; h_rd(16'h0711); a[15:8] = hv;
        repeat (500) @(posedge clk);
        h_rd(16'h0710); b[7:0] = hv; h_rd(16'h0711); b[15:8] = hv;
        sx_hchk(a == b, "memory stands still while both are halted");
        h_wr(16'h07E0, 8'hA7); h_rd(16'h07E0); sx_hchk(hv == 8'hA7, "write and read of the data memory");
        h_rd(16'h0000); h_rd(16'h0001); h_wr(16'h0153, 8'h00); h_rd1(16'h0153); sx_hchk(hv == 8'h00, "register read and write");
        repeat (sx_hlen) @(posedge clk);
        h_ctrl(8'h00); sx_host_t1 = xcyc;
    end
    5: begin
        h_ctrl(8'h01); sx_host_t0 = xcyc;
        repeat (1000) @(posedge clk);
        h_status; sx_hchk(hs0[1:0] == 2'b01, "core 0 halted, core 1 running");
        h_rd(16'h0700); h_status; sx_hchk(hs1[7] == 1, "memory read refused: core 1 runs");
        h_ins(8'h06, 16'hAD01);                                                  // sts 0x61, r16  (save r16)
        h_ins(8'h06, 16'hE50A); h_ins(8'h06, 16'hAD00);                          // ldi r16, 0x5A; sts 0x60, r16
        sx_hchk(ram8(11'h060) == 8'h5A, "injected instructions executed in core 0 while core 1 runs");
        h_ins(8'h06, 16'hA501);                                                  // lds r16, 0x61  (restore r16)
        h_status; sx_hchk(hs1[7] == 0, "injection accepted");
        for (i = 0; i < 20; i = i + 1) h_step;                                   // single steps of core 0
        repeat (sx_hlen) @(posedge clk);
        h_ctrl(8'h00); sx_host_t1 = xcyc;
    end
    endcase
end endtask
// ------------------------------------------------------------------ scenarios
task stress_test;
    integer start, k, nf0;
    begin
        if ($value$plusargs("stress=%d", sx_scen)) ;
        if ($value$plusargs("sn=%d", sx_n)) ;
        if ($value$plusargs("ocap=%d", sx_ocap)) ;
        if ($test$plusargs("sxnouart")) sx_nouart = 1;
        if ($value$plusargs("sxrep=%d", sx_rep)) ;
        if ($value$plusargs("sxtime=%d", sx_time)) ;
        start = 3000; if ($value$plusargs("sxstart=%d", start)) ;
        sx_en = 1;
        case (sx_scen)
        1: begin : s1                                       // UART echo + SPI master
            u_on = 1; if ($value$plusargs("ucpb=%f", u_cyc)) ; if ($value$plusargs("uoff=%f", u_offt)) ;
            repeat (start) @(posedge clk);
            if ($value$plusargs("sxhost=%d", sx_hk)) begin
                if ($value$plusargs("sxhlen=%d", sx_hlen)) ; if ($value$plusargs("sxhostt=%d", sx_hostt)) ;
                fork sx_uart_stream_h(sx_n); sx_host(sx_hk); join
                sx_host_analysis(sx_hk, sx_n);
                if (ss_on && ss_act) @(posedge uio_in[3]);
                #1;
                $display("STRESS HOST scenario %0d: host checks %0s, SPI model errors %0d, core 1 errors %0d (first %0d), core 0 errors %0d", sx_hk, sx_host_ok ? "ok" : "FAILED", ss_err, sx_ram(11'h713), sx_ram(11'h712), sx_ram(11'h715));
                sx_monitor_report; sx_fwreport; spislv_final;
                if (!sx_host_ok) sx_fail("host check");
                if (sx_fails == 0) $display("STRESS PASS scenario 1 host %0d", sx_hk); else $display("STRESS FAIL scenario 1 host %0d", sx_hk);
                $finish;
            end
            if (sx_nouart) repeat (sx_time) @(posedge clk); else sx_uart_stream(sx_n);
            if (ss_on && ss_act) @(posedge uio_in[3]);      // end of the SPI transfer that is running
            #1;
            if (ss_on && ss_xfer < 2) sx_fail("fewer than 2 SPI transfers");
            if ($test$plusargs("extras")) sx_extras_check;
            sx_final(1, 1);
        end
        2: begin : s2                                       // UART echo + I2C firmware master
            u_on = 1; if ($value$plusargs("ucpb=%f", u_cyc)) ; if ($value$plusargs("uoff=%f", u_offt)) ;
            repeat (start) @(posedge clk);
            if (sx_nouart) repeat (sx_time) @(posedge clk); else sx_uart_stream(sx_n);
            if (i2cs_inseg) wait (!i2cs_inseg);
            #1;
            if (i2cs_on && sx_ram16(11'h710) < 1) sx_fail("no complete I2C sequence");
            sx_final(1, 1);
        end
        6: begin : s6                                       // one core: UART echo + SPI slave (both models)
            u_on = 1; if ($value$plusargs("ucpb=%f", u_cyc)) ; if ($value$plusargs("uoff=%f", u_offt)) ;
            repeat (start) @(posedge clk);
            fork
                sx_uart_stream(sx_n);
                begin wait (sm_done >= sm_xfers); end
            join
            #1;
            if (sx_ram16(11'h710) + 2 < sm_done) sx_fail("the firmware completed fewer SPI transfers than the model");
            sx_final(1, 1);
        end
        7: begin : s7                                       // WS2812 controller, long chain
            integer nled, nfr; nled = 100; nfr = 2; if ($value$plusargs("snled=%d", nled)) ; if ($value$plusargs("snfr=%d", nfr)) ;
            w_on = 1; w_clear;
            wait (w_nframes >= nfr); #1;
            sx_ws_check(3 * nled);
            sx_monitor_report; sx_fwreport;
            if (sx_fails == 0) $display("STRESS PASS scenario 7"); else $display("STRESS FAIL scenario 7 (%0d failures)", sx_fails);
            $finish;
        end
        8: begin : s8                                       // WS2812 LED with forwarding: sender in the testbench
            integer nb, nfr, jit, gap, f, k2, bad, ex, fl; real e;
            nb = 300; nfr = 3; jit = 0; gap = 3200; e = 0.0; ws_in = 0;
            if ($value$plusargs("snb=%d", nb)) ; if ($value$plusargs("snfr=%d", nfr)) ; if ($value$plusargs("swj=%d", jit)) ;
            if ($value$plusargs("swg=%d", gap)) ; if ($value$plusargs("swe=%f", e)) ; if ($value$plusargs("swin=%d", ws_in)) ;
            x_oe[ws_in] = 1; x_val[ws_in] = 0;
            w_on = 1; w_clear;
            repeat (start) @(posedge clk);
            for (f = 0; f < nfr; f = f + 1) begin
                wsx_frame(nb, e / 100.0, jit);
                repeat (gap) @(posedge clk);
            end
            repeat (3500) @(posedge clk);
            // the forwarded stream: every frame has nb - 3 bytes, ws_pat(3 ...)
            bad = 0;
            for (f = 0; f < w_nframes && f < 64; f = f + 1) begin
                if (w_fbytes[f] != nb - 3) begin bad = bad + 1; $display("STRESS WS output frame %0d has %0d bytes, expected %0d", f, w_fbytes[f], nb - 3); end
                for (k2 = 0; k2 < nb - 3 && k2 < w_fbytes[f]; k2 = k2 + 1) if (w_b[w_fstart[f] + k2] !== ws_pat(k2 + 3)) begin
                    bad = bad + 1; if (bad < 4) $display("STRESS WS output frame %0d byte %0d is %02x, expected %02x", f, k2, w_b[w_fstart[f] + k2], ws_pat(k2 + 3)); end
            end
            $display("STRESS WS forward: input %0d frames of %0d bytes, bit time error %0f%%, jitter +-%0d cycles, gap %0d; output: %0d bits, %0d frames, %0d bytes, %0d wrong, %0d bad high times, %0d bad periods, %0d partial",
                     nfr, nb, e, jit, gap, w_bits, w_nframes, w_nbytes, bad, w_bad_h, w_bad_per, w_partial);
            $display("STRESS WS forward: T0H %0f..%0f T1H %0f..%0f period %0f..%0f extra low between bytes %0f..%0f cycles; low time between frames at the output:", w_t0h_min, w_t0h_max, w_t1h_min, w_t1h_max, w_per_min, w_per_max, w_gap_min, w_gap_max);
            for (f = 0; f < wg_n && f < 8; f = f + 1) $display("    gap %0d: %0d cycles", f, wg[f]);
            $display("STRESS WS forward: sender input gap %0d cycles; firmware: frames %0d, bytes in last frame %0d, frames with wrong count %0d, kept bytes %02x %02x %02x (expected %02x %02x %02x), overrun errors %0d",
                     gap, sx_ram16(11'h710), sx_ram16(11'h716), sx_ram(11'h733), sx_ram(11'h730), sx_ram(11'h731), sx_ram(11'h732), ws_pat(0), ws_pat(1), ws_pat(2), sx_ram(11'h715));
            if (w_nframes != nfr || bad != 0 || w_bad_h != 0 || w_partial != 0) sx_fail("forwarded stream wrong or incomplete");
            if (w_bad_per != 0) begin
                // the forward cell follows the input period; periods outside 75 +- 9 are a failure only if the input was inside
                if (0.75 * (e < 0 ? -e : e) + 2.0 * jit <= 9.0) sx_fail("forwarded bit period outside the model limits");
                else $display("STRESS WS forward: note: the input period itself is outside 75 +- 9 cycles (error %0f%% plus 2 x %0d cycles jitter), so the forwarded periods outside the limits are not counted as a failure", e, jit);
            end
            if (sx_ram16(11'h710) != nfr || sx_ram(11'h733) != 0) sx_fail("firmware frame count");
            if (sx_ram(11'h730) != ws_pat(0) || sx_ram(11'h731) != ws_pat(1) || sx_ram(11'h732) != ws_pat(2)) sx_fail("kept bytes");
            if (sx_fails == 0) $display("STRESS PASS scenario 8"); else $display("STRESS FAIL scenario 8 (%0d failures)", sx_fails);
            $finish;
        end
        3: begin : s3                                       // SPI slave (core 0, master model) + WS2812 frames (core 1)
            integer nled, f, kk, nbad; nled = 8; if ($value$plusargs("snled=%d", nled)) ;
            w_on = 1; w_clear;
            wait (sm_done >= sm_xfers); #1;
            if (!$test$plusargs("sxnows")) begin
                if (w_inframe) begin nf0 = w_nframes; wait (w_nframes != nf0); end
                sx_ws_check(3 * nled);
            end
            sx_final(!$test$plusargs("sxnows"), 1);
        end
        endcase
    end
endtask
