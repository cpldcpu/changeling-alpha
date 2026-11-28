#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# usage: waitfault.sh name 'sed-expression'   -> build/fault/<name>.vvp: tb_sys with a temporary copy of rdual.v carrying a fault
set -e
cd "$(dirname "$0")/.."
mkdir -p build/fault
RTLDIR=../src/rsoc8/rtl
cp $RTLDIR/rdual.v build/fault/$1.v
sed -i "$2" build/fault/$1.v
cmp -s $RTLDIR/rdual.v build/fault/$1.v && { echo "fault $1 changed nothing"; exit 1; }
RTL="$RTLDIR/rcore8d.v build/fault/$1.v $RTLDIR/rlinecells.v $RTLDIR/rlcports.v $RTLDIR/revents.v $RTLDIR/rtimers.v $RTLDIR/rclock.v $RTLDIR/rhost.v $RTLDIR/rpe_top.v $RTLDIR/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/fault/$1.vvp tb/tb_sys.v $RTL
echo built build/fault/$1.vvp
