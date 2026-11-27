#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# usage: arbfault.sh name 'sed-expression' file   -> build/fault/<name>.vvp from a temporary copy of the RTL
set -e
cd "$(dirname "$0")/.."
mkdir -p build/fault/$1
cp ../../rtl/rdual.v ../../rtl/rcore8d.v build/fault/$1/
sed -i "$2" build/fault/$1/$3
cmp -s ../../rtl/$3 build/fault/$1/$3 && { echo "fault $1 changed nothing"; exit 1; }
iverilog -g2005 -DSIM -o build/fault/$1.vvp tb/tb_dual.v build/fault/$1/rdual.v build/fault/$1/rcore8d.v
echo built build/fault/$1.vvp
