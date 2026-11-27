#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Inserts known faults into copies of the RTL and runs the exception check on each. Every fault must be detected.
# The first two are the RTL as it was before the corrections for the physical implementation (draft 0.37).
# Two further changes were tried and are not violations of the exception, so the check does not report them:
# dq enabled by cen as before draft 0.37 (cen is low in the cycle after a fetch whatever the memory puts out; the
# change of draft 0.37 was needed because dq is constrained to one cycle), and the code memory read of a core
# without cke (the read request is already gated by cke through the core enable).
cd "$(dirname "$0")"; mkdir -p build/faults; ok=0; n=0
fault() {   # name, file, sed expression
    [ -n "$ONLY" ] && [ "$ONLY" != "$1" ] && return
    d=build/faults/$1; rm -rf $d; mkdir -p $d; cp ../rtl/rdual.v ../rtl/rcore8d.v $d/
    sed -i "$3" $d/$2
    cmp -s ../rtl/$2 $d/$2 && { echo "fault $1 changed nothing"; exit 2; }
    n=$((n+1)); echo "== fault $1"
    if MAXCEX=2 BMC_DEPTH=6 sh run.sh $d > build/faults/$1.log 2>&1; then echo "   NOT DETECTED"; else ok=$((ok+1)); grep "VIOLATED" build/faults/$1.log | sed 's/(cycle [0-9]*)//' | sort -u | head -${SHOWMAX:-4}; echo "   detected: $(grep -c VIOLATED build/faults/$1.log) reports"; fi
}
fault restore_read   rdual.v   's/wire \[1:0\] rest = dirty \& ~{h_cm1, h_cm0} \& {2{cke}};/wire [1:0] rest = dirty \& ~{h_cm1, h_cm0};/'
fault inject_any     rdual.v   's/            if (cke) case (jst)/            case (jst)/'
fault cores_no_cke   rdual.v   's/((~brkf \& ~halt_req) | hrun) \& {2{cke}} \& {2{~hhold}};/((~brkf \& ~halt_req) | hrun) \& {2{~hhold}};/'
fault core_extra_step rcore8d.v 's/        end else if (cen) begin/        end else if (cen | rd_first) begin/'
echo "faults detected: $ok of $n"; [ $ok = $n ]
