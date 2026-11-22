#!/bin/sh
# Runs the model-based random tests of the blocks without a firmware test: events, dual (locks, wait, ARB), clkctl, prot, host.
# usage: tests/run_models.sh [first_seed last_seed]   (default 0 100). Set LITERAL=1 to follow the specification text literally
# where the RTL deviates (clkctl, host), FAULTS=1 to run the fault insertion lists afterwards.
cd "$(dirname "$0")/.."
A=${1:-0}; B=${2:-100}
for t in ev dual clkctl prot host; do echo "== $t"; python3 tests/${t}_test.py $A $B | grep -v '^  *cov' ; done
if [ -n "$FAULTS" ]; then for b in ev dual clkctl prot host; do python3 tests/fault_run.py $b $A $B | tail -1; done; fi
