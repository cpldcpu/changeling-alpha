// Directed tests with two pairs of line cells on a common pin bus: SPI master and slave in modes 0
// and 1, WS2812 forwarding within a pair, UART with prescaler, filter and glitches, holding
// register overflow, status clearing, enable. Self-checking.
`timescale 1ns/1ps
module tb_lc2;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;
    reg ptick_div = 0; reg pt = 1;
    always @(posedge clk) pt <= ptick_div ? ~pt : 1'b1;

    reg  [7:0] ext = 8'hFF, ext_en = 8'h00, glitch = 8'h00;      // pins driven by the testbench
    wire [7:0] pins;
    reg  [7:0] p1 = 8'hFF, p2 = 8'hFF, p3 = 8'hFF, pf = 8'hFF;
    always @(posedge clk) begin p1 <= pins ^ glitch; p2 <= p1; p3 <= p2; end   // output register, synchroniser
    always @(negedge clk) pf <= p2;

    reg        rcfg_we [0:1]; reg tcfg_we [0:1]; reg stat_we [0:1]; reg data_re [0:1]; reg data_we [0:1];
    reg  [3:0] cfg_a; reg [7:0] wd;
    wire [7:0] rstat [0:1]; wire [7:0] tstat [0:1]; wire [7:0] rdata [0:1];
    wire [1:0] rxs, rxb, mid, o_t, o_n, o_ct, o_cn, o_dr, revt, tevt, smp;
    wire [2:0] tsel [0:1]; wire [2:0] nsel [0:1];
    genvar g;
    generate for (g = 0; g < 2; g = g + 1) begin : p
        rlc_rx r (.clk(clk), .rst_n(rst_n), .ptick(pt), .pins_r(p3), .pins_f(pf),
            .cfg_we(rcfg_we[g]), .cfg_a(cfg_a), .cfg_wdata(wd), .cfg_rdata(),
            .stat(rstat[g]), .stat_we(stat_we[g]), .stat_wdata(wd), .rdata(rdata[g]), .data_re(data_re[g]),
            .nb_mid(mid[g]), .rx_strobe(rxs[g]), .rx_bit(rxb[g]), .evt(revt[g]), .ref_evt(), .dbg_smp(smp[g]), .dbg_acc());
        rlc_tx t (.clk(clk), .rst_n(rst_n), .ptick(pt), .pins_r(p3),
            .cfg_we(tcfg_we[g]), .cfg_a(cfg_a), .cfg_wdata(wd), .cfg_rdata(),
            .stat(tstat[g]), .data_we(data_we[g]), .data_wdata(wd),
            .nb_strobe(rxs[g]), .nb_bit(rxb[g]), .tx_mid(mid[g]), .tx_strobe(), .tx_bit(),
            .o_true(o_t[g]), .o_second(o_n[g]), .o_claim_t(o_ct[g]), .o_claim_n(o_cn[g]), .o_tsel(tsel[g]),
            .o_nsel(nsel[g]), .o_drive(o_dr[g]), .o_ddr(), .evt(tevt[g]));
    end endgenerate

    // pin multiplexer: the cell with the lowest number has priority, within a cell the true output;
    // a pin that nothing drives reads high (pull-up)
    reg [7:0] pv; integer i, k;
    always @* begin
        pv = 8'hFF;
        for (i = 0; i < 8; i = i + 1) begin
            if (ext_en[i]) pv[i] = ext[i];
            for (k = 1; k >= 0; k = k - 1) begin
                if (o_cn[k] && nsel[k] == i && o_dr[k]) pv[i] = o_n[k];
                if (o_ct[k] && tsel[k] == i && o_dr[k]) pv[i] = o_t[k];
            end
        end
    end
    assign pins = pv;

    integer errors = 0, n;

    // SPI master: every sample point is at the clock edge in the middle of the bit
    reg spi_on = 0, spi_m1 = 0, smp_d = 0, sck_d = 0; integer nsmp = 0;
    always @(posedge clk) begin
        smp_d <= spi_on & smp[0]; sck_d <= o_n[0];
        if (spi_on & smp[0]) nsmp <= nsmp + 1;
        if (smp_d && !(sck_d == spi_m1 && o_n[0] == ~spi_m1)) begin
            errors = errors + 1; $display("FAIL SPI master: sample point is not at the sampling clock edge");
        end
    end
    // width of a low pulse on pin 5, in clock cycles
    integer lowlen = 0, lastlow = 0;
    always @(posedge clk) begin
        if (!pins[5]) lowlen <= lowlen + 1;
        else begin if (lowlen != 0) lastlow <= lowlen; lowlen <= 0; end
    end

    task cw(input t, input integer ci, input [3:0] a, input [7:0] v); begin
        @(negedge clk); cfg_a = a; wd = v; if (t) tcfg_we[ci] = 1; else rcfg_we[ci] = 1;
        @(negedge clk); tcfg_we[ci] = 0; rcfg_we[ci] = 0;
    end endtask
    task cfg(input t, input integer ci, input [119:0] v); integer j; begin      // LCCTRL .. LCCS, LCCTRL written last
        for (j = 1; j < 15; j = j + 1) cw(t, ci, j[3:0], v[(14 - j) * 8 +: 8]);
        cw(t, ci, 4'd0, v[119:112]);
    end endtask
    task automatic send(input integer ci, input [7:0] v); integer t; begin
        t = 0; @(negedge clk); while (!tstat[ci][6] && t < 20000) begin @(negedge clk); t = t + 1; end
        if (!tstat[ci][6]) begin errors = errors + 1; $display("FAIL: transmit buffer of cell %0d stays full", ci); end
        wd = v; data_we[ci] = 1; @(negedge clk); data_we[ci] = 0;
    end endtask
    task automatic recv(input integer ci, input [7:0] exp_v, input [255:0] what); integer t; reg [7:0] got; begin
        t = 0; @(negedge clk);
        while (!rstat[ci][7] && t < 20000) begin @(negedge clk); t = t + 1; end
        got = rdata[ci];
        if (!rstat[ci][7]) begin errors = errors + 1; $display("FAIL %0s: no frame", what); end
        else begin
            data_re[ci] = 1; @(negedge clk); data_re[ci] = 0;
            if (got !== exp_v) begin errors = errors + 1; $display("FAIL %0s: got %02x, expected %02x", what, got, exp_v); end
        end
    end endtask
    task check(input cond, input [255:0] what); begin
        if (!cond) begin errors = errors + 1; $display("FAIL %0s", what); end
    end endtask
    integer e0, k2; reg [7:0] got8;
    // clocks nb bits into pin 2 (data, changes while the clock is low) and pin 3 (clock), most significant bit of v first
    task bits(input [7:0] v, input integer nb); integer j; begin
        for (j = 0; j < nb; j = j + 1) begin
            ext[3] = 0; repeat (8) @(negedge clk); ext[2] = v[7 - j]; repeat (8) @(negedge clk);
            ext[3] = 1; repeat (8) @(negedge clk);
        end
    end endtask
    // nf falling edges of the data pin
    task dfall(input integer nf); integer j; begin
        for (j = 0; j < nf; j = j + 1) begin ext[2] = 1; repeat (6) @(negedge clk); ext[2] = 0; repeat (6) @(negedge clk); end
    end endtask
    task alloff; integer j; begin
        for (j = 0; j < 2; j = j + 1) begin cw(0, j, 4'd0, 8'h00); cw(1, j, 4'd0, 8'h00); end
        ext_en = 0; ext = 8'hFF; glitch = 0; repeat (20) @(negedge clk);
    end endtask

    // WS2812 waveform from the testbench: 75 cycles per bit, 48 high for a one, 24 for a zero
    task ws_byte(input [7:0] v); integer j; begin
        for (j = 7; j >= 0; j = j - 1) begin
            ext[0] = 1; repeat (v[j] ? 48 : 24) @(negedge clk);
            ext[0] = 0; repeat (v[j] ? 27 : 51) @(negedge clk);
        end
    end endtask

    task spi(input mode1); begin
        // pair 0: master. pin 0 MOSI, pin 1 SCK, pin 2 MISO.  pair 1: slave with chip select on pin 3
        // transmit: EN TXEN | OEM=1 | OUTSEL=0 OUTEN NSEL=1 NEN | NFN, CPHA | TWOPH | A B=8 C | - ENC | LEN=7
        cfg(1, 0, {8'hA0, 8'h01, 8'h13, (mode1 ? 8'h0A : 8'h08), 8'h04, 8'h01, 8'h08, 8'h01, 8'h00, 8'hF0, 8'hE0, 8'h00, 8'h00, 8'h00, 8'h00});
        // receive:  EN RXEN | INSEL=2 | - | - | TRIG=2: middle of the transmitted bit | - | DEC | LEN=7
        cfg(0, 0, {8'hC0, 8'h40, 8'h00, 8'h00, 8'h02, 8'h01, 8'h01, 8'h00, 8'hF0, 8'h00, 8'hE0, 8'h00, 8'h00, 8'h00, 8'h00});
        // slave transmit: OEM=1 | OUTSEL=2 OUTEN | CSEL=1, CPHA | EDGE = sampling edge, TRIG=1 | ... | SSEL=3 SSEN active low
        cfg(1, 1, {8'hA0, 8'h01, 8'h50, (mode1 ? 8'h22 : 8'h20), (mode1 ? 8'h81 : 8'h41), 8'h01, 8'h01, 8'h01, 8'h00, 8'hF0, 8'hE0, 8'h00, 8'h00, 8'h00, 8'h70});
        // slave receive: INSEL=0 | CSEL=1 CEN | EDGE, TRIG=1 | DEC | LEN=7 | SSEL=3 SSEN
        cfg(0, 1, {8'hC0, 8'h00, 8'h00, 8'h30, (mode1 ? 8'h81 : 8'h41), 8'h01, 8'h01, 8'h00, 8'hF0, 8'h00, 8'hE0, 8'h00, 8'h00, 8'h00, 8'h70});
        ext_en[3] = 1; ext[3] = 1; repeat (10) @(negedge clk);
        spi_m1 = mode1; spi_on = 1; nsmp = 0;
        send(1, 8'h5A);                                 // the slave has its first frame ready before chip select
        ext[3] = 0; repeat (10) @(negedge clk);
        send(1, 8'hC3);
        send(0, 8'hA5); send(0, 8'h3C);
        recv(0, 8'h5A, mode1 ? "SPI mode 1 master byte 1" : "SPI mode 0 master byte 1");
        recv(1, 8'hA5, mode1 ? "SPI mode 1 slave byte 1" : "SPI mode 0 slave byte 1");
        send(1, 8'h7E); send(0, 8'h81);
        recv(0, 8'hC3, "SPI master byte 2"); recv(1, 8'h3C, "SPI slave byte 2");
        recv(0, 8'h7E, "SPI master byte 3"); recv(1, 8'h81, "SPI slave byte 3");
        repeat (40) @(negedge clk);
        check(!tstat[0][5] && (mode1 || !tstat[1][5]), "SPI: not busy after the last frame");
        check(nsmp == 24, "SPI master: 24 sample points for three frames"); spi_on = 0;
        check(pins[2] === o_t[1], "SPI: slave drives MISO while selected");
        ext[3] = 1; repeat (10) @(negedge clk);
        check(pins[2] === 1'b1 && !o_dr[1] && !tstat[1][5], "SPI: slave releases MISO when not selected");
        alloff;
    end endtask

    initial begin
        for (n = 0; n < 2; n = n + 1) begin rcfg_we[n] = 0; tcfg_we[n] = 0; stat_we[n] = 0; data_re[n] = 0; data_we[n] = 0; end
        repeat (3) @(posedge clk); #1 rst_n = 1; repeat (4) @(negedge clk);

        // ---------------- SPI
        spi(0);
        spi(1);

        // ---------------- WS2812: pair 0 receives pin 0 and sends each bit again on pin 4; pair 1 receives pin 4
        ext_en[0] = 1; ext[0] = 0;
        cfg(0, 0, {8'hC0, 8'h00, 8'h00, 8'h00, 8'h68, 8'd36, 8'd150, 8'h00, 8'hF0, 8'h00, 8'hE0, 8'h00, 8'h00, 8'h00, 8'h00});
        //         EN TXEN | OEM=1 | OUTSEL=4 OUTEN | - | TRIG=2 | A=48 B=70 C=24 | - | LEN=7 SRC CMP
        cfg(1, 0, {8'hA0, 8'h01, 8'h90, 8'h00, 8'h02, 8'd48, 8'd70, 8'd24, 8'h00, 8'hF0, 8'hEC, 8'h00, 8'h00, 8'h00, 8'h00});
        cfg(0, 1, {8'hC0, 8'h80, 8'h00, 8'h00, 8'h68, 8'd36, 8'd150, 8'h00, 8'hF0, 8'h00, 8'hE0, 8'h00, 8'h00, 8'h00, 8'h00});
        repeat (50) @(negedge clk);
        fork
            begin ws_byte(8'hFF); ws_byte(8'h00); ws_byte(8'hA5); ws_byte(8'h3C); end
            begin recv(0, 8'hFF, "WS2812 first pair byte 1"); recv(0, 8'h00, "WS2812 first pair byte 2");
                  recv(0, 8'hA5, "WS2812 first pair byte 3"); recv(0, 8'h3C, "WS2812 first pair byte 4"); end
            begin recv(1, 8'hFF, "WS2812 forwarded byte 1"); recv(1, 8'h00, "WS2812 forwarded byte 2");
                  recv(1, 8'hA5, "WS2812 forwarded byte 3"); recv(1, 8'h3C, "WS2812 forwarded byte 4"); end
        join
        repeat (400) @(negedge clk);
        check(rstat[0][4] && rstat[1][4], "WS2812: idle flag after the end of the data");
        alloff;

        // ---------------- UART in pair 1: prescaler 4, peripheral clock divided by 2, majority filter, glitches
        ptick_div = 1;
        //         EN TXEN PRE=2 | OEM=1 | OUTSEL=5 OUTEN | - | - | A B=4 | - ENC | LEN=7 LSBF SS | - | IDLE=1
        cfg(1, 1, {8'hA2, 8'h01, 8'hB0, 8'h00, 8'h00, 8'h01, 8'h04, 8'h01, 8'h00, 8'hF0, 8'hF1, 8'h00, 8'h04, 8'h00, 8'h00});
        //         EN RXEN PRE=2 | INSEL=5 FILT=2 | - | - | falling, ACC, STOP=2 | A=6 B=4 | DEC | LEN=7 LSBF
        cfg(0, 1, {8'hC2, 8'hA8, 8'h00, 8'h00, 8'hB0, 8'h06, 8'h04, 8'h00, 8'hF0, 8'h00, 8'hF0, 8'h00, 8'h00, 8'h00, 8'h00});
        repeat (100) @(negedge clk);
        fork
            begin send(1, 8'h4B); send(1, 8'h00); send(1, 8'hFF); send(1, 8'h55); end
            begin : gl                                    // single-cycle glitches on the line
                repeat (60) begin repeat (23) @(negedge clk); glitch[5] = 1; @(negedge clk); glitch[5] = 0; end
            end
            begin recv(1, 8'h4B, "UART byte 1"); recv(1, 8'h00, "UART byte 2"); recv(1, 8'hFF, "UART byte 3"); recv(1, 8'h55, "UART byte 4"); end
        join
        // the prescaler restarts with a frame: the start bit has full length whatever the phase of the prescaler
        send(1, 8'hFF); repeat (400) @(negedge clk);
        check(lastlow == 32, "start bit of 32 clock cycles, first frame");
        repeat (3) @(negedge clk);
        send(1, 8'hFF); repeat (400) @(negedge clk);
        check(lastlow == 32, "start bit of 32 clock cycles, second frame");
        repeat (5) @(negedge clk);
        send(1, 8'hFF); repeat (400) @(negedge clk);
        check(lastlow == 32, "start bit of 32 clock cycles, third frame");
        recv(1, 8'hFF, "UART byte 5"); recv(1, 8'hFF, "UART byte 6");
        check(rstat[1][2], "overflow with three frames unread");
        @(negedge clk); wd = 8'h04; stat_we[1] = 1; @(negedge clk); stat_we[1] = 0; @(negedge clk);
        // holding register: two frames are kept, the third is lost
        send(1, 8'h11); send(1, 8'h22); send(1, 8'h33);
        repeat (1500) @(negedge clk);
        check(rstat[1][7] && rstat[1][2], "overflow flag after three unread frames");
        recv(1, 8'h11, "oldest frame after overflow"); recv(1, 8'h22, "second frame after overflow");
        check(!rstat[1][7], "holding register empty after two reads");
        @(negedge clk); wd = 8'h04; stat_we[1] = 1; @(negedge clk); stat_we[1] = 0; @(negedge clk);
        check(!rstat[1][2], "overflow flag cleared by writing a one");
        check(revt[1] == 1'b0, "no event without a mask");
        cw(0, 1, 4'd13, 8'h10); repeat (2) @(negedge clk);
        check(revt[1] == rstat[1][4], "event flag follows the masked status");
        cw(1, 1, 4'd13, 8'h40); repeat (2) @(negedge clk);
        check(tevt[1] == 1'b1, "transmit cell: event flag for an empty buffer");
        cw(0, 1, 4'd0, 8'h42); cw(1, 1, 4'd0, 8'h02); repeat (2) @(negedge clk);
        check(rstat[1] == 8'h00 && tstat[1] == 8'h40, "status after disabling the cells");
        ptick_div = 0;


        // ------------------------------------------------------------ C9: bus condition detector, edge count (LCX, LCEC)
        // pin 2 data, pin 3 clock, driven by the testbench; receive cell 0 samples at the rising clock edge
        e0 = errors;
        alloff; ext_en = 8'h0C; ext = 8'hFF; repeat (8) @(negedge clk);
        cw(0, 0, 4'd15, 8'h0C);                                                    // BCD, BEV
        cfg(0, 0, {8'hC0, 8'h40, 8'h00, 8'h70, 8'h41, 8'd1, 8'd1, 8'd5, 8'hF0, 8'h00, 8'hE0, 8'h00, 8'h00, 8'h80, 8'h00});
        repeat (8) @(negedge clk);
        check(!p[0].r.s_sta && !p[0].r.s_stp && !revt[0], "C9: no flag after enabling");
        ext[2] = 0; repeat (8) @(negedge clk);                                     // start
        check(p[0].r.s_sta && !p[0].r.s_stp, "C9: STA after a falling data edge while the clock is high");
        check(revt[0], "C9: event of the cell with BEV");
        cfg_a = 4'd15; #1; check(p[0].r.cfg_rdata == 8'h2C, "C9: LCX reads STA, BEV, BCD");
        cw(0, 0, 4'd15, 8'h2C); repeat (2) @(negedge clk);
        check(!p[0].r.s_sta && !revt[0], "C9: STA cleared by writing a one");
        cfg_a = 4'd15; #1; check(p[0].r.cfg_rdata == 8'h0C, "C9: configuration bits kept by the clearing write");
        bits(8'hE0, 3);                                                            // three bits of a frame
        check(p[0].r.nbit == 3'd3, "C9: three bits received");
        ext[3] = 0; repeat (8) @(negedge clk); ext[2] = 1; repeat (8) @(negedge clk);
        ext[3] = 1; repeat (8) @(negedge clk); ext[2] = 0; repeat (8) @(negedge clk);   // repeated start
        check(p[0].r.s_sta && p[0].r.nbit == 3'd0, "C9: repeated start sets STA and resets the bit count");
        cw(0, 0, 4'd15, 8'h2C);
        bits(8'hA6, 8); recv(0, 8'hA6, "C9: byte after the repeated start");
        check(!p[0].r.s_sta && !p[0].r.s_stp, "C9: no flag from data that changes while the clock is low");
        // rule B2: data edge in the same cycle as a clock edge
        ext[3] = 0; repeat (8) @(negedge clk); ext[2] = 0; repeat (8) @(negedge clk);
        ext[3:2] = 2'b11; repeat (8) @(negedge clk);                               // both rise together
        check(!p[0].r.s_sta && !p[0].r.s_stp, "C9 B2: data rises with the rising clock edge: no flag");
        ext[3:2] = 2'b00; repeat (8) @(negedge clk);                               // both fall together
        check(!p[0].r.s_sta && !p[0].r.s_stp, "C9 B2: data falls with the falling clock edge: no flag");
        ext[3] = 1; repeat (8) @(negedge clk); ext[2] = 1; repeat (8) @(negedge clk);   // stop
        check(p[0].r.s_stp && !p[0].r.s_sta, "C9: STP after a rising data edge while the clock is high");
        ext[2] = 0; repeat (8) @(negedge clk);
        check(p[0].r.s_stp && p[0].r.s_sta, "C9: both flags stored");
        cw(0, 0, 4'd15, 8'h1C); repeat (2) @(negedge clk);
        check(!p[0].r.s_stp && p[0].r.s_sta, "C9: only the flag written with a one is cleared");
        cw(0, 0, 4'd15, 8'h2C);
        // edge count: LCEC = 5 falling data edges while the clock is low
        ext[2] = 1; repeat (8) @(negedge clk); ext[3] = 0; repeat (8) @(negedge clk);
        cw(0, 0, 4'd15, 8'h3C);
        dfall(4); check(!p[0].r.s_ecf, "C9: no ECF after four edges");
        ext[3] = 1; repeat (8) @(negedge clk); ext[3] = 0; repeat (8) @(negedge clk);   // a clock pulse clears the count
        dfall(4); check(!p[0].r.s_ecf, "C9: clock edge clears the count");
        dfall(1); check(p[0].r.s_ecf && revt[0], "C9: ECF at the fifth edge");
        check(!p[0].r.s_sta && !p[0].r.s_stp, "C9: no bus condition from edges while the clock is low");
        cw(0, 0, 4'd15, 8'h4C); repeat (2) @(negedge clk); check(!p[0].r.s_ecf, "C9: ECF cleared");
        cw(0, 0, 4'd7, 8'h00); dfall(8); check(!p[0].r.s_ecf, "C9: LCEC = 0, no count");
        // detector off
        cw(0, 0, 4'd15, 8'h00); ext[3] = 1; repeat (8) @(negedge clk); ext[2] = 0; repeat (8) @(negedge clk);
        ext[2] = 1; repeat (8) @(negedge clk);
        check(!p[0].r.s_sta && !p[0].r.s_stp, "C9: BCD = 0, no flags");
        $display("C9 directed: %0d errors", errors - e0);

        // ------------------------------------------------------------ C8: first bit at the shift edge (ESTR)
        // transmit cell 0: clock pin 3 (the other side samples at the rising edge), output pin 4, most significant bit first
        e0 = errors;
        alloff; ext_en = 8'h08; ext = 8'hFF; repeat (8) @(negedge clk);
        for (n = 0; n < 2; n = n + 1) begin                                        // n = 0: ESTR = 0, n = 1: ESTR = 1
            cw(1, 0, 4'd0, 8'h00); cw(1, 0, 4'd15, n ? 8'h04 : 8'h00);
            cfg(1, 0, {8'hA0, 8'h01, 8'h90, 8'h60, 8'h41, 8'd1, 8'd1, 8'd1, 8'h00, 8'hF0, 8'hE0, 8'h00, 8'h04, 8'h00, 8'h00});
            ext[3] = 1; repeat (8) @(negedge clk);
            send(0, 8'h5A); repeat (8) @(negedge clk);                             // written while the clock is high
            if (n == 0) check(tstat[0][5] && pins[4] == 1'b0, "C8: ESTR = 0: first bit on the pin at the write");
            else        check(!tstat[0][5] && pins[4] == 1'b1, "C8: ESTR = 1: nothing on the pin before the shift edge");
            got8 = 0;
            for (k2 = 0; k2 < 8; k2 = k2 + 1) begin
                if (n == 1 || k2 > 0) begin ext[3] = 0; repeat (8) @(negedge clk); end   // shift edge
                if (k2 == 0 && n == 1) check(tstat[0][5] && pins[4] == 1'b0, "C8: ESTR = 1: first bit after the first shift edge");
                ext[3] = 1; got8 = {got8[6:0], pins[4]}; repeat (8) @(negedge clk);
            end
            check(got8 == 8'h5A, n ? "C8: ESTR = 1: frame 0x5A sampled at the rising edges" : "C8: ESTR = 0: frame 0x5A sampled at the rising edges");
            ext[3] = 0; repeat (8) @(negedge clk);
            check(!tstat[0][5] && pins[4] == 1'b1, "C8: idle after the eighth shift edge");
            ext[3] = 1; repeat (8) @(negedge clk);
        end
        $display("C8 directed: %0d errors", errors - e0);
        alloff;

        if (errors == 0) $display("PASS: all directed line cell tests"); else $display("%0d errors", errors);
        $finish;
    end
    initial begin #40000000; $display("FAIL: timeout"); $finish; end
endmodule
