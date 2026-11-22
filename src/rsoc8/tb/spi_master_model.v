// Model of an SPI master (the chip is the slave), included in tb_sys.v. Written from the definition of SPI,
// not from the line cell code. Enabled by +spimst.
// Pins: 0 MOSI (driven by the model), 1 SCK (driven), 2 MISO (input of the model; it must be released by the chip while
// CS is high), 3 CS (driven, active low), 4 ready (output of the chip, to be pulled low by +pd=10: the model starts a
// transfer when it is high; the firmware drops it when CS rises).
// Plusargs: +spimst_mode=n   clock mode: CPOL = n[1], CPHA = n[0]; data most significant bit first
//           +spimst_hp=n     half period of SCK in clock cycles (bit time 2 n), default 8
//           +spimst_cs=n     clock cycles from CS low to the first clock edge, default 40
//           +spimst_hold=n   clock cycles from the last clock edge to CS high, default 8
//           +spimst_n=n      bytes per transfer, default 4;  +spimst_xfers=n  number of transfers, default 3
//           +spimst_gap=n    extra clock cycles between two bytes of a transfer (0: continuous clock), default 0
//           +spimst_idle=n   clock cycles from CS high to the next CS low, default 400
//           +spimst_mdly=n   MOSI changes n cycles after the shifting edge (setup of MOSI at the chip = hp - n), default 0
//           +spimst_start=n  clock cycles from the ready signal to the first CS low, default 100
//           +spimst_abort=n  the first transfer is ended with CS high after n bits (the second one is complete)
//           +spimst_rel=n    longest allowed time in cycles from CS high to the release of MISO by the chip, default 8
//           +spimst_v        print every byte
// The model samples MISO at the sampling edge, in the clock cycle before the edge is visible on the pin, so a MISO
// change that coincides with the edge is not seen (setup 0 = error). It checks the bytes on MISO against 0x3C + 53 i,
// measures the time from the shifting edge to the change of MISO and the setup of MISO before the sampling edge, and
// checks that the chip does not drive MISO while CS is high (uio_oe[2]).
reg sm_on = 0; reg [1:0] sm_m = 0;
integer sm_hp = 8, sm_cs = 40, sm_hold = 8, sm_n = 4, sm_xfers = 3, sm_gap = 0, sm_idle = 400, sm_mdly = 0, sm_start = 100, sm_abort = 0, sm_v = 0;
integer sm_su_all = 1000, sm_err = 0, sm_done = 0, sm_bad = 0, sm_tco = 0, sm_tco_max = 0, sm_su = 0, sm_su_min = 1000, sm_t_miso = 0, sm_t_edge = 0, sm_rel_bad = 0;
reg sm_shift_pend = 0; integer sm_t_shift = 0;
reg sm_busy = 0;
wire sm_miso = uio_in[2];
function [7:0] sm_tx(input integer i); sm_tx = 8'hA5 + 29 * i; endfunction
function [7:0] sm_exp(input integer i); sm_exp = 8'h3C + 53 * i; endfunction
// timing of MISO after the shifting edge, and release of MISO while CS is high
always @(sm_miso) if (sm_on && sm_busy) begin
    sm_t_miso = xcyc;
    if (sm_shift_pend) begin sm_tco = xcyc - sm_t_shift; if (sm_tco > sm_tco_max) sm_tco_max = sm_tco; sm_shift_pend = 0; end
end
integer sm_t_csh = 0, sm_rel = 0, sm_rel_max = 0, sm_rel_lim = 8, sm_drv_cs = 0; reg sm_csh = 1;
always @(posedge clk) if (sm_on) begin
    if (uio_in[3] === 1'b1) begin
        if (!sm_csh) begin sm_csh = 1; sm_rel = -1; end
        if (uio_oe[2]) sm_rel = xcyc - sm_t_csh + 1;                 // time of the last cycle in which the chip still drove MISO
        if (uio_oe[2] && xcyc - sm_t_csh + 1 > sm_rel_lim) begin
            if (sm_rel_bad == 0) $display("SPIMST FAIL: the chip drives MISO %0d cycles after CS rises", xcyc - sm_t_csh + 1);
            sm_rel_bad = sm_rel_bad + 1; sm_err = sm_err + 1;
        end
    end else begin
        if (sm_csh) begin sm_csh = 0; if (sm_rel > sm_rel_max) sm_rel_max = sm_rel; end
    end
end
reg [7:0] sm_sh; integer sm_k, sm_b, sm_x, sm_nb, sm_nbits; reg sm_cpol, sm_cpha;
reg [7:0] sm_got [0:255];
task sm_wait(input integer n); begin if (n > 0) repeat (n) @(posedge clk); end endtask
// one clock edge at the next clock edge of the testbench: the pin changes after it
task sm_sck(input v); begin @(posedge clk); x_val[1] <= v; sm_t_edge = xcyc; end endtask
task sm_mosi(input v); begin
    if (sm_mdly == 0) x_val[0] <= v; else begin repeat (sm_mdly) @(posedge clk); x_val[0] <= v; end
end endtask
// the bit time is 2 hp cycles; the edges are at the start of the bit (CPHA = 1) or in its middle (CPHA = 0)
task sm_xfer(input integer nbits);
    integer bit_i, byte_i; reg mb;
    begin
        sm_busy = 1; sm_bad = 0; sm_tco_max = 0; sm_su_min = 1000; sm_shift_pend = 0; byte_i = 0;
        @(posedge clk); x_val[3] <= 0;                                     // CS low
        sm_cpol = sm_m[1]; sm_cpha = sm_m[0];
        if (!sm_cpha) x_val[0] <= sm_tx(0) >> 7;                           // first bit before the first edge
        sm_wait(sm_cs - 1);
        for (bit_i = 0; bit_i < nbits; bit_i = bit_i + 1) begin
            byte_i = bit_i / 8;
            if (bit_i % 8 == 0 && bit_i > 0) sm_wait(sm_gap);
            if (!sm_cpha) begin
                @(posedge clk); x_val[1] <= ~sm_cpol; sm_t_edge = xcyc;       // leading edge = sampling edge
                sm_sh = {sm_sh[6:0], sm_miso};                              // the value before the edge
                sm_su = sm_t_edge - sm_t_miso; if (sm_su < sm_su_min) sm_su_min = sm_su; if (sm_su < sm_su_all) sm_su_all = sm_su;
                sm_wait(sm_hp - 1);
                @(posedge clk); x_val[1] <= sm_cpol; sm_t_edge = xcyc; sm_t_shift = xcyc; sm_shift_pend = 1;      // trailing edge = shifting edge
                if (bit_i % 8 == 7) begin sm_got[byte_i] = sm_sh; end
                if (bit_i + 1 < nbits) begin mb = sm_tx((bit_i + 1) / 8) >> (7 - ((bit_i + 1) % 8)); if (sm_mdly == 0) x_val[0] <= mb; else x_val[0] <= #(sm_mdly * 10) mb;
                    sm_wait(sm_hp - 1); end
            end else begin
                @(posedge clk); x_val[1] <= ~sm_cpol; sm_t_edge = xcyc; sm_t_shift = xcyc; sm_shift_pend = 1;      // leading edge = shifting edge
                mb = sm_tx(bit_i / 8) >> (7 - (bit_i % 8)); if (sm_mdly == 0) x_val[0] <= mb; else x_val[0] <= #(sm_mdly * 10) mb;
                sm_wait(sm_hp - 1);
                @(posedge clk); x_val[1] <= sm_cpol; sm_t_edge = xcyc;       // trailing edge = sampling edge
                sm_sh = {sm_sh[6:0], sm_miso};
                sm_su = sm_t_edge - sm_t_miso; if (sm_su < sm_su_min) sm_su_min = sm_su; if (sm_su < sm_su_all) sm_su_all = sm_su;
                if (bit_i % 8 == 7) begin sm_got[byte_i] = sm_sh; end
                if (bit_i + 1 < nbits) sm_wait(sm_hp - 1);
            end
        end
        sm_wait(sm_hold - 1);
        @(posedge clk); x_val[3] <= 1; sm_t_csh = xcyc;                    // CS high
        sm_busy = 0;
        for (byte_i = 0; byte_i < nbits / 8; byte_i = byte_i + 1) begin
            if (sm_got[byte_i] !== sm_exp(byte_i)) begin sm_bad = sm_bad + 1; if (sm_v || sm_bad <= 3) $display("SPIMST byte %0d from the chip %02x, expected %02x", byte_i, sm_got[byte_i], sm_exp(byte_i)); end
            else if (sm_v) $display("SPIMST byte %0d %02x ok", byte_i, sm_got[byte_i]);
        end
        if (nbits >= 8) begin
            sm_err = sm_err + (sm_bad != 0);
            if (sm_su_min < 1) begin sm_err = sm_err + 1; $display("SPIMST FAIL: MISO changes in the cycle of the sampling edge"); end
            $display("SPIMST mode %0d transfer %0d: %0d bytes, bad %0d, half period %0d, CS to first edge %0d, pauses %0d cycles, MISO change after the shifting edge max %0d cycles, MISO setup min %0d cycles",
                     sm_m, sm_done + 1, nbits / 8, sm_bad, sm_hp, sm_cs, sm_gap, sm_tco_max, sm_su_min);
        end else $display("SPIMST transfer %0d aborted after %0d bits", sm_done + 1, nbits);
        sm_done = sm_done + 1;
    end
endtask
initial begin
    #1;
    if ($test$plusargs("spimst")) begin
        sm_on = 1;
        if ($value$plusargs("spimst_mode=%d", sm_m)) ;
        if ($value$plusargs("spimst_hp=%d", sm_hp)) ;
        if ($value$plusargs("spimst_cs=%d", sm_cs)) ;
        if ($value$plusargs("spimst_hold=%d", sm_hold)) ;
        if ($value$plusargs("spimst_n=%d", sm_n)) ;
        if ($value$plusargs("spimst_xfers=%d", sm_xfers)) ;
        if ($value$plusargs("spimst_gap=%d", sm_gap)) ;
        if ($value$plusargs("spimst_idle=%d", sm_idle)) ;
        if ($value$plusargs("spimst_mdly=%d", sm_mdly)) ;
        if ($value$plusargs("spimst_start=%d", sm_start)) ;
        if ($value$plusargs("spimst_abort=%d", sm_abort)) ;
        if ($value$plusargs("spimst_rel=%d", sm_rel_lim)) ;
        if ($test$plusargs("spimst_v")) sm_v = 1;
        x_oe[0] = 1; x_oe[1] = 1; x_oe[3] = 1; x_val[3] = 1; x_val[1] = sm_m[1]; x_val[0] = 0;
        for (sm_x = 0; sm_x < sm_xfers; sm_x = sm_x + 1) begin
            wait (uio_in[4] === 1'b1); sm_wait(sm_start);
            if (sm_x == 0 && sm_abort != 0) sm_xfer(sm_abort); else sm_xfer(8 * sm_n);
            sm_wait(sm_idle);
        end
    end
end
task spimst_final; begin
    if (sm_on) begin
        if (sm_done < sm_xfers) begin sm_err = sm_err + 1; $display("SPIMST FAIL: the test ended after %0d of %0d transfers", sm_done, sm_xfers); end
        if (sm_err == 0) $display("SPIMST PASS (%0d transfers, MISO setup min %0d cycles, MISO released at most %0d cycles after CS high)", sm_done, sm_su_all, sm_rel_max);
        else $display("SPIMST FAIL (%0d errors in %0d transfers)", sm_err, sm_done);
    end
end endtask
// +spimst_trace: times of the clock edges and of the state of transmit cell 0 (hierarchical references), in cycles from CS low
integer sm_trace = 0, sm_t0cs = 0;
always @(negedge uio_in[3]) sm_t0cs = xcyc;
always @(uio_in[1]) if (sm_on && sm_trace && !uio_in[3]) $display("TRACE %0d SCK %b", xcyc - sm_t0cs, uio_in[1]);
always @(top.u.ports.t0.tbusy) if (sm_on && sm_trace) $display("TRACE %0d BUSY %b", xcyc - sm_t0cs, top.u.ports.t0.tbusy);
always @(top.u.ports.t0.tbuf_full) if (sm_on && sm_trace) $display("TRACE %0d TXE %b", xcyc - sm_t0cs, ~top.u.ports.t0.tbuf_full);
always @(uio_in[2]) if (sm_on && sm_trace) $display("TRACE %0d MISO %b", xcyc - sm_t0cs, uio_in[2]);
initial begin #1; if ($test$plusargs("spimst_trace")) sm_trace = 1; end
