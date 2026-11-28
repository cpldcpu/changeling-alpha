# Formal check of the two-cycle timing exception

`src/timing.sdc` gives two clock cycles to every path that starts at one of the three memories or at one of
62 flip-flops (`state` and `ir` of both cores; `jst`, `jmode`, `jcore`, `jword` of the injection sequencer).
Static timing analysis accepts these paths with up to 33.3 ns. This is correct only if nothing captures a
value that depends on such a start point in the clock cycle directly after the start point changed. The check
in this folder proves that condition on the RTL of `rdual.v` with both cores (`rcore8d.v`).

## What is proved

For the two-core block, from any state that satisfies the listed assumptions:

| Property | Statement |
|---|---|
| P1 | The 62 start flip-flops change only at the end of a clock cycle with the core clock enable `cke`. |
| P2 | In the cycle after bits of a start flip-flop changed, the next value of every register and every output of the block is the same for any value of those bits. |
| P3 | In the cycle after an access to a memory, the next value of every register and every output is the same for any value of that memory's output. Excepted: `dq` of the cores for the data memory, and the read data to the host link (`h_rdata`). Both are constrained to one cycle in `timing.sdc`. |
| I2, I3 | A pending restore read or break clear ends with the next cycle with `cke` (helper invariants). |
| I5 | While an injection runs, `jbusy` is set (helper invariant). |
| I4 | A core that waits for a byte from the data memory has read it one cycle ago or holds it in `dq` (helper invariant). |

Outputs with an enable (memory address and data, register bus address and data) are compared only while their
enable is active; the enables themselves are always compared.

Method: the flip-flops of the flattened block are cut open, so that the block becomes a function from state
and inputs to next state and outputs (`gen_exc.py`). A wrapper holds the state and evaluates this function
twice per cycle: with the real values, and with the start point under test replaced by free values. A
difference at anything that is captured is a violation. Each of the four cases (start flip-flops, code memory
0, code memory 1, data memory) is checked from reset to a bounded depth and by an induction step of length 3
from an arbitrary state, with the SAT solver built into Yosys. Together these two results hold for runs of any
length.

## Assumptions

| Assumption | Basis |
|---|---|
| The core clock enable is active in at most one of two consecutive cycles and at least one of four | core divider 2, 3 or 4. Not proved on `rclock.v`. Divider 1 violates the exception by construction. Dividers above 4 are not covered |
| No core reset during operation | the reset is asynchronous and changes the start flip-flops in any cycle; paths from a reset are not part of this check |
| Host accesses (`h_acc`) only if `h_quiet` was active in the cycle before | `rhost.v`: `h_acc` is a register loaded from `acc_ok` |
| Injection commands only for a halted, enabled core while no injection runs | `rhost.v`: `inj_cmd` is a register loaded from `core_ok` |
| Host events (access, injection command, break clear, change of the halt requests) are 8 clock cycles apart or more, and an access or an injection command does not coincide with another event | `rhost.v`: one action per received byte; a byte takes 8 periods of the host clock. Not proved on `rhost.v` |

## Findings and their correction

The first run, on the RTL of commit 7fe556b, found two violations. Both are corrected in `rdual.v`, and the
check now passes without a waiver and with all outputs checked.

1. **`h_quiet` and `inj_busy` depended on `jst` in the cycle after it changed.** The host link samples both when
   a command byte is complete, which can be any cycle. Correction: the status comes from a register of its own
   (`jbusy`) and from `jreq`. Helper invariant I5 states that `jbusy` is set while an injection runs.
2. **`jto` (time-out counter of the injection) depended on the state of the core under injection in the cycle
   after that state changed**, if the other core restarted that core during an injection. Correction: `jto`
   changes only in cycles with `cke`.

Still open: the restore read after a host access can coincide with the next host access if the core divider is
larger than the distance between host events. The proof therefore covers dividers 2 to 4 only. With the reset
value 2 the case cannot occur.

## Is the check able to fail?

`faults.sh` inserts four faults into copies of the RTL and each is reported: the restore read in any cycle and
the injection sequencer in any cycle (both are the RTL as it was before draft 0.37), the cores without the
clock enable, and a core that also advances in the cycle after a data read.

Two further changes are not violations of the exception and are not reported, as it must be: `dq` enabled by
`cen` (the form before draft 0.37; `cen` is low in the cycle after a fetch whatever the memory puts out), and a
code memory read without `cke` (the request is already gated through the core enable).

A first version of the check used clocked assertions. The SAT pass of Yosys evaluates those one cycle late, so
the induction step passed without testing anything, and the first two faults above were not detected. The
assertions are now unclocked. This is the reason `faults.sh` is part of the check.

## Running

```
sh run.sh            # all four cases; about 4 minutes; exit status 1 on a violation
sh faults.sh         # fault insertion; about 12 minutes
./cex.sh S 3 q84     # counterexample of an induction step, with chosen signals (register numbers: build/S/exc_top.v)
```

`YOSYS` names the Yosys command (default `yosys`; the check was developed with Yosys 0.71 from the Python
package `yowasp-yosys`). `BMC_DEPTH` (default 8) and `IND` (default 3) set the depths. No SMT solver is needed.

## Not covered

- The routed netlist. The proof is on RTL; synthesis may restructure gating so that a signal that is logically
  constant in a cycle still glitches. This needs the gate-level simulation with delays.
- `rhost.v`, `rclock.v` and the peripherals as start or end points. The peripherals are end points through the
  register bus outputs of this block, which are checked.
- Core dividers 1 and above 4, and the core reset.
