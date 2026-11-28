#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Interrupt during a wait, system testbench. About 25 minutes.
cd "$(dirname "$0")/.."
mkdir -p build
RTLDIR=../src/rsoc8/rtl
RTL="$RTLDIR/rcore8d.v $RTLDIR/rdual.v $RTLDIR/rlinecells.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/tb_sys.vvp tb/tb_sys.v $RTL || exit 1
python3 tests/waitirq.py --cdivs 1,2,3 --arbs 0,1,2 --tests a,b,c > build/waitirq_full.log 2>&1
tail -30 build/waitirq_full.log
