// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Model of an I2C slave with clock stretching, included in tb_sys.v. Written from the I2C definition (NXP UM10204),
// not from the line cell code. Enabled by +i2cs. Pins: 4 SDA, 5 SCL, both open drain (the model pulls low through xl_a).
// The chip is the master. The model acknowledges its address, takes the bytes of a write and returns bytes on a read.
// Data written by the master: byte i of a segment must be 0x3C + 27 i. Data returned on a read: 0x69 + 3 i.
// Plusargs: +i2cs_addr=h      7-bit address that is acknowledged (default 52); +i2cs_addr2=h second address (default none)
//           +i2cs_noack        no acknowledge for any address
//           +i2cs_nochk       do not check the data of writes (two masters with different data)
//           +i2cs_nackdata=n  no acknowledge for data byte n (0 = first) of a write
//           +i2cs_str=n       longest stretch in clock cycles; +i2cs_strp=p  chance in percent, per falling edge of SCL, that the
//                             model holds SCL low for 1 to n cycles after it (any bit, any acknowledge); default p = 100 if str is given
//           +i2cs_strack=n    stretch of n cycles after every acknowledge (after the ninth clock), fixed
//           +i2cs_seed=n      seed of the random numbers
//           +i2cs_stuck=k     the model holds SDA low from the start of the simulation until k clock pulses (falling edges of SCL)
//                             have passed; k = 999: never
//           +i2cs_sclstuck    the model holds SCL low from the start for ever
//           +i2cs_dly=n       SDA changes n clock cycles after the falling edge of SCL (default 2)
// Checks: SDA does not change while SCL is high except for start and stop at the boundary of a byte; written bytes;
// number of clock pulses per segment is a multiple of nine. Measures: shortest SCL low and high time at the pin, shortest time
// from a change of SDA to the rising edge of SCL, longest stretch, in clock cycles of the chip.
reg i2cs_on = 0, i2cs_nack = 0;
integer i2cs_addr = 8'h52, i2cs_addr2 = -1, i2cs_nackdata = -1, i2cs_str = 0, i2cs_strp = 0, i2cs_strack = 0, i2cs_seed = 1, i2cs_stuck = 0, i2cs_dly = 2;
reg i2cs_sclstuck = 0, i2cs_nochk = 0;
integer i2cs_ph = 0;               // 0 idle (not addressed), 1 address, 2 write data, 3 read data, 4 read data after a NACK
integer i2cs_nb = 0, i2cs_idx = 0, i2cs_err = 0, i2cs_seg = 0, i2cs_pulses = 0, i2cs_sbad = 0;
integer i2cs_t_sclr = 0, i2cs_t_sclf = 0, i2cs_t_sda = 0, i2cs_lowmin = 100000, i2cs_highmin = 100000, i2cs_sumin = 100000, i2cs_strmax = 0, i2cs_nstr = 0;
integer i2cs_segw = 0, i2cs_segr = 0, i2cs_segaddr_unused = 0, i2cs_start_cnt = 0, i2cs_stretchrun = 0;
reg [7:0] i2cs_sh = 0, i2cs_cur = 0; reg [7:0] i2cs_segaddr = 0; reg i2cs_rw = 0, i2cs_ackd = 0, i2cs_inseg = 0;
wire i2cs_sda = uio_in[4], i2cs_scl = uio_in[5];
function [7:0] i2cs_rbyte(input integer i); i2cs_rbyte = 8'h69 + 3 * i; endfunction
function [7:0] i2cs_wbyte(input integer i); i2cs_wbyte = 8'h3C + 27 * i; endfunction
task i2cs_sdaout(input b); begin   // b = 1 releases SDA
    if (i2cs_dly == 0) xl_a[4] = ~b; else xl_a[4] <= #(i2cs_dly * 10) ~b;
end endtask
task i2cs_segend; begin
    if (i2cs_inseg) begin
        $display("I2CS segment %0d: address 0x%02x %0s, %0d bytes written, %0d bytes read, %0d clock pulses, stretches %0d (longest %0d cycles)",
                 i2cs_seg, i2cs_segaddr[7:0], i2cs_rw ? "R" : "W", i2cs_segw, i2cs_segr, i2cs_pulses, i2cs_nstr, i2cs_strmax);
        i2cs_inseg = 0;
    end
end endtask
initial begin
    #1;
    if ($test$plusargs("i2cs")) begin
        i2cs_on = 1;
        if ($value$plusargs("i2cs_addr=%h", i2cs_addr)) ;
        if ($value$plusargs("i2cs_addr2=%h", i2cs_addr2)) ;
        if ($test$plusargs("i2cs_noack")) i2cs_nack = 1;
        if ($value$plusargs("i2cs_nackdata=%d", i2cs_nackdata)) ;
        if ($value$plusargs("i2cs_str=%d", i2cs_str)) i2cs_strp = 100;
        if ($value$plusargs("i2cs_strp=%d", i2cs_strp)) ;
        if ($value$plusargs("i2cs_strack=%d", i2cs_strack)) ;
        if ($value$plusargs("i2cs_seed=%d", i2cs_seed)) ;
        if ($value$plusargs("i2cs_stuck=%d", i2cs_stuck)) ;
        if ($value$plusargs("i2cs_dly=%d", i2cs_dly)) ;
        if ($test$plusargs("i2cs_nochk")) i2cs_nochk = 1;
        if ($test$plusargs("i2cs_sclstuck")) begin i2cs_sclstuck = 1; xl_a[5] = 1; end
        if (i2cs_stuck != 0) xl_a[4] = 1;
    end
end
// ---------------------------------------------------------------- start and stop
always @(negedge i2cs_sda) if (i2cs_on && i2cs_scl && !(i2cs_stuck > 0)) begin
    if (i2cs_ph != 0 && i2cs_nb >= 2 && i2cs_nb != 9) begin i2cs_err = i2cs_err + 1; $display("I2CS FAIL: start inside a byte (after %0d clock pulses)", i2cs_nb); end
    i2cs_segend;
    i2cs_ph = 1; i2cs_nb = 0; i2cs_idx = 0; i2cs_pulses = 0; i2cs_seg = i2cs_seg + 1; i2cs_inseg = 1; i2cs_segw = 0; i2cs_segr = 0;
    i2cs_nstr = 0; i2cs_strmax = 0; i2cs_start_cnt = i2cs_start_cnt + 1; xl_a[4] = 0;
end
always @(posedge i2cs_sda) if (i2cs_on && i2cs_scl && !(i2cs_stuck > 0)) begin
    if (i2cs_ph != 0 && i2cs_nb >= 2 && i2cs_nb != 9 && i2cs_ph != 4) begin i2cs_err = i2cs_err + 1; $display("I2CS FAIL: stop inside a byte (after %0d clock pulses)", i2cs_nb); end
    i2cs_segend; i2cs_ph = 0; xl_a[4] = 0;
end
always @(i2cs_sda) if (i2cs_on) begin
    if (i2cs_scl && i2cs_ph != 0 && i2cs_nb >= 2 && i2cs_nb != 9 && !(i2cs_stuck > 0)) begin
        i2cs_sbad = i2cs_sbad + 1; i2cs_err = i2cs_err + 1; $display("I2CS FAIL: SDA changes while SCL is high inside a byte (pulse %0d)", i2cs_nb);
    end
    i2cs_t_sda = xcyc;
end
// ---------------------------------------------------------------- clock pulses
always @(posedge i2cs_scl) if (i2cs_on) begin if ($test$plusargs("i2cs_dbg")) $display("DBG rise cyc %0d sda %b ph %0d nb %0d", xcyc, i2cs_sda, i2cs_ph, i2cs_nb);
    if (xcyc - i2cs_t_sclf < i2cs_lowmin && i2cs_t_sclf != 0 && !i2cs_stretchrun) i2cs_lowmin = xcyc - i2cs_t_sclf;
    if (xcyc - i2cs_t_sda < i2cs_sumin && i2cs_t_sda != 0 && i2cs_ph != 0) i2cs_sumin = xcyc - i2cs_t_sda;
    i2cs_t_sclr = xcyc;
    if (i2cs_ph != 0 && i2cs_stuck <= 0) begin
        i2cs_pulses = i2cs_pulses + 1;
        if (i2cs_nb < 8) begin i2cs_sh = {i2cs_sh[6:0], i2cs_sda}; i2cs_nb = i2cs_nb + 1; end
        else begin                                                         // ninth clock: acknowledge from the master after a read byte
            i2cs_nb = 9;
            if (i2cs_ph == 3) begin
                if (i2cs_sda) i2cs_ph = 4;                                  // NACK: the read is over
            end
        end
    end
end
always @(negedge i2cs_scl) if (i2cs_on) begin : fall
    integer n;
    if (xcyc - i2cs_t_sclr < i2cs_highmin && i2cs_t_sclr != 0) i2cs_highmin = xcyc - i2cs_t_sclr;
    i2cs_t_sclf = xcyc;
    if (i2cs_stuck > 0) begin                                               // a stuck slave: counts clock pulses, then lets go
        i2cs_pulses = i2cs_pulses + 1;
        if (i2cs_pulses >= i2cs_stuck) begin xl_a[4] = 0; i2cs_stuck = 0; i2cs_pulses = 0; $display("I2CS the stuck slave releases SDA"); end
    end else if (i2cs_ph != 0) begin
        if (i2cs_nb == 8 && i2cs_ph == 1) begin                             // address received: acknowledge
            i2cs_rw = i2cs_sh[0]; i2cs_segaddr = i2cs_sh[7:1];
            if (!i2cs_nack && (i2cs_sh[7:1] == i2cs_addr || i2cs_sh[7:1] == i2cs_addr2)) begin i2cs_sdaout(0); i2cs_ackd = 1; end
            else begin i2cs_ph = 0; i2cs_ackd = 0; end
        end else if (i2cs_nb == 8 && i2cs_ph == 2) begin                    // data byte received
            if (i2cs_nochk) $display("I2CS data byte %0d written: %02x", i2cs_idx, i2cs_sh);
            else if (i2cs_sh !== i2cs_wbyte(i2cs_idx)) begin i2cs_err = i2cs_err + 1; $display("I2CS FAIL: byte %0d written is %02x, expected %02x", i2cs_idx, i2cs_sh, i2cs_wbyte(i2cs_idx)); end
            i2cs_segw = i2cs_segw + 1;
            if (i2cs_idx == i2cs_nackdata) begin i2cs_sdaout(1); end else i2cs_sdaout(0);
            i2cs_idx = i2cs_idx + 1;
        end else if (i2cs_nb == 8 && i2cs_ph == 3) begin                    // last bit of a byte read: release SDA for the acknowledge
            i2cs_sdaout(1);
        end else if (i2cs_nb == 9) begin                                    // end of the acknowledge clock
            i2cs_nb = 0;
            if (i2cs_ph == 1) i2cs_ph = i2cs_rw ? 3 : 2;
            if (i2cs_ph == 3) begin
                i2cs_cur = i2cs_rbyte(i2cs_idx); i2cs_idx = i2cs_idx + 1; i2cs_segr = i2cs_segr + 1; i2cs_sdaout(i2cs_cur[7]);
            end else if (i2cs_ph == 4) i2cs_sdaout(1);
            else i2cs_sdaout(1);
        end else if (i2cs_ph == 3 && i2cs_nb < 8) begin                     // data bit of a read
            i2cs_sdaout(i2cs_cur[7 - i2cs_nb]);
        end
        // ---- stretch: after the falling edge, at any bit including the acknowledge
        n = 0;
        if (i2cs_strp > 0 && i2cs_str > 0 && ($random(i2cs_seed) & 32'h7fffffff) % 100 < i2cs_strp) n = 1 + ($random(i2cs_seed) & 32'h7fffffff) % i2cs_str;
        if (i2cs_strack > 0 && i2cs_nb == 0 && i2cs_pulses % 9 == 0) n = i2cs_strack;     // after the ninth clock
        if (n > 0) begin
            i2cs_stretchrun = 1; xl_a[5] = 1; i2cs_nstr = i2cs_nstr + 1; if (n > i2cs_strmax) i2cs_strmax = n;
            repeat (n) @(posedge clk);
            xl_a[5] = 0; i2cs_stretchrun = 0;
        end
    end
end
task i2cs_final; begin
    if (i2cs_on) begin
        i2cs_segend;
        if (i2cs_err == 0) $display("I2CS PASS (%0d starts, SCL low min %0d, high min %0d cycles, SDA setup before SCL rise min %0d cycles)", i2cs_start_cnt, i2cs_lowmin, i2cs_highmin, i2cs_sumin);
        else $display("I2CS FAIL (%0d errors)", i2cs_err);
    end
end endtask
