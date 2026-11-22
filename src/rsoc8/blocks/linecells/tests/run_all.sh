#!/bin/sh
# Verification of the line cells. Needs: iverilog, python3.
set -e
cd "$(dirname "$0")/.."
mkdir -p build
iverilog -g2005 -o build/tb_lc.vvp tb/tb_lc.v ../../rtl/rlinecells.v
iverilog -g2005 -o build/tb_lc2.vvp tb/tb_lc2.v ../../rtl/rlinecells.v
python3 tests/lc_test.py ${CASES:-200}
vvp -n build/tb_lc2.vvp | grep -E "PASS|FAIL|errors"
