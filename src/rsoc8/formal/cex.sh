#!/bin/sh
# usage: cex.sh <case> <n> signal...   prints the counterexample of the induction step of length n for one case
cd "$(dirname "$0")/build/$1"; N=$2; shift; shift
SETS=$(for t in $(seq 1 $((N-1))); do printf -- "-set-at $t fail_any 0 "; done)
SHOW=$(for s in fail_vec step hgap cgap prev_cke cke h_acc h_we h_addr inj_cmd inj_core halt_req prev_halt_req brk_clr prev_quiet prev_busy prev_halted A_core_cen A_h_quiet A_inj_busy "$@"; do printf -- "-show $s "; done)
${YOSYS:-yosys} -p "read_verilog -formal exc_top.v; read_verilog rdual_comb.v; prep -top exc_top; flatten; async2sync; chformal -lower; opt -full; opt_clean; setattr -unset init w:*; sat -seq $N -set-at 1 step 3 $SETS -prove-skip $((N-1)) -prove-asserts -set-assumes $SHOW" 2>&1 | grep -E "^\s+[0-9]+ \\\\|SAT proof" | awk '{printf "%s %-14s %s %s\n",$1,$2,$4,$5}'
