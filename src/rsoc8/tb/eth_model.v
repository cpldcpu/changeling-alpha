// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Independent 10BASE-T model, included in tb_sys.v (the old generator behind +eth= is unchanged).
//
//   Transmitter: drives input pin 1 (em_on / em_pin). Sends complete frames: preamble 7 x 0x55, SFD 0xD5, the
//   bytes of the frame, the FCS (computed here with the CRC-32 definition: MSB-first division by the generator
//   polynomial, remainder complemented, x^31 coefficient first) and the idle pulse TP_IDL.
//   Receiver: watches the output pin 0 of the chip (TD+), pin 2 as TD- with +ethdiff. Decodes by the edge
//   times only (a mid-bit edge is one whose distance from the last mid-bit edge is 0.75 to 1.25 bit times),
//   checks preamble, SFD, byte alignment, FCS, idle pulse, bit time, level durations, gap between frames.
//
// Time: the testbench clock has a period of 10 ns, which stands for one chip clock cycle (16.7 ns). A bit is
// 6 cycles = 60 ns in this time scale; 100 ns real = 6 cycles. All reports are in clock cycles.
//
// Plusargs:
//   +ethm=<n>      1 ARP, ping of several lengths, frames to be ignored; 2 the same with the longest frames;
//                  3 link pulses between frames; 4 short check (ARP twice, 3 pings); 5 shortest check for tolerance sweeps (ARP, 1 ping)
//   +ethppm=<n>    bit time error of the transmitter in ppm (signed; + is a longer bit)
//   +ethjit=<ps>   peak random jitter of every transmitted edge, in ps of the testbench time scale
//   +ethseed=<n>   seed of the jitter generator
//   +ethidl=<c>    high time of TP_IDL after the last bit cell, in clock cycles (default 12 = 2 bit times)
//   +ethidlmin=<c> smallest high time of the final level of a frame of the chip that is accepted (default 12)
//   +ethboot=<c>   wait before the first frame (default 6000)
//   +ethgap=<c>    pause of the transmitter between its frames and the end of the previous frame (default 700)
//   +ethnlp=<c>    link pulse generator with this interval in clock cycles (default off; 16 ms is 960000 cycles)
//   +ethnlpforce   send link pulses also while the model sends a frame (a fault: the frame is damaged)
//   +ethdiff       the chip frame is the difference TD+ (pin 0) minus TD- (pin 2)
//   +ethmax=<n>    largest frame in test 2, in bytes without FCS
//   +ethshort      test 1 without the largest standard frame
//   +ethverbose    print every frame
// The model prints ETHM PASS or ETHM FAIL <n> at the end.
integer em_force = 0;
reg em_on = 0, em_pin = 0, em_mon = 0, em_txbusy = 0;
integer em_ppm = 0, em_jit = 0, em_idl = 12, em_idlmin = 12, em_seed = 1, em_diff = 0, em_test = 0, em_gap = 700;
integer em_nlpint = 0, em_max = 1916, em_verbose = 0, em_err = 0;
real em_bt = 60.0;                                   // nominal bit time in ns of the testbench time scale
reg [47:0] em_cmac = 48'h02C0FFEE0001;               // address of the chip (the firmware has the same)
reg [31:0] em_cip  = {8'd192, 8'd168, 8'd4, 8'd2};
reg [47:0] em_hmac = 48'h020A0B0C0D0E;               // the model as host
reg [31:0] em_hip  = {8'd192, 8'd168, 8'd4, 8'd1};
reg [47:0] em_bcast = 48'hFFFFFFFFFFFF;

reg [7:0] emt [0:4095]; integer emt_n = 0;           // frame to send, without FCS
reg [7:0] emr [0:4095]; integer emr_n = 0;           // frame received from the chip, with FCS
reg [7:0] eme [0:4095]; integer eme_n = 0;           // frame expected from the chip, without FCS
reg [7:0] em_fcsb [0:3];
integer em_exp = 0;

function [7:0] em_getb(input integer which, input integer i);
    em_getb = (which == 0) ? emt[i] : (which == 1) ? emr[i] : eme[i];
endfunction

// ---------------------------------------------------------------- CRC-32 from the definition
// IEEE 802.3: the first 32 bits are complemented, the message is multiplied by x^32 and divided by the generator,
// the remainder is complemented. The shift register form below starts with all ones, which is the same thing.
// The bits of a byte come least significant bit first, the FCS goes out with the x^31 coefficient first.
task em_fcs(input integer which, input integer n);
    reg [31:0] r, f; reg [7:0] b, tb_; reg fb; integer i, k, j;
    begin
        r = 32'hFFFFFFFF;
        for (i = 0; i < n; i = i + 1) begin
            b = em_getb(which, i);
            for (k = 0; k < 8; k = k + 1) begin
                fb = r[31] ^ b[k]; r = {r[30:0], 1'b0}; if (fb) r = r ^ 32'h04C11DB7;
            end
        end
        f = ~r;
        for (j = 0; j < 4; j = j + 1) begin
            for (k = 0; k < 8; k = k + 1) tb_[k] = f[31 - (8 * j + k)];
            em_fcsb[j] = tb_;
        end
    end
endtask

// ones' complement sum of len bytes (big endian words, odd last byte padded with zero), not inverted
reg [15:0] em_cs;
task em_csum(input integer which, input integer start, input integer len);
    integer i, s;
    begin
        s = 0;
        for (i = 0; i < len; i = i + 2) s = s + em_getb(which, start + i) * 256 + ((i + 1 < len) ? em_getb(which, start + i + 1) : 0);
        while (s > 65535) s = (s & 65535) + (s >> 16);
        em_cs = s;
    end
endtask

// ---------------------------------------------------------------- frame builders
task emb(input integer which, input [7:0] v);
    begin
        if (which == 0) begin emt[emt_n] = v; emt_n = emt_n + 1; end
        else begin eme[eme_n] = v; eme_n = eme_n + 1; end
    end
endtask
task ew(input integer which, input [15:0] v); begin emb(which, v[15:8]); emb(which, v[7:0]); end endtask
task em6(input integer which, input [47:0] v); begin ew(which, v[47:32]); ew(which, v[31:16]); ew(which, v[15:0]); end endtask
task em4(input integer which, input [31:0] v); begin ew(which, v[31:16]); ew(which, v[15:0]); end endtask
task empad(input integer which, input integer n);
    begin
        if (which == 0) while (emt_n < n) begin emt[emt_n] = 0; emt_n = emt_n + 1; end
        else while (eme_n < n) begin eme[eme_n] = 0; eme_n = eme_n + 1; end
    end
endtask
function [7:0] em_pat(input integer i, input integer seed);
    em_pat = (i * 37 + seed * 11 + (i >> 3) * 5 + 3) & 255;
endfunction

// ARP request from sha/spa asking for tpa
task em_arp_req(input [47:0] dmac, input [47:0] sha, input [31:0] spa, input [31:0] tpa);
    begin
        emt_n = 0; eme_n = 0;
        em6(0, dmac); em6(0, sha); ew(0, 16'h0806);
        ew(0, 16'h0001); ew(0, 16'h0800); emb(0, 6); emb(0, 4); ew(0, 16'h0001); em6(0, sha); em4(0, spa); em6(0, 48'd0); em4(0, tpa);
        empad(0, 60);
        em_exp = (tpa == em_cip) && (dmac == em_cmac || dmac == em_bcast);
        if (em_exp) begin
            em6(1, sha); em6(1, em_cmac); ew(1, 16'h0806);
            ew(1, 16'h0001); ew(1, 16'h0800); emb(1, 6); emb(1, 4); ew(1, 16'h0002); em6(1, em_cmac); em4(1, em_cip); em6(1, sha); em4(1, spa);
            empad(1, 60);
        end
    end
endtask

// ICMP echo request with L bytes of data; badip / badicmp flip a bit of the checksum
task em_echo(input [47:0] dmac, input [31:0] dip, input integer L, input [15:0] id, input [15:0] sq, input integer seed,
             input integer badip, input integer badicmp);
    integer i, tot; reg [15:0] c;
    begin
        emt_n = 0; eme_n = 0; tot = 28 + L;
        em6(0, dmac); em6(0, em_hmac); ew(0, 16'h0800);
        emb(0, 8'h45); emb(0, 8'h00); ew(0, tot); ew(0, 16'h1234); ew(0, 16'h0000); emb(0, 8'h80); emb(0, 8'h01); ew(0, 16'h0000);
        em4(0, em_hip); em4(0, dip);
        em_csum(0, 14, 20); c = ~em_cs; if (badip) c = c ^ 16'h0100; emt[24] = c[15:8]; emt[25] = c[7:0];
        emb(0, 8'h08); emb(0, 8'h00); ew(0, 16'h0000); ew(0, id); ew(0, sq);
        for (i = 0; i < L; i = i + 1) emb(0, em_pat(i, seed));
        em_csum(0, 34, 8 + L); c = ~em_cs; if (badicmp) c = c ^ 16'h0001; emt[36] = c[15:8]; emt[37] = c[7:0];
        empad(0, 60);
        em_exp = (dmac == em_cmac) && (dip == em_cip) && !badip && !badicmp;
        if (em_exp) begin
            em6(1, em_hmac); em6(1, em_cmac); ew(1, 16'h0800);
            emb(1, 8'h45); emb(1, 8'h00); ew(1, tot); ew(1, 16'h0000); ew(1, 16'h4000); emb(1, 8'h40); emb(1, 8'h01); ew(1, 16'h0000);
            em4(1, em_cip); em4(1, em_hip);
            em_csum(2, 14, 20); c = ~em_cs; eme[24] = c[15:8]; eme[25] = c[7:0];
            emb(1, 8'h00); emb(1, 8'h00); ew(1, 16'h0000); ew(1, id); ew(1, sq);
            for (i = 0; i < L; i = i + 1) emb(1, em_pat(i, seed));
            em_csum(2, 34, 8 + L); c = ~em_cs; eme[36] = c[15:8]; eme[37] = c[7:0];
            empad(1, 60);
        end
    end
endtask

// ---------------------------------------------------------------- transmitter
reg em_bits [0:20000]; integer em_nb = 0;
real em_et [0:40000]; reg em_el [0:40000]; integer em_ne = 0;
real em_tx_end = -1.0e9, em_tx_start = 0;
integer em_lastseed = 1, em_ntx = 0;
real em_rnd;
function real em_jitter(input integer dummy);       // uniform in -em_jit .. +em_jit ps, result in ns
    integer r;
    begin
        r = $random(em_lastseed); if (r < 0) r = -r;
        em_jitter = ((r % 20001) - 10000) / 10000.0 * em_jit / 1000.0;
    end
endfunction
task em_pushbyte(input [7:0] v); integer k; begin for (k = 0; k < 8; k = k + 1) begin em_bits[em_nb] = v[k]; em_nb = em_nb + 1; end end endtask

// flip >= 0: invert that bit of the data after the FCS was computed (bit counting from the first byte of the frame)
task em_send(input integer flip);
    integer i, k; real bt, h, t0, t, tp; reg lvl, prev;
    begin
        em_fcs(0, emt_n);
        em_nb = 0;
        for (i = 0; i < 7; i = i + 1) em_pushbyte(8'h55);
        em_pushbyte(8'hD5);
        for (i = 0; i < emt_n; i = i + 1) em_pushbyte(emt[i]);
        for (i = 0; i < 4; i = i + 1) em_pushbyte(em_fcsb[i]);
        if (flip >= 0) em_bits[64 + flip] = ~em_bits[64 + flip];
        bt = em_bt * (1.0 + em_ppm / 1.0e6); h = bt / 2.0;
        em_lastseed = em_seed + em_ntx; em_ntx = em_ntx + 1;
        // edge list
        em_ne = 0; prev = 0; tp = 0;
        for (k = 0; k < 2 * em_nb; k = k + 1) begin
            lvl = (k % 2 == 0) ? ~em_bits[k / 2] : em_bits[k / 2];
            if (lvl != prev) begin
                t = k * h; if (em_jit != 0) t = t + em_jitter(0);
                if (t <= tp + 0.05) t = tp + 0.05;
                em_et[em_ne] = t; em_el[em_ne] = lvl; em_ne = em_ne + 1; prev = lvl; tp = t;
            end
        end
        // idle pulse: high for em_idl cycles behind the last bit cell
        t = 2 * em_nb * h;
        if (!prev) begin t = t + (em_jit != 0 ? em_jitter(0) : 0.0); if (t <= tp + 0.05) t = tp + 0.05; em_et[em_ne] = t; em_el[em_ne] = 1; em_ne = em_ne + 1; tp = t; end
        t = 2 * em_nb * h + em_idl * 10.0; if (em_jit != 0) t = t + em_jitter(0);
        if (t <= tp + 0.05) t = tp + 0.05;
        em_et[em_ne] = t; em_el[em_ne] = 0; em_ne = em_ne + 1;
        // play
        em_txbusy = 1; em_on = 1; t0 = $realtime; em_tx_start = t0;
        for (k = 0; k < em_ne; k = k + 1) begin
            if (t0 + em_et[k] > $realtime) #(t0 + em_et[k] - $realtime);
            em_pin = em_el[k];
        end
        em_tx_end = $realtime; em_txbusy = 0;
    end
endtask

// one link pulse, w cycles high
integer em_nlp_tx = 0;
task em_nlp(input integer w); begin em_txbusy = 1; em_on = 1; em_pin = 1; #(w * 10.0); em_pin = 0; em_txbusy = 0; em_nlp_tx = em_nlp_tx + 1; end endtask
// background generator
always begin : nlpgen
    #1;
    if (em_nlpint > 0 && em_mon) begin
        repeat (em_nlpint) @(posedge clk_x);
        while (em_txbusy && !em_force) @(posedge clk_x);
        em_nlp(6);
    end else #100;
end

// ---------------------------------------------------------------- receiver of the chip's output
wire em_td_p = uio_oe[0] ? uio_out[0] : 1'b0;
wire em_td_m = uio_oe[2] ? uio_out[2] : 1'b0;
wire em_line = em_diff ? (em_td_p & ~em_td_m) : em_td_p;
real rm_t [0:40000]; reg rm_l [0:40000]; integer rm_n = 0;
real rm_last = 0, em_lastend = -1.0e9;
reg rbit [0:20000];
integer em_rxn = 0, em_rxnew = 0, em_nlp_rx = 0, em_badfr = 0;
real em_hi_min = 1e9, em_hi_max = 0, em_lo_min = 1e9, em_lo_max = 0, em_bt_min = 1e9, em_bt_max = 0;
real em_gap_min = 1e9, em_lat = 0, em_tp_min = 1e9, em_tp_max = 0, em_lastnlp = -1.0;
real em_nlpi_min = 1e9, em_nlpi_max = 0;

always @(em_line) if (em_mon) begin
    if (rm_n < 40000) begin rm_t[rm_n] = $realtime; rm_l[rm_n] = em_line; rm_n = rm_n + 1; end
    rm_last = $realtime;
end
always @(posedge clk_x) if (em_mon && rm_n > 0 && ($realtime - rm_last) > (em_line ? 8.0 : 2.5) * em_bt) em_carrier_end;

task em_fail(input [8*40-1:0] msg); begin em_err = em_err + 1; $display("ETHM ERROR: %0s", msg); end endtask

task em_carrier_end;
    integer j, nb, jend, i, nbytes, bad, k, fb; real dt, tmid, d, w, gap, tp, jr; reg [7:0] bv; reg lv; reg fok;
    begin
        bad = 0;
        if (rm_n == 2 && rm_l[0] == 1 && rm_l[1] == 0 && (rm_t[1] - rm_t[0]) < 1.5 * em_bt) begin
            // link pulse
            w = (rm_t[1] - rm_t[0]) / 10.0; em_nlp_rx = em_nlp_rx + 1;
            if (em_lastnlp > 0) begin d = (rm_t[0] - em_lastnlp) / 10.0; if (d < em_nlpi_min) em_nlpi_min = d; if (d > em_nlpi_max) em_nlpi_max = d; end
            em_lastnlp = rm_t[0];
            if (em_verbose) $display("ETHM chip link pulse, width %0.2f cycles", w);
        end else begin
            // ---- gap before the frame (carrier starts half a bit before the first edge)
            gap = ((rm_t[0] - 0.5 * em_bt) - em_lastend) / 10.0;
            em_lat = gap;
            if (em_lastend > -1.0e8 && gap < em_gap_min) em_gap_min = gap;
            if (em_lastend > -1.0e8 && gap < 576.0) begin $display("ETHM ERROR: gap before the frame is %0.1f cycles, minimum 576", gap); bad = bad + 1; end
            // ---- decode by the edge times
            nb = 0; jend = -1; tmid = rm_t[0];
            if (rm_l[0] != 1) begin $display("ETHM ERROR: first edge is not rising"); bad = bad + 1; end
            rbit[0] = 1; nb = 1;
            for (j = 1; j < rm_n && jend < 0; j = j + 1) begin
                dt = rm_t[j] - tmid;
                if (dt < 0.75 * em_bt) ;                                  // edge at the bit boundary
                else if (dt <= 1.25 * em_bt) begin
                    rbit[nb] = rm_l[j]; nb = nb + 1; tmid = rm_t[j];
                    d = dt / 10.0; if (d < em_bt_min) em_bt_min = d; if (d > em_bt_max) em_bt_max = d;
                end else jend = j;                                        // level held longer than a bit: idle pulse ends
            end
            if (jend >= 0 && jend != rm_n - 1) begin $display("ETHM ERROR: edges behind the end of the frame"); bad = bad + 1; end
            // ---- idle pulse: duration of the last high level
            if (em_line === 1'b1 || rm_l[rm_n - 1] == 1) begin $display("ETHM ERROR: line stays high behind the frame"); bad = bad + 1; tp = 0; end
            else tp = (rm_t[rm_n - 1] - rm_t[rm_n - 2]) / 10.0;
            if (tp < em_tp_min) em_tp_min = tp;
            if (tp > em_tp_max) em_tp_max = tp;
            if (tp < em_idlmin) begin $display("ETHM ERROR: idle pulse (final high level) is %0.2f cycles, minimum %0d", tp, em_idlmin); bad = bad + 1; end
            // ---- level durations inside the frame: every level lasts a half bit or a bit
            for (j = 1; j < rm_n - 1; j = j + 1) begin
                d = (rm_t[j] - rm_t[j - 1]) / 10.0;
                if (rm_l[j - 1]) begin if (d < em_hi_min) em_hi_min = d; if (d > em_hi_max) em_hi_max = d; end
                else begin if (d < em_lo_min) em_lo_min = d; if (d > em_lo_max) em_lo_max = d; end
                if (!((d > 2.9 && d < 3.1) || (d > 5.9 && d < 6.1))) begin
                    if (bad < 5) $display("ETHM ERROR: level of %0.2f cycles at edge %0d", d, j); bad = bad + 1;
                end
            end
            // ---- preamble and start frame delimiter
            fok = 1;
            for (i = 0; i < 56 && i < nb; i = i + 1) if (rbit[i] != ((i % 2) == 0)) fok = 0;
            bv = 0; for (i = 0; i < 8; i = i + 1) if (56 + i < nb) bv[i] = rbit[56 + i];
            if (nb < 64 || !fok || bv != 8'hD5) begin $display("ETHM ERROR: preamble or start frame delimiter wrong (%0d bits, SFD %02x)", nb, bv); bad = bad + 1; end
            // ---- bytes
            nbytes = (nb - 64) / 8;
            if (nb < 64 || ((nb - 64) % 8) != 0) begin $display("ETHM ERROR: %0d bits behind the delimiter, not a whole number of bytes", nb - 64); bad = bad + 1; end
            emr_n = 0;
            for (i = 0; i < nbytes && i < 4096; i = i + 1) begin
                for (k = 0; k < 8; k = k + 1) bv[k] = rbit[64 + 8 * i + k];
                emr[i] = bv; emr_n = emr_n + 1;
            end
            if (emr_n < 6) begin $display("ETHM ERROR: frame of %0d bytes", emr_n); bad = bad + 1; end
            else begin
                em_fcs(1, emr_n - 4);
                for (i = 0; i < 4; i = i + 1) if (emr[emr_n - 4 + i] != em_fcsb[i]) fok = 0;
                if (!fok) begin $display("ETHM ERROR: FCS of the frame of the chip is wrong"); bad = bad + 1; end
            end
            if (em_verbose) $display("ETHM chip frame %0d bytes, %0d bits, idle pulse %0.2f cycles, gap %0.1f cycles, %0d errors, starts at cycle %0.0f", emr_n, nb, tp, gap, bad, rm_t[0]/10.0);
            em_rxn = em_rxn + 1; em_rxnew = 1; em_badfr = em_badfr + bad; em_err = em_err + bad;
            em_lastend = rm_t[rm_n - 1];
        end
        rm_n = 0;
    end
endtask

// ---------------------------------------------------------------- scenario
integer em_ntests = 0, em_npass = 0;
real em_maxlat = 0;
task em_wait(input integer cyc); begin repeat (cyc) @(posedge clk_x); end endtask
task em_wait_rx(input integer cyc);
    integer k;
    begin k = 0; while (!em_rxnew && k < cyc) begin @(posedge clk_x); k = k + 1; end end
endtask

// send emt, then check the answer (or its absence). name: text, flip: bit to invert, wait: cycles to wait
task em_do(input [8*40-1:0] name, input integer flip, input integer wcyc);
    integer i, e0, mism; real lat;
    begin
        em_ntests = em_ntests + 1; e0 = em_err;
        if (em_lastend < em_tx_end) em_lastend = em_tx_end;
        em_rxnew = 0;
        em_send(flip);
        if (em_verbose) $display("ETHM sent %0d bytes, ends at cycle %0.0f", emt_n, $realtime/10.0);
        if (em_tx_end > em_lastend) em_lastend = em_tx_end;
        if (em_exp) begin
            em_wait_rx(wcyc);
            if (!em_rxnew) begin em_fail("no answer"); end
            else begin
                lat = em_lat; if (lat > em_maxlat) em_maxlat = lat;
                mism = 0;
                if (emr_n != eme_n + 4) begin $display("ETHM ERROR: answer has %0d bytes without FCS, expected %0d", emr_n - 4, eme_n); em_err = em_err + 1; end
                for (i = 0; i < eme_n && i < emr_n - 4 && mism < 4; i = i + 1)
                    if (emr[i] != eme[i]) begin $display("ETHM ERROR: byte %0d of the answer is %02x, expected %02x", i, emr[i], eme[i]); mism = mism + 1; em_err = em_err + 1; end
                $display("ETHM %0s: answer %0d bytes, %0s, delay %0.0f cycles behind the request", name, emr_n, (em_err == e0) ? "ok" : "WRONG", lat);
            end
            em_wait(40);
        end else begin
            em_wait(wcyc);
            if (em_rxnew) begin em_fail("unexpected answer"); $display("ETHM %0s: WRONG, the chip answered a frame it must ignore (%0d bytes)", name, emr_n); end
            else $display("ETHM %0s: ignored, ok", name);
        end
        if (em_err == e0) em_npass = em_npass + 1;
        em_rxnew = 0;
        em_wait(em_gap);
    end
endtask

task em_ping(input integer L, input integer seed);
    begin em_echo(em_cmac, em_cip, L, 16'hB00B + L, L + 1, seed, 0, 0); em_do("ping", -1, 400000); end
endtask

task em_selftest;
    integer i; reg [7:0] k9 [0:8]; reg ok;
    begin
        // CRC-32 of "123456789": 0xCBF43926, sent as 26 39 F4 CB
        for (i = 0; i < 9; i = i + 1) emt[i] = 8'h31 + i;
        em_fcs(0, 9);
        ok = (em_fcsb[0] == 8'h26 && em_fcsb[1] == 8'h39 && em_fcsb[2] == 8'hF4 && em_fcsb[3] == 8'hCB);
        if (ok) $display("ETHM model self test: CRC-32 of 123456789 ok");
        else begin em_fail("model CRC-32 self test"); end
        // checksum example of RFC 1071: 00 01 f2 03 f4 f5 f6 f7 -> sum ddf2
        emt[0] = 8'h00; emt[1] = 8'h01; emt[2] = 8'hf2; emt[3] = 8'h03; emt[4] = 8'hf4; emt[5] = 8'hf5; emt[6] = 8'hf6; emt[7] = 8'hf7;
        em_csum(0, 0, 8);
        if (em_cs !== 16'hddf2) em_fail("model checksum self test"); else $display("ETHM model self test: RFC 1071 checksum ok");
    end
endtask

integer em_arg;
task em_finish;
    begin
        $display("ETHM chip frames: %0d, frames with errors %0d; level durations (cycles) high %0.2f..%0.2f low %0.2f..%0.2f; bit time (mid to mid) %0.3f..%0.3f; idle pulse %0.2f..%0.2f; smallest gap %0.1f; longest answer delay %0.0f",
                 em_rxn, em_badfr, em_hi_min, em_hi_max, em_lo_min, em_lo_max, em_bt_min, em_bt_max, em_tp_min, em_tp_max, em_gap_min, em_maxlat);
        if (em_nlp_rx > 0) $display("ETHM link pulses of the chip: %0d, interval %0.0f..%0.0f cycles", em_nlp_rx, em_nlpi_min, em_nlpi_max);
        if (em_err == 0) $display("ETHM PASS (%0d of %0d tests)", em_npass, em_ntests); else $display("ETHM FAIL %0d errors (%0d of %0d tests clean)", em_err, em_npass, em_ntests);
        $finish;
    end
endtask

integer em_i, em_big, em_boot = 6000;
initial begin
    #1;
    if ($value$plusargs("ethm=%d", em_test)) begin
        if ($value$plusargs("ethppm=%d", em_ppm)) ;
        if ($value$plusargs("ethjit=%d", em_jit)) ;
        if ($value$plusargs("ethseed=%d", em_seed)) ;
        if ($value$plusargs("ethidl=%d", em_idl)) ;
        if ($value$plusargs("ethidlmin=%d", em_idlmin)) ;
        if ($value$plusargs("ethgap=%d", em_gap)) ;
        if ($value$plusargs("ethnlp=%d", em_nlpint)) ;
        if ($value$plusargs("ethmax=%d", em_max)) ;
        if ($test$plusargs("ethdiff")) em_diff = 1;
        if ($test$plusargs("ethnlpforce")) em_force = 1;
        if ($test$plusargs("ethverbose")) em_verbose = 1;
        if ($value$plusargs("ethboot=%d", em_boot)) ;
        #(em_boot * 10.0);                                // cycles for the firmware to configure the cells (default 6000)
        em_on = 1; em_pin = 0; em_mon = 1;
        em_wait(100);
        em_selftest;
        case (em_test)
        1, 2: begin
            em_arp_req(em_bcast, em_hmac, em_hip, em_cip);               em_do("ARP request, broadcast", -1, 100000);
            em_arp_req(em_cmac, em_hmac, em_hip, em_cip);                em_do("ARP request, unicast", -1, 100000);
            em_ping(0, 1);  em_ping(1, 2);  em_ping(18, 3);  em_ping(19, 4);  em_ping(32, 5);  em_ping(56, 6);  em_ping(100, 7);  em_ping(255, 8);
            // frames that must be ignored; each is followed by a ping that must be answered
            em_echo(48'h02C0FFEE0099, em_cip, 18, 1, 1, 9, 0, 0);       em_do("ping, other MAC address", -1, 20000);
            em_echo(em_cmac, {8'd192, 8'd168, 8'd4, 8'd9}, 18, 1, 1, 9, 0, 0); em_do("ping, other IP address", -1, 20000);
            em_echo(em_bcast, em_cip, 18, 1, 1, 9, 0, 0);               em_do("ping, broadcast MAC address", -1, 20000);
            em_echo(em_cmac, em_cip, 18, 1, 1, 9, 1, 0);                em_do("ping, wrong IP header checksum", -1, 20000);
            em_echo(em_cmac, em_cip, 18, 1, 1, 9, 0, 1);                em_do("ping, wrong ICMP checksum", -1, 20000);
            em_echo(em_cmac, em_cip, 18, 1, 1, 9, 0, 0); em_exp = 0;    em_do("ping, wrong FCS (payload bit)", 8 * 40 + 3, 20000);
            em_echo(em_cmac, em_cip, 18, 1, 1, 9, 0, 0); em_exp = 0;    em_do("ping, wrong FCS (first FCS bit)", 8 * emt_n, 20000);
            em_echo(em_cmac, em_cip, 18, 1, 1, 9, 0, 0); em_exp = 0;    em_do("ping, wrong FCS (last FCS bit)", 8 * emt_n + 31, 20000);
            em_arp_req(em_bcast, em_hmac, em_hip, {8'd192, 8'd168, 8'd4, 8'd7}); em_do("ARP request for another IP", -1, 20000);
            em_arp_req(48'h02C0FFEE0099, em_hmac, em_hip, em_cip);       em_do("ARP request, other MAC", -1, 20000);
            em_arp_req(em_bcast, em_hmac, em_hip, em_cip); em_exp = 0;  em_do("ARP request, wrong FCS", 8 * 20 + 1, 20000);
            em_echo(em_cmac, em_cip, 18, 1, 1, 9, 0, 0); emt[12] = 8'h88; emt[13] = 8'hB5; em_exp = 0; em_do("unknown Ethernet type", -1, 20000);
            em_ping(18, 10);
            if (!$test$plusargs("ethshort")) em_ping(1472, 11);                                            // largest standard frame: 1514 bytes + FCS
            if (em_test == 2) begin
                em_big = em_max - 42;
                em_echo(em_cmac, em_cip, em_big, 16'hB00B, 1, 12, 0, 0);  em_do("ping, largest frame", -1, 1200000);
                em_echo(em_cmac, em_cip, em_big + 1, 16'hB00B, 1, 13, 0, 0); em_exp = 0; em_do("ping, one byte over the limit", -1, 700000);
                em_ping(18, 14);
            end
        end
        4: begin
            em_arp_req(em_bcast, em_hmac, em_hip, em_cip); em_do("ARP request", -1, 100000);
            em_arp_req(em_bcast, em_hmac, em_hip, em_cip); em_do("ARP request again", -1, 100000);
            em_ping(18, 3);
            em_ping(100, 7);
            em_ping(0, 1);
        end
        5: begin
            em_arp_req(em_bcast, em_hmac, em_hip, em_cip); em_do("ARP request", -1, 100000);
            em_ping(100, 7);
        end
        3: begin
            // link pulses between frames; offsets before a frame and after a frame, in cycles
            em_ping(18, 3);
            for (em_i = 0; em_i < 12; em_i = em_i + 1) begin
                em_arg = (em_i == 0) ? 1 : (em_i == 1) ? 2 : (em_i == 2) ? 3 : (em_i == 3) ? 4 : (em_i == 4) ? 6 : (em_i == 5) ? 8 : (em_i == 6) ? 12 : (em_i == 7) ? 18 : (em_i == 8) ? 24 : (em_i == 9) ? 36 : (em_i == 10) ? 100 : 300;
                em_echo(em_cmac, em_cip, 18, 16'hB00B, 1, 20 + em_i, 0, 0);
                em_nlp(6); em_wait(em_arg);                               // pulse, then the frame em_arg cycles after its end
                em_do("ping behind a link pulse", -1, 100000);
            end
            for (em_i = 0; em_i < 6; em_i = em_i + 1) begin
                em_arg = (em_i == 0) ? 1 : (em_i == 1) ? 6 : (em_i == 2) ? 12 : (em_i == 3) ? 30 : (em_i == 4) ? 100 : 400;
                em_echo(em_cmac, em_cip, 18, 16'hB00C, 1, 40 + em_i, 0, 0);
                em_send(-1); em_lastend = em_tx_end; em_wait(em_arg); em_nlp(6); em_nlp_tx = em_nlp_tx;   // the pulse follows the frame
                em_wait_rx(100000);
                if (!em_rxnew) em_fail("no answer"); else begin
                    em_ntests = em_ntests + 1;
                    for (em_big = 0; em_big < eme_n; em_big = em_big + 1) if (emr[em_big] != eme[em_big]) em_err = em_err + 1;
                    $display("ETHM ping with a link pulse %0d cycles behind the frame: answer %0d bytes", em_arg, emr_n); end
                em_npass = em_npass + 1; em_rxnew = 0; em_wait(em_gap);
            end
            em_ping(18, 5);
        end
        endcase
        em_finish;
    end
end
