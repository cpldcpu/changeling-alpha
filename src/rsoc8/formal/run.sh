#!/bin/sh
# Formal check of the two-cycle timing exception (timing.sdc) on rdual with both cores.
# usage: run.sh [directory with rdual.v and rcore8d.v]     default: ../rtl
# Needs Yosys (YOSYS=command, default yosys). Results on standard output; exit status 1 on a violation.
cd "$(dirname "$0")"
RTL=$(cd "${1:-../rtl}" && pwd); Y=${YOSYS:-yosys}; D=${BMC_DEPTH:-8}; rc=0
mkdir -p build && cd build
$Y -q -p "read_verilog $RTL/rdual.v $RTL/rcore8d.v; script ../flat.ys" || exit 2
for c in S cm0 cm1 dm; do
    mkdir -p $c; cp rdual_flat.v $c/; cd $c
    echo "case $c: $(CASE=$c python3 ../../gen_exc.py rdual_flat.v . | tail -1)"
    python3 ../../run_exc.py bmc $D || rc=1
    python3 ../../run_exc.py ind ${IND:-3} || rc=1
    cd ..
done
[ $rc = 0 ] && echo "exception check: PASS (bounded depth $D from reset and induction step of length ${IND:-3}, all cases)" || echo "exception check: FAIL"
exit $rc
