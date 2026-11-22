// rcore8d - rcore8 for the two-core arrangement (reduced AVR instruction set).
//
// Differences to the single-core rcore8:
//   - cen: the core advances only in cycles with cen = 1. All state holds otherwise.
//   - data memory with synchronous read: LD, LDS and POP take two cycles, RET and RETI three.
//   - register bus with 9 address bits (bit 8 = configuration page at data address 0x3F00).
//   - bus_req: the instruction needs the shared bus (data memory or register bus) in this cycle.
//     It is decoded from the instruction and the state only. The arbiter answers with cen.
//   - code memory port with an 11-bit address: bit 10 selects the code memory of core 0 or 1.
//     Loads and stores to 0x4000.. use this port (pm_dacc = 1).
//   - SLEEP and BREAK are reported as pulses; waiting and halting are done outside with cen.
//   - unlock window (CCP) for protected registers.
//
// Outputs are valid for the cycle if cen = 1; the surrounding logic ignores them otherwise.
// Sequencing follows the rules P1-P7, M1-M5 and Q1-Q5 of the architecture specification.

module rcore8d #(
    parameter PC_W    = 10,           // 10: own code memory only; 11: both code memories
    parameter CODE_ID = 0,            // number of the core's own code memory
    parameter SP_W    = 12,
    parameter DM_AW   = 11,
    parameter NIRQ    = 16,
    parameter HAS_H   = 0,
    parameter [15:0] SP_RESET = 16'h083F
) (
    input                   clk,
    input                   rst_n,
    input                   cen,        // advance in this cycle
    input                   start,      // restart at address 0 (independent of cen)

    output [10:0]           pm_addr,    // code memory port
    output                  pm_re,
    output                  pm_we,
    output                  pm_wsel,    // 0 = low byte, 1 = high byte
    output [7:0]            pm_wdata,
    output                  pm_dacc,    // the access is a load or store, not a fetch
    input  [15:0]           pm_rdata,   // valid in the cycle after pm_re

    output [DM_AW-1:0]      dm_addr,    // data memory, synchronous read
    output                  dm_re,
    output                  dm_we,
    output [7:0]            dm_wdata,
    input  [7:0]            dm_rdata,

    output                  bus_req,    // needs data memory or register bus in this cycle

    output [8:0]            io_addr,    // register bus, combinational read, masked write
    output                  io_re,
    output                  io_we,
    output [7:0]            io_wdata,
    output [7:0]            io_wmask,
    input  [7:0]            io_rdata,
    output                  io_unlock,  // unlock window is open
    input                   io_prot,    // the addressed register is protected

    input  [NIRQ:1]         irq,
    output [NIRQ:1]         irq_ack,
    output                  irq_en,     // I flag

    output                  sleep,      // SLEEP executes in this cycle
    output                  brk,        // BREAK executes in this cycle
    output [PC_W-1:0]       dbg_pc,
    input                   inj,        // an injected instruction runs: interrupt delay and unlock window stand still
    output                  at_start    // the next enabled cycle starts an instruction or an interrupt entry
);

    localparam S_EXEC  = 4'd0,
               S_FLUSH = 4'd1,   // discard the word on pm_rdata, fetch continues
               S_CALL2 = 4'd2,   // call / interrupt entry: push high byte, fetch target
               S_RET2  = 4'd3,   // return: high byte arrives, read low byte
               S_RET3  = 4'd4,   // return: low byte arrives, fetch at the return address
               S_LD2   = 4'd5,   // data memory load: byte arrives
               S_LDF1  = 4'd6,   // load from code memory: present address
               S_LDF2  = 4'd7,   // load from code memory: take data, fetch again
               S_STF1  = 4'd8;   // store to code memory: write

    localparam TW = PC_W - 8;

    // ---------------------------------------------------------------- state
    reg [3:0]       state;
    reg [PC_W-1:0]  pc;          // address being fetched in this cycle
    reg [SP_W-1:0]  sp;
    reg [15:0]      ir;          // instruction copy for the states after S_EXEC
    reg [TW-1:0]    tmp;         // high byte of a return address
    reg             is_reti;
    reg             i_delay;     // one instruction of interrupt inhibit after I was set
    reg [2:0]       ccp;         // unlock window
    reg             fI, fT, fH, fV, fN, fZ, fC;
    reg [7:0]       R [0:15];    // r16..r31

    wire st_exec  = (state == S_EXEC);
    wire st_call2 = (state == S_CALL2);
    wire st_ret2  = (state == S_RET2);
    wire st_ret3  = (state == S_RET3);
    wire st_ld2   = (state == S_LD2);
    wire st_ldf1  = (state == S_LDF1);
    wire st_ldf2  = (state == S_LDF2);
    wire st_stf1  = (state == S_STF1);
    wire in_pf    = st_ldf1 | st_ldf2 | st_stf1;
    wire [15:0] ins = (in_pf | st_ld2) ? ir : pm_rdata;

    // data memory byte: taken from the memory output in the cycle after the read, or from a
    // capture register if the core was not enabled in that cycle
    // dq takes the memory output one clock cycle after the read. The keep attribute preserves its name: the
    // timing constraints of the implementation flow exclude it from the two-cycle exception of the data memory.
    reg       rd_first, dq_v;
    (* keep *) reg [7:0] dq;
    wire [7:0] dmq = dq_v ? dq : dm_rdata;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin rd_first <= 1'b0; dq_v <= 1'b0; dq <= 8'h00; end
        else begin
            rd_first <= cen & dm_re;
            if (cen | start)    dq_v <= 1'b0;
            else if (rd_first)  begin dq_v <= 1'b1; dq <= dm_rdata; end
        end
    end

    // ---------------------------------------------------------------- interrupts
    wire        irq_any  = |irq;
    wire        irq_take = st_exec & fI & ~i_delay & irq_any;
    reg [PC_W-1:0] irq_vec;
    reg [NIRQ:1]   irq_sel;
    integer k;
    always @* begin
        irq_vec = {PC_W{1'b0}};
        irq_sel = {NIRQ{1'b0}};
        for (k = NIRQ; k >= 1; k = k - 1)
            if (irq[k]) begin
                irq_vec = k;
                irq_sel = {NIRQ{1'b0}};
                irq_sel[k] = 1'b1;
            end
    end
    assign irq_ack = irq_sel & {NIRQ{irq_take}};
    assign irq_en  = fI;

    wire exec = st_exec & ~irq_take;

    // ---------------------------------------------------------------- decode
    wire [3:0] op   = ins[15:12];
    wire [3:0] nib  = ins[3:0];
    wire [3:0] rd_i = ins[7:4];
    wire [3:0] rr_i = ins[3:0];
    wire [7:0] Rd   = R[rd_i];
    wire [7:0] Rr   = R[rr_i];
    wire [7:0] K    = {ins[11:8], ins[3:0]};
    wire [2:0] bsel = ins[2:0];

    wire o_cpc  = (op == 4'h0) & (ins[11:10] == 2'b01);
    wire o_sbc  = (op == 4'h0) & (ins[11:10] == 2'b10);
    wire o_add  = (op == 4'h0) & (ins[11:10] == 2'b11);
    wire o_cpse = (op == 4'h1) & (ins[11:10] == 2'b00);
    wire o_cp   = (op == 4'h1) & (ins[11:10] == 2'b01);
    wire o_sub  = (op == 4'h1) & (ins[11:10] == 2'b10);
    wire o_adc  = (op == 4'h1) & (ins[11:10] == 2'b11);
    wire o_and  = (op == 4'h2) & (ins[11:10] == 2'b00);
    wire o_eor  = (op == 4'h2) & (ins[11:10] == 2'b01);
    wire o_or   = (op == 4'h2) & (ins[11:10] == 2'b10);
    wire o_mov  = (op == 4'h2) & (ins[11:10] == 2'b11);
    wire o_cpi  = (op == 4'h3);
    wire o_sbci = (op == 4'h4);
    wire o_subi = (op == 4'h5);
    wire o_ori  = (op == 4'h6);
    wire o_andi = (op == 4'h7);
    wire o_ldi  = (op == 4'hE);
    wire o_rjmp = (op == 4'hC);
    wire o_rcall= (op == 4'hD);
    wire o_lds  = (op == 4'hA) & ~ins[11];
    wire o_sts  = (op == 4'hA) &  ins[11];
    wire o_in   = (op == 4'hB) & ~ins[11];
    wire o_out  = (op == 4'hB) &  ins[11];
    wire o_brbs = (op == 4'hF) & (ins[11:10] == 2'b00);
    wire o_brbc = (op == 4'hF) & (ins[11:10] == 2'b01);
    wire o_bld  = (op == 4'hF) & (ins[11:9] == 3'b100) & ~ins[3];
    wire o_bst  = (op == 4'hF) & (ins[11:9] == 3'b101) & ~ins[3];
    wire o_sbrc = (op == 4'hF) & (ins[11:9] == 3'b110) & ~ins[3];
    wire o_sbrs = (op == 4'hF) & (ins[11:9] == 3'b111) & ~ins[3];

    // pointer loads and stores, push and pop
    wire g_ldst8 = (op == 4'h8) & (ins[11:10] == 2'b00) & (ins[2:0] == 3'b000);    // LD/ST Y, Z
    wire g_ldst9 = (op == 4'h9) & (ins[11:10] == 2'b00);
    wire nib_ptr = (nib == 4'h1) | (nib == 4'h2) | (nib == 4'h9) | (nib == 4'hA) |
                   (nib == 4'hC) | (nib == 4'hD) | (nib == 4'hE);
    wire o_ldp   = (g_ldst8 | (g_ldst9 & nib_ptr)) & ~ins[9];
    wire o_stp   = (g_ldst8 | (g_ldst9 & nib_ptr)) &  ins[9];
    wire o_pop   = g_ldst9 & (nib == 4'hF) & ~ins[9];
    wire o_push  = g_ldst9 & (nib == 4'hF) &  ins[9];
    wire p_post  = g_ldst9 & (nib[1:0] == 2'b01);
    wire p_pre   = g_ldst9 & (nib[1:0] == 2'b10);
    wire [1:0] p_sel = (nib[3:2] == 2'b11) ? 2'd0 : (nib[3] ? 2'd1 : 2'd2);        // X, Y, Z

    // one-operand group and miscellaneous
    wire g_one  = (op == 4'h9) & (ins[11:9] == 3'b010);
    wire o_com  = g_one & (nib == 4'h0);
    wire o_neg  = g_one & (nib == 4'h1);
    wire o_swap = g_one & (nib == 4'h2);
    wire o_inc  = g_one & (nib == 4'h3);
    wire o_asr  = g_one & (nib == 4'h5);
    wire o_lsr  = g_one & (nib == 4'h6);
    wire o_ror  = g_one & (nib == 4'h7);
    wire o_dec  = g_one & (nib == 4'hA);
    wire o_bset = g_one & (nib == 4'h8) & ~ins[8] & ~ins[7];
    wire o_bclr = g_one & (nib == 4'h8) & ~ins[8] &  ins[7];
    wire g_misc = g_one & (nib == 4'h8) &  ins[8];
    wire o_ret  = g_misc & (ins[7:4] == 4'h0);
    wire o_reti = g_misc & (ins[7:4] == 4'h1);
    wire o_sleep= g_misc & (ins[7:4] == 4'h8);
    wire o_break= g_misc & (ins[7:4] == 4'h9);
    wire o_wdr  = g_misc & (ins[7:4] == 4'hA);
    wire o_ijmp = g_one & (nib == 4'h9) & (ins[8:4] == 5'b00000);
    wire o_icall= g_one & (nib == 4'h9) & (ins[8:4] == 5'b10000);

    wire g_iob  = (op == 4'h9) & ins[11] & ~ins[10];
    wire o_cbi  = g_iob & (ins[9:8] == 2'b00);
    wire o_sbic = g_iob & (ins[9:8] == 2'b01);
    wire o_sbi  = g_iob & (ins[9:8] == 2'b10);
    wire o_sbis = g_iob & (ins[9:8] == 2'b11);

    // ---------------------------------------------------------------- ALU
    wire a_sub  = o_sub | o_subi | o_cp | o_cpi | o_sbc | o_sbci | o_cpc | o_neg | o_dec;
    wire a_wc   = o_adc | o_sbc | o_sbci | o_cpc;                 // uses carry in
    wire a_imm  = o_cpi | o_sbci | o_subi | o_ori | o_andi;
    wire a_inde = o_inc | o_dec;
    wire [7:0] alu_a = o_neg ? 8'h00 : Rd;
    wire [7:0] alu_b = o_neg ? Rd : a_inde ? 8'h00 : a_imm ? K : Rr;
    wire [7:0] alu_bx = alu_b ^ {8{a_sub}};
    wire       alu_ci = o_inc ? 1'b1 : o_dec ? 1'b0 : a_wc ? (fC ^ a_sub) : a_sub;
    wire [8:0] alu_s  = {1'b0, alu_a} + {1'b0, alu_bx} + {8'h00, alu_ci};
    wire       c8 = alu_s[8];
    wire       c7 = alu_a[7] ^ alu_bx[7] ^ alu_s[7];              // carry into bit 7
    wire       c4 = alu_a[4] ^ alu_bx[4] ^ alu_s[4];              // carry into bit 4

    wire g_add   = o_add | o_adc;
    wire g_subf  = o_sub | o_subi | o_cp | o_cpi | o_sbc | o_sbci | o_cpc | o_neg;
    wire g_logic = o_and | o_andi | o_or | o_ori | o_eor;
    wire g_shift = o_asr | o_lsr | o_ror;
    wire [7:0] logic_r = (o_and | o_andi) ? (Rd & alu_b) : (o_or | o_ori) ? (Rd | alu_b) : (Rd ^ alu_b);
    wire [7:0] shift_r = {o_asr ? Rd[7] : o_ror ? fC : 1'b0, Rd[7:1]};
    wire [7:0] alu_r = g_logic ? logic_r : g_shift ? shift_r : o_com ? ~Rd : alu_s[7:0];
    wire       alu_z = (alu_r == 8'h00);
    wire       alu_wr = g_add | o_sub | o_subi | o_sbc | o_sbci | o_neg | g_logic | g_shift | o_com | a_inde;


    wire fS = fN ^ fV;
    wire [7:0] sreg = {fI, fT, (HAS_H ? fH : 1'b0), fS, fV, fN, fZ, fC};

    // ---------------------------------------------------------------- pointers, stack, data address
    wire [15:0] pX = {R[11], R[10]};
    wire [15:0] pY = {R[13], R[12]};
    wire [15:0] pZ = {R[15], R[14]};
    wire [15:0] ptr     = (p_sel == 2'd0) ? pX : (p_sel == 2'd1) ? pY : pZ;
    wire [15:0] ptr_adj = ptr + (p_pre ? 16'hFFFF : 16'h0001);
    wire [15:0] ptr_adr = p_pre ? ptr_adj : ptr;
    wire        ptr_upd = p_post | p_pre;
    wire [15:0] lds_adr = {8'h00, ~ins[8], ins[8], ins[10], ins[9], ins[3:0]};

    wire [PC_W-1:0] pc_m1   = pc - 1'b1;
    wire [PC_W-1:0] ret_adr = irq_take ? pc_m1 : pc;      // instruction not executed / next instruction

    wire do_call  = exec & (o_rcall | o_icall);
    wire do_ret   = exec & (o_ret | o_reti);
    wire st_push  = irq_take | do_call | st_call2 | (exec & o_push);
    wire st_pop   = do_ret | st_ret2 | (exec & o_pop);
    wire [SP_W-1:0] sp_p1 = sp + 1'b1;
    wire [SP_W-1:0] sp_m1 = sp - 1'b1;

    wire        use_lds = o_lds | o_sts;
    wire [15:0] d_adr   = use_lds ? lds_adr : ptr_adr;
    wire        d_flash = d_adr[14];
    wire        d_cfg   = ~d_flash & (&d_adr[13:8]);
    wire        d_io    = ~d_flash & (d_adr[13:6] == 8'h00);
    wire        d_bus   = d_cfg | d_io;
    wire        d_ram   = ~d_flash & ~d_bus;
    wire        mem_ld  = exec & (o_ldp | o_lds);
    wire        mem_st  = exec & (o_stp | o_sts);
    wire        ldf_start = exec & o_ldp & d_flash;
    wire        stf_start = exec & o_stp & d_flash;
    wire        ld2_start = (mem_ld & d_ram) | (exec & o_pop);
    wire        ld_bus    = mem_ld & d_bus;

    assign dm_addr  = st_push ? sp[DM_AW-1:0] : st_pop ? sp_p1[DM_AW-1:0] : d_adr[DM_AW-1:0];
    assign dm_we    = st_push | (mem_st & d_ram);
    assign dm_re    = st_pop  | (mem_ld & d_ram);
    assign dm_wdata = (irq_take | do_call) ? ret_adr[7:0] : st_call2 ? {{(8-TW){1'b0}}, tmp} : Rd;

    // ---------------------------------------------------------------- register bus
    wire        x_inout  = exec & (o_in | o_out);
    wire        x_iobit  = exec & g_iob;
    wire [5:0]  inout_a  = {ins[10:9], ins[3:0]};
    wire        core_reg = (inout_a[5:2] == 4'b1111);                    // 0x3C..0x3F
    wire        io_a_sreg = (inout_a == 6'h3F);
    wire        io_a_spl  = (inout_a == 6'h3D);
    wire        io_a_sph  = (inout_a == 6'h3E);
    wire        io_a_ccp  = (inout_a == 6'h3C);

    assign io_addr  = x_inout ? {3'b000, inout_a} : x_iobit ? {4'b0000, ins[7:3]}
                    : d_cfg ? {1'b1, d_adr[7:0]} : {3'b000, d_adr[5:0]};
    assign io_re    = (x_inout & o_in & ~core_reg) | (x_iobit & (o_sbic | o_sbis)) | ld_bus;
    assign io_we    = (x_inout & o_out & ~core_reg) | (x_iobit & (o_sbi | o_cbi)) | (mem_st & d_bus);
    assign io_wdata = x_iobit ? {8{o_sbi}} : Rd;
    assign io_wmask = x_iobit ? (8'h01 << bsel) : 8'hFF;

    wire unlocked = (ccp != 3'd0);
    assign io_unlock = unlocked;

    wire [15:0] sp16 = {{(16-SP_W){1'b0}}, sp};
    wire [7:0] in_data = io_a_sreg ? sreg : io_a_spl ? sp16[7:0] : io_a_sph ? sp16[15:8]
                       : io_a_ccp ? 8'h00 : io_rdata;

    // request for the shared bus: from the instruction word and the state only
    assign bus_req = (st_exec & ( irq_take | o_ldp | o_stp | o_lds | o_sts | o_push | o_pop
                                | o_rcall | o_icall | o_ret | o_reti
                                | ((o_in | o_out) & ~core_reg) | g_iob))
                   | st_call2 | st_ret2;

    // ---------------------------------------------------------------- skips and branches
    wire skip = exec & ( (o_cpse & (Rd == Rr))
                       | (o_sbrc & ~Rd[bsel]) | (o_sbrs &  Rd[bsel])
                       | (o_sbic & ~io_rdata[bsel]) | (o_sbis & io_rdata[bsel]) );
    wire br_take = exec & ((o_brbs & sreg[bsel]) | (o_brbc & ~sreg[bsel]));
    wire [15:0]     br16    = {{9{ins[9]}}, ins[9:3]};
    wire [15:0]     rj16    = {{4{ins[11]}}, ins[11:0]};
    wire [PC_W-1:0] pc_rel  = pc + ((o_rjmp | o_rcall) ? rj16[PC_W-1:0] : br16[PC_W-1:0]);
    wire            rel_go  = br_take | (exec & (o_rjmp | o_rcall));
    wire            ind_go  = exec & (o_ijmp | o_icall);

    // ---------------------------------------------------------------- code memory port
    wire [PC_W-1:0] ret_pc = {tmp, dmq};
    wire [PC_W-1:0] f_pc   = st_ret3 ? ret_pc : pc;
    wire [10:0]     f_pcx  = (PC_W == 11) ? f_pc : {(CODE_ID != 0), f_pc[9:0]};
    assign pm_dacc  = st_ldf1 | st_stf1;
    assign pm_addr  = pm_dacc ? ptr_adr[11:1] : f_pcx;
    assign pm_re    = st_exec | (state == S_FLUSH) | st_call2 | st_ret3 | st_ldf1 | st_ldf2;
    assign pm_we    = st_stf1;
    assign pm_wsel  = ptr_adr[0];
    assign pm_wdata = Rd;
    wire [7:0] f_byte = ptr_adr[0] ? pm_rdata[15:8] : pm_rdata[7:0];

    // ---------------------------------------------------------------- register file write
    wire        reg_we  = (exec & (alu_wr | o_mov | o_ldi | o_swap | o_bld | o_in)) | ld_bus | st_ldf2 | st_ld2;
    wire [7:0]  bld_r   = (Rd & ~(8'h01 << bsel)) | ({7'b0, fT} << bsel);
    wire [7:0]  reg_wd  = st_ldf2 ? f_byte
                        : st_ld2  ? dmq
                        : ld_bus  ? io_rdata
                        : o_in    ? in_data
                        : o_mov   ? Rr
                        : o_ldi   ? K
                        : o_swap  ? {Rd[3:0], Rd[7:4]}
                        : o_bld   ? bld_r
                        : alu_r;
    wire        ptr_we  = ptr_upd & ((exec & (o_stp | o_ldp) & ~d_flash) | st_ldf2 | st_stf1);
    wire [3:0]  ptr_lo_i = {1'b1, p_sel != 2'd0, p_sel != 2'd1, 1'b0};   // 10 X, 12 Y, 14 Z

`ifdef SIM
    integer i;
    initial for (i = 0; i < 16; i = i + 1) R[i] = 8'h00;
`endif
    always @(posedge clk) if (cen) begin
        if (ptr_we) begin
            R[ptr_lo_i]        <= ptr_adj[7:0];
            R[ptr_lo_i | 4'h1] <= ptr_adj[15:8];
        end
        if (reg_we)
            R[rd_i] <= reg_wd;                  // the destination register wins over a pointer update
    end

    // ---------------------------------------------------------------- sequencing
    wire set_i_ins = exec & ((o_bset & (ins[6:4] == 3'd7)) | (o_out & io_a_sreg & Rd[7]));
    wire out_ccp   = exec & o_out & io_a_ccp & (Rd == 8'hD8);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state   <= S_FLUSH;
            pc      <= {PC_W{1'b0}};
            sp      <= SP_RESET[SP_W-1:0];
            ir      <= 16'h0000;
            tmp     <= {TW{1'b0}};
            is_reti <= 1'b0;
            i_delay <= 1'b0;
            ccp     <= 3'd0;
            fI <= 1'b0; fT <= 1'b0; fH <= 1'b0; fV <= 1'b0; fN <= 1'b0; fZ <= 1'b0; fC <= 1'b0;
        end else if (start) begin
            state <= S_FLUSH; pc <= {PC_W{1'b0}}; i_delay <= 1'b0; ccp <= 3'd0;
        end else if (cen) begin
            // ---- stack pointer
            if (st_push)      sp <= sp_m1;
            else if (st_pop)  sp <= sp_p1;
            else if (exec & o_out & io_a_spl) sp[7:0] <= Rd;
            else if (exec & o_out & io_a_sph) sp[SP_W-1:8] <= Rd[SP_W-9:0];

            // ---- unlock window
            if (out_ccp)                              ccp <= 3'd4;
            else if (io_we & io_prot & unlocked)      ccp <= 3'd0;
            else if (exec & unlocked & ~inj)          ccp <= ccp - 1'b1;

            // ---- program counter and state
            case (state)
            S_EXEC: begin
                if (irq_take) begin
                    pc <= irq_vec; tmp <= ret_adr[PC_W-1:8]; fI <= 1'b0; state <= S_CALL2;
                end else begin
                    i_delay <= inj ? (i_delay | set_i_ins) : set_i_ins;
                    if (rel_go)               pc <= pc_rel;
                    else if (ind_go)          pc <= pZ[PC_W-1:0];
                    else if (ldf_start | stf_start | do_ret | ld2_start) pc <= pc;
                    else                      pc <= pc + 1'b1;

                    if (do_call)              begin tmp <= ret_adr[PC_W-1:8]; state <= S_CALL2; end
                    else if (do_ret)          begin is_reti <= o_reti; state <= S_RET2; end
                    else if (ldf_start)       begin ir <= pm_rdata; state <= S_LDF1; end
                    else if (stf_start)       begin ir <= pm_rdata; state <= S_STF1; end
                    else if (ld2_start)       begin ir <= pm_rdata; state <= S_LD2; end
                    else if (rel_go | ind_go | skip) state <= S_FLUSH;
                end
            end
            S_FLUSH: begin pc <= pc + 1'b1; state <= S_EXEC; end
            S_CALL2: begin pc <= pc + 1'b1; state <= S_EXEC; end
            S_LD2:   begin pc <= pc + 1'b1; state <= S_EXEC; end
            S_RET2:  begin tmp <= dmq[TW-1:0]; state <= S_RET3; end
            S_RET3:  begin
                pc <= ret_pc + 1'b1;
                if (is_reti) begin fI <= 1'b1; i_delay <= 1'b1; end
                state <= S_EXEC;
            end
            S_LDF1:  state <= S_LDF2;
            S_LDF2:  begin pc <= pc + 1'b1; state <= S_EXEC; end
            S_STF1:  state <= S_FLUSH;
            default: state <= S_FLUSH;
            endcase

            // ---- flags
            if (exec) begin
                if (g_add | g_subf) begin
                    fC <= c8 ^ a_sub;
                    fH <= c4 ^ a_sub;
                    fV <= c7 ^ c8;
                    fN <= alu_r[7];
                    fZ <= alu_z & (a_wc & a_sub ? fZ : 1'b1);
                end
                if (a_inde) begin fV <= c7 ^ c8; fN <= alu_r[7]; fZ <= alu_z; end
                if (g_logic) begin fV <= 1'b0; fN <= alu_r[7]; fZ <= alu_z; end
                if (o_com) begin fC <= 1'b1; fV <= 1'b0; fN <= alu_r[7]; fZ <= alu_z; end
                if (g_shift) begin fC <= Rd[0]; fN <= alu_r[7]; fV <= alu_r[7] ^ Rd[0]; fZ <= alu_z; end
                if (o_bst) fT <= Rd[bsel];
                if (o_bset | o_bclr)
                    case (ins[6:4])
                    3'd0: fC <= o_bset;
                    3'd1: fZ <= o_bset;
                    3'd2: fN <= o_bset;
                    3'd3: fV <= o_bset;
                    3'd5: fH <= o_bset;
                    3'd6: fT <= o_bset;
                    3'd7: fI <= o_bset;
                    default: ;
                    endcase
                if (o_out & io_a_sreg) begin
                    fI <= Rd[7]; fT <= Rd[6]; fH <= Rd[5]; fV <= Rd[3]; fN <= Rd[2]; fZ <= Rd[1]; fC <= Rd[0];
                end
            end
        end
    end

    assign sleep  = exec & o_sleep;
    assign brk    = exec & o_break;
    assign dbg_pc = pc;
    assign at_start = st_exec;

endmodule
