// SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
// SPDX-License-Identifier: Apache-2.0
// Replacement for rcore8d in the block test of rdual (tb_dual.v): a scripted user of the register bus.
// Ops come from a file (hex, one 32-bit word per op: kind[29:26] unlock[25] addr[24:16] wdata[15:8] wmask[7:0]),
// kinds: 0 NOP, 1 READ, 2 WRITE, 3 SLEEP, 4 BREAK, 5 set I flag, 6 clear I flag.
// An op is consumed in a cycle with cen = 1. The value seen on io_rdata is shown on dbg_pc.
module rcore8d #(
    parameter PC_W = 10, parameter CODE_ID = 0, parameter SP_W = 12, parameter DM_AW = 11, parameter NIRQ = 16,
    parameter HAS_H = 0, parameter [15:0] SP_RESET = 16'h083F
) (
    input clk, input rst_n, input cen, input start,
    output [10:0] pm_addr, output pm_re, output pm_we, output pm_wsel, output [7:0] pm_wdata, output pm_dacc, input [15:0] pm_rdata,
    output [DM_AW-1:0] dm_addr, output dm_re, output dm_we, output [7:0] dm_wdata, input [7:0] dm_rdata,
    output bus_req,
    output [8:0] io_addr, output io_re, output io_we, output [7:0] io_wdata, output [7:0] io_wmask, input [7:0] io_rdata,
    output io_unlock, input io_prot,
    input [NIRQ:1] irq, output [NIRQ:1] irq_ack, output irq_en,
    output sleep, output brk, output [PC_W-1:0] dbg_pc, input inj, output at_start
);
    reg [31:0] mem [0:4095];
    reg [11:0] pc; reg ie;
    integer i; reg [1023:0] fn;
    initial begin
        for (i = 0; i < 4096; i = i + 1) mem[i] = 32'h0;
        if (CODE_ID == 0) begin if ($value$plusargs("ops0=%s", fn)) $readmemh(fn, mem); end
        else begin if ($value$plusargs("ops1=%s", fn)) $readmemh(fn, mem); end
    end
    wire [31:0] w = mem[pc];
    wire [3:0] kind = w[29:26];
    assign pm_addr = 0; assign pm_re = 0; assign pm_we = 0; assign pm_wsel = 0; assign pm_wdata = 0; assign pm_dacc = 0;
    assign dm_addr = 0; assign dm_re = 0; assign dm_we = 0; assign dm_wdata = 0;
    assign bus_req = (kind == 4'd1) | (kind == 4'd2);
    assign io_addr = w[24:16]; assign io_re = (kind == 4'd1); assign io_we = (kind == 4'd2);
    assign io_wdata = w[15:8]; assign io_wmask = w[7:0]; assign io_unlock = w[25];
    assign irq_ack = 0; assign irq_en = ie; assign sleep = (kind == 4'd3); assign brk = (kind == 4'd4);
    assign dbg_pc = io_rdata; assign at_start = 1'b1;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) begin pc <= 0; ie <= 0; end
        else if (cen) begin
            pc <= pc + 1;
            if (kind == 4'd5) ie <= 1; if (kind == 4'd6) ie <= 0;
        end
endmodule
