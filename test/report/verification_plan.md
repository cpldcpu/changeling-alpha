# Verification plan

Date: 22 November 2026. State: plan. What exists today is in the verification report
(`rpe_verification.pdf`); this file lists what is to be added before the submission, in order of
priority. Nothing in sections 1 to 6 is done yet, and whether the formal tools run in the environment in
which the RTL is written is not checked; they run in GitHub Actions.

## What exists (summary)

- Every block has a behavioural model in Python that was written from the specification; RTL and model are
  compared cycle by cycle or frame by frame, directed and with random configurations.
- The two cores run random instruction streams in lockstep with a cycle model.
- The whole chip runs firmware against protocol models (UART, SPI, I2C, USB host, 10BASE-T, WS2812) that
  were written independently of the RTL.
- Faults were inserted by hand into RTL, firmware and models to check that the tests fail.
- Gaps named in the report: no static timing, no gate-level simulation, no formal proof, no coverage figure.

## 1. Formal proofs of the line cells, per configuration

Tool: SymbiYosys. The configuration registers are constants or constrained to a family; the solver chooses
the input. First bounded (all inputs up to two or three frames from reset), then by induction for one
configuration as a trial.

| Proof | Claim | Open fields |
|---|---|---|
| 1a Round trip | For every sequence of data and every write time, the receive cell of a pair delivers exactly the frames written to the transmit cell, in order, none lost or added | `LEN`, `LSBF`, `PAR`, stuffing limit, data, write times |
| 1b Timing tolerance | For every input waveform whose bit lengths deviate by at most d clock cycles from nominal, in any combination, every bit is sampled once with the right value. Result: the largest d per configuration | bit lengths within the bound, data |
| 1c Reference equivalence | For any input sequence, also malformed, frames and status flags equal those of a reference decoder written from the rules of the specification, independently of the RTL | input |
| 1d Return to search | After any input, the cell is back in its search state a bounded number of cycles after the line has become idle | input |

Configurations: UART without and with parity, SPI slave in the four modes, I2C reception with start and
stop, NRZI with bit stuffing (USB), Manchester (10BASE-T), compare mode (WS2812). The proofs use 2 to 8
clock cycles per bit; that the timer counts correctly for larger values is shown separately.

Trial case, to be done first: proof 1a for UART.

Limits: the proofs show that the cell follows the rules. That the rules match a protocol standard remains
with the protocol models, and firmware is outside.

## 2. Other formal proofs

| Target | Property |
|---|---|
| Line cells, version equivalence | with `LCX` = 0 and `LCEC` = 0 the RTL behaves like the RTL of draft 0.34 (sequential equivalence) |
| Arbiter and locks (`rdual.v`) | never two grants in one cycle; bounded waiting time in every arbitration mode; no write lost |
| Protection (`rhost.v`, module `rprot`) | a protected register changes only after the unlock sequence |
| Line cells, safety | a frame is dropped only with `OVR` set; no output drive while the cell is disabled; with `ESTR` the output changes only at shift edges |
| Core (`rcore8d.v`) | every instruction against a per-instruction specification of result, flags and cycle count |
| Clock switch (`rclock.v`) | never two sources enabled; no pulse shorter than a half period of the faster source |

## 3. Traceability and functional coverage

- A generated table maps every numbered rule of the specification to the tests that check it. Rules without
  a test are listed.
- The random tests of the line cells record which field values and combinations were drawn and which
  internal situations occurred (overrun, discarded stuffed bit, both holding slots full, every transmit
  stage, additional bit with stuffing). Holes are closed with directed cases.
- Coverage of instruction x flag result in the lockstep tests of the cores.

## 4. Mutation testing

`mcy` generates single faults in the synthesised line cells and in the arbiter and reports which ones the
suites detect. Result: a mutation score per block, and a list of undetected faults that are either
equivalent or show a missing test.

## 5. Code coverage

Line, branch and toggle coverage of the line cell suite with Verilator. Icarus Verilog has no coverage.

## 6. Gate-level simulation

- The cocotb tests in `test/` on the netlist of the Tiny Tapeout flow (workflow job `gl_test`).
- The same with randomised start values of all flip-flops, to show that reset alone gives a defined state.
- More firmware tests through the pins: SPI, I2C, two cores.

## 7. Further items

- Longer random lockstep runs in CI.
- Test on an FPGA against real devices, if a board with enough logic and memory is available.
- Write-up of the method for the competition: specification with numbered rules first; models and tests
  written by separate agents from the specification; review log; fault insertion; this plan and its results.

## Order

1. Proof 1a for UART as the trial case.
2. Traceability table and functional coverage.
3. Version equivalence and arbiter properties.
4. Proofs 1b to 1d and the other configurations.
5. Mutation testing.
6. Core instruction proofs.
7. Gate-level simulation with random start values, when the netlist exists.

## Status, 25 November 2026

Not in the plan above and done first, because the timing closure depends on it: a formal check of the
two-cycle timing exception on the two-core block (`test/formal/`, method, assumptions and findings in its
README). The items of the plan itself are not started.
