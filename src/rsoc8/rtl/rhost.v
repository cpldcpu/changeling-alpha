// rhost - host link: SPI slave, loader, debug access, mailbox, core reset.  rprot - program protection.
//
// Follows the rules L1-L10 of the architecture specification. The three SPI pins are sampled with the
// system clock; there is no logic on the host clock. The host clock must not be faster than one
// eighth of the system clock.
//
// Commands (first byte after the falling chip select):
//   0x02 write    AH AL data...          address increments
//   0x03 read     AH AL xx  -> data...   memories: address increments; registers: one read per command
//   0x04 control  byte: bit 7 core reset, bit 4 selected core, bits 1:0 halt requests
//   0x05 status   xx -> S0 S1 PCH PCL
//   0x06 inject   IH IL                  instruction for the selected core, which then returns to its position
//   0x07 mailbox write  byte
//   0x08 mailbox read   xx -> status, byte
//   0x09 execute  IH IL                  like inject, without the return (jumps)
//   0x0A step                            the selected core executes one instruction
//
// Registers:  0x0C MBSTAT  RXF TXE - - - - - -   (read only)      0x0D MBDATA

module rhost (
    input            clk,
    input            rst_n,          // system reset
    input            sck, cs_n, mosi,
    output           miso,

    // host access port of rdual
    output reg       h_acc,
    output reg       h_we,
    output           h_core,
    output reg [15:0] h_addr,
    output reg [7:0] h_wdata,
    input      [7:0] h_rdata,
    input            h_quiet,
    output reg [1:0] inj_cmd,
    output           inj_core,
    output reg [15:0] inj_word,
    input            inj_busy,
    input            inj_fail,       // the core could not advance; the injection was ended

    output reg       rst_core_n,     // reset of the cores and the peripherals
    output     [1:0] halt_req,
    output reg [1:0] brk_clr,
    input      [1:0] brk_flag, core_en, core_wait,
    input     [10:0] pc0,
    input      [9:0] pc1,

    // register bus (mailbox)
    input      [8:0] io_addr,
    input            io_host,
    input            io_re,
    input            io_we,
    input      [7:0] io_wdata,
    output reg [7:0] io_rdata,
    output           mbx             // the mailbox holds a byte from the host
);
    // ---------------------------------------------------------------- pin sampling
    reg [2:0] s_ck; reg [2:0] s_cs; reg [1:0] s_di;
    wire sel  = ~s_cs[1];
    wire rise = sel & s_ck[1] & ~s_ck[2];
    wire fall = sel & ~s_ck[1] & s_ck[2];
    wire cs_fall = ~s_cs[1] & s_cs[2];

    // ---------------------------------------------------------------- shift registers
    reg [7:0] rx, tx;
    (* keep *) reg [7:0] tx_next;    // see tx_hold
    reg [2:0] bitn;
    reg [3:0] slot;                  // number of the byte being received: 0 code, then 1.. (stops at 15)
    reg [7:0] cmd;
    wire [7:0] rxn = {rx[6:0], s_di[1]};
    wire byte_done = rise & (bitn == 3'd7);
    assign miso = tx[7];

    // ---------------------------------------------------------------- control and status
    reg       c_rst, c_core, err, rd_pend, rd_ref, mb_rxf, mb_txe, take, take_n;
    reg [1:0] c_halt;
    reg [7:0] mb_rx, mb_tx;
    assign halt_req = c_halt;
    assign h_core   = c_core;
    assign inj_core = c_core;
    assign mbx      = mb_rxf;
    wire       acc_ok  = c_rst | h_quiet;
    wire       is_reg  = ~h_addr[14] & ((&h_addr[13:8]) | (h_addr[13:6] == 8'h00));
    wire [1:0] halted  = c_halt | brk_flag;
    wire       core_ok = halted[c_core] & core_en[c_core] & ~core_wait[c_core] & ~c_rst & ~inj_busy;
    wire [7:0] st0 = {acc_ok, inj_busy, brk_flag, 2'b00, halted};
    wire [7:0] st1 = {err, c_rst, core_wait, 1'b0, c_core, core_en};
    wire [10:0] pcs = c_core ? {1'b0, pc1} : pc0;
    wire a_st = (io_addr == 9'h00C), a_da = (io_addr == 9'h00D);

    always @* begin
        io_rdata = 8'h00;
        if (a_st) io_rdata = {mb_rxf, mb_txe, 6'd0};
        if (a_da) io_rdata = mb_rx;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_ck <= 3'd0; s_cs <= 3'b111; s_di <= 2'd0; rx <= 8'd0; tx <= 8'd0; tx_next <= 8'd0; bitn <= 3'd0; slot <= 4'd0;
            cmd <= 8'd0; c_rst <= 1'b1; c_core <= 1'b0; c_halt <= 2'b00; err <= 1'b0; rd_pend <= 1'b0; rd_ref <= 1'b0;
            mb_rxf <= 1'b0; mb_txe <= 1'b1; take <= 1'b0; take_n <= 1'b0; mb_rx <= 8'd0; mb_tx <= 8'd0;
            h_acc <= 1'b0; h_we <= 1'b0; h_addr <= 16'd0; h_wdata <= 8'd0; inj_cmd <= 2'd0; inj_word <= 16'd0;
            rst_core_n <= 1'b0; brk_clr <= 2'b00;
        end else begin
            s_ck <= {s_ck[1:0], sck}; s_cs <= {s_cs[1:0], cs_n}; s_di <= {s_di[0], mosi};
            rst_core_n <= ~c_rst;
            h_acc <= 1'b0; inj_cmd <= 2'd0; brk_clr <= 2'b00; rd_ref <= 1'b0;
            // ---- result of a read access: valid in the cycle after h_acc
            if (inj_fail) err <= 1'b1;
            rd_pend <= h_acc & ~h_we;
            if (rd_pend) tx_next <= h_rdata;
            // ---- mailbox, firmware side
            if (io_re & a_da & ~io_host) mb_rxf <= 1'b0;
            if (io_we & a_da & ~io_host) begin mb_tx <= io_wdata; mb_txe <= 1'b0; end
            // ---- SPI
            if (!sel) begin bitn <= 3'd0; slot <= 4'd0; tx <= 8'd0; tx_next <= 8'd0; take <= 1'b0; take_n <= 1'b0; end
            else begin
                if (fall) tx <= (bitn == 3'd0) ? tx_next : {tx[6:0], 1'b0};
                if (rise) begin
                    rx <= rxn; bitn <= bitn + 3'd1;
                    if (take) begin mb_txe <= 1'b1; take <= 1'b0; end       // the host clocks the mailbox byte
                end
                if (byte_done) begin
                    if (slot != 4'd15) slot <= slot + 4'd1;
                    tx_next <= 8'd0;
                    if (slot == 4'd0) begin
                        cmd <= rxn;
                        if (rxn == 8'h0A) begin if (core_ok) inj_cmd <= 2'd3; else err <= 1'b1; end
                    end else case (cmd)
                        8'h02: begin                                        // write
                            if (slot == 4'd1) h_addr[15:8] <= rxn;
                            else if (slot == 4'd2) h_addr[7:0] <= rxn;
                            else begin
                                if (slot != 4'd3) h_addr <= h_addr + 16'd1;
                                if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b1; h_wdata <= rxn; end else err <= 1'b1;
                            end
                        end
                        8'h03: begin                                        // read
                            if (slot == 4'd1) h_addr[15:8] <= rxn;
                            else if (slot == 4'd2) h_addr[7:0] <= rxn;
                            else if (slot == 4'd3 || !is_reg) begin
                                if (slot != 4'd3) h_addr <= h_addr + 16'd1;
                                if (acc_ok) begin h_acc <= 1'b1; h_we <= 1'b0; end else begin err <= 1'b1; rd_ref <= 1'b1; end
                            end else tx_next <= tx_hold;
                        end
                        8'h04: if (slot == 4'd1) begin                      // control
                            c_rst <= rxn[7]; c_core <= rxn[4]; c_halt <= rxn[1:0];
                            brk_clr <= c_halt & ~rxn[1:0];
                        end
                        8'h05: case (slot)                                  // status
                            4'd1: tx_next <= st0;
                            4'd2: begin tx_next <= st1; err <= 1'b0; end
                            4'd3: tx_next <= {5'd0, pcs[10:8]};
                            4'd4: tx_next <= pcs[7:0];
                            default: ;
                        endcase
                        8'h06, 8'h09: begin                                 // inject, execute
                            if (slot == 4'd1) inj_word[15:8] <= rxn;
                            else if (slot == 4'd2) begin
                                inj_word[7:0] <= rxn;
                                if (core_ok) inj_cmd <= (cmd == 8'h06) ? 2'd1 : 2'd2; else err <= 1'b1;
                            end
                        end
                        8'h07: if (slot == 4'd1) begin                      // mailbox write
                            if (!mb_rxf) begin mb_rx <= rxn; mb_rxf <= 1'b1; end else err <= 1'b1;
                        end
                        8'h08: case (slot)                                  // mailbox read
                            4'd1: begin tx_next <= {mb_rxf, mb_txe, 6'd0}; take_n <= ~mb_txe; end      // the decision to take is made together with the status byte
                            4'd2: begin tx_next <= mb_tx; take <= take_n; end
                            default: ;
                        endcase
                        default: ;
                    endcase
                end
            end
        end
    end
    // tx_hold and tx_next take the data of a host read one clock cycle after the access. The keep attributes
    // preserve their names: the timing constraints exclude them from the two-cycle exception of the code memories.
    (* keep *) reg [7:0] tx_hold;    // last register value, repeated in a read command on the register bus
    always @(posedge clk or negedge rst_n)
        if (!rst_n) tx_hold <= 8'd0; else if (rd_ref) tx_hold <= 8'd0; else if (rd_pend) tx_hold <= h_rdata;      // a refused read leaves zero to repeat
endmodule

// ------------------------------------------------------------------ program protection (rule M4)
// Registers: 0x158 PMCR  LOCK - - - - - XWE PWE   0x159 PMLIM   (both protected)
module rprot (
    input            clk,
    input            rst_n,
    input      [8:0] io_addr,
    input            io_host,
    input            io_we,
    input      [7:0] io_wdata,
    output reg [7:0] io_rdata,
    input            io_unlock,
    output           io_prot,
    input      [9:0] cm0_addr, cm1_addr,
    input            cm0_we, cm1_we, cm0_wother, cm1_wother, cm_host,
    output           cm0_we_ok, cm1_we_ok        // write enables to the macros
);
    reg       lock, xwe, pwe;
    reg [7:0] lim;
    wire a_c = (io_addr == 9'h158), a_l = (io_addr == 9'h159);
    assign io_prot = a_c | a_l;
    wire ok = io_unlock | io_host;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin lock <= 1'b0; xwe <= 1'b0; pwe <= 1'b0; lim <= 8'd0; end
        else begin
            if (io_we & a_c & ok) begin lock <= lock | io_wdata[7]; xwe <= io_wdata[1]; pwe <= io_wdata[0]; end
            if (io_we & a_l & ok) lim <= io_wdata;
        end
    end
    always @* begin
        io_rdata = 8'h00;
        if (a_c) io_rdata = {lock, 5'd0, xwe, pwe};
        if (a_l) io_rdata = lim;
    end
    wire in0 = (cm0_addr[9:2] >= lim), in1 = (cm1_addr[9:2] >= lim);
    assign cm0_we_ok = cm0_we & (cm_host | (~lock & in0 & (cm0_wother ? xwe : pwe)));
    assign cm1_we_ok = cm1_we & (cm_host | (~lock & in1 & (cm1_wother ? xwe : pwe)));
endmodule
