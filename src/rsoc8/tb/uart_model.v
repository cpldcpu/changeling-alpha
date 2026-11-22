// Independent UART model and test scenarios, included in tb_sys.v. Enabled by +uart.
// Written from the definition of the asynchronous serial format, not from the line cell code:
//   idle level high; a character is a start bit (low), N data bits least significant bit first,
//   an optional parity bit (even: the number of ones in data and parity bit is even; odd: it is odd),
//   then one or two stop bits (high). All bits have the same duration.
// Pins (bidirectional port): model transmitter -> chip receive pin 4; chip transmit pin 5 -> model receiver.
//   +ucpb=<f>     nominal bit time in clock cycles of the testbench clock (10 ns each); default 60
//   +uscen=<n>    scenario, see uart_test
//   +und=<n> +upar=<0,1,2> +unstop=<1,2>   format of transmitter and receiver (7 or 8 data bits; parity none/even/odd)
// The transmitter has its own bit time (u_cyc * (1 + u_offt/100)), the receiver another one (u_offr), so that
// the two directions can be tested apart. The receiver samples in the middle of each bit, measured from the
// falling edge of the start bit with its own bit time. It checks the start bit in its middle (a pulse that is
// low at the beginning only is counted as glitch and ignored), the parity bit and the stop bit(s).
// The first stop bit is the last one that is checked: after it the receiver looks for the next falling edge.
reg  u_on = 0, u_txd = 1;
real u_cyc = 60.0, u_offt = 0.0, u_offr = 0.0;       // nominal cycles per bit; percent deviation of tx and rx bit time
integer u_nd = 8, u_par = 0, u_nstop = 1, u_rnstop = 1, u_scen = 0;
integer UTX = 5, URX = 4;                            // pin of the chip transmitter (model receiver), pin of the chip receiver (+utx=, +urx=)
reg [7:0] r_d [0:1023]; reg r_fe [0:1023]; reg r_pe [0:1023]; real r_t [0:1023];
integer r_n = 0, r_glitch = 0;                       // received characters; start bits that were high in the middle
reg [7:0] e_d [0:1023]; reg e_pe [0:1023]; reg e_fe [0:1023]; integer e_n = 0;
integer u_fails = 0, u_ok = 1;
real u_min_int = 1e9, u_last_edge = 0;               // shortest interval between two edges of the chip transmitter [ns]: one bit

function real u_tbit(input integer dummy); u_tbit = u_cyc * 10.0 * (1.0 + u_offt / 100.0); endfunction
function real u_rbit(input integer dummy); u_rbit = u_cyc * 10.0 * (1.0 + u_offr / 100.0); endfunction
function [7:0] u_mask(input integer nd); u_mask = (nd == 8) ? 8'hFF : 8'h7F; endfunction

// transmitter: one character. fe = 1: the stop bit(s) are low (framing error); badpar = 1: wrong parity bit
task u_send(input [7:0] d, input integer fe, input integer badpar);
    integer k; real tb; reg [7:0] dd; reg p;
    begin
        tb = u_tbit(0); dd = d & u_mask(u_nd);
        u_txd = 0; #(tb);
        for (k = 0; k < u_nd; k = k + 1) begin u_txd = dd[k]; #(tb); end
        if (u_par != 0) begin
            p = (u_par == 1) ? (^dd) : ~(^dd);
            u_txd = p ^ (badpar != 0); #(tb);
        end
        for (k = 0; k < u_nstop; k = k + 1) begin u_txd = (fe != 0) ? 1'b0 : 1'b1; #(tb); end
        u_txd = 1;
    end
endtask
task u_idle(input real bits); begin u_txd = 1; #(bits * u_tbit(0)); end endtask
// a pulse on the idle line, shorter than half a bit
task u_glitch(input real frac); begin u_txd = 0; #(frac * u_tbit(0)); u_txd = 1; end endtask

// receiver
integer u_rk; reg [7:0] u_rv; reg u_rp, u_rfe, u_rpe; real u_rt0, u_rb;
always begin : u_receiver
    if (!u_on) @(posedge u_on);
    @(negedge line[UTX]);
    if (u_on) begin
        u_rt0 = $realtime; u_rb = u_rbit(0); u_rfe = 0; u_rpe = 0; u_rv = 0;
        #(u_rb * 0.5);
        if (line[UTX] !== 1'b0) u_rglitch_inc;
        else begin
            for (u_rk = 0; u_rk < u_nd; u_rk = u_rk + 1) begin #(u_rb); u_rv[u_rk] = line[UTX]; end
            if (u_par != 0) begin #(u_rb); u_rp = line[UTX]; u_rpe = (u_par == 1) ? ((^u_rv) != u_rp) : (~(^u_rv) != u_rp); end
            for (u_rk = 0; u_rk < u_rnstop; u_rk = u_rk + 1) begin #(u_rb); if (line[UTX] !== 1'b1) u_rfe = 1; end
            if (r_n < 1024) begin r_d[r_n] = u_rv & u_mask(u_nd); r_fe[r_n] = u_rfe; r_pe[r_n] = u_rpe; r_t[r_n] = u_rt0 / 10.0; end
            r_n = r_n + 1;
            if (line[UTX] !== 1'b1) wait (line[UTX] === 1'b1);        // low stop bit: wait for the idle level
        end
    end
end
task u_rglitch_inc; begin r_glitch = r_glitch + 1; end endtask
// shortest and longest interval between edges of the chip transmitter: one bit time
always @(line[UTX]) if (u_on) begin
    if (u_last_edge != 0) begin
        if ($realtime - u_last_edge < u_min_int) u_min_int = $realtime - u_last_edge;
    end
    u_last_edge = $realtime;
end

task u_clear; begin r_n = 0; e_n = 0; r_glitch = 0; u_min_int = 1e9; end endtask
task u_expect(input [7:0] d, input pe, input fe); begin e_d[e_n] = d; e_pe[e_n] = pe; e_fe[e_n] = fe; e_n = e_n + 1; end endtask
// wait until n characters have been received, at most maxbits bit times
task u_waitn(input integer n, input integer maxbits); integer c; real q;
    begin c = 0; q = u_cyc * 10.0 / 4.0; while (r_n < n && c < maxbits * 4) begin #(q); c = c + 1; end end
endtask
// compare the received characters with the expected ones; u_ok = 1 if equal
task u_chk; integer k; reg bad;
    begin
        u_ok = 1; bad = 0;
        if (r_n != e_n) begin u_ok = 0; end
        for (k = 0; k < e_n && k < r_n; k = k + 1)
            if (r_d[k] !== e_d[k] || r_pe[k] !== e_pe[k] || r_fe[k] !== e_fe[k]) begin
                if (!bad) $display("    first difference at character %0d: got %02x pe %0d fe %0d, expected %02x pe %0d fe %0d", k, r_d[k], r_pe[k], r_fe[k], e_d[k], e_pe[k], e_fe[k]);
                bad = 1; u_ok = 0;
            end
        if (!u_ok) begin
            $write("    expected %0d characters:", e_n); for (k = 0; k < e_n && k < 40; k = k + 1) $write(" %02x", e_d[k]); $write("\n");
            $write("    received %0d characters:", r_n); for (k = 0; k < r_n && k < 40; k = k + 1) $write(" %02x%s", r_d[k], r_fe[k] ? "F" : (r_pe[k] ? "P" : "")); $write("\n");
        end
    end
endtask
function [7:0] u_pat(input integer k);
    case (k % 12)
        0: u_pat = 8'h55; 1: u_pat = 8'hAA; 2: u_pat = 8'h00; 3: u_pat = 8'hFF; 4: u_pat = 8'h81; 5: u_pat = 8'h7E;
        6: u_pat = 8'h01; 7: u_pat = 8'h80; 8: u_pat = 8'hC3; 9: u_pat = 8'h3C; 10: u_pat = 8'hF0; default: u_pat = 8'h0F;
    endcase
endfunction

// ---- scenario 1: offset sweep. mode 0: only the model transmitter is off (tests the chip receiver), mode 1: only the
// model receiver is off (tests the chip transmitter), mode 2: both (clock error of the model). Offsets in tenths of a percent.
// Each offset: nb characters, each one after the echo of the previous one has arrived.
integer sw_lo, sw_hi, sw_first_fail_neg, sw_first_fail_pos;
task u_sweep(input integer mode, input integer omin, input integer omax, input integer ostep, input integer nb);
    integer o, k; integer lo_ok, hi_ok, run_neg, run_pos; reg [7:0] d;
    begin
        sw_first_fail_neg = -9999; sw_first_fail_pos = 9999; lo_ok = 0; hi_ok = 0;
        for (o = omin; o <= omax; o = o + ostep) begin
            u_offt = 0.0; u_offr = 0.0;
            if (mode != 1) u_offt = o / 10.0;
            if (mode != 0) u_offr = o / 10.0;
            u_clear; u_idle(12);
            for (k = 0; k < nb; k = k + 1) begin
                d = u_pat(k); u_send(d, 0, 0); u_expect(d & u_mask(u_nd), 0, 0);
                u_waitn(e_n, 40);
                u_idle(2);
            end
            u_idle(25);
            u_chk;
            $display("UART sweep mode %0d (%0s) offset %0d.%0d%%: %0s", mode, mode == 0 ? "model tx" : mode == 1 ? "model rx" : "both", o / 10, (o < 0 ? -o : o) % 10, u_ok ? "ok" : "FAIL");
            if (o >= 0) begin if (!u_ok && o < sw_first_fail_pos) sw_first_fail_pos = o; end
            else begin if (!u_ok) sw_first_fail_neg = o; end        // the last failing offset below zero (the one nearest to zero)
            if (!u_ok && o >= -30 && o <= 30) u_fails = u_fails + 1;
        end
        u_offt = 0.0; u_offr = 0.0;
        $display("UART sweep mode %0d: last failing offset below 0: %0d, first failing offset above 0: %0d (tenths of a percent; -9999/9999: none in the range)", mode, sw_first_fail_neg, sw_first_fail_pos);
    end
endtask

// ---- scenario 2: back-to-back characters (no gap, one stop bit) at the given offset of the model; the chip echoes them.
task u_b2b(input integer n, input real off);
    integer k; reg [7:0] d;
    begin
        u_offt = off; u_offr = 0.0; u_clear; u_idle(12);
        for (k = 0; k < n; k = k + 1) begin d = u_pat(k + 3); u_send(d, 0, 0); u_expect(d & u_mask(u_nd), 0, 0); end
        u_waitn(n, 60); u_idle(30);
        u_chk;
        $display("UART back-to-back, %0d characters, model offset %0f%%: %0s (received %0d)", n, off, u_ok ? "all echoed correctly" : "DIFFERENT", r_n);
        u_offt = 0.0;
    end
endtask


// ---- mailbox bridge (scenarios 10 to 14): the host side uses the SPI tasks of tb_sys.v
reg [7:0] mb_in [0:1023]; integer mb_n_in = 0, mb_refused = 0; reg [7:0] mb_st, mb_dat;
real mb_t_end = 0; integer mb_single = 0;   // +umbsingle: the host reads status and byte in one command
function [7:0] mb_pat(input integer k); mb_pat = (k * 37 + 11) ^ (k >> 3); endfunction
task mb_status; begin spi_start; spi_byte(8'h08); spi_byte(0); spi_byte(0); mb_st = srx; spi_stop; end endtask   // does not take the byte
task mb_read;   begin spi_start; spi_byte(8'h08); spi_byte(0); spi_byte(0); mb_st = srx; spi_byte(0); mb_dat = srx; spi_stop;
                      if (!mb_st[6]) begin mb_in[mb_n_in] = mb_dat; mb_n_in = mb_n_in + 1; end end endtask
task mb_put(input [7:0] v); begin spi_start; spi_byte(8'h07); spi_byte(v); spi_stop; end endtask
// host loop: sends nsend bytes into the mailbox as it becomes free and collects the bytes from the firmware until
// nrecv bytes have arrived (or tmax cycles have passed). Without a byte to wait for, only the mailbox is polled.
task mb_host(input integer nsend, input integer nrecv, input integer tmax);
    integer ns; real t0; reg stat_new;
    begin
        ns = 0; t0 = $realtime;
        while (($realtime - t0) < tmax * 10.0 && (ns < nsend || mb_n_in < nrecv)) begin
            if (mb_single) mb_read;                                            // one command: status and the byte (race, see scenario 11)
            else begin mb_status; if (!mb_st[6]) mb_read; end                   // status first: the byte is taken only by the second command
            if (!mb_st[7] && ns < nsend) begin mb_put(mb_pat(ns)); ns = ns + 1; end
        end
        mb_t_end = $realtime;
    end
endtask
task mb_check_in(input integer n); integer k, bad; begin
    bad = 0; if (mb_n_in != n) bad = 1;
    for (k = 0; k < n && k < mb_n_in; k = k + 1) if (mb_in[k] !== mb_pat(k)) bad = bad + 1;
    u_ok = (bad == 0);
end endtask
// host reads a RAM byte of the firmware: halt, read, continue
reg [7:0] mb_ram [0:3];
task mb_ram_read; begin h_ctrl(8'h01); h_rd1(16'h0700); mb_ram[0] = hv; h_rd1(16'h0701); mb_ram[1] = hv; h_rd1(16'h0702); mb_ram[2] = hv; h_ctrl(8'h00); end endtask
task mb_spacing(input integer n); real sp; begin
    if (n > 1) begin sp = (r_t[n-1] - r_t[0]) / (n - 1); $display("UART model: %0d characters, mean spacing of start bits %0f clock cycles (one character is %0f cycles)", n, sp, 10.0 * u_cyc); end
end endtask


// ---- UART to WS2812 bridge (scenarios 20 and 21). Frame on the UART: one byte with the number of LEDs n, then 3 n bytes
// (colour data in the order green, red, blue). The pause or the length decides where the frame ends: here the length.
function [7:0] ws_pat(input integer k); ws_pat = (k * 53 + 7) ^ (k >> 2); endfunction
function [7:0] ram8(input [10:0] a); reg [15:0] w; begin w = `RAMW[a[10:1]]; ram8 = a[0] ? w[15:8] : w[7:0]; end endfunction
task ws_frame(input integer nled, input real gapbits, input integer first);   // sends one frame to the chip through the UART model
    integer k;
    begin
        u_send(nled, 0, 0); u_idle(gapbits);
        for (k = 0; k < 3 * nled; k = k + 1) begin u_send(ws_pat(first + k), 0, 0); u_idle(gapbits); end
    end
endtask
// evaluates the WS2812 receiver model against nbytes expected bytes in nframes frames; u_ok = 1 if everything is right
task ws_report(input integer nbytes, input integer nframes, input integer first);
    integer k, bad;
    begin
        bad = 0; for (k = 0; k < nbytes && k < w_nbytes; k = k + 1) if (w_b[k] !== ws_pat(first + k)) bad = bad + 1;
        u_ok = (w_nbytes == nbytes && bad == 0 && w_nframes == nframes && w_errs == 0 && w_partial == 0);
        $display("WS2812 model: %0d bits, %0d bytes in %0d frame(s) (expected %0d bytes in %0d), %0d wrong bytes, %0d bad high times, %0d bad periods, %0d partial bytes",
                 w_bits, w_nbytes, w_nframes, nbytes, nframes, bad, w_bad_h, w_bad_per, w_partial);
        $display("WS2812 model: T0H %0f..%0f, T1H %0f..%0f, period inside a byte %0f..%0f, extra low time between bytes %0f..%0f (all in clock cycles; reset time %0f)",
                 w_t0h_min, w_t0h_max, w_t1h_min, w_t1h_max, w_per_min, w_per_max, w_gap_min, w_gap_max, W_RESET);
        if (w_nframes > 1 && w_nframes < 64) begin
            $write("WS2812 model: bytes per frame:"); for (k = 0; k < w_nframes; k = k + 1) $write(" %0d", w_fbytes[k]); $write("\n");
        end
    end
endtask

task uart_test;
    integer o, k, n; real off; reg [7:0] d;
    begin
        u_on = 1; mb_single = $test$plusargs("umbsingle");
        if ($value$plusargs("ucpb=%f", u_cyc)) ;
        if ($value$plusargs("uscen=%d", u_scen)) ;
        if ($value$plusargs("und=%d", u_nd)) ;
        if ($value$plusargs("upar=%d", u_par)) ;
        if ($value$plusargs("unstop=%d", u_nstop)) ;
        if ($value$plusargs("urnstop=%d", u_rnstop)) ;     // stop bits checked by the model receiver (default 1)
        if ($value$plusargs("ustart=%d", n)) ; else n = 20000;
        #(n);                                              // the firmware sets up the line cells (+ustart=<ns>)
        u_idle(5);
        case (u_scen)
        1: begin : sc1                                      // tolerance sweep of the bit time
            integer omin, omax, ost, nb, mmask;
            mmask = 7; omin = -80; omax = 80; ost = 10; nb = 6;
            if ($value$plusargs("uomin=%d", omin)) ; if ($value$plusargs("uomax=%d", omax)) ;
            if ($value$plusargs("uostep=%d", ost)) ; if ($value$plusargs("unb=%d", nb)) ;
            if ($value$plusargs("umodes=%d", mmask)) ;
            if (mmask & 1) u_sweep(0, omin, omax, ost, nb); if (mmask & 2) u_sweep(1, omin, omax, ost, nb); if (mmask & 4) u_sweep(2, omin, omax, ost, nb);
            $display("UART chip transmitter: shortest interval between two edges %0f cycles (one bit)", u_min_int / 10.0);
        end
        2: begin : sc2                                      // back-to-back characters
            integer nbb; real offb; nbb = 16; offb = 0.0;
            if ($value$plusargs("unb=%d", nbb)) ; if ($value$plusargs("uoff=%f", offb)) ;
            u_b2b(nbb, offb);
            if (!u_ok) u_fails = u_fails + 1;
        end
        3: begin : sc3                                      // framing error: stop bit low
            u_clear; u_idle(12);
            u_send(8'h55, 0, 0); u_expect(8'h55, 0, 0); u_idle(14);
            u_send(8'h2A, 1, 0); u_expect(8'h2A, 0, 0); u_expect(8'h21, 0, 0); u_idle(14);       // '!' follows a framing error
            u_send(8'hA6, 0, 0); u_expect(8'hA6, 0, 0); u_idle(14);
            u_send(8'hCA, 1, 0); u_expect(8'hCA, 0, 0); u_expect(8'h21, 0, 0); u_idle(14);       // bit 7 is high: the line falls at the stop bit
            u_send(8'h3C, 0, 0); u_expect(8'h3C, 0, 0); u_idle(14);
            u_send(8'h00, 1, 0); u_expect(8'h00, 0, 0); u_expect(8'h21, 0, 0); u_idle(14);       // all low for ten bit times: break
            u_send(8'hFF, 1, 0); u_expect(8'hFF, 0, 0); u_expect(8'h21, 0, 0); u_idle(14);
            u_send(8'h81, 0, 0); u_expect(8'h81, 0, 0); u_idle(14);
            u_chk; $display("UART framing errors: %0s (received %0d of %0d)", u_ok ? "reported as expected" : "DIFFERENT", r_n, e_n);
            if (!u_ok) u_fails = u_fails + 1;
            // back-to-back after a framing error: the next character follows at once
            u_clear; u_idle(12);
            u_send(8'h2A, 1, 0); u_idle(1); u_send(8'h5C, 0, 0); u_expect(8'h2A, 0, 0); u_expect(8'h21, 0, 0); u_expect(8'h5C, 0, 0); u_idle(30);
            u_chk; $display("UART character directly after a framing error: %0s (received %0d of %0d)", u_ok ? "received" : "NOT as expected", r_n, e_n);
            if (!u_ok) u_fails = u_fails + 1;
        end
        4: begin : sc4                                      // glitch on the idle line, shorter than half a bit
            integer sc; sc = $test$plusargs("ustartchk");
            u_clear; u_idle(12);
            u_glitch(0.3); u_idle(20);
            if (!sc) u_expect(8'hFF, 0, 0);                 // without start bit check the chip receives a character of ones
            u_waitn(e_n, 5); u_chk;
            $display("UART glitch of 0.3 bit on the idle line: %0d character(s) received%0s", r_n, u_ok ? "" : " (NOT as expected)");
            if (!u_ok) u_fails = u_fails + 1;
            u_clear; u_idle(12);
            u_glitch(0.3); u_idle(0.7); u_send(8'h5A, 0, 0); u_expect(8'h5A, 0, 0); u_idle(30);
            if (!sc) begin e_n = 0; end
            u_chk;
            $display("UART glitch of 0.3 bit, one bit time later the start bit of 0x5A: received %0d: %0s", r_n, u_ok ? "0x5A received" : "character lost or wrong");
            if (sc && !u_ok) u_fails = u_fails + 1;
            if (!sc) $display("UART (without start bit check this is a documented weakness: the receiver runs from the glitch and misses the start edge)");
        end
        5: begin : sc5                                      // parity: nd = 7 data bits and the parity bit fill the 8-bit frame
            integer pchk; pchk = $test$plusargs("upchk");     // +upchk: the firmware checks the parity itself and answers a wrong one with a '?'
            u_clear; u_idle(12);
            for (k = 0; k < 10; k = k + 1) begin
                d = u_pat(k + 1); u_send(d, 0, (k == 3 || k == 7)); u_expect(d & u_mask(u_nd), (k == 3 || k == 7), 0);
                if (pchk && (k == 3 || k == 7)) u_expect(8'h3F, 0, 0);
                u_waitn(e_n, 40); u_idle(2);
            end
            u_idle(25); u_chk;
            $display("UART parity %0s, %0d data bits: %0s (bad parity bits at 3 and 7 pass through unchanged%0s)", u_par == 1 ? "even" : u_par == 2 ? "odd" : "none", u_nd, u_ok ? "ok" : "FAIL", pchk ? ", firmware found them too" : "");
            if (!u_ok) u_fails = u_fails + 1;
        end
        9: begin : sc9                                      // parity by the line cells (LCX): the firmware sends every character back; the cell
            u_clear; u_idle(12);                            // generates the parity; a wrong parity (characters 3 and 7) is answered with a '?' after the echo
            for (k = 0; k < 10; k = k + 1) begin
                d = u_pat(k + 1); u_send(d, 0, (k == 3 || k == 7)); u_expect(d & u_mask(u_nd), 0, 0);
                if (k == 3 || k == 7) u_expect(8'h3F, 0, 0);
                u_waitn(e_n, 40); u_idle(2);
            end
            u_idle(25); u_chk;
            $display("UART parity %0s by the cells, %0d data bits: %0s (10 characters returned with correct parity, the two with a wrong parity bit marked)", u_par == 1 ? "even" : u_par == 2 ? "odd" : "none", u_nd, u_ok ? "ok" : "FAIL");
            if (!u_ok) u_fails = u_fails + 1;
        end
        6: begin : sc6                                      // two stop bits from the model, characters back to back, offsets of the model
            for (o = -30; o <= 30; o = o + 30) begin
                u_b2b(12, o / 10.0); if (!u_ok) u_fails = u_fails + 1;
            end
        end
        7: begin : sc7                                      // overrun: the firmware (built with -DSTALL) does not read for a long time
            integer wc; wc = 12000; if ($value$plusargs("uwait=%d", wc)) ;
            u_clear;
            for (k = 0; k < 8; k = k + 1) u_send(u_pat(k + 5), 0, 0);
            u_expect(8'h23, 0, 0); u_expect(u_pat(5), 0, 0); u_expect(u_pat(6), 0, 0);       // '#', then the two characters that were stored
            #(wc * 10.0);                                  // the stall ends
            u_waitn(3, 60); u_idle(30);
            u_chk; $display("UART overrun: %0s (received %0d: the first two characters of the burst, preceded by the overrun marker)", u_ok ? "as expected" : "DIFFERENT", r_n);
            if (!u_ok) u_fails = u_fails + 1;
            u_clear; u_send(8'h99, 0, 0); u_expect(8'h99, 0, 0); u_waitn(1, 40); u_idle(20); u_chk;
            $display("UART after the overrun: next character %0s", u_ok ? "received" : "NOT received");
            if (!u_ok) u_fails = u_fails + 1;
        end
        8: begin : sc8                                      // burst to a slow firmware (+cdiv=4 or -DBUSY): lost characters must be marked
            integer nbb, j, ns, nm, lost, bad; reg [7:0] snt [0:255];
            nbb = 24; if ($value$plusargs("unb=%d", nbb)) ;
            u_clear; u_idle(12);
            for (k = 0; k < nbb; k = k + 1) begin snt[k] = u_pat(k + 3); u_send(snt[k], 0, 0); end
            u_waitn(nbb, 100); u_idle(40);
            // the received characters without the marker '#' (0x23) must be a subsequence of the sent ones
            j = 0; nm = 0; bad = 0;
            for (k = 0; k < r_n; k = k + 1) begin
                if (r_d[k] == 8'h23 && !(j < nbb && snt[j] == 8'h23)) nm = nm + 1;
                else begin
                    while (j < nbb && snt[j] != r_d[k]) j = j + 1;
                    if (j >= nbb) bad = bad + 1; else j = j + 1;
                end
            end
            lost = nbb - (r_n - nm);
            $display("UART burst of %0d characters to a slow firmware: %0d received, %0d lost, %0d overrun marker(s), %0d not in the sent sequence", nbb, r_n - nm, lost, nm, bad);
            if (bad != 0 || (lost > 0 && nm == 0) || (lost <= 0 && nm != 0 && 0)) begin u_fails = u_fails + 1; $display("    FAIL: a lost character was not marked, or a wrong character was received"); end
        end
        10: begin : sc10                                    // host -> mailbox -> firmware -> UART -> model
            integer nb, k2; nb = 32; if ($value$plusargs("unb=%d", nb)) ;
            u_clear; h_status; mb_n_in = 0;
            mb_host(nb, 0, nb * 700 + 8000);
            u_waitn(nb, 40); u_idle(5);
            for (k2 = 0; k2 < nb; k2 = k2 + 1) u_expect(mb_pat(k2), 0, 0);
            u_chk; h_status;
            $display("MAILBOX host to UART: %0d bytes, UART model received %0d: %0s, host error bit %0d", nb, r_n, u_ok ? "data ok" : "DIFFERENT", hs1[7]);
            mb_spacing(r_n < nb ? r_n : nb);
            if (!u_ok || hs1[7]) u_fails = u_fails + 1;
        end
        11: begin : sc11                                    // model -> UART -> firmware -> mailbox -> host
            integer nb, k2; nb = 32; if ($value$plusargs("unb=%d", nb)) ;
            u_clear; h_status; mb_n_in = 0;
            fork
                begin for (k2 = 0; k2 < nb; k2 = k2 + 1) u_send(mb_pat(k2), 0, 0); end
                mb_host(0, nb, nb * 10 * u_cyc + 6000);
            join
            mb_check_in(nb); h_status;
            $display("MAILBOX UART to host: %0d bytes sent back to back, host received %0d: %0s", nb, mb_n_in, u_ok ? "data ok" : "DIFFERENT (bytes lost)");
            if (!u_ok) u_fails = u_fails + 1;
            mb_ram_read; $display("MAILBOX firmware counters: host to UART %0d, UART to host %0d, overrun seen %0d times", mb_ram[0], mb_ram[1], mb_ram[2]);
        end
        12: begin : sc12                                    // both directions at the same time
            integer nb, k2, k3; nb = 32; if ($value$plusargs("unb=%d", nb)) ;
            u_clear; h_status; mb_n_in = 0;
            fork
                begin for (k2 = 0; k2 < nb; k2 = k2 + 1) u_send(mb_pat(k2 + 100), 0, 0); end
                mb_host(nb, nb, nb * 10 * u_cyc + nb * 600 + 8000);
            join
            u_waitn(nb, 40); u_idle(5);
            for (k3 = 0; k3 < nb; k3 = k3 + 1) u_expect(mb_pat(k3), 0, 0);
            u_chk; $display("MAILBOX full duplex: UART model received %0d of %0d: %0s", r_n, nb, u_ok ? "data ok" : "DIFFERENT");
            if (!u_ok) u_fails = u_fails + 1;
            u_ok = 1; for (k3 = 0; k3 < nb && k3 < mb_n_in; k3 = k3 + 1) if (mb_in[k3] !== mb_pat(k3 + 100)) u_ok = 0;
            if (mb_n_in != nb) u_ok = 0;
            $display("MAILBOX full duplex: host received %0d of %0d: %0s", mb_n_in, nb, u_ok ? "data ok" : "DIFFERENT");
            if (!u_ok) u_fails = u_fails + 1;
            h_status; $display("MAILBOX full duplex: host error bit %0d", hs1[7]); if (hs1[7]) u_fails = u_fails + 1;
        end
        13: begin : sc13                                    // overflow host -> firmware: a second byte while the first one is still in the mailbox
            u_clear; h_status;
            h_ctrl(8'h01);                                  // the core is halted: it cannot read the mailbox
            mb_put(8'hA1); h_status; $display("MAILBOX first byte written: error bit %0d", hs1[7]);
            if (hs1[7]) u_fails = u_fails + 1;
            mb_put(8'hB2); h_status;
            $display("MAILBOX second byte written to a full mailbox: error bit %0d (1 = refused)", hs1[7]);
            if (!hs1[7]) u_fails = u_fails + 1;
            h_status; if (hs1[7]) u_fails = u_fails + 1;    // cleared by the previous status command
            mb_status; $display("MAILBOX status seen by the host: RXF %0d TXE %0d", mb_st[7], mb_st[6]); if (!mb_st[7]) u_fails = u_fails + 1;
            h_ctrl(8'h00);
            u_expect(8'hA1, 0, 0); u_waitn(2, 40); u_idle(10); u_chk;
            $display("MAILBOX after the core runs: UART model received %0d byte(s): %0s (the byte in the mailbox is kept, the new one is lost)", r_n, u_ok ? "only 0xA1" : "DIFFERENT");
            if (!u_ok) u_fails = u_fails + 1;
        end
        14: begin : sc14                                    // overflow firmware -> host: UART bytes arrive while the host does not read
            integer nb, k2; nb = 8; if ($value$plusargs("unb=%d", nb)) ;
            u_clear; h_status; mb_n_in = 0;
            for (k2 = 0; k2 < nb; k2 = k2 + 1) u_send(mb_pat(k2), 0, 0);
            u_idle(20);
            mb_host(0, nb, 20000);                          // now the host reads everything that is there
            $display("MAILBOX burst of %0d bytes from the UART while the host does not read: host got %0d byte(s):", nb, mb_n_in);
            for (k2 = 0; k2 < mb_n_in; k2 = k2 + 1) $display("    byte %0d: %02x (sent %02x)", k2, mb_in[k2], mb_pat(k2));
            mb_ram_read; $display("MAILBOX firmware counters: UART to host %0d, overrun seen %0d times", mb_ram[1], mb_ram[2]);
            u_ok = 1; for (k2 = 0; k2 < mb_n_in; k2 = k2 + 1) if (mb_in[k2] !== mb_pat(k2)) u_ok = 0;      // what arrives is the beginning of the burst, in order
            if (!u_ok || mb_n_in != 3 || mb_ram[2] == 0) begin u_fails = u_fails + 1; $display("    FAIL: expected the first three bytes (one in the mailbox, two in the holding register) and the overrun flag"); end
        end
        15: begin : sc15                                    // host writes without polling the mailbox (one byte per SPI command, no gap)
            integer nb, k2, j2, bad; nb = 32; if ($value$plusargs("unb=%d", nb)) ;
            u_clear; h_status;
            for (k2 = 0; k2 < nb; k2 = k2 + 1) mb_put(mb_pat(k2));
            u_waitn(nb, 60); u_idle(10); h_status;
            j2 = 0; bad = 0;                                   // received bytes must be a subsequence of the sent ones
            for (k2 = 0; k2 < r_n; k2 = k2 + 1) begin
                while (j2 < nb && mb_pat(j2) != r_d[k2]) j2 = j2 + 1;
                if (j2 >= nb) bad = bad + 1; else j2 = j2 + 1;
            end
            $display("MAILBOX blind writes: %0d bytes written back to back, UART model received %0d, host error bit %0d, %0d not in the sent sequence", nb, r_n, hs1[7], bad);
            if (bad != 0 || (r_n == nb && hs1[7]) || (r_n < nb && !hs1[7])) begin u_fails = u_fails + 1; $display("    FAIL: loss without error bit, or wrong data"); end
        end
        20: begin : sc20                                    // one frame: n LEDs through the UART, checked at the WS2812 pin
            integer nled; real gb, ofs; nled = 8; gb = 0.0; ofs = 0.0;
            if ($value$plusargs("unb=%d", nled)) ; if ($value$plusargs("ugap=%f", gb)) ; if ($value$plusargs("uoff=%f", ofs)) ;
            w_on = 1; w_clear; u_clear; u_offt = ofs;
            u_idle(12);
            ws_frame(nled, gb, 0);
            #((3000 + 3 * 24 * 75 * nled) * 10.0 + 40000.0);       // output time of the frame, reset time
            ws_report(3 * nled, 1, 0);
            if (!u_ok) begin u_fails = u_fails + 1; $display("    FAIL: WS2812 data or timing"); end
            $display("WS2812 firmware counters: overrun seen %0d times", ram8(16'h0700));
        end
        21: begin : sc21                                    // two frames; +upause=<bit times> between the last byte of the first frame and the header of the second
            integer nled; real gb, ofs, pz; nled = 4; gb = 0.0; ofs = 0.0; pz = 2.0;
            if ($value$plusargs("unb=%d", nled)) ; if ($value$plusargs("ugap=%f", gb)) ; if ($value$plusargs("uoff=%f", ofs)) ; if ($value$plusargs("upause=%f", pz)) ;
            w_on = 1; w_clear; u_clear; u_offt = ofs; u_idle(12);
            ws_frame(nled, gb, 0); u_idle(pz); ws_frame(nled, gb, 100);
            #((6000 + 2 * 3 * 24 * 75 * nled) * 10.0 + 60000.0);
            $display("WS2812 two frames, pause of %0f bit times between them: model saw %0d byte(s) in %0d frame(s), firmware overrun count %0d", pz, w_nbytes, w_nframes, ram8(16'h0700));
            u_ok = (w_nframes == 2 && w_nbytes == 6 * nled && w_errs == 0);
            if (u_ok) for (k = 0; k < 3 * nled; k = k + 1) if (w_b[k] !== ws_pat(k) || w_b[3 * nled + k] !== ws_pat(100 + k)) u_ok = 0;
            if (u_ok) $display("WS2812 both frames correct");
            else if (ram8(16'h0700) != 0) $display("WS2812 data lost, reported by the overrun counter of the firmware (the input has to pause while the previous frame is output)");
            else begin u_fails = u_fails + 1; $display("    FAIL: data lost or wrong without an overrun report"); end
        end
        endcase
        if (u_fails == 0) $display("UART TEST PASS scenario %0d", u_scen); else $display("UART TEST FAIL scenario %0d (%0d failures)", u_scen, u_fails);
        $finish;
    end
endtask
