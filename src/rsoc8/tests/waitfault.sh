#!/bin/sh
# usage: waitfault.sh name 'sed-expression'   -> build/fault/<name>.vvp: tb_sys with a temporary copy of rdual.v carrying a fault
set -e
cd "$(dirname "$0")/.."
mkdir -p build/fault
cp rtl/rdual.v build/fault/$1.v
sed -i "$2" build/fault/$1.v
cmp -s rtl/rdual.v build/fault/$1.v && { echo "fault $1 changed nothing"; exit 1; }
RTL="rtl/rcore8d.v build/fault/$1.v rtl/rlinecells.v rtl/rlcports.v rtl/revents.v rtl/rtimers.v rtl/rclock.v rtl/rhost.v rtl/rpe_top.v rtl/rpe_osc_stub.v tb/ihp/RM_IHPSG13_1P_1024x16_c2_bm_bist.v tb/ihp/RM_IHPSG13_1P_core_behavioral_bm_bist.v"
iverilog -g2005 -DSIM -DFUNCTIONAL -o build/fault/$1.vvp tb/tb_sys.v $RTL
echo built build/fault/$1.vvp
