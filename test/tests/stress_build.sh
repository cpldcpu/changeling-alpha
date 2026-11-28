#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# compiles the testbench into build/tb_sys.vvp (plusargs select everything else)
cd "$(dirname "$0")/.."
mkdir -p build
RTLDIR=../src/rsoc8/rtl
RTL=${RTL:-"$RTLDIR/rcore8d.v $RTLDIR/rdual.v $RTLDIR/rlinecells.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"}
iverilog -g2005 -DSIM -DFUNCTIONAL -o ${OUT:-build/tb_sys.vvp} tb/tb_sys.v $RTL
