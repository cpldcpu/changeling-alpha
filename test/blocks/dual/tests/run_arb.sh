#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Arbitration tests of rdual (all with the cycle model in lockstep). Logs in build/arblog/. Takes about an hour.
cd "$(dirname "$0")/.."
mkdir -p build/arblog build/rand
iverilog -g2005 -DSIM -o build/tbd.vvp tb/tb_dual.v ../../../src/rsoc8/rtl/rdual.v ../../../src/rsoc8/rtl/rcore8d.v || exit 1
L=build/arblog
python3 tests/arbsweep.py --classes all --vs all --arbs 0,1,2 --variants 2 --covreport > $L/matrix.log 2>&1
python3 tests/arbsweep.py --classes pushpop --vs all --arbs 0,1,2 --variants 2 --covreport > $L/pushpop.log 2>&1
for c in 2 3; do python3 tests/arbsweep.py --classes all --vs ld_Xp,pushpop,rcall2,in_tick,sts --arbs 0,1,2 --variants 1 --cdiv $c > $L/matrix_cdiv$c.log 2>&1; done
python3 tests/arbsweep.py --timing --classes all > $L/timing.log 2>&1
for c in 1 2 3; do python3 tests/arbsweep.py --irq --arbs 0,1,2 --variants 8 --cdiv $c --covreport > $L/irq_cdiv$c.log 2>&1; done
for c in 1 2 3; do python3 tests/arbcode.py all --arbs 0,1,2 --variants 3 --cdiv $c > $L/code_cdiv$c.log 2>&1; done
python3 tests/randstress.py 1000 1300 4000 > $L/randstress.log 2>&1
SEEDS=100 sh tests/run_all.sh > $L/run_all.log 2>&1
echo finished > $L/done
