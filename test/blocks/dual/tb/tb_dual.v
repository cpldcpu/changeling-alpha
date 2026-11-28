// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Testbench for rdual: three memories, register bus model, trace of instruction starts.
`timescale 1ns/1ps
module tb_dual;
    parameter HAS_H = 0, NIRQ = 4;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    wire [9:0] a0, a1; wire re0, we0, ws0, wo0, re1, we1, ws1, wo1; wire [7:0] wd0, wd1; reg [15:0] q0, q1;
    wire [10:0] dm_addr; wire dm_re, dm_we; wire [7:0] dm_wdata; reg [7:0] dm_rdata;
    wire [8:0] io_addr; wire io_core, io_re, io_we, io_unlock; wire [7:0] io_wdata, io_wmask, io_rdata;
    reg  [NIRQ-1:0] pend0 = 0, pend1 = 0; wire [NIRQ-1:0] ack0, ack1;
    wire [1:0] brk_flag, core_en, core_wait, core_cen; wire bus_hold, idle; wire [10:0] pc0; wire [9:0] pc1;
    reg [1:0] halt_req = 0, brk_clr = 0;

    reg [15:0] rom0 [0:1023];
    reg [15:0] rom1 [0:1023];
    reg [15:0] romx [0:2047];
    reg [7:0]  ram [0:2047];
    reg [7:0]  io  [0:511];
    wire [15:0] ev = {io[7], io[6]};

    rdual #(.NIRQ(NIRQ), .HAS_H(HAS_H)) dut (
        .clk(clk), .rst_n(rst_n), .cke(cke),
        .cm0_addr(a0), .cm0_re(re0), .cm0_we(we0), .cm0_wsel(ws0), .cm0_wdata(wd0), .cm0_wother(wo0), .cm0_rdata(q0),
        .cm1_addr(a1), .cm1_re(re1), .cm1_we(we1), .cm1_wsel(ws1), .cm1_wdata(wd1), .cm1_wother(wo1), .cm1_rdata(q1),
        .dm_addr(dm_addr), .dm_re(dm_re), .dm_we(dm_we), .dm_wdata(dm_wdata), .dm_rdata(dm_rdata),
        .io_addr(io_addr), .io_core(io_core), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata), .io_wmask(io_wmask),
        .io_rdata(io_rdata), .io_unlock(io_unlock), .io_prot(1'b0),
        .evt({ev, ev}), .irq0(pend0), .irq1(pend1), .irq_ack0(ack0), .irq_ack1(ack1),
        .halt_req(halt_req), .brk_clr(brk_clr), .brk_flag(brk_flag), .core_en(core_en), .core_wait(core_wait),
        .core_cen(core_cen), .bus_hold(bus_hold), .dbg_pc0(pc0), .dbg_pc1(pc1), .idle(idle),
        .rst_sys_n(rst_n), .h_acc(h_acc), .h_we(1'b0), .h_core(1'b0), .h_addr(h_addr), .h_wdata(8'h00), .h_rdata(h_rdata),
        .h_quiet(h_quiet), .io_host(io_host), .cm_host(cm_host),
        .inj_cmd(inj_cmd), .inj_core(inj_core), .inj_word(16'h0000), .inj_busy(inj_busy), .inj_fail(inj_fail));

    // ---------------------------------------------------------------- host stimulus (+hrand=seed)
    // Both cores are halted at random times. While they are halted, the host port reads random
    // locations of the three memories, and a NOP is injected into a random core. The register bus
    // model, the cycle count and the trace stand still during that time, so the trace must be the
    // same as without the stimulus.
    reg h_acc = 0; reg [15:0] h_addr = 0; wire [7:0] h_rdata; wire h_quiet, io_host, cm_host, inj_busy, inj_fail;
    reg [1:0] inj_cmd = 0; reg inj_core = 0;
    integer hseed = 0, hrand = 0, hleft = 0, hn_halt = 0, hn_rd = 0, hn_inj = 0, herr = 0, hx;
    reg hchk = 0, injw = 0; reg [7:0] hexp, hexp_q; reg [15:0] haddr_q;
    wire hfz = (halt_req != 0) | h_acc | (dut.dirty != 0) | inj_busy | (inj_cmd != 0);
    always @(posedge clk) begin
        h_acc <= 0; inj_cmd <= 0; hchk <= h_acc; hexp_q <= hexp; haddr_q <= h_addr;
        if (hchk && h_rdata !== hexp_q) begin herr = herr + 1; if (herr < 5) $display("HOST read %04x: %02x expected %02x", haddr_q, h_rdata, hexp_q); end
        if (hrand != 0 && rst_n) begin
            if (halt_req == 0) begin
                if (($random(hseed) & 63) == 0) begin halt_req <= 2'b11; hleft = 2 + ($random(hseed) & 31); hn_halt = hn_halt + 1; injw = 0; end
            end else if (inj_busy | (inj_cmd != 0)) begin
            end else if (hleft <= 0) halt_req <= 2'b00;      // also directly after a read: the cores must wait for the re-read
            else begin
                hleft = hleft - 1; hx = $random(hseed);
                if (!h_quiet) begin end
                else if ((hx & 7) == 0 && hleft > 0 && dut.at[hx[8]] && dut.valid == 2'b11) begin inj_cmd <= 2'd1; inj_core <= hx[8]; hn_inj = hn_inj + 1; end   // only at an instruction start: completing an instruction first would shift the two cores against each other
                else if (hx[4]) begin
                    h_acc <= 1; hn_rd = hn_rd + 1;
                    case (hx[6:5])
                        2'd0: begin h_addr <= 16'h4000 | hx[18:8]; hexp <= hx[8] ? rom0[hx[18:9]][15:8] : rom0[hx[18:9]][7:0]; end
                        2'd1: begin h_addr <= 16'h4800 | hx[18:8]; hexp <= hx[8] ? rom1[hx[18:9]][15:8] : rom1[hx[18:9]][7:0]; end
                        default: begin
                            hx[19:8] = 12'h040 + hx[18:8];
                            h_addr <= {4'd0, hx[19:8]}; hexp <= ram[hx[18:8]];
                        end
                    endcase
                end
            end
        end
    end

    integer i, trace, cyc, maxcyc, fd, noexit, pmw, timer_en, tcnt, cdiv, cph;
    // core clock enable: one cycle in cdiv (+cdiv=n). The trace counts enabled cycles only.
    reg cke = 1;
    always @(posedge clk) begin cph <= (cph + 1 >= cdiv) ? 0 : cph + 1; cke <= (cph + 1 >= cdiv); end
    reg [1023:0] hex0, hex1, tracefile, covname;

    always @(posedge clk) begin
        if (we0 && pmw) begin if (ws0) rom0[a0][15:8] <= wd0; else rom0[a0][7:0] <= wd0; end
        if (we1 && pmw) begin if (ws1) rom1[a1][15:8] <= wd1; else rom1[a1][7:0] <= wd1; end
        if (re0) q0 <= rom0[a0];
        if (re1) q1 <= rom1[a1];
        if (dm_we) ram[dm_addr] <= dm_wdata;
        if (dm_re) dm_rdata <= ram[dm_addr];
    end

    // register bus model: plain storage with masked writes.
    //   0x030 / 0x034: interrupt requests of core 0 / core 1 (write sets bits, read returns them)
    //   0x031 write: character output      0x032 write: end simulation with this exit code
    //   0x033 write (with +timer): request 1 of core 0 after that many cycles
    //   0x006, 0x007: event flags for both cores
    // +side: two registers with side effects (arbitration tests)
    //   0x00F "ticket": a read returns the number of reads so far (and counts one more)
    //   0x00C "write counter": every write counts one; a read returns the count (low 8 bits)
    reg side = 0; integer tk = 0, wc = 0;
    integer rdc0 [0:511]; integer rdc1 [0:511]; integer wrc0 [0:511]; integer wrc1 [0:511];
    integer covfd = 0;
    assign io_rdata = (side && io_addr == 9'h00F) ? tk[7:0] : (side && io_addr == 9'h00C) ? wc[7:0]
                    : (io_addr == 9'h030) ? {{(8-NIRQ){1'b0}}, pend0}
                    : (io_addr == 9'h034) ? {{(8-NIRQ){1'b0}}, pend1} : io[io_addr];
    wire [7:0] io_new = (io[io_addr] & ~io_wmask) | (io_wdata & io_wmask);
    always @(posedge clk) if (cke && !hfz) begin
        if (io_re && rst_n) begin if (io_core) rdc1[io_addr] = rdc1[io_addr] + 1; else rdc0[io_addr] = rdc0[io_addr] + 1; end
        if (io_we && rst_n) begin if (io_core) wrc1[io_addr] = wrc1[io_addr] + 1; else wrc0[io_addr] = wrc0[io_addr] + 1; end
        if (side && io_re && io_addr == 9'h00F) tk = tk + 1;
        if (side && io_we && io_addr == 9'h00C) wc = wc + 1;
        if (io_we) io[io_addr] <= io_new;
        pend0 <= (pend0 & ~ack0) | ((io_we && io_addr == 9'h030) ? io_new[NIRQ-1:0] : {NIRQ{1'b0}})
               | ((timer_en != 0 && tcnt == 1) ? 1 : 0);
        pend1 <= (pend1 & ~ack1) | ((io_we && io_addr == 9'h034) ? io_new[NIRQ-1:0] : {NIRQ{1'b0}});
        if (timer_en != 0) begin
            if (io_we && io_addr == 9'h033) tcnt <= io_new;
            else if (tcnt != 0) tcnt <= tcnt - 1;
        end
        if (rst_n && io_we && io_addr == 9'h031 && !trace) $write("%c", io_new);
        if (rst_n && io_we && io_addr == 9'h032 && !noexit) begin
            $display("EXIT %0d cycles %0d", io_new, cyc); if (trace != 0) $fclose(fd); $finish;
        end
    end

    task dump_end; begin
        if (covfd != 0) begin
            $fdisplay(covfd, "TICK %0d WCNT %0d", tk, wc);
            for (i = 0; i < 512; i = i + 1) begin
                if (rdc0[i] + wrc0[i] != 0) $fdisplay(covfd, "CNT 0 %0d %0d %0d", i, rdc0[i], wrc0[i]);
                if (rdc1[i] + wrc1[i] != 0) $fdisplay(covfd, "CNT 1 %0d %0d %0d", i, rdc1[i], wrc1[i]);
            end
            $fclose(covfd);
        end
        if (hrand != 0) $display("HOST halts %0d reads %0d injections %0d errors %0d", hn_halt, hn_rd, hn_inj, herr);
        $fwrite(fd, "ram "); for (i = 0; i < 2048; i = i + 1) $fwrite(fd, "%02x", ram[i]);
        $fwrite(fd, "\nio "); for (i = 0; i < 512; i = i + 1) $fwrite(fd, "%02x", io[i]);
        $fwrite(fd, "\nrom0 "); for (i = 0; i < 1024; i = i + 1) $fwrite(fd, "%04x", rom0[i]);
        $fwrite(fd, "\nrom1 "); for (i = 0; i < 1024; i = i + 1) $fwrite(fd, "%04x", rom1[i]);
        $fwrite(fd, "\n"); $fclose(fd);
    end endtask

    // trace: one line for every cycle in which a core starts an instruction or an interrupt entry
    wire [7:0] sr0 = {dut.core0.fI, dut.core0.fT, (HAS_H != 0) & dut.core0.fH, dut.core0.fN ^ dut.core0.fV,
                      dut.core0.fV, dut.core0.fN, dut.core0.fZ, dut.core0.fC};
    wire [7:0] sr1 = {dut.core1.fI, dut.core1.fT, (HAS_H != 0) & dut.core1.fH, dut.core1.fN ^ dut.core1.fV,
                      dut.core1.fV, dut.core1.fN, dut.core1.fZ, dut.core1.fC};
    reg [15:0] t16;
    // +cov=file: every cycle in which a core is held, with the state of the core and its instruction
    //   H core state ins   held by the arbiter (rule U3)      S core state ins   stolen by an access to its code memory (U7)
    //   R core             refetch cycle (U7)
    reg [15:0] li0 = 0, li1 = 0;
    wire [15:0] ci0 = dut.core0.irq_take ? 16'hFFFF : dut.core0.ins;
    wire [15:0] ci1 = dut.core1.irq_take ? 16'hFFFF : dut.core1.ins;
    wire [15:0] hi0 = (dut.core0.state == 0) ? ci0 : li0;
    wire [15:0] hi1 = (dut.core1.state == 0) ? ci1 : li1;
    always @(negedge clk) if (rst_n && cke && !hfz && covfd != 0) begin
        if (dut.req0 && !dut.g0) $fdisplay(covfd, "H 0 %0d %04x", dut.core0.state, hi0);
        if (dut.req1 && !dut.g1) $fdisplay(covfd, "H 1 %0d %04x", dut.core1.state, hi1);
        if (dut.stolen0) $fdisplay(covfd, "S 0 %0d %04x", dut.core0.state, hi0);
        if (dut.stolen1) $fdisplay(covfd, "S 1 %0d %04x", dut.core1.state, hi1);
        if (dut.refetch[0]) $fdisplay(covfd, "R 0 %0d %04x", dut.core0.state, hi0);
        if (dut.refetch[1]) $fdisplay(covfd, "R 1 %0d %04x", dut.core1.state, hi1);
        if (dut.cen[0] && dut.core0.state == 0) li0 <= ci0;
        if (dut.cen[1] && dut.core1.state == 0) li1 <= ci1;
    end
    always @(negedge clk) if (rst_n && cke && !hfz) begin
        if (maxcyc != 0 && cyc >= maxcyc) begin
            if (trace != 0) dump_end; else $display("TIMEOUT cycles %0d", cyc);
            $finish;
        end
        if (trace != 0 && core_cen[0] && dut.core0.state == 0) begin
            t16 = 0; t16[10:0] = dut.core0.pc - 1'b1;
            $fwrite(fd, "%0d 0 %04x ", cyc, t16);
            for (i = 0; i < 16; i = i + 1) $fwrite(fd, "%02x", dut.core0.R[i]);
            t16 = 0; t16[11:0] = dut.core0.sp;
            $fwrite(fd, " %02x %04x %x%x %x %x %x %x%x\n", sr0, t16, pend0, pend1, core_en, core_wait, dut.arb, dut.lk_held, dut.lk_own & dut.lk_held);
        end
        if (trace != 0 && core_cen[1] && dut.core1.state == 0) begin
            t16 = 0; t16[9:0] = dut.core1.pc - 1'b1;
            $fwrite(fd, "%0d 1 %04x ", cyc, t16);
            for (i = 0; i < 16; i = i + 1) $fwrite(fd, "%02x", dut.core1.R[i]);
            t16 = 0; t16[11:0] = dut.core1.sp;
            $fwrite(fd, " %02x %04x %x%x %x %x %x %x%x\n", sr1, t16, pend0, pend1, core_en, core_wait, dut.arb, dut.lk_held, dut.lk_own & dut.lk_held);
        end
        cyc = cyc + 1;
    end

    initial begin
        for (i = 0; i < 2048; i = i + 1) ram[i] = 0;
        for (i = 0; i < 512; i = i + 1) io[i] = 0;
        for (i = 0; i < 1024; i = i + 1) begin rom0[i] = 0; rom1[i] = 0; end
        cdiv = 1; cph = 0; if ($value$plusargs("cdiv=%d", cdiv)) ;
        trace = 0; cyc = 0; maxcyc = 0; pmw = 0; q0 = 0; q1 = 0; dm_rdata = 0; timer_en = 0; tcnt = 0;
        // +hex=file: one image of up to 2048 words for core 0 alone; +hex0= / +hex1=: one image per core
        if ($value$plusargs("hex=%s", hex0)) begin
            for (i = 0; i < 2048; i = i + 1) romx[i] = 0;
            $readmemh(hex0, romx);
            for (i = 0; i < 1024; i = i + 1) begin rom0[i] = romx[i]; rom1[i] = romx[i + 1024]; end
        end else begin
            if (!$value$plusargs("hex0=%s", hex0)) begin $display("no +hex or +hex0"); $finish; end
            $readmemh(hex0, rom0);
            if ($value$plusargs("hex1=%s", hex1)) $readmemh(hex1, rom1);
        end
        if ($value$plusargs("trace=%s", tracefile)) begin trace = 1; fd = $fopen(tracefile, "w"); end
        if ($value$plusargs("maxcyc=%d", maxcyc)) ;
        if ($test$plusargs("pmw")) pmw = 1;
        if ($test$plusargs("side")) side = 1;
        for (i = 0; i < 512; i = i + 1) begin rdc0[i] = 0; rdc1[i] = 0; wrc0[i] = 0; wrc1[i] = 0; end
        if ($value$plusargs("cov=%s", covname)) covfd = $fopen(covname, "w");
        if ($test$plusargs("timer")) timer_en = 1;
        if ($value$plusargs("hrand=%d", hseed)) hrand = 1;
        noexit = 0; if ($test$plusargs("noexit")) noexit = 1;
        repeat (3) @(posedge clk);
        #1 rst_n = 1;
    end
endmodule
