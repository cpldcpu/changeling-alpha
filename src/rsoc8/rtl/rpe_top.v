// rpe_top - top level of the protocol emulator.
//
//   rpe_chip            chip level with 8 inputs, 8 outputs and 8 bidirectional pins (the pin set of a Tiny Tapeout
//                       project; the Tiny Tapeout top module in src/ of the repository instantiates it)
//   rpe_core            all blocks, the three SRAM macros and the oscillator
//   rpe_mem             one SRAM macro RM_IHPSG13_1P_1024x16_c2_bm_bist with byte write
//
// Pins:  ui_in   0 host link clock, 1 host link chip select, 2 host link data in,
//                3 clock source strap (0 external, 1 oscillator), 4 reference input, 5-7 inputs
//        uo_out  0 host link data out, 1 clock output, 2 debug signal, 3-4 outputs, 5-7 outputs or PWM
//        uio     bidirectional port, line cells
// All eight input pins can be read in PINB; output pins 1 to 7 are port outputs while their
// function is not enabled.
//
// The oscillator is the module rpe_osc (ports en, trim[7:0], clk). rpe_osc_stub.v holds a version
// without oscillator: its clock output is low, and the strap pin has to select the external clock.

`default_nettype none

module rpe_mem (
    input  wire        clk,
    input  wire [9:0]  addr,
    input  wire        re,
    input  wire        we,
    input  wire        wsel,          // byte written: 0 low, 1 high
    input  wire [7:0]  wdata,
    output wire [15:0] rdata
);
    RM_IHPSG13_1P_1024x16_c2_bm_bist u_mem (
        .A_CLK(clk), .A_MEN(re | we), .A_WEN(we), .A_REN(re), .A_ADDR(addr),
        .A_DIN({wdata, wdata}), .A_DLY(1'b1), .A_DOUT(rdata),
        .A_BM(wsel ? 16'hFF00 : 16'h00FF),
        .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0), .A_BIST_REN(1'b0),
        .A_BIST_ADDR(10'd0), .A_BIST_DIN(16'd0), .A_BIST_BM(16'd0));
endmodule

module rpe_core (
    input  wire       clk_ext,
    input  wire       rst_n,
    input  wire [7:0] in_pins,
    output wire [7:0] out_pins,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe
);
    // ---------------------------------------------------------------- clock, reset
    wire clk, rst_sys_n, rst_c, cke, ptick, clk_osc, clk_slow, osc_en, relax_en;
    wire [7:0] osc_trim;

    // ---------------------------------------------------------------- register bus
    wire [8:0] io_addr;
    wire       io_core, io_host, io_re, io_we, io_unlock;
    wire [7:0] io_wdata, io_wmask;
    wire [7:0] rd_ports, rd_evt, rd_tim, rd_clk, rd_host, rd_prot;
    wire       prot_ports, prot_ck, prot_pm;

    // ---------------------------------------------------------------- memories
    wire [9:0]  a0, a1;
    wire        re0, we0, ws0, wo0, re1, we1, ws1, wo1, we0_ok, we1_ok, cm_host;
    wire [7:0]  wd0, wd1;
    wire [15:0] q0, q1, qd;
    wire [10:0] dm_addr;
    wire        dm_re, dm_we;
    wire [7:0]  dm_wdata;
    reg         dm_hi;                    // byte of the last read of the data memory
    rpe_mem m_code0 (.clk(clk), .addr(a0), .re(re0), .we(we0_ok), .wsel(ws0), .wdata(wd0), .rdata(q0));
    rpe_mem m_code1 (.clk(clk), .addr(a1), .re(re1), .we(we1_ok), .wsel(ws1), .wdata(wd1), .rdata(q1));
    rpe_mem m_data  (.clk(clk), .addr(dm_addr[10:1]), .re(dm_re), .we(dm_we), .wsel(dm_addr[0]), .wdata(dm_wdata), .rdata(qd));
    always @(posedge clk or negedge rst_sys_n)
        if (!rst_sys_n) dm_hi <= 1'b0; else if (dm_re) dm_hi <= dm_addr[0];
    wire [7:0] dm_rdata = dm_hi ? qd[15:8] : qd[7:0];

    // ---------------------------------------------------------------- cores
    wire [31:0] evt;
    wire [16:1] irq0, irq1, ack0, ack1;
    wire [1:0]  halt_req, brk_clr, brk_flag, core_en, core_wait, core_cen, inj_cmd;
    wire        bus_hold, idle, h_acc, h_we, h_core, h_quiet, inj_core, inj_busy, inj_fail;
    wire [10:0] pc0;
    wire [9:0]  pc1;
    wire [15:0] h_addr, inj_word;
    wire [7:0]  h_wdata, h_rdata;
    rdual cores (.clk(clk), .rst_n(rst_c), .cke(cke),
        .cm0_addr(a0), .cm0_re(re0), .cm0_we(we0), .cm0_wsel(ws0), .cm0_wdata(wd0), .cm0_wother(wo0), .cm0_rdata(q0),
        .cm1_addr(a1), .cm1_re(re1), .cm1_we(we1), .cm1_wsel(ws1), .cm1_wdata(wd1), .cm1_wother(wo1), .cm1_rdata(q1),
        .dm_addr(dm_addr), .dm_re(dm_re), .dm_we(dm_we), .dm_wdata(dm_wdata), .dm_rdata(dm_rdata),
        .io_addr(io_addr), .io_core(io_core), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata), .io_wmask(io_wmask),
        .io_rdata(rd_ports | rd_evt | rd_tim | rd_clk | rd_host | rd_prot), .io_unlock(io_unlock),
        .io_prot(prot_ports | prot_ck | prot_pm),
        .evt(evt), .irq0(irq0), .irq1(irq1), .irq_ack0(ack0), .irq_ack1(ack1),
        .halt_req(halt_req), .brk_clr(brk_clr), .brk_flag(brk_flag), .core_en(core_en), .core_wait(core_wait),
        .core_cen(core_cen), .bus_hold(bus_hold), .dbg_pc0(pc0), .dbg_pc1(pc1), .idle(idle),
        .rst_sys_n(rst_sys_n), .h_acc(h_acc), .h_we(h_we), .h_core(h_core), .h_addr(h_addr), .h_wdata(h_wdata),
        .h_rdata(h_rdata), .h_quiet(h_quiet), .io_host(io_host), .cm_host(cm_host),
        .inj_cmd(inj_cmd), .inj_core(inj_core), .inj_word(inj_word), .inj_busy(inj_busy), .inj_fail(inj_fail));

    // ---------------------------------------------------------------- host link, program protection
    wire miso, mbx;
    rhost host (.clk(clk), .rst_n(rst_sys_n), .sck(in_pins[0]), .cs_n(in_pins[1]), .mosi(in_pins[2]), .miso(miso),
        .h_acc(h_acc), .h_we(h_we), .h_core(h_core), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .h_quiet(h_quiet), .inj_cmd(inj_cmd), .inj_core(inj_core), .inj_word(inj_word), .inj_busy(inj_busy),
        .inj_fail(inj_fail), .rst_core_n(rst_c), .halt_req(halt_req), .brk_clr(brk_clr), .brk_flag(brk_flag),
        .core_en(core_en), .core_wait(core_wait), .pc0(pc0), .pc1(pc1),
        .io_addr(io_addr), .io_host(io_host), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata),
        .io_rdata(rd_host), .mbx(mbx));
    rprot prot (.clk(clk), .rst_n(rst_c), .io_addr(io_addr), .io_host(io_host), .io_we(io_we), .io_wdata(io_wdata),
        .io_rdata(rd_prot), .io_unlock(io_unlock), .io_prot(prot_pm), .cm0_addr(a0), .cm1_addr(a1),
        .cm0_we(we0), .cm1_we(we1), .cm0_wother(wo0), .cm1_wother(wo1), .cm_host(cm_host),
        .cm0_we_ok(we0_ok), .cm1_we_ok(we1_ok));

    // ---------------------------------------------------------------- pins and line cells
    wire [7:0] pins_sync;
    wire [1:0] lc_own, ref_evt, acc_evt, smp_evt, rxs, rxb, rxf, txs, txb;
    wire [3:0] lc_evt;
    wire       pc_evt, capt_evt, oca_evt, ocb_evt, ovf_evt, trim_evt, cko_en, cko, dbg_en, dbg;
    wire [2:0] pwm_en, pwm_out;
    rlcports ports (.clk(clk), .rst_n(rst_c), .rst_sys_n(rst_sys_n), .ptick(ptick),
        .io_addr(io_addr), .io_core(io_core), .io_host(io_host), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata),
        .io_wmask(io_wmask), .io_rdata(rd_ports), .io_unlock(io_unlock), .io_prot(prot_ports),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe), .in_pins(in_pins), .out_pins(out_pins),
        .ovr_en({pwm_en, 2'd0, dbg_en, cko_en, 1'b1}), .ovr_val({pwm_out, 2'd0, dbg, cko, miso}),
        .lc_own(lc_own), .lc_evt(lc_evt), .pc_evt(pc_evt), .ref_evt(ref_evt), .acc_evt(acc_evt), .smp_evt(smp_evt),
        .rx_strobe(rxs), .rx_frame(rxf), .rx_bit(rxb), .tx_strobe(txs), .tx_bit(txb), .pins_sync(pins_sync));

    // ---------------------------------------------------------------- event flags, timers, CRC
    revents events (.clk(clk), .rst_n(rst_c), .ptick(ptick),
        .io_addr(io_addr), .io_core(io_core), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata), .io_wmask(io_wmask),
        .io_rdata(rd_evt), .pc_evt(pc_evt), .capt_evt(capt_evt), .oca_evt(oca_evt), .ocb_evt(ocb_evt),
        .ovf_evt(ovf_evt), .trim_evt(trim_evt), .mbx(mbx), .lc_evt(lc_evt), .lc_own(lc_own),
        .evt(evt), .irq0(irq0), .irq1(irq1), .irq_ack0(ack0), .irq_ack1(ack1));
    rtimers timers (.clk(clk), .rst_n(rst_c), .ptick(ptick),
        .io_addr(io_addr), .io_core(io_core), .io_host(io_host), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata),
        .io_rdata(rd_tim), .pins_sync(pins_sync), .acc_evt(acc_evt), .ref_evt(ref_evt),
        .rx_strobe(rxs), .rx_frame(rxf), .rx_bit(rxb), .tx_strobe(txs), .tx_bit(txb),
        .capt_evt(capt_evt), .oca_evt(oca_evt), .ocb_evt(ocb_evt), .ovf_evt(ovf_evt),
        .pwm_en(pwm_en), .pwm_out(pwm_out));

    // ---------------------------------------------------------------- clocking, oscillator
    rpe_osc osc (.en(osc_en), .en_relax(relax_en), .trim(osc_trim), .clk(clk_osc), .clk_slow(clk_slow));
    rclock u_clock (.clk_ext(clk_ext), .clk_osc(clk_osc), .clk_slow(clk_slow), .rst_n(rst_n), .strap(in_pins[3]),
        .clk(clk), .rst_sys_n(rst_sys_n), .osc_en(osc_en), .relax_en(relax_en), .osc_trim(osc_trim),
        .io_addr(io_addr), .io_host(io_host), .io_re(io_re), .io_we(io_we), .io_wdata(io_wdata),
        .io_rdata(rd_clk), .io_unlock(io_unlock), .io_prot(prot_ck), .cke(cke), .ptick(ptick),
        .ref_host(in_pins[0]), .ref_pin(in_pins[4]), .ref_evt(ref_evt), .trim_evt(trim_evt),
        .smp_evt(smp_evt), .acc_evt(acc_evt), .tx_strobe(txs), .core_cen(core_cen), .bus_hold(bus_hold),
        .cko_en(cko_en), .cko(cko), .dbg_en(dbg_en), .dbg(dbg));
endmodule

module rpe_chip (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    rpe_core u (.clk_ext(clk), .rst_n(rst_n), .in_pins(ui_in), .out_pins(uo_out),
                .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe));
    wire unused = ena;
endmodule

`default_nettype wire
