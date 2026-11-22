// System testbench: the Tiny Tapeout top level rpe_chip with the simulation model of the
// IHP SRAM macro (tb/ihp, compile with -DFUNCTIONAL). Runs firmware built with avr-gcc. A model of
// the SPI host releases the core reset.
//   +hex0=file +hex1=file   code memory images (16-bit words); +hex=file: one image of 2K words for core 0
//   a write to fast I/O address 0x1F ends the simulation with that value as exit code
//   +cdiv=n: the host writes CLKCDIV = n - 1 before it releases the core reset (default n = 1; the reset value of
//            the register gives divider 2, which is kept with +cdivreset)
//   +duty=<percent>: duty cycle of the external clock; +ethm=<n> and related plusargs: Ethernet model, see tb/eth_model.v
//   bidirectional pins: undriven pins read high (+pd=<hex mask>: low); +loop=xy connects pin x to pin y (x drives y)
`timescale 1ns/1ps
module tb_sys;
    reg clk_x = 0, rst_x = 1;          // external clock and reset pin
    initial #1 rst_x = 0;
    // external clock, period 10 ns; +duty=<percent> sets the percentage of the period that the clock is high (default 50)
    integer duty = 50; real clk_th = 5.0, clk_tl = 5.0;
    initial begin
        if ($value$plusargs("duty=%d", duty)) begin clk_th = 10.0 * duty / 100.0; clk_tl = 10.0 - clk_th; end
        forever begin #(clk_tl) clk_x = 1; #(clk_th) clk_x = 0; end
    end
    // ---------------------------------------------------------------- device: the Tiny Tapeout top level
    wire [7:0] uio_out, uio_oe, out_pins; reg [7:0] uio_in; reg [7:0] in_pins = 8'h02;
    rpe_chip top (.ui_in(in_pins), .uo_out(out_pins), .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
                           .ena(1'b1), .clk(clk_x), .rst_n(rst_x));
    // signals inside the device that the testbench observes
    wire clk = top.u.clk, rst_n = top.u.rst_sys_n, rst_c = top.u.rst_c;
    wire [8:0] io_addr = top.u.io_addr; wire io_we = top.u.io_we, io_core = top.u.io_core, io_host = top.u.io_host;
    wire [7:0] io_wdata = top.u.io_wdata;
    wire [10:0] pc0 = top.u.pc0; wire [9:0] pc1 = top.u.pc1;
    wire [1:0] core_en = top.u.core_en, core_wait = top.u.core_wait, brk_flag = top.u.brk_flag;
    `define ROM0 top.u.m_code0.u_mem.i_SRAM_1P_behavioral_bm_bist.memory
    `define ROM1 top.u.m_code1.u_mem.i_SRAM_1P_behavioral_bm_bist.memory
    `define RAMW top.u.m_data.u_mem.i_SRAM_1P_behavioral_bm_bist.memory
    reg [15:0] romx [0:2047];
    integer cdiv = 1;

    // reference signal on input pin 4 (+ref=half period in ps)
    integer ref_half = 0;
    initial begin #2; if ($value$plusargs("ref=%d", ref_half)) forever begin #(ref_half / 1000.0) in_pins[4] = ~in_pins[4]; end end
    // counts rising edges of the clock output and the debug pin since the last write to fast address 0x1D
    integer n_cko = 0, n_dbg = 0;
    real t_cko = 0, p_cko = 0;
    always @(posedge out_pins[1]) begin n_cko = n_cko + 1; p_cko = $realtime - t_cko; t_cko = $realtime; end
    always @(posedge out_pins[2]) n_dbg = n_dbg + 1;
    always @(posedge clk) if (io_we && io_addr == 9'h01D) begin
        if (n_cko > 0 || n_dbg > 0) $display("PINS clock output %0d debug %0d, period of the clock output %0.1f ns, value written %0d", n_cko, n_dbg, p_cko, io_wdata);
        n_cko = 0; n_dbg = 0;
    end

    // duty measurement of the PWM pins: cycles high per pin since the last write to fast address 0x1E
    integer pwh [0:2]; integer pwn = 0; initial begin pwh[0] = 0; pwh[1] = 0; pwh[2] = 0; end
    always @(posedge clk) begin
        if (io_we && io_addr == 9'h01E) begin
            if (pwn > 0 && pwh[2] > 0) $display("PWM cycles %0d high %0d %0d %0d", pwn, pwh[0], pwh[1], pwh[2]);
            pwh[0] = 0; pwh[1] = 0; pwh[2] = 0; pwn = 0; end
        else begin pwn = pwn + 1; pwh[0] = pwh[0] + out_pins[5]; pwh[1] = pwh[1] + out_pins[6]; pwh[2] = pwh[2] + out_pins[7]; end
    end

    // pins: a driven pin shows its output, others are pulled high; optional connection from one pin to another
    integer lp_from = -1, lp_to = -1, lp, i, cyc = 0, maxcyc = 2000000;
    reg [7:0] line; reg [7:0] pulldn = 8'h00; reg [15:0] shorts = 16'h0000;       // +pd=<hex mask>: these undriven pins read low
    `include "tb/i2c_sensor.v"
    `include "tb/usb_host.v"
    // external models on the bidirectional pins (spi_*, i2c_* models below): a model that drives a pin sets its bit
    // in x_oe and the level in x_val; the pin then has the level of the model ANDed with the chip's output if the
    // chip drives it as well. xcyc counts clock cycles of the chip. All models are off unless their plusarg is given.
    reg [7:0] x_oe = 8'h00, x_val = 8'hFF; integer xcyc = 0;
    // open-drain pull-down masks of the two I2C models (slave model xl_a, master model xl_b): a bit set pulls the pin low
    reg [7:0] xl_a = 8'h00, xl_b = 8'h00;
    always @(posedge clk) xcyc = xcyc + 1;
    `include "tb/spi_slave_model.v"
    `include "tb/spi_master_model.v"
    `include "tb/i2c_slave_model.v"
    `include "tb/i2c_master_model.v"
`include "tb/ws2812_model.v"
`include "tb/uart_model.v"
`include "tb/stress.v"
    initial begin #0.5; if ($value$plusargs("urx=%d", URX)) ; if ($value$plusargs("utx=%d", UTX)) ; if ($value$plusargs("wpin=%d", WPIN)) ; end
    `include "tb/eth_model.v"
    always @(posedge clk) if (io_we && io_addr == 9'h01E && io_wdata == 8'hB5) n_busrst = n_busrst + 1;
    // +wave=<file>: one line per clock cycle with pins and line cell signals, between a write of a value
    // other than 0 to fast address 0x19 and a write of 0. Used to draw the timing diagrams of the datasheet.
    integer wv_f = 0; reg wv_on = 0; reg [1023:0] wv_name; integer wv_c = 0;
    initial if ($value$plusargs("wave=%s", wv_name)) wv_f = $fopen(wv_name, "w");
    always @(posedge clk) if (wv_f != 0) begin
        if (io_we && io_addr == 9'h019) begin
            wv_on = (io_wdata != 0); wv_c = 0;
            if (wv_on) begin                                  // configuration of the four cells, as comment lines
                $fdisplay(wv_f, "# R0 %02x %02x 00 %02x %02x %02x %02x 00 %02x 00 %02x %02x %02x %02x %02x", top.u.ports.r0.r_ctrl, top.u.ports.r0.r_pin, top.u.ports.r0.r_clk, top.u.ports.r0.r_tim, top.u.ports.r0.r_a, top.u.ports.r0.r_b, top.u.ports.r0.r_dec, top.u.ports.r0.r_sh, top.u.ports.r0.r_match, top.u.ports.r0.r_run, top.u.ports.r0.r_evm, top.u.ports.r0.r_cs);
                $fdisplay(wv_f, "# R1 %02x %02x 00 %02x %02x %02x %02x 00 %02x 00 %02x %02x %02x %02x %02x", top.u.ports.r1.r_ctrl, top.u.ports.r1.r_pin, top.u.ports.r1.r_clk, top.u.ports.r1.r_tim, top.u.ports.r1.r_a, top.u.ports.r1.r_b, top.u.ports.r1.r_dec, top.u.ports.r1.r_sh, top.u.ports.r1.r_match, top.u.ports.r1.r_run, top.u.ports.r1.r_evm, top.u.ports.r1.r_cs);
                $fdisplay(wv_f, "# T0 %02x %02x %02x %02x %02x %02x %02x %02x 00 %02x %02x 00 %02x %02x %02x", top.u.ports.t0.r_ctrl, top.u.ports.t0.r_pin, top.u.ports.t0.r_out, top.u.ports.t0.r_clk, top.u.ports.t0.r_tim, top.u.ports.t0.r_a, top.u.ports.t0.r_b, top.u.ports.t0.r_c, top.u.ports.t0.r_enc, top.u.ports.t0.r_sh, top.u.ports.t0.r_run, top.u.ports.t0.r_evm, top.u.ports.t0.r_cs);
            end
        end
        if (wv_on) begin
            $fdisplay(wv_f, "%0d %02x %b %b %b %02x %02x %b %b %b %02x %02x %b %b %b %b", wv_c, uio_in,
                top.u.ports.r0.dbg_acc, top.u.ports.r0.dbg_smp, top.u.ports.r0.run, top.u.ports.rstat0, top.u.ports.tstat0,
                top.u.ports.r1.dbg_acc, top.u.ports.r1.dbg_smp, top.u.ports.r1.run, top.u.ports.rstat1, top.u.ports.tstat1,
                top.u.ports.t0.data_we, top.u.ports.r0.data_re, top.u.ports.t1.data_we, top.u.ports.r1.data_re);
            wv_c = wv_c + 1;
        end
    end
    function net(input [2:0] pa, input [2:0] pb);
        net = (uio_oe[pa] & uio_oe[pb]) ? (uio_out[pa] & uio_out[pb]) : uio_oe[pa] ? uio_out[pa] : uio_oe[pb] ? uio_out[pb] : ~pulldn[pa];
    endfunction
    always @(uio_oe or uio_out or pulldn or shorts or lp_from or lp_to or eth_on or eth_pin or h_en or h_dp or h_dm or s_sda_low or s_int_n or sens_use or u_txd or u_on or x_oe or x_val or xl_a or xl_b or em_on or em_pin) begin
        for (i = 0; i < 8; i = i + 1) line[i] = uio_oe[i] ? uio_out[i] : ~pulldn[i];
        uio_in = line;
        if (lp_from >= 0) uio_in[lp_to] = line[lp_from] & line[lp_to];
        // +short=<hex digits abcd>: pin a is wired to pin b, pin c to pin d. A wired pair has the level of
        // its driver, the AND of both if both drive, and the level of the pull resistor if none drives.
        if (shorts[15:12] != shorts[11:8]) begin uio_in[shorts[14:12]] = net(shorts[14:12], shorts[10:8]); uio_in[shorts[10:8]] = uio_in[shorts[14:12]]; end
        if (shorts[7:4] != shorts[3:0])    begin uio_in[shorts[6:4]] = net(shorts[6:4], shorts[2:0]);     uio_in[shorts[2:0]] = uio_in[shorts[6:4]]; end
        if (eth_on) uio_in[1] = eth_pin;
        if (em_on) uio_in[1] = em_pin;                // independent Ethernet model (tb/eth_model.v)
        if (sens_use) begin uio_in[4] = line[4] & ~s_sda_low; uio_in[6] = line[6] & s_int_n; end      // sensor model
        if (u_on) uio_in[URX] = u_txd;                                  // UART model drives the chip receive pin 4 (+uart)
        if (h_en) begin uio_in[0] = h_dp; uio_in[1] = h_dm; end      // USB host model drives D+ and D-
        for (i = 0; i < 8; i = i + 1) if (x_oe[i]) uio_in[i] = uio_oe[i] ? (uio_out[i] & x_val[i]) : x_val[i];
        uio_in = uio_in & ~(xl_a | xl_b);
    end

    always @(posedge clk) begin
        if (rst_c) cyc <= cyc + 1;
        if (rst_c && io_we && !io_host && io_addr == 9'h01F) begin
            spislv_final; spimst_final; i2cs_final; i2cm_final;
            $display("EXIT %0d (core %0d) cycles %0d", io_wdata, io_core, cyc); $finish;
        end
        if (cyc > maxcyc) begin $display("TIMEOUT pc0=%03x pc1=%03x en=%b wait=%b brk=%b", pc0, pc1, core_en, core_wait, brk_flag); $finish; end
    end

    // +wlog: log of event flags, waits, instruction starts and interrupt acknowledges (arbitration tests, WL lines)
    //   WL cyc FLAGS f0 f1      the event flags as core 0 and core 1 see them changed
    //   WL cyc WAIT bb          core_wait changed
    //   WL cyc S c pc take irq  core c starts an instruction at word address pc; take = interrupt entry; irq = request pending
    //   WL cyc W c addr data    core c writes the register bus (only addresses 0x1A..0x1C: markers of the firmware)
    reg wlog = 0; reg [15:0] wl_f0, wl_f1; reg [1:0] wl_w;
    initial begin if ($test$plusargs("wlog")) wlog = 1; wl_f0 = 0; wl_f1 = 0; wl_w = 0; end
    always @(posedge clk) if (wlog && rst_c) begin
        if (top.u.evt[15:0] !== wl_f0 || top.u.evt[31:16] !== wl_f1) $display("WL %0d FLAGS %04x %04x", cyc, top.u.evt[15:0], top.u.evt[31:16]);
        wl_f0 <= top.u.evt[15:0]; wl_f1 <= top.u.evt[31:16];
        if (core_wait !== wl_w) $display("WL %0d WAIT %b", cyc, core_wait);
        wl_w <= core_wait;
        if (top.u.core_cen[0] && top.u.cores.core0.state == 0) $display("WL %0d S 0 %03x %b %b", cyc, top.u.cores.core0.pc - 11'd1, top.u.cores.core0.irq_take, |top.u.cores.core0.irq);
        if (top.u.core_cen[1] && top.u.cores.core1.state == 0) $display("WL %0d S 1 %03x %b %b", cyc, top.u.cores.core1.pc - 10'd1, top.u.cores.core1.irq_take, |top.u.cores.core1.irq);
        if (io_we && !io_host && io_addr >= 9'h01A && io_addr <= 9'h01C) $display("WL %0d W %0d %02x %02x", cyc, io_core, io_addr, io_wdata);
    end

    // 10BASE-T generator on pin 1 (+eth=bit time in ps, +ethn=payload bytes, +ethstart=delay in ps):
    // idle low, each bit is the inverted data bit followed by the data bit, least significant bit first
    reg [31:0] ecrc; integer eth_bad = 0;
    reg eth_on = 0, eth_pin = 0; integer eth_bit = 0, eth_n = 24, eth_start = 4000000, eb, ek; reg [7:0] ebyte;
    task eth_byte(input [7:0] v); begin
        for (ek = 0; ek < 8; ek = ek + 1) begin
            eth_pin = ~v[ek]; #(eth_bit / 2000.0); eth_pin = v[ek]; #(eth_bit / 2000.0);
        end
    end endtask
    initial begin
        #1;
        if ($value$plusargs("eth=%d", eth_bit)) begin
            if ($value$plusargs("ethn=%d", eth_n)) ;
            if ($value$plusargs("ethbad=%d", eth_bad)) ;
            if ($value$plusargs("ethstart=%d", eth_start)) ;
            eth_on = 1; #(eth_start / 1000.0);
            for (eb = 0; eb < 7; eb = eb + 1) eth_byte(8'h55);
            eth_byte(8'hD5);
            ecrc = 32'hFFFFFFFF;
            for (eb = 0; eb < eth_n; eb = eb + 1) begin
                ebyte = eb * 37 + 11;
                for (ek = 0; ek < 8; ek = ek + 1) ecrc = (ecrc[0] ^ ebyte[ek]) ? (ecrc >> 1) ^ 32'hEDB88320 : ecrc >> 1;
                if (eth_bad == eb + 1) ebyte = ebyte ^ 8'h10;          // +ethbad=n: one wrong bit in byte n
                eth_byte(ebyte);
            end
            if ($test$plusargs("ethfcs")) begin                        // frame check sequence, then the idle pulse
                ecrc = ~ecrc;
                eth_byte(ecrc[7:0]); eth_byte(ecrc[15:8]); eth_byte(ecrc[23:16]); eth_byte(ecrc[31:24]);
                eth_pin = 1; #(3 * eth_bit / 1000.0);
            end
            eth_pin = 0;
        end
    end
    // ---------------------------------------------------------------- SPI master of the host
    real spi_half = 53.0;                  // ns; the clock of the testbench is 10 ns, so about 10.6 cycles per bit
    reg [7:0] srx; integer herrs = 0;
    task spi_start; begin in_pins[1] = 0; #(spi_half); end endtask
    task spi_stop;  begin #(spi_half) in_pins[1] = 1; #(4 * spi_half); end endtask
    task spi_byte(input [7:0] v); integer k; begin
        for (k = 7; k >= 0; k = k - 1) begin
            in_pins[2] = v[k]; #(spi_half) srx[k] = out_pins[0]; in_pins[0] = 1; #(spi_half) in_pins[0] = 0;
        end
    end endtask
    task h_ctrl(input [7:0] v); begin spi_start; spi_byte(8'h04); spi_byte(v); spi_stop; end endtask
    task h_wr(input [15:0] a, input [7:0] v); begin spi_start; spi_byte(8'h02); spi_byte(a[15:8]); spi_byte(a[7:0]); spi_byte(v); spi_stop; end endtask
    reg [7:0] hv, hv2, hs0, hs1; reg [15:0] hpc;
    task h_rd(input [15:0] a); begin
        spi_start; spi_byte(8'h03); spi_byte(a[15:8]); spi_byte(a[7:0]); spi_byte(0); spi_byte(0); hv = srx; spi_byte(0); hv2 = srx; spi_stop;
    end endtask
    task h_rd1(input [15:0] a); begin
        spi_start; spi_byte(8'h03); spi_byte(a[15:8]); spi_byte(a[7:0]); spi_byte(0); spi_byte(0); hv = srx; spi_stop;
    end endtask
    task h_status; begin
        spi_start; spi_byte(8'h05); spi_byte(0); spi_byte(0); hs0 = srx; spi_byte(0); hs1 = srx; spi_byte(0); hpc[15:8] = srx; spi_byte(0); hpc[7:0] = srx; spi_stop;
    end endtask
    task h_ins(input [7:0] c, input [15:0] w); begin spi_start; spi_byte(c); spi_byte(w[15:8]); spi_byte(w[7:0]); spi_stop; #400; end endtask
    task h_step; begin spi_start; spi_byte(8'h0A); spi_stop; #400; end endtask
    task hchk(input c, input [319:0] msg); begin if (!c) begin herrs = herrs + 1; $display("HOST FAIL: %0s (hv %02x %02x status %02x %02x pc %04x)", msg, hv, hv2, hs0, hs1, hpc); end end endtask
    task h_load(input integer mem); integer k, last; reg [15:0] w; begin
        last = -1; for (k = 0; k < 1024; k = k + 1) begin w = mem ? img1[k] : img0[k]; if (w !== 16'h0000) last = k; end
        if (last >= 0) begin
            spi_start; spi_byte(8'h02); spi_byte(mem ? 8'h48 : 8'h40); spi_byte(8'h00);
            for (k = 0; k <= last; k = k + 1) begin w = mem ? img1[k] : img0[k]; spi_byte(w[7:0]); spi_byte(w[15:8]); end
            spi_stop;
        end
    end endtask
    reg [15:0] img0 [0:1023]; reg [15:0] img1 [0:1023];
    integer htest = 0, spiload = 0, brk_adr = 0, pcs_seen, k2; reg [15:0] c1, c2, pcl; reg [7:0] o0, o1, r16v;
    task host_test; begin
        #30000;
        // ---- running: status, access refused, mailbox
        h_status; hchk(hs0[1:0] == 2'b00 && hs1[1:0] == 2'b01 && hs0[7] == 0 && hs1[7] == 0, "status while running");
        h_rd(16'h0700); hchk(hv == 0, "read refused while the core runs");
        h_status; hchk(hs1[7] == 1, "error bit after a refused access");
        h_status; hchk(hs1[7] == 0, "error bit cleared by the status command");
        spi_start; spi_byte(8'h07); spi_byte(8'h41); spi_stop; #5000;
        spi_start; spi_byte(8'h08); spi_byte(0); spi_byte(0); hv = srx; spi_byte(0); hv2 = srx; spi_stop;
        hchk(hv[6] == 0 && hv2 == 8'h42, "mailbox echo");
        spi_start; spi_byte(8'h08); spi_byte(0); spi_byte(0); hv = srx; spi_stop; hchk(hv[6] == 1, "mailbox empty after the read");
        // ---- halt: memory stands still, registers of the peripherals
        h_ctrl(8'h01); h_status; hchk(hs0[0] && hs0[7], "halted, access allowed"); pcl = hpc;
        h_rd(16'h0700); c1 = {hv2, hv}; #20000; h_rd(16'h0700); c2 = {hv2, hv};
        hchk(c1 == c2 && c1 > 16'd20, "counter stands still while halted");
        h_rd(16'h4000); hchk({hv2, hv} == `ROM0[0], "read of the code memory");
        h_rd(16'h4000 + 2 * brk_adr); hchk({hv2, hv} == `ROM0[brk_adr], "read of the code memory at the function");
        h_wr(16'h0710, 8'h3C); h_rd(16'h0710); hchk(hv == 8'h3C, "write and read of the data memory");
        h_wr(16'h0002, 8'h96); #200; hchk(uio_out == 8'h96, "write to PORT by the host");
        h_rd(16'h0000); hchk(hv == 8'h96 && hv2 == 8'h96, "read of PINR; a register is read once per command");
        h_rd1(16'h3F21); hchk(hv == 8'h80, "read of OSCTRIM in the configuration page");
        h_wr(16'h3F51, 8'h01); h_rd1(16'h3F51); hchk(hv == 8'h01, "protected register written by the host"); h_wr(16'h3F51, 8'h02);
        h_status; hchk(hpc == pcl && hs1[7] == 0, "program counter unchanged by the accesses");
        // ---- single step
        pcs_seen = 0;
        for (k2 = 0; k2 < 6; k2 = k2 + 1) begin h_step; h_status; if (hpc != pcl) pcs_seen = pcs_seen + 1; pcl = hpc; end
        hchk(pcs_seen == 6, "six steps, six new program counter values");
        h_rd(16'h0700); c1 = {hv2, hv};
        for (k2 = 0; k2 < 60; k2 = k2 + 1) h_step;
        h_rd(16'h0700); c2 = {hv2, hv};
        hchk(c2 > c1 && c2 < c1 + 16'd8, "sixty steps execute the program: the counter advances");
        // ---- injection: save r16, load a value, store it, restore r16
        h_status; pcl = hpc;
        h_rd(16'h0060); o0 = hv; o1 = hv2;
        h_ins(8'h06, 16'hAD01); h_rd1(16'h0061); r16v = hv;            // sts 0x61, r16
        h_ins(8'h06, 16'hE50A); h_ins(8'h06, 16'hAD00);               // ldi r16, 0x5A; sts 0x60, r16
        h_rd1(16'h0060); hchk(hv == 8'h5A, "injected instructions executed");
        h_ins(8'h06, 16'hA501); h_ins(8'h06, 16'hAD00); h_rd1(16'h0060); hchk(hv == r16v, "register restored");
        h_wr(16'h0060, o0); h_wr(16'h0061, o1);
        h_status; hchk(hpc == pcl && hs1[7] == 0, "program counter unchanged by the injections");
        // ---- break point at the function tick
        h_rd(16'h0700); c1 = {hv2, hv};
        h_wr(16'h4000 + 2 * brk_adr, 8'h98); h_wr(16'h4001 + 2 * brk_adr, 8'h95);
        h_ctrl(8'h00); #20000;
        h_status; hchk(hs0[4] && hs0[0] && hs0[7], "break flag, core halted");
        hchk(hpc == brk_adr + 2, "program counter after the break point");
        h_wr(16'h4000 + 2 * brk_adr, rom_save[7:0]); h_wr(16'h4001 + 2 * brk_adr, rom_save[15:8]);
        h_ctrl(8'h01);                                                // halt request, so that the core stays halted
        h_ins(8'h09, 16'hCFFE);                                       // rjmp .-2: back to the instruction that was replaced
        h_status; hchk(hpc == brk_adr + 1, "program counter set back");
        h_ctrl(8'h00); #100; h_status; hchk(hs0[4] == 0 && hs0[0] == 0, "break flag cleared, core runs");
        #20000; h_ctrl(8'h01); h_rd(16'h0700); c2 = {hv2, hv}; hchk(c2 > c1 + 16'd3, "program continues after the break point");
        // ---- core 1 selected
        h_ctrl(8'h13); h_status; hchk(hs1[2] == 1 && hpc == 0 && hs0[1:0] == 2'b11, "status of core 1");
        h_ins(8'h06, 16'h0000); h_status; hchk(hs1[7] == 1, "injection into a core that is not enabled is refused");
        h_wr(16'h0022, 8'h05); h_rd1(16'h0022); hchk(hv == 8'h05, "interrupt enable mask of core 1 written and read");
        h_ctrl(8'h01); h_rd1(16'h0022); hchk(hv == 8'h00, "the mask of core 0 is a different register");
        // ---- end: the firmware exits when the host writes the variable
        if (herrs == 0) $display("HOST PASS"); else $display("HOST errors %0d", herrs);
        h_wr(16'h0702, 8'hA5); h_ctrl(8'h00);
    end endtask
    reg [15:0] rom_save;

    reg [1023:0] f0, f1;
    initial begin
        for (i = 0; i < 1024; i = i + 1) `RAMW[i] = 0;
        for (i = 0; i < 1024; i = i + 1) begin `ROM0[i] = 0; `ROM1[i] = 0; end
        if ($value$plusargs("hex=%s", f0)) begin
            for (i = 0; i < 2048; i = i + 1) romx[i] = 0;
            $readmemh(f0, romx);
            for (i = 0; i < 1024; i = i + 1) begin `ROM0[i] = romx[i]; `ROM1[i] = romx[i + 1024]; end
        end else begin
            if (!$value$plusargs("hex0=%s", f0)) begin $display("no image"); $finish; end
            $readmemh(f0, `ROM0);
            if ($value$plusargs("hex1=%s", f1)) $readmemh(f1, `ROM1);
        end
        if ($value$plusargs("loop=%d", lp)) begin lp_from = lp / 10; lp_to = lp % 10; end
        if ($value$plusargs("maxcyc=%d", maxcyc)) ;
        if ($value$plusargs("cdiv=%d", cdiv)) ;
        if ($value$plusargs("htest=%d", htest)) ;
        if ($value$plusargs("pd=%h", pulldn)) ;
        if ($value$plusargs("short=%h", shorts)) ;
        if ($value$plusargs("spihalf=%f", spi_half)) ;            // half period of the host clock in ns
        if ($test$plusargs("strap")) in_pins[3] = 1;               // start from the oscillator
        if ($value$plusargs("brk=%d", brk_adr)) ;
        if ($test$plusargs("spiload")) spiload = 1;
        for (i = 0; i < 1024; i = i + 1) begin img0[i] = `ROM0[i]; img1[i] = `ROM1[i]; end
        rom_save = `ROM0[brk_adr];
        if (spiload) for (i = 0; i < 1024; i = i + 1) begin `ROM0[i] = 16'hxxxx; `ROM1[i] = 16'hxxxx; end
        repeat (3) @(posedge clk_x); #1 rst_x = 1;
        // the host: load the program if asked for, release the core reset, then the test sequence
        #200;
        if (spiload) begin
            for (i = 0; i < 1024; i = i + 1) begin `ROM0[i] = 16'h0000; `ROM1[i] = 16'h0000; end
            h_load(0);
            for (i = 0; i < 1024; i = i + 1) if (`ROM0[i] !== img0[i]) herrs = herrs + 1;
            h_load(1);
            for (i = 0; i < 1024; i = i + 1) if (`ROM1[i] !== img1[i]) herrs = herrs + 1;
            if (herrs != 0) $display("HOST load errors %0d", herrs); else $display("HOST load ok");
            // reads through the host link while the core reset is still set
            h_status; hchk(hs0[7] == 1'b1, "status in the core reset: access allowed");
            h_rd(16'h4000); hchk({hv2, hv} === img0[0], "read of code memory 0 in the core reset");
            h_rd(16'h4802); hchk({hv2, hv} === img1[1], "read of code memory 1 in the core reset");
            if (herrs != 0) $display("HOST read in reset FAIL"); else $display("HOST read in reset ok");
        end
        if (!$test$plusargs("cdivreset")) h_wr(16'h3F22, cdiv - 1);   // the host sets the core divider (+cdiv=n, default 1); +cdivreset: reset value, divider 2
        h_ctrl(8'h00);
        if (htest == 1) host_test;
        if ($test$plusargs("sensor")) sens_use = 1;                              // +sensor: I2C sensor model on pins 4 to 6
        if ($test$plusargs("stress")) stress_test;                                 // +stress=n: two protocols at once (tb/stress.v)
        if ($test$plusargs("uart")) uart_test;                                   // +uart: UART model and its scenarios (tb/uart_model.v)
        if ($test$plusargs("usbhost")) begin pulldn[0] = 1; usb_test; end      // +usbhost: USB host model on pins 0 and 1
    end
endmodule
