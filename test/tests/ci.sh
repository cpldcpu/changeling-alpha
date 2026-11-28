#!/bin/sh
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
# Regression for continuous integration. Runs four suites and compares their output with the expected
# output in tests/expected/. Any difference fails. The suites use fixed seeds, so the output is the same on
# every run with the same tools (Icarus Verilog 12, gcc-avr 7.3.0, avr-libc as in Ubuntu 24.04).
#
#   sh test/tests/ci.sh            run and compare
#   sh test/tests/ci.sh --update   run and store the output as the new expected output
#
# Not included because of their run time: run_uart.sh, spii2c.sh, run_eth.sh, run_waitirq.sh, the stress
# tests and blocks/dual/tests/run_arb.sh.
cd "$(dirname "$0")/.."
mkdir -p build/ci tests/expected
run() { echo "== $1"; sh "$2" > build/ci/$1.txt 2>&1; echo "   exit status $?"; }
run linecells blocks/linecells/tests/run_all.sh
run dual      blocks/dual/tests/run_all.sh
run models    tests/run_models.sh
run fw        tests/run_fw.sh
if [ "$1" = "--update" ]; then cp build/ci/*.txt tests/expected/; echo "expected output updated"; exit 0; fi
bad=0
for s in linecells dual models fw; do
    if diff -u tests/expected/$s.txt build/ci/$s.txt > build/ci/$s.diff; then echo "ok   $s"; else echo "FAIL $s"; head -40 build/ci/$s.diff; bad=1; fi
done
exit $bad
