// Model of a sensor with I2C interface and interrupt output, included in tb_sys.v.
// Pins: 4 SDA, 5 SCL, 6 interrupt (active low, open drain). Address 0x29.
// Register 0 is a status byte, registers 1 to 6 hold the sample. sens_event produces a new sample
// and pulls the interrupt line low. Reading register 1 takes a copy of the sample for the rest of
// the read and releases the interrupt line.
reg s_sda_low = 0, s_int_n = 1, sens_on = 1, sens_use = 0;
reg [7:0] s_seq = 0, s_snap = 0, s_sh = 0, s_ptr = 0, s_out = 0, s_tevt = 0;
reg [1:0] s_ph = 0;                 // 0 idle, 1 address, 2 write, 3 read
reg s_first = 0, s_rdone = 0; integer hframe = 0;
integer s_bit = 0, s_reads = 0, s_starts = 0, s_lost = 0;
reg [7:0] s_snaps [0:255];          // sample numbers in the order in which they were read
wire s_sda = uio_in[4], s_scl = uio_in[5];
function [7:0] s_reg(input [7:0] a, input [7:0] q);
    case (a)
        8'd0: s_reg = {7'd0, ~s_int_n};
        8'd1: s_reg = q;        8'd2: s_reg = ~q;        8'd3: s_reg = q * 3;
        8'd4: s_reg = q * 5;    8'd5: s_reg = q * 7;     8'd6: s_reg = 8'hA0 | q[3:0];
        default: s_reg = 8'hFF;
    endcase
endfunction
integer s_nlong = 0;
real s_t0 = 0, s_dur_min = 1e12, s_dur_max = 0, s_tl = 0, s_per_min = 1e12, s_per_max = 0;
always @(posedge s_scl) if (sens_use && s_ph != 0) begin if ($realtime - s_tl < 100000) begin if ($realtime - s_tl > 30000 && s_nlong < 8) begin s_nlong = s_nlong + 1; $display("SCL period of %0.1f us at %0.3f ms (bit %0d, phase %0d)", ($realtime - s_tl) / 1000, $realtime / 1e6, s_bit, s_ph); end if ($realtime - s_tl < s_per_min) s_per_min = $realtime - s_tl; if ($realtime - s_tl > s_per_max) s_per_max = $realtime - s_tl; end s_tl = $realtime; end     // SCL period inside a transfer
task sens_event; begin s_seq = s_seq + 1; s_tevt = hframe; if (s_int_n) s_t0 = $realtime; else s_lost = s_lost + 1; s_int_n = 0; end endtask
always @(negedge s_sda) if (s_scl && sens_use) begin s_ph = 1; s_bit = 0; s_starts = s_starts + 1; end      // start
always @(posedge s_sda) if (s_scl && sens_use) begin                                                        // stop
    if (s_ph == 3 || s_rdone) begin if ($realtime - s_t0 > s_dur_max) s_dur_max = $realtime - s_t0; if ($realtime - s_t0 < s_dur_min) s_dur_min = $realtime - s_t0; end
    s_ph = 0; s_sda_low = 0; s_rdone = 0;
end
always @(posedge s_scl) if (s_ph != 0) begin
    if (s_bit < 8) begin s_sh = {s_sh[6:0], s_sda}; s_bit = s_bit + 1; end
    else begin if (s_ph == 3 && s_sda) begin s_ph = 0; s_rdone = 1; end s_bit = 9; end           // ninth bit; no acknowledge ends a read
end
always @(negedge s_scl) begin
    if (s_ph == 0) s_sda_low = 0;
    else if (s_bit == 8) begin                                            // ninth bit follows
        if (s_ph == 1) begin
            if (s_sh[7:1] == 7'h29 && sens_on) begin s_sda_low = 1; s_first = 1; end else begin s_ph = 0; s_sda_low = 0; end
        end else if (s_ph == 2) begin
            s_sda_low = 1;
            if (s_first) begin s_ptr = s_sh; s_first = 0; end else s_ptr = s_ptr + 1;
        end else s_sda_low = 0;
    end else if (s_bit == 9) begin                                        // first bit of the next byte
        s_bit = 0;
        if (s_ph == 1) s_ph = s_sh[0] ? 3 : 2;
        if (s_ph == 3) begin
            if (s_ptr == 1) begin s_snap = s_seq; s_int_n = 1; s_snaps[s_reads] = s_seq; s_reads = s_reads + 1; end
            s_out = s_reg(s_ptr, s_snap); s_ptr = s_ptr + 1; s_sda_low = ~s_out[7];
        end else s_sda_low = 0;
    end else if (s_ph == 3) s_sda_low = ~s_out[7 - s_bit];
end
