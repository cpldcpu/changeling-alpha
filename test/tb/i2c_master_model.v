// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Model of an I2C master, included in tb_sys.v. Written from the I2C definition (NXP UM10204), not from the line cell
// code. Enabled by +i2cm. Pins: 4 SDA, 5 SCL, open drain (the model pulls low through xl_b), 6 DONE (driven by the model:
// low during the test, high when it is over, for the firmware of the chip), 6 is also read as GO in the arbitration test.
// The chip is a slave (firmware test 18) or a master (arbitration, firmware test 19). Pull-ups: the pins read high if nobody drives.
// The model has a stimulus sequence (normal mode) or one transfer started together with the chip (arbitration mode).
// Normal mode: transfers selected by the bits of +i2cm_seq=hex (default 1f); chip address +i2cm_addr=h (default 52):
//   bit 0  address 0x30 (another device) write: no acknowledge expected, bus idle afterwards, nothing driven by the chip
//   bit 1  write of two bytes 0x3C + 27 i to the chip
//   bit 2  read of +i2cm_nrd (default 3) bytes from the chip, 0x69 + 3 i expected, the last one is not acknowledged
//   bit 3  write of one byte, repeated start, read of two bytes
//   bit 4  address 0x30 write (no acknowledge), repeated start, address of the chip write, one byte, stop
// Plusargs: +i2cm_per=n       SCL period in clock cycles (600 = 100 kHz, 150 = 400 kHz), default 600; the low time is 52 % of it
//           +i2cm_lo=n +i2cm_hi=n   explicit low and high time in clock cycles
//           +i2cm_dh=n        SDA changes n cycles after the falling edge of SCL (default 3)
//           +i2cm_hs=n        start hold time and stop set-up in cycles (default = high time)
//           +i2cm_t0=n        clock cycles before the first start condition (default 3000)
//           +i2cm_ackerr=h    the model sends the address 0x30 transfers also with these extras: (none)
//           +i2cm_arb         arbitration mode: wait for GO (pin 6 rises, driven by the chip), start n cycles later
//           +i2cm_arbd=n      cycles from GO to the start of the model (default 0; GO is one instruction before the chip starts)
//           +i2cm_arbaddr=h   address of the model in arbitration mode (default 51), write, two bytes
// Checks: acknowledge or no acknowledge as expected; read data; the chip does not pull SDA low while the model sends a one
// (except in arbitration mode, where it is the loss of arbitration); SDA of the chip does not change while SCL is high;
// bus idle after a stop; chip log of the received bytes (read from the data memory of the chip). Measures: margin of the
// data from the chip before the rising edge of SCL, latency of the acknowledge after the falling edge of the eighth clock,
// stretches of SCL by the chip, all in clock cycles.
reg i2cm_on = 0, i2cm_arb = 0, i2cm_lost = 0, i2cm_busy = 0, i2cm_rcv = 0, i2cm_ackslot = 0, i2cm_arbmode = 0;
integer i2cm_per = 600, i2cm_lo = -1, i2cm_hi = -1, i2cm_dh = 3, i2cm_hs = -1, i2cm_t0 = 3000, i2cm_arbd = 0, i2cm_seqm = 31, i2cm_addr = 8'h52, i2cm_arbaddr = 8'h51;
integer i2cm_err = 0, i2cm_xfers = 0, i2cm_acks = 0, i2cm_other = 0, i2cm_wbytes = 0, i2cm_rbytes = 0, i2cm_str = 0, i2cm_strmax = 0, i2cm_nstr = 0;
integer i2cm_t_chip = 0, i2cm_t_fall = 0, i2cm_margin = 100000, i2cm_lat = 0, i2cm_latmax = 0, i2cm_marginack = 100000, i2cm_marginrd = 100000, i2cm_chcnt = 0, i2cm_nlog = 0;
integer i2cm_lostbit = -1, i2cm_t_go = 0, i2cm_t_chipsda = 0, i2cm_t_mysda = 0, i2cm_won_chk = 0, i2cm_rel_t = 0;
reg i2cm_chip_ch = 0; reg [7:0] i2cm_log [0:63];
reg [7:0] i2cm_rv; reg i2cm_ra, i2cm_rr;
wire i2cm_chip_low = uio_oe[4] & ~uio_out[4];
function [7:0] i2cm_peek(input integer a); reg [15:0] w; begin w = `RAMW[a >> 1]; i2cm_peek = (a & 1) ? w[15:8] : w[7:0]; end endfunction
function [7:0] i2cm_w(input integer i); i2cm_w = 8'h3C + 27 * i; endfunction
function [7:0] i2cm_r(input integer i); i2cm_r = 8'h69 + 3 * i; endfunction
// ---------------------------------------------------------------- monitors
always @(i2cm_chip_low) if (i2cm_on) begin i2cm_t_chip = xcyc; i2cm_chip_ch = 1; end
always @(negedge uio_in[5]) if (i2cm_on) begin i2cm_t_fall = xcyc; i2cm_chip_ch = 0; end
always @(posedge uio_in[5]) if (i2cm_on && i2cm_busy && i2cm_rcv && i2cm_chip_ch) begin
    if (xcyc - i2cm_t_chip < i2cm_margin) i2cm_margin = xcyc - i2cm_t_chip;
    if (i2cm_ackslot) begin
        if (xcyc - i2cm_t_chip < i2cm_marginack) i2cm_marginack = xcyc - i2cm_t_chip;
        if (i2cm_t_chip - i2cm_t_fall > i2cm_latmax) i2cm_latmax = i2cm_t_chip - i2cm_t_fall;
    end else if (xcyc - i2cm_t_chip < i2cm_marginrd) i2cm_marginrd = xcyc - i2cm_t_chip;
end
// ---------------------------------------------------------------- primitives; every task starts and ends at a rising edge of the clock
task i2cm_cyc(input integer n); begin if (n > 0) repeat (n) @(posedge clk); end endtask
// SCL has just been released by the model: wait until the line is high; counts the cycles in which the chip (or the slave) holds it
task i2cm_waitscl; integer k; begin
    k = 0; @(posedge clk);
    while (uio_in[5] !== 1'b1 && k <= 100000) begin @(posedge clk); k = k + 1; end
    if (k > 100000) begin $display("I2CM FAIL: SCL stays low"); i2cm_err = i2cm_err + 1; end
    if (k > 0) begin i2cm_nstr = i2cm_nstr + 1; if (k > i2cm_strmax) i2cm_strmax = k; end
end endtask
// one bit with SCL low on entry (the falling edge was issued at the present clock edge); b = 1 releases SDA
// ackslot = 1: the ninth clock, the chip answers; rcv = 1: the chip drives SDA (data of a read or the acknowledge)
task i2cm_bit(input b, input rcv, input ackslot, output r);
    reg rr;
    begin
        i2cm_rcv = rcv; i2cm_ackslot = ackslot;
        i2cm_cyc(i2cm_dh); xl_b[4] <= ~b;
        i2cm_cyc(i2cm_lo - i2cm_dh);
        xl_b[5] <= 0;
        i2cm_waitscl;
        rr = uio_in[4];                                     // level at the rising edge
        if (i2cm_arbmode) begin
            if (i2cm_bitno > i2cm_lose_at && (uio_oe[4] || uio_oe[5]) && !i2cm_lost) begin i2cm_relbad = i2cm_relbad + 1; i2cm_err = i2cm_err + 1;
                $display("I2CM FAIL: the chip still drives a line (oe SDA %b SCL %b) at bit %0d, it lost arbitration at bit %0d", uio_oe[4], uio_oe[5], i2cm_bitno, i2cm_lose_at); end
            i2cm_bitno = i2cm_bitno + 1;
        end
        r = rr;
        if (i2cm_arbmode) begin : hiph                       // with two masters the clock is the AND of both: the high time ends when either pulls SCL low
            integer kk;
            for (kk = 0; kk < i2cm_hi - 1; kk = kk + 1) begin @(posedge clk); if (uio_in[5] !== 1'b1) kk = 1000000; else r = uio_in[4]; end
        end else begin
            i2cm_cyc(i2cm_hi - 1);
            r = uio_in[4];                                  // level at the end of the high time
        end
        if (rr !== r) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: SDA changes while SCL is high (%b -> %b)", rr, r); end
        if (b && !r && !rcv) begin                          // the chip pulls SDA low while the model sends a one
            if (i2cm_arbmode) begin i2cm_lost = 1; xl_b[4] <= 0; xl_b[5] <= 0; end
            else begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip pulls SDA low while the model sends a one"); end
        end
        if (!i2cm_lost) xl_b[5] <= 1;
        i2cm_rcv = 0; i2cm_ackslot = 0;
    end
endtask
task i2cm_start; begin @(posedge clk); xl_b[4] <= 1; i2cm_cyc(i2cm_hs); xl_b[5] <= 1; end endtask
task i2cm_restart; begin
    i2cm_cyc(i2cm_dh); xl_b[4] <= 0; i2cm_cyc(i2cm_lo - i2cm_dh); xl_b[5] <= 0; i2cm_waitscl; i2cm_cyc(i2cm_hi / 2);
    xl_b[4] <= 1; i2cm_cyc(i2cm_hs); xl_b[5] <= 1;
end endtask
task i2cm_stop; begin
    i2cm_cyc(i2cm_dh); xl_b[4] <= 1; i2cm_cyc(i2cm_lo - i2cm_dh); xl_b[5] <= 0; i2cm_waitscl; i2cm_cyc(i2cm_hs); xl_b[4] <= 0;
    i2cm_cyc(i2cm_lo);
end endtask
// write a byte, returns the acknowledge bit in i2cm_ra (0 = acknowledged)
task i2cm_wr(input [7:0] v); integer k; reg rb; begin
    for (k = 7; k >= 0; k = k - 1) if (!i2cm_lost) i2cm_bit(v[k], 0, 0, rb);
    if (!i2cm_lost) i2cm_bit(1, 1, 1, i2cm_ra);
end endtask
task i2cm_rd(input nack); integer k; reg rb; begin
    i2cm_rv = 0;
    for (k = 7; k >= 0; k = k - 1) begin i2cm_bit(1, 1, 0, rb); i2cm_rv = {i2cm_rv[6:0], rb}; end
    i2cm_bit(nack, 0, 0, rb);
end endtask
task i2cm_idle_check(input integer tag); begin
    if (uio_in[5:4] !== 2'b11 || uio_oe[4] || uio_oe[5]) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: bus not idle or the chip drives a line after transfer %0d (SDA %b SCL %b, oe %b%b)", tag, uio_in[4], uio_in[5], uio_oe[4], uio_oe[5]); end
end endtask
// ---------------------------------------------------------------- transfers
task i2cm_other_addr(input integer rs); begin       // address of another device; rs = 1: repeated start in place of the stop
    i2cm_start; i2cm_wr(8'h30 << 1);
    if (i2cm_ra !== 1'b1) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip acknowledges the address 0x30"); end
    i2cm_other = i2cm_other + 1;
    if (!rs) begin i2cm_stop; i2cm_idle_check(i2cm_xfers); end
    i2cm_xfers = i2cm_xfers + 1;
end endtask
task i2cm_write_chip(input integer n, input integer first_start); integer i; begin    // address, n bytes, no stop
    if (first_start) i2cm_start;
    i2cm_wr(i2cm_addr << 1);
    if (i2cm_ra !== 1'b0) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip does not acknowledge its address (write)"); end else i2cm_acks = i2cm_acks + 1;
    for (i = 0; i < n; i = i + 1) begin
        i2cm_wr(i2cm_w(i));
        if (i2cm_ra !== 1'b0) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip does not acknowledge data byte %0d", i); end
        else begin i2cm_log[i2cm_nlog] = i2cm_w(i); i2cm_nlog = i2cm_nlog + 1; i2cm_wbytes = i2cm_wbytes + 1; end
    end
end endtask
task i2cm_read_chip(input integer n); integer i; begin    // address read, n bytes, no stop
    i2cm_wr((i2cm_addr << 1) | 1);
    if (i2cm_ra !== 1'b0) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip does not acknowledge its address (read)"); end else i2cm_acks = i2cm_acks + 1;
    for (i = 0; i < n; i = i + 1) begin
        i2cm_rd(i == n - 1);
        if (i2cm_rv !== i2cm_r(i)) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: read byte %0d is %02x, expected %02x", i, i2cm_rv, i2cm_r(i)); end
        i2cm_rbytes = i2cm_rbytes + 1;
    end
end endtask
integer i2cm_arbn = 2, i2cm_nrd = 3, i2cm_arbxor = 0, i2cm_chipaddr = 8'h52, i2cm_bitno = 0, i2cm_lose_at = 1000, i2cm_relbad = 0;
integer i2cm_t_msda = 0, i2cm_t_csda = 0;
always @(xl_b[4]) if (i2cm_on && xl_b[4] && i2cm_t_msda == 0) i2cm_t_msda = xcyc;
always @(i2cm_chip_low) if (i2cm_on && i2cm_chip_low && i2cm_t_csda == 0) i2cm_t_csda = xcyc;
reg i2cm_chip_wins = 0;
// first bit at which the chip would send a one and the model a zero (the chip loses there), or the first bit at which the chip sends a zero (it wins)
task i2cm_calc_lose; integer k, bi; reg dn; reg [7:0] cbyte, mbyte; begin
    i2cm_lose_at = 1000; i2cm_chip_wins = 0; dn = 0;
    for (k = 0; k < 2; k = k + 1) begin
        cbyte = (k == 0) ? (i2cm_chipaddr << 1) : i2cm_w(0); mbyte = (k == 0) ? (i2cm_arbaddr << 1) : (i2cm_w(0) ^ i2cm_arbxor);
        for (bi = 0; bi < 8; bi = bi + 1) if (!dn && cbyte[7 - bi] !== mbyte[7 - bi]) begin
            dn = 1; if (cbyte[7 - bi]) i2cm_lose_at = 9 * k + bi; else i2cm_chip_wins = 1;
        end
    end
end endtask
task i2cm_arb_xfer; integer i; reg [7:0] va; begin       // address (write) and bytes with arbitration, started together with the chip
    i2cm_arbmode = 1;
    wait (uio_in[6] === 1'b0); wait (uio_in[6] === 1'b1); i2cm_t_go = xcyc; i2cm_t_csda = 0; i2cm_t_msda = 0;
    i2cm_cyc(i2cm_arbd);
    xl_b[4] <= 1;                                         // start; SCL is pulled low after the hold time or when the other master has done so
    begin : stw integer kk; for (kk = 0; kk < i2cm_hs && uio_in[5] === 1'b1; kk = kk + 1) @(posedge clk); end
    xl_b[5] <= 1;
    va = i2cm_arbaddr << 1;
    i2cm_bitno = 0;
    i2cm_wr(va);
    if (!i2cm_lost) begin
        i2cm_busy = 1;
        if (i2cm_ra !== 1'b0) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: no acknowledge for the address 0x%02x", i2cm_arbaddr); end
        for (i = 0; i < i2cm_arbn && !i2cm_lost; i = i + 1) begin
            i2cm_wr(i2cm_w(i) ^ (i == 0 ? i2cm_arbxor : 0));
            if (!i2cm_lost && i2cm_ra !== 1'b0) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: no acknowledge for data byte %0d", i); end
            else if (!i2cm_lost) i2cm_wbytes = i2cm_wbytes + 1;
        end
        if (!i2cm_lost) begin i2cm_stop; $display("I2CM arbitration: the model won, address 0x%02x and %0d bytes sent", i2cm_arbaddr[7:0], i2cm_wbytes); end
    end
    if (i2cm_lost) begin
        $display("I2CM arbitration: the model lost; both lines released at once; waiting for the stop of the chip");
        i2cm_cyc(5); i2cm_waitscl;
        i = 0; while (i == 0) begin @(posedge uio_in[4]); if (uio_in[5] === 1'b1) i = 1; end         // the stop condition of the chip
    end
    i2cm_busy = 0;
end endtask
initial begin
    #1;
    if ($test$plusargs("i2cm")) begin
        i2cm_on = 1;
        if ($value$plusargs("i2cm_per=%d", i2cm_per)) ;
        if ($value$plusargs("i2cm_lo=%d", i2cm_lo)) ;
        if ($value$plusargs("i2cm_hi=%d", i2cm_hi)) ;
        if ($value$plusargs("i2cm_dh=%d", i2cm_dh)) ;
        if ($value$plusargs("i2cm_hs=%d", i2cm_hs)) ;
        if ($value$plusargs("i2cm_t0=%d", i2cm_t0)) ;
        if ($value$plusargs("i2cm_seq=%h", i2cm_seqm)) ;
        if ($value$plusargs("i2cm_addr=%h", i2cm_addr)) ;
        if ($value$plusargs("i2cm_arbd=%d", i2cm_arbd)) ;
        if ($value$plusargs("i2cm_arbaddr=%h", i2cm_arbaddr)) ;
        if ($value$plusargs("i2cm_arbn=%d", i2cm_arbn)) ;
        if ($value$plusargs("i2cm_nrd=%d", i2cm_nrd)) ;
        if ($value$plusargs("i2cm_arbxor=%h", i2cm_arbxor)) ;
        if ($value$plusargs("i2cm_chipaddr=%h", i2cm_chipaddr)) ;
        if ($test$plusargs("i2cm_arb")) i2cm_arb = 1;
        if (i2cm_lo < 0) i2cm_lo = i2cm_per * 52 / 100;
        if (i2cm_hi < 0) i2cm_hi = i2cm_per - i2cm_lo;
        if (i2cm_hs < 0) i2cm_hs = i2cm_hi;
        x_oe[6] = 1; x_val[6] = 0;                                      // DONE low
        if (i2cm_arb) begin
            x_oe[6] = 0; x_oe[7] = 1; x_val[7] = 0;                    // DONE on pin 7 in arbitration mode, pin 6 is GO from the chip
            i2cm_calc_lose;
            i2cm_arb_xfer;
            i2cm_cyc(500); x_val[7] = 1;
            i2cm_cyc(4000);
            i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the firmware of the chip did not end after DONE"); i2cm_final; $finish;
        end
        else begin
            i2cm_cyc(i2cm_t0);
            i2cm_busy = 1;
            if (i2cm_seqm & 1) i2cm_other_addr(0);
            if (i2cm_seqm & 2) begin i2cm_write_chip(2, 1); i2cm_stop; i2cm_idle_check(2); i2cm_xfers = i2cm_xfers + 1; end
            if (i2cm_seqm & 4) begin i2cm_start; i2cm_read_chip(i2cm_nrd); i2cm_stop; i2cm_idle_check(3); i2cm_xfers = i2cm_xfers + 1; end
            if (i2cm_seqm & 8) begin i2cm_write_chip(1, 1); i2cm_restart; i2cm_read_chip(2); i2cm_stop; i2cm_idle_check(4); i2cm_xfers = i2cm_xfers + 1; end
            if (i2cm_seqm & 16) begin i2cm_other_addr(1); i2cm_restart; i2cm_write_chip(1, 0); i2cm_stop; i2cm_idle_check(5); i2cm_xfers = i2cm_xfers + 1; end
            i2cm_busy = 0;
            i2cm_cyc(500); x_val[6] = 1;                                // DONE
            i2cm_cyc(4000);                                             // the firmware of the chip has not ended: the test ends here
            i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the firmware of the chip did not end after DONE"); i2cm_final; $finish;
        end
    end
end
task i2cm_final; integer i, nrx; begin
    if (i2cm_on) begin
        if (!i2cm_arb) begin
            nrx = i2cm_peek(16'h0701);
            if (nrx !== i2cm_nlog) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip logged %0d data bytes of writes, the model sent %0d", nrx, i2cm_nlog); end
            else for (i = 0; i < nrx && i < 32; i = i + 1)
                if (i2cm_peek(16'h0710 + i) !== i2cm_log[i]) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip logged byte %0d = %02x, sent %02x", i, i2cm_peek(16'h0710 + i), i2cm_log[i]); end
            if (i2cm_peek(16'h0700) !== i2cm_acks) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip counted %0d own addresses, the model sent %0d", i2cm_peek(16'h0700), i2cm_acks); end
            if (i2cm_peek(16'h0702) !== i2cm_other) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the chip counted %0d other addresses, the model sent %0d", i2cm_peek(16'h0702), i2cm_other); end
            $display("I2CM %0d transfers, %0d own addresses acknowledged, %0d other addresses, %0d bytes written, %0d bytes read; SCL low %0d high %0d cycles",
                     i2cm_xfers, i2cm_acks, i2cm_other, i2cm_wbytes, i2cm_rbytes, i2cm_lo, i2cm_hi);
            $display("I2CM chip as slave: margin of its SDA changes before the SCL rise: acknowledge min %0d, read data min %0d cycles; latency of the acknowledge after the 8th falling edge max %0d cycles; chip stretched SCL %0d times (longest %0d cycles)",
                     i2cm_marginack, i2cm_marginrd, i2cm_latmax, i2cm_nstr, i2cm_strmax);
        end
        if (i2cm_arb) begin
            if (i2cm_lost != i2cm_chip_wins) begin i2cm_err = i2cm_err + 1; $display("I2CM FAIL: the model %0s arbitration, expected the %0s to win", i2cm_lost ? "lost" : "won", i2cm_chip_wins ? "chip" : "model"); end
            $display("I2CM arbitration: %0s won; SDA of the chip fell %0d cycles %0s the SDA of the model; chip drove a line after losing: %0d times",
                     i2cm_lost ? "the chip" : "the model", (i2cm_t_csda > i2cm_t_msda) ? i2cm_t_csda - i2cm_t_msda : i2cm_t_msda - i2cm_t_csda, (i2cm_t_csda > i2cm_t_msda) ? "after" : "before", i2cm_relbad);
        end
        if (i2cm_err == 0) $display("I2CM PASS");
        else $display("I2CM FAIL (%0d errors)", i2cm_err);
    end
end endtask

// +i2cm_trace: every change of SDA and SCL, with the drivers (chip, model)
integer i2cm_trace = 0; initial begin #1; if ($test$plusargs("i2cm_trace")) i2cm_trace = 1; end
always @(uio_in[4] or uio_in[5]) if (i2cm_on && i2cm_trace) $display("TRACE %0d SDA %b SCL %b  chip pulls SDA %b SCL %b  model pulls SDA %b SCL %b", xcyc, uio_in[4], uio_in[5], uio_oe[4] & ~uio_out[4], uio_oe[5] & ~uio_out[5], xl_b[4], xl_b[5]);
