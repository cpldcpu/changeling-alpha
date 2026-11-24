// rpe_osc - placeholder for the oscillator macro: no oscillator. The clock output is low, so the
// strap pin has to select the external clock. The macro will have the same ports.
module rpe_osc (
    input  wire       en,
    input  wire       en_relax,
    input  wire [7:0] trim,
    output wire       clk,
    output wire       clk_slow
);
    assign clk = 1'b0;
    assign clk_slow = 1'b0;
endmodule
