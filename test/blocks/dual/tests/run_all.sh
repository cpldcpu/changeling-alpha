#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Verification of rdual (two rcore8d cores). Needs: iverilog, python3, avr-gcc with avr-libc.
set -e
cd "$(dirname "$0")/.."
mkdir -p build/rand
python3 tests/gen_ctest.py > /dev/null
iverilog -g2005 -DSIM -o build/tbd.vvp tb/tb_dual.v ../../../src/rsoc8/rtl/rdual.v ../../../src/rsoc8/rtl/rcore8d.v
echo "random lockstep"; python3 tests/randtest_d.py 0 ${SEEDS:-100} 4000 | tail -1
python3 tests/directed.py
for p in 1 2 3 4; do
  sh tests/build_c.sh $p > /dev/null
  if [ $p = 4 ]; then T=+timer; else T=; fi
  echo "C test part $p on core 0: $(vvp -n build/tbd.vvp +hex=build/c$p.hex +maxcyc=600000 $T | grep -E 'EXIT|TIMEOUT')"
done
