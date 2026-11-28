// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Model of a USB low-speed host, included in tb_sys.v. Device on pins 0 (D+) and 1 (D-).
// It sends packets with NRZI coding, bit stuffing and CRC, receives the answers of the device and
// measures the answer time. usb_test enumerates the device the way a PC does and then polls the
// interrupt endpoint.

reg h_en = 0, h_dp = 0, h_dm = 1;          // the host drives the two lines
real ubit = 400.6;                          // bit time of the host in ns (the device has 400.0)
real devbit = 400.0;
reg [7:0] htx [0:15];                       // packet to send, without the sync byte
reg [7:0] hrx [0:15];                       // received packet, without the sync byte
reg [7:0] hbuf [0:127];                     // data of a control read
reg [7:0] udesc [0:95];                     // expected descriptors: device 18, configuration 34, report 23
integer hrn, usb_err = 0, n_busrst = 0, hones, haddr = 0, n_naks = 0, n_answers = 0;
real t_eop = 0, ans_min = 99, ans_max = 0, ans;
reg hl;
// --- extra stimulus for the tests on the oscillator (all off by default) ---
integer steady_fr = 30;                     // +steady=<n>: frames of the steady state phase after the stimulus
integer wait_fr = 14;                       // +wait=<n>: frames between the end of the bus reset and the first request
integer txpos = 0;                          // +txpos=<bit times>: the poll starts this long after the keep-alive signal
integer varpkt = 0;                         // +varpkt=<bit times>: one packet for another device this long after the keep-alive signal, content changes every frame
integer varmode = 0;                        // +varmode=1: lengths alternate between the shortest and the longest
integer kskip = 0;                          // +kskip: one keep-alive signal is left out when the first frame with +varpkt starts
integer vseed = 1, vn = 0;
real jump_pct = 0;                          // +jump=<percent>: frequency of the oscillator changes at once
integer susp_ms = 0; real susp_jump = 0;    // +suspend=<ms>: no signals on the bus for this long, then resume; +suspjump=<percent> during it
reg ufq = 0;                                // quiet: failures are counted by the caller
real t_rste = 0, t_loop = 0;

task ufail(input [479:0] msg); begin usb_err = usb_err + 1; if (!ufq) $display("USB FAIL at %0t: %0s (received %0d bytes: %02x %02x %02x %02x)", $time, msg, hrn, hrx[0], hrx[1], hrx[2], hrx[3]); end endtask

task h_bit(input b); begin
    if (!b) begin hl = ~hl; hones = 0; end else hones = hones + 1;
    h_dp = hl; h_dm = ~hl; #(ubit);
    if (hones == 6) begin hl = ~hl; h_dp = hl; h_dm = ~hl; #(ubit); hones = 0; end     // stuffed bit
end endtask
task h_send(input integer n); integer i, k; begin
    h_en = 1; hl = 0; hones = 0; h_dp = 0; h_dm = 1;
    for (k = 0; k < 8; k = k + 1) h_bit(k == 7);                    // sync
    for (i = 0; i < n; i = i + 1) for (k = 0; k < 8; k = k + 1) h_bit(htx[i][k]);
    h_dp = 0; h_dm = 0; #(2 * ubit);                                // end of packet
    h_dp = 0; h_dm = 1; t_eop = $realtime; #(ubit); h_en = 0;
end endtask
// the receiver takes its sample half a bit time after the last edge on D+ and every bit time after that,
// so it follows a device whose bit time differs from the nominal one
integer hph = 0; reg hlastv = 0;
task h_next; reg done; begin
    done = 0;
    while (!done) begin
        #(devbit / 16);
        if (uio_in[0] !== hlastv) begin hph = 0; hlastv = uio_in[0]; end
        else begin hph = (hph + 1) % 16; if (hph == 8) done = 1; end
    end
end endtask
// receive a packet of the device; hrn = number of bytes, -1 if nothing came within tmo bit times
task h_recv(input integer tmo); integer t, k, nb, ones; reg prev, cur, b, se0; reg [7:0] sh; begin
    hrn = 0; t = 0; hrx[0] = 0; hrx[1] = 0; hrx[2] = 0; hrx[3] = 0;
    while (!(uio_in[0] === 1'b1 && uio_in[1] === 1'b0) && t < tmo * 8) begin #(ubit / 8); t = t + 1; end
    if (t >= tmo * 8) hrn = -1;
    else begin
        ans = ($realtime - t_eop) / devbit; n_answers = n_answers + 1;
        if (ans < ans_min) ans_min = ans;
        if (ans > ans_max) ans_max = ans;
        hph = 0; hlastv = uio_in[0]; h_next; prev = 0; nb = 0; ones = 0; se0 = 0; k = 0; sh = 0;
        while (!se0 && nb < 14) begin
            cur = uio_in[0];
            if (uio_in[0] === 1'b0 && uio_in[1] === 1'b0) se0 = 1;
            else begin
                b = (cur == prev); prev = cur;
                if (ones == 6) begin ones = 0; if (b) ufail("stuffed bit is not 0"); end
                else begin
                    ones = b ? ones + 1 : 0;
                    sh = {b, sh[7:1]}; k = k + 1;
                    if (k == 8) begin
                        k = 0;
                        if (nb == 0) begin if (sh !== 8'h80) ufail("sync byte of the device"); end else hrx[nb - 1] = sh;
                        nb = nb + 1;
                    end
                end
                h_next;
            end
        end
        if (k != 0) ufail("packet of the device does not end on a byte");
        hrn = nb - 1;
        #(3 * devbit);
    end
end endtask

function [4:0] ucrc5(input [10:0] d); integer i; reg [4:0] v; reg fb; begin
    v = 5'h1F;
    for (i = 0; i < 11; i = i + 1) begin fb = v[0] ^ d[i]; v = v >> 1; if (fb) v = v ^ 5'h14; end
    ucrc5 = ~v;
end endfunction
reg [15:0] c16;
task ucrc16_htx(input integer first, input integer n); integer i, k; reg fb; begin       // over htx[first .. first+n-1]
    c16 = 16'hFFFF;
    for (i = first; i < first + n; i = i + 1) for (k = 0; k < 8; k = k + 1) begin fb = c16[0] ^ htx[i][k]; c16 = c16 >> 1; if (fb) c16 = c16 ^ 16'hA001; end
    c16 = ~c16;
end endtask
task ucrc16_hrx(input integer n); integer i, k; reg fb; begin                           // over hrx[1 .. n], residual
    c16 = 16'hFFFF;
    for (i = 1; i <= n; i = i + 1) for (k = 0; k < 8; k = k + 1) begin fb = c16[0] ^ hrx[i][k]; c16 = c16 >> 1; if (fb) c16 = c16 ^ 16'hA001; end
end endtask

task h_token(input [7:0] pid, input [6:0] addr, input [3:0] ep, input bad); reg [10:0] f; reg [4:0] c; begin
    h_sync;
    f = {ep, addr}; c = ucrc5(f); if (bad) c = c ^ 5'h04;
    htx[0] = pid; htx[1] = f[7:0]; htx[2] = {c, f[10:8]};
    h_send(3);
end endtask
task h_data(input [7:0] pid, input integer n, input bad); begin      // data in htx[1 .. n]; follows a token after 2 bit times
    #(2 * ubit); htx[0] = pid; ucrc16_htx(1, n); if (bad) c16 = c16 ^ 16'h0100;
    htx[n + 1] = c16[7:0]; htx[n + 2] = c16[15:8];
    h_send(n + 3);
end endtask
task h_ack; begin #(2 * ubit); htx[0] = 8'hD2; h_send(1); #(4 * ubit); end endtask
real t_ka = 0;
task h_keepalive; begin hframe = hframe + 1; t_ka = $realtime; h_en = 1; h_dp = 0; h_dm = 0; #(2 * ubit); h_dm = 1; #(ubit); h_en = 0; #(6 * ubit); end endtask
// hfr = 0: a frame is 60 bit times of idle and a keep-alive signal, which shortens the simulation.
// hfr > 0 (+frame=<ns>): keep-alive signals with this period, as on a real bus; a transaction that would
// not end before the next keep-alive signal waits for it.
real hfr = 0, t_next = 0;
task h_frame; begin if ($realtime < t_next) #(t_next - $realtime); t_next = t_next + hfr; h_keepalive; end endtask
task h_sync; begin if (hfr > 0 && $realtime + 260 * ubit > t_next) h_frame; end endtask
task h_idle(input integer frames); integer i; begin for (i = 0; i < frames; i = i + 1) begin if (hfr > 0) h_frame; else begin #(60 * ubit); h_keepalive; end end end endtask
task h_reset; begin if (rstdbg && t_rst0 == 0) begin t_rst0 = $realtime; $display("RSTDBG: first bus reset starts at %0.1f us", $realtime / 1000); end hframe = 0; t_next = $realtime + 100000 + hfr; h_en = 1; h_dp = 0; h_dm = 0; #100000; h_dm = 1; t_rste = $realtime; #(4 * ubit); h_en = 0; #20000; end endtask

// SETUP stage: 8 request bytes in rq (first byte in the lowest 8 bits)
reg [63:0] rq_last;
task ctrl_setup(input [63:0] rq, input bad); integer i; begin
    rq_last = rq;
    h_token(8'h2D, haddr, 0, 0);
    for (i = 0; i < 8; i = i + 1) htx[1 + i] = rq[8 * i +: 8];
    h_data(8'hC3, 8, bad);
    h_recv(18);
    if (bad) begin if (hrn != -1) ufail("data packet with a wrong CRC-16 was answered"); end
    else if (hrn != 1 || hrx[0] !== 8'hD2) ufail("SETUP not acknowledged");
    #(4 * ubit);
end endtask
// data stage of a control read and its status stage; got = number of bytes in hbuf, -2 = STALL
integer got;
task ctrl_in(input integer wlen); integer tries, n, i; reg [7:0] tog; reg done; begin
    got = 0; tog = 8'h4B; done = 0; tries = 0;
    while (!done && tries < 400) begin
        h_token(8'h69, haddr, 0, 0); h_recv(18);
        if (hrn == 1 && hrx[0] === 8'h5A) begin n_naks = n_naks + 1; tries = tries + 1; #(30 * ubit); end
        else if (hrn == 1 && hrx[0] === 8'h1E) begin got = -2; done = 1; #(4 * ubit); end
        else if (hrn >= 3 && hrx[0] === tog) begin
            n = hrn - 3; ucrc16_hrx(hrn - 1);
            if (c16 !== 16'hB001) ufail("CRC-16 of a data packet of the device");
            for (i = 0; i < n; i = i + 1) hbuf[got + i] = hrx[1 + i];
            got = got + n; h_ack; tog = tog ^ 8'h88;
            if (n < 8 || got >= wlen) done = 1;
        end else begin ufail("answer to IN in the data stage"); done = 1; end
    end
    if (!done) begin ufail("data stage: only NAK"); $display("      request %h, wLength %0d, data received %0d", rq_last, wlen, got); end
    if (got >= 0) begin                                             // status stage: OUT with an empty DATA1
        done = 0; tries = 0;
        while (!done && tries < 50) begin
            h_token(8'hE1, haddr, 0, 0); h_data(8'h4B, 0, 0); h_recv(18);
            if (hrn == 1 && hrx[0] === 8'hD2) done = 1; else begin tries = tries + 1; #(30 * ubit); end
        end
        if (!done) ufail("status stage of a control read");
        #(4 * ubit);
    end
end endtask
// status stage of a request without data: IN, the device answers an empty DATA1
task ctrl_status; integer tries; reg done; begin
    done = 0; tries = 0;
    while (!done && tries < 400) begin
        h_token(8'h69, haddr, 0, 0); h_recv(18);
        if (hrn == 1 && hrx[0] === 8'h5A) begin n_naks = n_naks + 1; tries = tries + 1; #(30 * ubit); end
        else if (hrn == 3 && hrx[0] === 8'h4B && hrx[1] === 8'h00 && hrx[2] === 8'h00) begin h_ack; done = 1; end
        else begin ufail("status stage of a request without data"); done = 1; end
    end
    if (!done) ufail("status stage: only NAK");
end endtask
task check_desc(input integer first, input integer n, input [479:0] name); integer i, bad; begin
    bad = (got != n);
    for (i = 0; i < n && !bad; i = i + 1) if (hbuf[i] !== udesc[first + i]) bad = 1;
    if (bad) begin usb_err = usb_err + 1; $display("USB FAIL: %0s: %0d bytes, first %02x %02x %02x %02x", name, got, hbuf[0], hbuf[1], hbuf[2], hbuf[3]); end
end endtask

integer n_rep = 0, ui; reg [7:0] rtog, rlast;
// stimulus before a poll: a packet for another device (content changes), a fixed delay after the keep-alive signal
task pre_poll; integer i; reg [7:0] b; begin
    if (varpkt > 0) begin
        #(varpkt * ubit); h_sync; vn = vn + 1;
        for (i = 0; i < 8; i = i + 1) begin
            b = $random(vseed);
            if (varmode == 1) b = vn[0] ? 8'hFF : 8'h00;
            htx[1 + i] = b;
        end
        htx[1] = htx[1] | 8'h40;                   // address of another device
        h_data(8'hC3, 8, 0);
    end
    if (txpos > 0) #(txpos * ubit);
end endtask
task poll_report(input ack); begin                                  // one poll of the interrupt endpoint
    pre_poll;
    h_token(8'h69, haddr, 1, 0); h_recv(18);
    if (hrn == 1 && hrx[0] === 8'h5A) n_naks = n_naks + 1;
    else if (hrn == 11) begin
        ucrc16_hrx(10);
        if (c16 !== 16'hB001) ufail("CRC-16 of a report");
        if (hrx[0] !== rtog) ufail("data toggle of a report");
        if (hrx[1] !== rlast) ufail("report counter");
        for (ui = 1; ui < 8; ui = ui + 1) if (hrx[1 + ui] !== ((ui * 17 + rlast) & 8'hFF)) ufail("report data");
        if (ack) begin h_ack; n_rep = n_rep + 1; rtog = rtog ^ 8'h88; rlast = rlast + 1; end else #(8 * ubit);
    end else ufail("answer to IN on the interrupt endpoint");
end endtask

// poll that tolerates failures: counts the answers that are wrong or missing. A report that comes again
// because the device did not see the acknowledge is acknowledged again and not counted.
integer tol_ok = 0, tol_miss = 0, tol_bad = 0, tol_dup = 0, tol_nak = 0; reg ptol_ok, ptol_nak;
task poll_tol; integer e0, q; reg good; begin
    ptol_ok = 0; ptol_nak = 0; e0 = usb_err; ufq = 1;
    pre_poll;
    h_token(8'h69, haddr, 1, 0); h_recv(18);
    if (hrn == -1) tol_miss = tol_miss + 1;
    else if (hrn == 1 && hrx[0] === 8'h5A) begin n_naks = n_naks + 1; tol_nak = tol_nak + 1; ptol_nak = 1; end       // the report is not ready: neither right nor wrong
    else if (hrn == 11) begin
        ucrc16_hrx(10); good = (c16 === 16'hB001);
        for (q = 1; q < 8; q = q + 1) if (hrx[1 + q] !== ((q * 17 + hrx[1]) & 8'hFF)) good = 0;
        if (good && hrx[0] === rtog && hrx[1] === rlast) begin h_ack; n_rep = n_rep + 1; rtog = rtog ^ 8'h88; rlast = rlast + 1; ptol_ok = 1; tol_ok = tol_ok + 1; end
        else if (good && hrx[0] === (rtog ^ 8'h88) && hrx[1] === rlast - 1) begin h_ack; tol_dup = tol_dup + 1; end
        else begin tol_bad = tol_bad + 1; #(8 * ubit); end
    end else begin tol_bad = tol_bad + 1; #(8 * ubit); end
    usb_err = e0; ufq = 0;
end endtask

// --- reports of the sensor bridge (firmware fwsens): 6 sample bytes, time of the interrupt, status ---
reg sr_chk = 1; integer sr_idx = -1, sj; integer sr_has, sr_n = 0, sr_drop = 0, sr_err = 0, sd; reg [7:0] sr_seq, sr_last = 0, sr_ts, sr_st;
task poll_sensor; begin
    sr_has = 0;
    h_token(8'h69, haddr, 1, 0); h_recv(18);
    if (hrn == 1 && hrx[0] === 8'h5A) begin n_naks = n_naks + 1; #(4 * ubit); end
    else if (hrn == 11) begin
        ucrc16_hrx(10);
        if (c16 !== 16'hB001) ufail("CRC-16 of a sensor report");
        if (hrx[0] !== rtog) ufail("data toggle of a sensor report");
        h_ack; rtog = rtog ^ 8'h88;
        sr_has = 1; sr_seq = hrx[1]; sr_ts = hrx[7]; sr_st = hrx[8]; sr_n = sr_n + 1;
        if (sr_st[7]) sr_err = sr_err + 1;
        else begin
            for (ui = 1; ui <= 6; ui = ui + 1) if (hrx[ui] !== s_reg(ui, sr_seq)) ufail("sample bytes of a sensor report");
            // every sample is either delivered or counted as dropped
            // the report holds one of the samples read from the sensor; the samples read in between are counted
            if (sr_chk) begin
                sj = sr_idx + 1; while (sj < s_reads && s_snaps[sj] !== sr_seq) sj = sj + 1;
                if (sj >= s_reads) ufail("sensor report with a sample that was not read");
                else begin if (sr_st[6:0] != sj - sr_idx - 1) ufail("drop count of a sensor report"); sr_idx = sj; end
            end
            sr_drop = sr_drop + sr_st[6:0]; sr_last = sr_seq;
        end
    end else ufail("answer to IN on the interrupt endpoint");
end endtask
// spacing of the events in phases B and C, in ns, and frames to wait in B (+oscusb: real time, one read takes about 1 ms)
integer fr_off = -1;
integer sb_gap = 400000, sb_idle = 70, sc_gap = 90000;
task sensor_test; integer k, tries; reg [7:0] te; begin
    rtog = 8'hC3;
    poll_sensor; if (sr_has) ufail("report without an event");
    if (feat_on) begin                                                       // GET_REPORT before the first sample: eight zero bytes
        ctrl_setup(64'h0008_0000_0100_01A1, 0); ctrl_in(8);
        if (got != 8 || hbuf[0] !== 0 || hbuf[1] !== 0 || hbuf[2] !== 0 || hbuf[3] !== 0 || hbuf[4] !== 0 || hbuf[5] !== 0 || hbuf[6] !== 0 || hbuf[7] !== 0) ufail("GET_REPORT before the first sample: eight zero bytes expected");
    end
    // A: one event, then polls until the report comes. Every sample arrives, in order, with its frame count.
    for (k = 0; k < 6; k = k + 1) begin
        h_idle(1); #(k * 9 * ubit); sens_event; te = s_tevt; tries = 0; sr_has = 0;
        while (!sr_has && tries < 12) begin h_idle(1); poll_sensor; tries = tries + 1; end
        if (!sr_has) ufail("no report after an event");
        else begin
            if (sr_seq !== s_seq || sr_st !== 8'h00) ufail("report after a single event");
            sd = (sr_ts - te + 1) & 8'hFF;
            if (hfr > 0) begin                                       // +oscusb: core 0 starts counting only when the oscillator runs, so the count is behind by a fixed number of frames
                if (fr_off < 0) begin fr_off = sd; $display("SENSOR A: frame count of the device is %0d frames behind the host (core 0 counts from the start of the USB loop)", (257 - sd) & 255); end
                else if (sd - fr_off > 1 || fr_off - sd > 1) ufail("frame count of a report (offset to the host changes)");
            end else if (sd > 2) ufail("frame count of a report");
        end
    end
    $display("SENSOR A: reports %0d, I2C read %0.0f to %0.0f us after the interrupt", sr_n, s_dur_min / 1000, s_dur_max / 1000);
    // B: four events without a poll, 400 us apart. The first sample is with the USB core before the
    // second event; of the other three only the newest is kept.
    fork
        begin repeat (4) begin #(sb_gap); sens_event; end end
        h_idle(sb_idle);
    join
    k = sr_n;
    repeat (6) begin poll_sensor; h_idle(1); end
    if (sr_n - k != 2 || sr_last !== s_seq || sr_drop != 2) ufail("reports after a burst of events");
    $display("SENSOR B: events %0d, reports %0d, dropped %0d", s_seq, sr_n, sr_drop);
    // C: events every 90 us while the host polls every frame
    fork
        begin repeat (8) begin #(sc_gap); sens_event; end end
        begin repeat (32) begin h_idle(1); poll_sensor; end end
    join
    repeat (10) begin h_idle(1); poll_sensor; end
    if (sr_last !== s_seq || sr_idx != s_reads - 1 || sr_n + sr_drop != s_reads) ufail("delivered plus dropped samples");
    $display("SENSOR C: events %0d (%0d replaced in the sensor before the read), I2C reads %0d, reports %0d, dropped %0d", s_seq, s_lost, s_reads, sr_n, sr_drop);
    // D: the interrupt line is low and the sensor does not answer; the report carries the error bit
    sens_on = 0; k = sr_err; s_int_n = 0; h_idle(6); s_int_n = 1; h_idle(4); sens_on = 1;
    repeat (4) begin poll_sensor; h_idle(1); end
    if (sr_err == k) ufail("no error report for a sensor that does not answer");
    sr_chk = 0;
    sens_event; tries = 0; sr_has = 0; sr_st = 8'h80;
    while (sr_st[7] && tries < 12) begin h_idle(1); poll_sensor; tries = tries + 1; if (!sr_has) sr_st = 8'h80; end
    if (sr_st[7] || sr_seq !== s_seq) ufail("report after the sensor answers again");
    $display("SENSOR: events %0d, reports %0d (%0d with error bit), dropped %0d, I2C reads %0d", s_seq, sr_n, sr_err, sr_drop, s_reads);
    $display("SENSOR: SCL period %0.0f to %0.0f ns inside a transfer (shortest: %0.1f kHz)", s_per_min, s_per_max, 1e6 / s_per_min);
end endtask

// --- device on the internal oscillator (+oscusb, testbench built with tb/osc_model.v) ---
// frequency of the system clock over windows of 0.2 ms, after the firmware has switched the loop on
real f_t_bad = 0, t_ev = 0; real f_now = 0, f_min = 99, f_max = 0, f_t0 = 0; integer f_n = 0, f_trim0 = -1, f_tmin = 255, f_tmax = 0; reg f_on = 0;
always @(posedge top.u.clk) begin
    if (f_n == 0) f_t0 = $realtime;
    f_n = f_n + 1;
    if ($realtime - f_t0 >= 200000) begin
        f_now = (f_n - 1) * 1000.0 / ($realtime - f_t0); f_n = 0;
        if (f_on) begin if (f_now < 15.0 * 0.985 || f_now > 15.0 * 1.015) f_t_bad = $realtime; if (f_now < f_min) f_min = f_now; if (f_now > f_max) f_max = f_now; end
    end
end
integer pp_t0 = 0, pp_ev = 0, pp_n = 0; integer pp_max [0:7]; initial begin pp_max[0] = 0; pp_max[1] = 0; pp_max[2] = 0; pp_max[3] = 0; pp_max[4] = 0; pp_max[5] = 0; pp_max[6] = 0; pp_max[7] = 0; end
integer cyc_n = 0, pr_t0 = 0, pr_max = 0, pr_maxrec = 0, pr_maxlock = 0, pr_n = 0, n_lost = 0, n_recov = 0, in_rec = 0;
real t_lost = 0, t_recov = 0, t_lost_last = 0;
integer s_tmin = 256, s_tmax = 0; reg s_on = 0;                        // trim value during the suspend
always @(posedge clk) begin
    cyc_n = cyc_n + 1;
    if (io_we && io_addr == 9'h01D && f_trim0 < 0) begin f_trim0 = io_wdata; f_on <= #400000 1'b1; t_loop = $realtime; $display("OSC loop on at %0.1f ms (%0.1f ms after the end of the bus reset), trim value %0d", $realtime / 1e6, ($realtime - t_rste) / 1e6, io_wdata); end
    if (io_we && io_addr == 9'h01C) begin                               // markers of the firmware built with -DOSC_PROBE
        case (io_wdata)
            8'h01: begin n_lost = n_lost + 1; in_rec = 1; t_lost = $realtime; $display("OSC lock lost, firmware starts the recovery at %0.3f ms (trim value %0d, frame %0d)", $realtime / 1e6, top.u.osc_trim, hframe); end
            8'h02: begin n_recov = n_recov + 1; in_rec = 0; t_recov = $realtime; $display("OSC recovered, loop on again at %0.3f ms (trim value %0d, frame %0d)", $realtime / 1e6, top.u.osc_trim, hframe); end
            8'h13: begin if (pp_ev < 8 && cyc_n - pp_t0 > pp_max[pp_ev]) pp_max[pp_ev] = cyc_n - pp_t0; pp_n = pp_n + 1; end
            8'h20, 8'h21, 8'h22, 8'h23, 8'h24, 8'h25, 8'h26: begin pp_ev = io_wdata[3:0]; pp_t0 = cyc_n; end
            8'h10: pr_t0 = cyc_n;
            8'h11: begin pr_n = pr_n + 1; if (cyc_n - pr_t0 > pr_max) pr_max = cyc_n - pr_t0; if (in_rec && cyc_n - pr_t0 > pr_maxrec) pr_maxrec = cyc_n - pr_t0; if (!in_rec && cyc_n - pr_t0 > pr_maxlock) pr_maxlock = cyc_n - pr_t0; end
        endcase
    end
    if (f_on) begin if (top.u.osc_trim < f_tmin) f_tmin = top.u.osc_trim; if (top.u.osc_trim > f_tmax) f_tmax = top.u.osc_trim; end
    if (s_on) begin if (top.u.osc_trim < s_tmin) s_tmin = top.u.osc_trim; if (top.u.osc_trim > s_tmax) s_tmax = top.u.osc_trim; end
end
real dr_to = 1.0, dr_step = 0;
`ifdef OSCMODEL
always #100000 if (dr_step != 0 && top.u.osc.drift < dr_to) top.u.osc.drift = top.u.osc.drift + dr_step;
`endif

// --- stimulus on the oscillator test: jump of the frequency, suspend and resume, fixed place or varying packets ---
real ans0_min, ans0_max;
task h_skipk; begin if ($realtime < t_next) #(t_next - $realtime); t_next = t_next + hfr; hframe = hframe + 1; end endtask
task osc_stats(input [479:0] tag); begin
    $display("%0s: frequency %0.3f to %0.3f MHz (%0.2f to %0.2f %%), trim values %0d to %0d, polls ok %0d NAK %0d missing %0d bad %0d repeated %0d",
             tag, f_min, f_max, (f_min / 15.0 - 1) * 100, (f_max / 15.0 - 1) * 100, f_tmin, f_tmax, tol_ok, tol_nak, tol_miss, tol_bad, tol_dup);
end endtask
task reset_stats; begin f_min = 99; f_max = 0; f_tmin = 255; f_tmax = 0; ans_min = 99; ans_max = 0; end endtask
// poll until 10 correct answers in a row (a report, or NAK while the report is not ready); sc_first = frame of the first report, sc_ten = frame of the tenth answer
integer sc_first, sc_ten, sc_fr, sc_good, sc_rec;
task recover_polls; begin
    sc_first = -1; sc_ten = -1; sc_rec = -1; sc_fr = 0; sc_good = 0;
    while ((sc_good < 10 || n_lost != n_recov) && sc_fr < 150) begin
        h_idle(1); poll_tol; sc_fr = sc_fr + 1;
        if (ptol_ok || ptol_nak) begin sc_good = sc_good + 1; if (ptol_ok && sc_first < 0) sc_first = sc_fr; end else sc_good = 0;
        if (sc_good == 10 && sc_ten < 0) sc_ten = sc_fr;
        if (n_lost == n_recov && sc_rec < 0 && n_lost > 0) sc_rec = sc_fr;
    end
end endtask
task osc_scen; integer k; real tj, tr; begin
    ans0_min = ans_min; ans0_max = ans_max;
    if (ans_max > 6.5 || ans_min < 2.0) ufail("answer time outside 2 to 6.5 bit times");
    osc_stats("before the stimulus");
    reset_stats; tol_ok = 0; tol_miss = 0; tol_bad = 0; tol_dup = 0;
    if (jump_pct != 0) begin
`ifdef OSCMODEL
        top.u.osc.drift = top.u.osc.drift * (1.0 + jump_pct / 100.0);
`endif
        tj = $realtime; t_ev = tj;
        $display("JUMP: frequency of the oscillator %0.1f %% at %0.3f ms (frame %0d), trim value %0d", jump_pct, tj / 1e6, hframe, top.u.osc_trim);
        recover_polls;
        $display("JUMP: first correct report %0d frames after the jump, 10 correct answers in a row after %0d frames, firmware has switched the loop on again after %0d frames; polls ok %0d missing %0d bad %0d repeated %0d; lost %0d recovered %0d",
                 sc_first, sc_ten, sc_rec, tol_ok, tol_miss, tol_bad, tol_dup, n_lost, n_recov);
        osc_stats("JUMP transient");
        if (sc_ten < 0) ufail("no recovery after the jump of the frequency");
        reset_stats;
    end
    if (susp_ms > 0) begin
        $display("SUSPEND: bus idle for %0d ms from %0.3f ms (frame %0d), trim value %0d", susp_ms, $realtime / 1e6, hframe, top.u.osc_trim);
        s_tmin = 256; s_tmax = 0; s_on = 1; k = top.u.osc_trim;
        if (susp_jump != 0) begin
            #(susp_ms * 500000.0);
`ifdef OSCMODEL
            top.u.osc.drift = top.u.osc.drift * (1.0 + susp_jump / 100.0);
`endif
            #(susp_ms * 500000.0);
        end else #(susp_ms * 1000000.0);
        s_on = 0;
        $display("SUSPEND: trim value %0d at the start, %0d to %0d during, %0d at the end; frequency now %0.3f MHz (%0.2f %%); keep-alive signals missed %0d", k, s_tmin, s_tmax, top.u.osc_trim, f_now, (f_now / 15.0 - 1) * 100, susp_ms);
        if (s_tmin != k || s_tmax != k) ufail("trim value changed while there was no reference");
        h_en = 1; h_dp = 1; h_dm = 0; #1000000.0;                    // resume: K state for 1 ms, ends with the keep-alive signal
        h_keepalive; t_next = $realtime + hfr; t_ev = $realtime;
        $display("SUSPEND: resume signal ended at %0.3f ms", $realtime / 1e6);
        recover_polls;
        $display("SUSPEND: first correct report %0d frames after the resume, 10 correct answers in a row after %0d frames, loop on again after %0d frames (-1: no recovery needed); lost %0d recovered %0d, trim value %0d",
                 sc_first, sc_ten, sc_rec, n_lost, n_recov, top.u.osc_trim);
        if (sc_ten < 0) ufail("no recovery after resume");
        osc_stats("SUSPEND transient");
        reset_stats;
    end
    // steady state: 30 frames with the stimulus (fixed place or varying packets)
    if (kskip && (varpkt > 0 || txpos > 0)) h_skipk;
    tm_on = 1;
    for (k = 0; k < steady_fr; k = k + 1) begin
        poll_tol; h_idle(1);
        if (!ptol_ok && !ptol_nak) ufail("poll in the steady state after the stimulus");
    end
    tm_on = 0;
    osc_stats("STEADY");
    if (tm_n > 0) $display("STEADY: %0d accepted measurements (%0d end at a keep-alive signal, %0d at another packet end), count %0d to %0d (target 15000), mean %0.1f", tm_n, tm_k, tm_n - tm_k, tm_min, tm_max, tm_sum * 1.0 / tm_n);
    if (f_min < 15.0 * 0.985 || f_max > 15.0 * 1.015) ufail("oscillator frequency outside 1.5 %");
    if (ans_max > 6.5 || ans_min < 2.0) ufail("answer time outside 2 to 6.5 bit times (steady state)");
    if (t_ev > 0) $display("SCEN: the frequency was outside 1.5 %% for the last time %0.1f frames after the %0s", (f_t_bad > t_ev ? f_t_bad - t_ev : 0.0) / 1e6, jump_pct != 0 ? "jump" : "resume");
    $display("SCEN: lost %0d recovered %0d; time in osc_track: longest %0d clock cycles (locked: %0d, during the recovery: %0d; %0d calls); firmware answers %0d, answer time %0.1f to %0.1f bit times", n_lost, n_recov, pr_max, pr_maxlock, pr_maxrec, pr_n, n_answers, ans_min, ans_max);
end endtask

// trim counter measurements that were accepted (EV_TRIM) while tm_on: how many, and the smallest and largest count
integer tm_n = 0, tm_k = 0, tm_min = 99999, tm_max = 0; reg tm_on = 0; integer tm_sum = 0;
always @(posedge clk) if (tm_on && top.u.trim_evt) begin
    tm_n = tm_n + 1; if ($realtime - t_ka < 2000.0) tm_k = tm_k + 1; tm_sum = tm_sum + top.u.u_clock.ctl.trcnt;
    if (top.u.u_clock.ctl.trcnt < tm_min) tm_min = top.u.u_clock.ctl.trcnt;
    if (top.u.u_clock.ctl.trcnt > tm_max) tm_max = top.u.u_clock.ctl.trcnt;
end


// --- HID class requests (+feat): GET_REPORT, SET_REPORT with an OUT data stage, GET_CONFIGURATION, GET_IDLE, SET_IDLE, protocol ---
reg feat_on = 0;
reg rstdbg = 0; real t_r0en = 0, t_rst0 = 0;
always @(posedge clk) if (rstdbg && io_we && io_addr == 9'h100 && !io_host && t_r0en == 0 && io_wdata[7]) begin t_r0en = $realtime; $display("RSTDBG: receive cell 0 enabled at %0.1f us", $realtime / 1000); end

integer pwm0_wr = 0, pm_hi, pm_k, fe0;
always @(posedge clk) if (io_we && io_addr == 9'h13A) pwm0_wr = pwm0_wr + 1;      // writes to PWM0 (configuration page 0x3A)
reg [7:0] pwv [0:7];
task pwm_meas; begin pm_hi = 0; for (pm_k = 0; pm_k < 2048; pm_k = pm_k + 1) begin @(posedge top.u.clk); pm_hi = pm_hi + out_pins[5]; end end endtask
// data stage of a control write: one OUT with DATA1 and n bytes (htx[1..n]); the answer is in hrn / hrx[0]
task ctrl_wdata(input integer n, input bad); integer i; begin
    h_token(8'hE1, haddr, 0, 0);
    for (i = 0; i < n; i = i + 1) htx[1 + i] = pwv[i];                   // the token has used htx[0..2]
    h_data(8'h4B, n, bad); h_recv(18); #(4 * ubit);
end endtask
task ctrl_status_stall; begin
    h_token(8'h69, haddr, 0, 0); h_recv(18);
    if (!(hrn == 1 && hrx[0] === 8'h1E)) ufail("status stage: STALL expected");
    #(4 * ubit);
end endtask
task load_out(input [7:0] b0); integer i; begin for (i = 0; i < 8; i = i + 1) pwv[i] = (i == 0) ? b0 : b0 + i * 5; end endtask
task chk_out_readback(input [479:0] tag); integer i; begin
    h_idle(1); ctrl_setup(64'h0008_0000_0200_01A1, 0); ctrl_in(8);
    if (got != 8) begin usb_err = usb_err + 1; $display("USB FAIL: %0s: GET_REPORT output returned %0d bytes", tag, got); end
    else for (i = 0; i < 8; i = i + 1) if (hbuf[i] !== pwv[i]) begin usb_err = usb_err + 1; $display("USB FAIL: %0s: output report byte %0d is %02x, expected %02x", tag, i, hbuf[i], pwv[i]); i = 8; end
end endtask
task chk_pwm(input [7:0] v, input integer wr, input [479:0] tag); begin
    if (top.u.timers.pwm0 !== v) begin usb_err = usb_err + 1; $display("USB FAIL: %0s: PWM0 is %02x, expected %02x", tag, top.u.timers.pwm0, v); end
    if (pwm0_wr - fe0 != wr) begin usb_err = usb_err + 1; $display("USB FAIL: %0s: %0d writes to PWM0, expected %0d", tag, pwm0_wr - fe0, wr); end
end endtask
task get_val(input [63:0] rq, input [7:0] ex, input [479:0] tag); begin
    ctrl_setup(rq, 0); ctrl_in(1);
    if (got != 1 || hbuf[0] !== ex) begin usb_err = usb_err + 1; $display("USB FAIL: %0s: %0d bytes, first %02x, expected 1 byte %02x", tag, got, hbuf[0], ex); end
    h_idle(1);
end endtask
task chk_inrep; integer i, bad; reg [7:0] c; begin
    h_idle(1); ctrl_setup(64'h0008_0000_0100_01A1, 0); ctrl_in(8); bad = 0; c = hbuf[0];
    if (got != 8) bad = 1;
    else if (sens_use) begin
        // a report newer by one than the last one polled is allowed: the sensor sends a report in every frame after +jump
        if (hbuf[0] === sr_seq + 8'd1) ; else if (hbuf[0] !== sr_seq || hbuf[6] !== sr_ts || hbuf[7] !== sr_st) bad = 1;
        for (i = 1; i <= 6; i = i + 1) if (hbuf[i - 1] !== s_reg(i, hbuf[0])) bad = 1;
    end else begin
        if (c !== rlast && c !== rlast - 8'd1) bad = 1;
        for (i = 1; i < 8; i = i + 1) if (hbuf[i] !== ((i * 17 + c) & 8'hFF)) bad = 1;
    end
    if (bad) begin usb_err = usb_err + 1; $display("USB FAIL: GET_REPORT input: %0d bytes %02x %02x %02x %02x %02x %02x %02x %02x (last report seen by the host: counter %02x)", got, hbuf[0], hbuf[1], hbuf[2], hbuf[3], hbuf[4], hbuf[5], hbuf[6], hbuf[7], sens_use ? sr_seq : rlast); end
    h_idle(1);
end endtask
task feat_test; integer i; begin
    fe0 = pwm0_wr;
    $display("FEAT: HID class requests");
    chk_inrep;                                                              // 1. GET_REPORT, input report: current data, DATA1, CRC-16 (ctrl_in)
    ctrl_setup(64'h0004_0000_0100_01A1, 0); ctrl_in(4); if (got != -2) ufail("GET_REPORT with wLength 4: STALL expected"); h_idle(1);
    ctrl_setup(64'h0008_0000_0300_01A1, 0); ctrl_in(8); if (got != -2) ufail("GET_REPORT with type 3: STALL expected"); h_idle(1);
    // 2. SET_REPORT
    load_out(8'hA5);
    ctrl_setup(64'h0008_0000_0200_0921, 0); ctrl_wdata(8, 0);
    if (!(hrn == 1 && hrx[0] === 8'hD2)) ufail("SET_REPORT: data packet not acknowledged");
    ctrl_status; h_idle(1);
    chk_pwm(8'hA5, 1, "SET_REPORT");
    pwm_meas; if (pm_hi != 8 * 8'hA5) begin usb_err = usb_err + 1; $display("USB FAIL: PWM pin high %0d cycles in 2048, expected %0d", pm_hi, 8 * 8'hA5); end
    chk_out_readback("SET_REPORT");
    // 3. the acknowledge is lost: the host sends the same data packet again; it is acknowledged again and applied once
    load_out(8'h3C);
    ctrl_setup(64'h0008_0000_0200_0921, 0); ctrl_wdata(8, 0);
    if (!(hrn == 1 && hrx[0] === 8'hD2)) ufail("SET_REPORT 2: data packet not acknowledged");
    ctrl_wdata(8, 0);                                                       // repeat: the host did not see the ACK
    if (!(hrn == 1 && hrx[0] === 8'hD2)) ufail("repeated OUT data packet not acknowledged again");
    ctrl_status; h_idle(1);
    chk_pwm(8'h3C, 2, "repeated OUT data packet (applied twice?)");
    chk_out_readback("repeated OUT");
    // 4. wrong CRC-16 in the OUT data packet: no answer, nothing applied; the correct packet after it is taken
    load_out(8'h77);
    ctrl_setup(64'h0008_0000_0200_0921, 0); ctrl_wdata(8, 1);
    if (hrn != -1) ufail("OUT data packet with a wrong CRC-16 was answered");
    chk_pwm(8'h3C, 2, "after OUT with wrong CRC-16");
    ctrl_wdata(8, 0);
    if (!(hrn == 1 && hrx[0] === 8'hD2)) ufail("OUT data packet after a bad one not acknowledged");
    ctrl_status; h_idle(1);
    chk_pwm(8'h77, 3, "after OUT with wrong CRC-16 and its repeat");
    chk_out_readback("OUT with wrong CRC-16");
    // 5. SET_REPORT with wLength 4 is refused: status stage STALL, nothing stored or applied
    ctrl_setup(64'h0004_0000_0200_0921, 0);
    for (i = 0; i < 4; i = i + 1) pwv[i] = 8'hEE;
    ctrl_wdata(4, 0); ctrl_status_stall; h_idle(1);
    chk_pwm(8'h77, 3, "refused SET_REPORT");
    load_out(8'h77); chk_out_readback("refused SET_REPORT");
    // 6. the other requests
    get_val(64'h0001_0000_0000_0880, 8'h01, "GET_CONFIGURATION");
    get_val(64'h0001_0000_0000_02A1, 8'h00, "GET_IDLE");
    ctrl_setup(64'h0000_0000_0500_0A21, 0); ctrl_status_stall; h_idle(1);   // idle rate 5: not supported
    get_val(64'h0001_0000_0000_02A1, 8'h00, "GET_IDLE after SET_IDLE 5");
    get_val(64'h0001_0000_0000_03A1, 8'h01, "GET_PROTOCOL");
    ctrl_setup(64'h0000_0000_0000_0B21, 0); ctrl_status; h_idle(1);
    get_val(64'h0001_0000_0000_03A1, 8'h00, "GET_PROTOCOL after SET_PROTOCOL 0");
    ctrl_setup(64'h0000_0000_0001_0B21, 0); ctrl_status; h_idle(1);
    get_val(64'h0001_0000_0000_03A1, 8'h01, "GET_PROTOCOL after SET_PROTOCOL 1");
    ctrl_setup(64'h0000_0000_0002_0B21, 0); ctrl_status_stall; h_idle(1);   // protocol 2 does not exist
    $display("FEAT: done, PWM0 written %0d times", pwm0_wr - fe0);
end endtask

// --- endpoint 0 robustness (+ep0): SETUP in the middle of a transfer, lengths that are multiples of 8, STALL ---
reg ep0_on = 0, zlp_probe = 0;
// np data packets of a control read, each acknowledged (the last one not if noack); no status stage
task ctrl_in_part(input integer np, input noack); integer k; reg [7:0] tg; begin
    tg = 8'h4B;
    for (k = 0; k < np; k = k + 1) begin
        h_token(8'h69, haddr, 0, 0); h_recv(18);
        if (hrn >= 3 && hrx[0] === tg) begin if (!(noack && k == np - 1)) h_ack; else #(8 * ubit); tg = tg ^ 8'h88; end
        else ufail("packet of a control read that is cut off");
    end
end endtask
task ctrl_expect_stall; begin
    h_token(8'h69, haddr, 0, 0); h_recv(18);
    if (!(hrn == 1 && hrx[0] === 8'h1E)) ufail("STALL expected");
    #(4 * ubit);
end endtask
// control read of wl bytes, then an IN token before the status stage: the device must have nothing more to send (NAK)
task ctrl_in_exact(input [63:0] rq, input integer wl, input integer first, input [479:0] name); begin
    ctrl_setup(rq, 0); ctrl_in(wl);
    check_desc(first, wl, name);
end endtask
task ctrl_in_nozlp(input [63:0] rq, input integer wl, input integer first, input [479:0] name); integer i, k; reg [7:0] tg; begin
    // like ctrl_in without the status stage, then one more IN: NAK expected (no zero-length packet)
    ctrl_setup(rq, 0); got = 0; tg = 8'h4B;
    for (k = 0; k < wl / 8; k = k + 1) begin
        h_token(8'h69, haddr, 0, 0); h_recv(18);
        if (hrn == 11 && hrx[0] === tg) begin for (i = 0; i < 8; i = i + 1) hbuf[got + i] = hrx[1 + i]; got = got + 8; h_ack; tg = tg ^ 8'h88; end
        else ufail("data packet of the control read");
    end
    check_desc(first, wl, name);
    h_token(8'h69, haddr, 0, 0); h_recv(18);
    if (!(hrn == 1 && hrx[0] === 8'h5A)) ufail("more data after a control read that is complete: NAK expected");
    #(4 * ubit);
    h_token(8'hE1, haddr, 0, 0); h_data(8'h4B, 0, 0); h_recv(18); if (!(hrn == 1 && hrx[0] === 8'hD2)) ufail("status stage of a control read");
    #(4 * ubit); h_idle(1);
end endtask
task ep0_test; integer i, w0; begin
    $display("EP0: robustness of endpoint 0");
    fe0 = pwm0_wr; w0 = n_naks;
    // 1. a SETUP in the middle of a control read restarts the transfer
    ctrl_setup(64'h00FF_0000_0200_0680, 0); ctrl_in_part(2, 0);
    ctrl_setup(64'h0012_0000_0100_0680, 0); ctrl_in(18); check_desc(0, 18, "device descriptor after a transfer that was cut off");
    h_idle(1);
    ctrl_setup(64'h00FF_0000_0200_0680, 0); ctrl_in_part(1, 1);               // the last packet was not acknowledged: the host gives up
    ctrl_setup(64'h0017_0000_2200_0681, 0); ctrl_in(23); check_desc(52, 23, "report descriptor after a packet without acknowledge");
    h_idle(1);
    ctrl_setup(64'h00FF_0000_0200_0680, 0); ctrl_in_part(5, 0);                // all data taken, the status stage is replaced by a new SETUP
    ctrl_setup(64'h0002_0000_0000_0080, 0); ctrl_in(2); if (got != 2) ufail("GET_STATUS after a transfer without status stage");
    h_idle(1);
    ctrl_setup(64'h0012_0000_0100_0680, 0); ctrl_setup(64'h0012_0000_0100_0680, 0);   // the same SETUP twice (ACK lost)
    ctrl_in(18); check_desc(0, 18, "device descriptor after a repeated SETUP");
    h_idle(1);
    if (feat_on || 1) begin                                                      // SET_REPORT interrupted before its data stage: nothing applied
        ctrl_setup(64'h0008_0000_0200_0921, 0);
        ctrl_setup(64'h0002_0000_0000_0080, 0); ctrl_in(2); if (got != 2) ufail("GET_STATUS after an interrupted SET_REPORT");
        if (feat_on) chk_pwm(8'h77, 0, "interrupted SET_REPORT");
        h_idle(1);
    end
    // 2. multiples of 8, host asks for less: no zero-length packet
    ctrl_in_nozlp(64'h0008_0000_0100_0680, 8, 0, "device descriptor, 8 bytes");
    ctrl_in_nozlp(64'h0010_0000_0100_0680, 16, 0, "device descriptor, 16 bytes");
    ctrl_in_nozlp(64'h0010_0000_0200_0680, 16, 18, "configuration descriptor, 16 bytes");
    ctrl_in_nozlp(64'h0018_0000_0200_0680, 24, 18, "configuration descriptor, 24 bytes");
    ctrl_in_nozlp(64'h0020_0000_0200_0680, 32, 18, "configuration descriptor, 32 bytes");
    ctrl_in_nozlp(64'h0010_0000_2200_0681, 16, 52, "report descriptor, 16 bytes");
    // 3. data length a multiple of 8 and the host asks for more: a zero-length packet closes the transfer
    //    (none of the descriptors has such a length; GET_REPORT returns 8 bytes)
    if (feat_on) begin
        ctrl_setup(64'h0010_0000_0100_01A1, 0); ctrl_in(16);
        if (got != 8) ufail("GET_REPORT with wLength 16: 8 bytes and a zero-length packet expected");
        h_idle(1);
        ctrl_setup(64'h0040_0000_0200_01A1, 0); ctrl_in(64);
        if (got != 8) ufail("GET_REPORT (output) with wLength 64: 8 bytes and a zero-length packet expected");
        h_idle(1);
    end
    // 4. STALL stays until the next SETUP; a SETUP with a wrong CRC does not clear it
    ctrl_setup(64'h00FF_0000_0300_0680, 0); ctrl_expect_stall; ctrl_expect_stall;
    ctrl_setup(64'h0002_0000_0000_0080, 1);
    ctrl_expect_stall;
    ctrl_setup(64'h0000_0000_0000_7740, 0); ctrl_expect_stall; h_idle(1);        // vendor request that does not exist: STALL
    ctrl_setup(64'h0002_0000_0000_0080, 0); ctrl_in(2); if (got != 2) ufail("GET_STATUS after STALL");
    h_idle(1);
    ctrl_setup(64'h0012_0000_0100_0680, 0); ctrl_in(18); check_desc(0, 18, "device descriptor after STALL");
    $display("EP0: done, NAK %0d", n_naks - w0);
end endtask

// frequency step of the oscillator while the sensor bridge reads events in every frame (tracking runs on core 1)
reg sj_ok; integer sj_k, sj_good, sj_first, sj_ten, sj_bad;
task poll_sensor_tol; integer e0; begin
    e0 = usb_err; ufq = 1; sr_chk = 0; poll_sensor; sj_ok = (usb_err == e0); usb_err = e0; ufq = 0;
end endtask
task sensor_jump; begin
    reset_stats; sj_good = 0; sj_first = -1; sj_ten = -1; sj_bad = 0;
`ifdef OSCMODEL
    top.u.osc.drift = top.u.osc.drift * (1.0 + jump_pct / 100.0);
`endif
    t_ev = $realtime;
    $display("JUMP: frequency of the oscillator %0.1f %% at %0.3f ms (frame %0d), trim value %0d, sensor event in every frame", jump_pct, $realtime / 1e6, hframe, top.u.osc_trim);
    for (sj_k = 0; sj_k < 60; sj_k = sj_k + 1) begin
        sens_event; h_idle(1); poll_sensor_tol;
        if (sj_ok && sr_has) begin sj_good = sj_good + 1; if (sj_first < 0) sj_first = sj_k + 1; end else if (!sj_ok) begin sj_good = 0; sj_bad = sj_bad + 1; end
        if (sj_good == 10 && sj_ten < 0) sj_ten = sj_k + 1;
    end
    $display("JUMP: first correct report after %0d frames, 10 correct reports in a row after %0d frames, %0d wrong or missing answers; lost %0d recovered %0d; frequency was outside 1.5 %% for the last time %0.1f frames after the jump",
             sj_first, sj_ten, sj_bad, n_lost, n_recov, (f_t_bad > t_ev ? f_t_bad - t_ev : 0.0) / 1e6);
    if (sj_ten < 0) ufail("no recovery after the jump of the frequency (sensor bridge)");
    reset_stats;
    for (sj_k = 0; sj_k < 20; sj_k = sj_k + 1) begin sens_event; h_idle(1); poll_sensor_tol; if (!sj_ok) ufail("sensor poll after the recovery"); end
    osc_stats("JUMP after the recovery");
    
    if (f_min < 15.0 * 0.985 || f_max > 15.0 * 1.015) ufail("oscillator frequency outside 1.5 % after the recovery");
end endtask

task usb_test; begin
    if ($test$plusargs("ep0")) ep0_on = 1;
    if ($test$plusargs("rstdbg")) rstdbg = 1;
    if ($test$plusargs("feat")) feat_on = 1;
    if ($test$plusargs("oscusb")) begin ubit = 667.67; devbit = 666.667; hfr = 1000000; sb_gap = 1500000; sb_idle = 10; sc_gap = 300000; end
    if ($value$plusargs("sbgap=%d", sb_gap)) ;
    if ($value$plusargs("scgap=%d", sc_gap)) ;
    $readmemh("build/usb_desc.hex", udesc);
    #30000;
    if ($test$plusargs("kskip")) kskip = 1;
    if ($value$plusargs("steady=%d", steady_fr)) ;
    if ($value$plusargs("wait=%d", wait_fr)) ;
    if ($value$plusargs("txpos=%d", txpos)) ;
    if ($value$plusargs("varpkt=%d", varpkt)) ;
    if ($value$plusargs("varmode=%d", varmode)) ;
    if ($value$plusargs("jump=%f", jump_pct)) ;
    if ($value$plusargs("suspend=%d", susp_ms)) ;
    if ($value$plusargs("suspjump=%f", susp_jump)) ;
    h_reset;
    if (hfr > 0 && wait_fr < 2) h_idle(wait_fr);
    else h_idle(2);
    if (hfr > 0 && wait_fr >= 2) begin h_idle(wait_fr - 2); if (f_trim0 < 0) ufail("the firmware did not switch the trim loop on within the wait before the first request"); end
    if ($test$plusargs("startonly")) begin       // only the start: report when the loop was switched on and the frequency after it
        h_idle(8);
        $display("START: loop on %0.1f ms after the end of the bus reset (0 = not yet), trim value %0d, frequency %0.3f to %0.3f MHz (%0.2f to %0.2f %%), trim values %0d to %0d",
                 f_trim0 < 0 ? 0.0 : (t_loop - t_rste) / 1e6, f_trim0, f_min, f_max, (f_min / 15.0 - 1) * 100, (f_max / 15.0 - 1) * 100, f_tmin, f_tmax);
        $finish;
    end
    if (!$test$plusargs("quick")) begin                                // +quick: only the requests that are needed
    $display("BUSRST: device has seen %0d bus reset(s) after the first one", n_busrst);
    // first contact at address 0: the first 64 bytes of the device descriptor
    ctrl_setup(64'h0040_0000_0100_0680, 0); ctrl_in(64); check_desc(0, 18, "device descriptor at address 0");
    h_reset; h_idle(1);
    $display("BUSRST: device has seen %0d bus reset(s) after the second one", n_busrst);
    if ($test$plusargs("rstonly")) $finish;
    ctrl_setup(64'h0000_0000_0005_0500, 0); ctrl_status; haddr = 5; h_idle(1);            // SET_ADDRESS 5
    ctrl_setup(64'h0012_0000_0100_0680, 0); ctrl_in(18); check_desc(0, 18, "device descriptor");
    ctrl_setup(64'h0008_0000_0100_0680, 0); ctrl_in(8); check_desc(0, 8, "first 8 bytes of the device descriptor");
    ctrl_setup(64'h0009_0000_0200_0680, 0); ctrl_in(9); check_desc(18, 9, "configuration descriptor, 9 bytes");
    h_idle(1);
    ctrl_setup(64'h00FF_0000_0200_0680, 0); ctrl_in(255); check_desc(18, 34, "configuration descriptor");
    ctrl_setup(64'h00FF_0000_0300_0680, 0); ctrl_in(255); if (got != -2) ufail("string descriptor: STALL expected");
    ctrl_setup(64'h0002_0000_0000_0080, 0); ctrl_in(2); if (got != 2 || hbuf[0] !== 8'h00 || hbuf[1] !== 8'h00) ufail("GET_STATUS");
    end
    // faults: wrong CRC-16 in the request, wrong CRC5 in a token, another address
    ctrl_setup(64'h0000_0000_0001_0900, 1);
    h_token(8'h69, haddr, 0, 1); h_recv(18); if (hrn != -1) ufail("token with a wrong CRC5 was answered");
    h_token(8'h69, 7'd6, 0, 0); h_recv(18); if (hrn != -1) ufail("token for another address was answered");
    h_token(8'h69, haddr, 1, 0); h_recv(18); if (!(hrn == 1 && hrx[0] === 8'h5A)) ufail("interrupt endpoint before the configuration: NAK expected");
    if (feat_on) get_val(64'h0001_0000_0000_0880, 8'h00, "GET_CONFIGURATION before SET_CONFIGURATION");
    ctrl_setup(64'h0000_0000_0001_0900, 0); ctrl_status;                                  // SET_CONFIGURATION 1
    ctrl_setup(64'h0000_0000_0000_0A21, 0); ctrl_status;                                  // HID SET_IDLE
    ctrl_setup(64'h0055_0000_2200_0681, 0); ctrl_in(85); check_desc(52, 23, "report descriptor");
    // interrupt endpoint: reports with a counter; one report is not acknowledged and must come again
    if (hfr > 0 && !$test$plusargs("nodrift")) begin dr_to = 1.03; dr_step = 0.00003; end           // the oscillator becomes 3 % faster within 10 ms
    if (sens_use) begin sensor_test; if (hfr > 0 && jump_pct != 0) sensor_jump; end else begin
    rtog = 8'hC3; rlast = 0;
    for (ui = 0; ui < 40 && n_rep < 3; ui = ui + 0) begin poll_report(1); h_idle(1); ui = ui + 1; end
    poll_report(0); h_idle(1);
    while (n_rep < 8 && ui < 80) begin poll_report(1); h_idle(1); ui = ui + 1; end
    if (n_rep != 8) ufail("eight reports");
    if (hfr > 0 && (jump_pct != 0 || susp_ms > 0 || varpkt > 0 || txpos > 0)) osc_scen;
    end
    if (feat_on) feat_test;
    if (ep0_on) ep0_test;
    if (n_busrst != (hfr > 0 ? 1 : 2) && !$test$plusargs("quick")) begin ufail("two bus resets seen by the device"); $display("      bus resets seen: %0d", n_busrst); end
    $display("USB answers %0d, answer time %0.1f to %0.1f bit times, NAK %0d, reports %0d", n_answers, ans_min, ans_max, n_naks, n_rep);
    if (ans_max > 6.5 || ans_min < 2.0) ufail("answer time outside 2 to 6.5 bit times");
    if (hfr > 0) begin
        $display("OSC frequency after the loop was switched on: %0.3f to %0.3f MHz (%0.2f to %0.2f %%), trim value %0d to %0d", f_min, f_max, (f_min / 15.0 - 1) * 100, (f_max / 15.0 - 1) * 100, f_tmin, f_tmax);
        if (f_min < 15.0 * 0.985 || f_max > 15.0 * 1.015) ufail("oscillator frequency outside 1.5 %");
    end
    if (pp_n > 0) $display("PASS TIME: %0d passes of the main loop between two calls of usb_poll; longest in clock cycles by event: none %0d, keep-alive %0d, SETUP %0d, OUT %0d, NAK %0d, IN0 %0d, IN1 %0d", pp_n, pp_max[0], pp_max[1], pp_max[2], pp_max[3], pp_max[4], pp_max[5], pp_max[6]);
    if (usb_err == 0) $display("USB PASS"); else $display("USB errors %0d", usb_err);
    $finish;
end endtask
