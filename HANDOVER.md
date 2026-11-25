# Handover: state of the repository and of the hardening

Date: 25 November 2026 (first version 22 November). For Tim S. B. (GitHub: cpldcpu).
Branch `integration` (pull request #1). `main` holds the unchanged template.

Other handover files: [analog/HANDOVER.md](analog/HANDOVER.md) (clock macro) and
[src/rsoc8/doc/history/handover_2026-11-21.md](src/rsoc8/doc/history/handover_2026-11-21.md) (design
package before the move into this repository; partly superseded by this file).

## 1. Summary

- The design is hardened with the oscillator macro. Run 45510873906 on commit `c7f1d06` passed all jobs:
  `gds`, `precheck`, `gl_test`, `viewer`.
- Setup slack at 16.67 ns: +1.75 ns at the slow corner, +5.38 ns typical, +5.19 ns fast. Hold +0.21 ns.
  No DRC, LVS, antenna, slew or capacitance violation.
- The cores run at half the system clock (reset value of the core divider). Timing depends on a two-cycle
  exception that is not yet verified at gate level with delays (section 6).
- Specification (draft 0.37), datasheet (revision 0.4) and verification report (issue 3) describe this state.

## 2. What passes

| Item | State |
|---|---|
| Base regression (`sh src/rsoc8/tests/ci.sh`: line cells, two cores, models, firmware) | passes, output equal to `tests/expected/` |
| Host link test (halt, memory access, step, inject, break) | passes at core dividers 1, 2 and 3 |
| Clocking block test (`tb/tb_clk.v`), with single measurement and loop against the relaxation oscillator | passes; three inserted faults are detected |
| cocotb tests through the pins (`test/`): load through the host link and UART echo; internal oscillators | pass on RTL and on the gate-level netlist |
| Document build (specification, datasheet, verification report) | passes |
| Long suites (`run_uart.sh`, `spii2c.sh`, `run_eth.sh`, `run_waitirq.sh`, `blocks/dual/tests/run_arb.sh`) | rerun on 25 November, pass. The exact-timing check in `run_arb.sh` passes with 62 checks after a correction of the check itself (verification report, section "State of the regression") |

Not rerun since the RTL changes in this repository: the stress tests (`tests/stress_*.py`).

## 3. Hardening setup

| Parameter | Value |
|---|---|
| Process, library | `ihp-sg13cmos5l`, `sg13cmos5l_stdcell`; LibreLane 3.1.0.dev4 |
| Area | 8x4 tiles, die 1724.16 x 710.64 µm, core area 1.208 mm² |
| Macros | three `RM_IHPSG13_1P_1024x16_c2_bm_bist` (236.8 x 336.46 µm each) in a row at the bottom edge at x = 3.36 (code 0), 599.08 (data), 1194.8 µm (code 1); `rpe_clk_analog` (171.5 x 137 µm) at x = 1514.88 µm |
| Standard cells | 27,439 cells, 403,463 µm², 43 % of the area outside the macros |
| Routing layers | Metal2 to Metal4 |
| Clock | 60 MHz (16.67 ns). Peripherals in every cycle, cores in every second cycle by clock enable (reset value of `CLKCDIV`). Second clock `clk_osc` at the macro pin, asynchronous to `clk`; false paths through `clk_slow`, the enables and the trim pins |
| Constraints | `src/timing.sdc`: two clock cycles from the three memories and from 62 core and injection flip-flops; 32 flip-flops excluded |
| Flow settings | `src/config.json`: slow corner as default corner, target density 40, timing-driven placement, design and timing repair after global routing, setup margin 1 ns, hold margin 0.3 ns, maximum wire length 200 µm in the repair steps, calibrated `LAYERS_RC` |
| Run time | `gds` job 2 h 55 min, of which 1 h 15 min timing repair after global routing (GitHub limit: 6 h) |

Timing facts at the slow corner (1.08 V, 125 °C): memory access 7.6 ns; decode, ALU and register file write
about 20 ns from a flip-flop; code memory to register file 27.1 ns in run 3. At the typical corner the long
path is 17.2 ns.

## 4. Run history

All runs in GitHub Actions on branch `integration`. Slack values are setup, after extraction.

| Run | Commit content | Result |
|---|---|---|
| 1 (45008538404) | first configuration | PDN-0179: rows between the macros without power stripe |
| 2 (45008997433) | macros 10.48 µm apart, density 60 | detailed routing did not converge (overflow 12,608), cancelled |
| 3 (45021839569) | density 40 | routed, LVS and hold clean. Typical −0.51 ns, slow −10.47 ns, fast +5.37 ns |
| 4 (45026958748) | `SYNTH_STRATEGY` DELAY 4 | identical to run 3; setting removed |
| A (45032707393) | two-cycle exception through kept nets | exception without effect; routing stuck (overflow 4,238), cancelled |
| B (45045076268) | exception from the code memories, macros spread | 0 DRC, 0 LVS, hold clean. Typical +0.24 ns, slow −9.57 ns (588 endpoints), fast +5.70 ns |
| C (45050602329) | slow corner as default corner, exception also from the data memory | slow −7.29 ns (461 endpoints), typical +1.57 ns |
| D (45057749114) | repair after global routing | slow −5.87 ns (357 endpoints), typical +2.44 ns. Routing overflow 16. Last run that routed |
| E (45062757331) | setup margin 3 ns | 50 minutes in the timing repair after global routing (297 endpoints), cancelled |
| F (45069729945) | RTL change of section 5, exception from 62 flip-flops, margin 1 ns | repair before routing closed setup (213 endpoints, 8 buffers). Global routing overflow 1,857, wire length 2.23 m (run D: 1.97 m); cancelled after 67 minutes |
| 45146827928 | data memory between the code memories, timing-driven placement (commits `f4fb731`, `fe8c981`, by Tim S. B.) | failed; not analysed in this file |
| 45253505420 | calibrated `LAYERS_RC`, wire length limit, `ca_flops` walks back through buffers to the flip-flop (`d00342a`) | failed; not analysed in this file |
| 45510873906 | oscillator macro integrated (`c7f1d06`) | passes. Slow +1.75 ns, typical +5.38 ns, fast +5.19 ns; overflow 0; wire length 1.32 m; 55 setup and 36 hold buffers in the last repair step |

Failing start points in run D: `cores.jst[1]` (264 endpoints, −5.87 ns), `core1.pm_we` (17, −2.48 ns),
code memory 0 to `dq` (16, −2.47 ns), `cores.jst[0]` (29, −1.35 ns), `ports.t0.TRIG[1]` to `timers.val`
(31, −0.92 ns). The first four are addressed by the RTL change of run F; the last is a single-cycle path
between peripherals and is open.

## 5. RTL changes for timing (commit 4b4bd2c)

Listed with reasons in [src/rsoc8/README.md](src/rsoc8/README.md), table "RTL changes after specification
draft 0.36". In short:

- `rdual.v`: the injection registers change only in cycles with the core clock enable; a command in another
  cycle is held in `jreq`. The read that restores a code memory output after a host access takes place only
  in an enabled cycle. Before this change the core could take a restored output after one cycle.
- `rcore8d.v`: `dq` captures without regard to `cen`. Keep attributes on `state` and `ir`.
- `rclock.v` (earlier commit): reset value of the core divider is 2.
- `rclock.v`, `rpe_top.v` (commit c7f1d06, by Tim S. B.): second enable `RELAXEN` (bit 7 of `CLKCTL`), input
  `clk_slow` with synchroniser, `REFSEL` = 3 selects it as the reference of the trim counter, debug signal 15.
  The oscillator is the macro `rpe_clk_analog`, declared in `src/rpe_clk_analog_bb.v`.

## 6. Open issues

Implementation:

1. The two-cycle exception is not verified. It is valid only if the capture enables stay low in the cycle
   without core clock enable and synthesis does not restructure the gating. Planned checks: gate-level
   simulation with delays (SDF), formal property on the enables. The gate-level test runs without delays.
2. Core divider 1 (`CLKCDIV` = 0) is not covered by the timing above a system clock of 30 MHz. Nothing in
   the hardware prevents the setting.
3. The ring oscillator reaches 84 MHz (typical) to 97 MHz (fast corner) at trim 255; the logic is timed for
   60 MHz. Nothing in the hardware limits the trim value.
4. The layout that passed DRC and LVS in `analog/results/` is `rpe_clk_analog.gds`. The flow integrates
   `rpe_clk_analog_tt.gds` (marker layers removed, no-fill shapes added). Its only DRC record is the
   precheck. The flow LVS treats the macro as a black box.
5. Each hardening trial takes about three hours in GitHub Actions.

Clocking:

6. The relaxation oscillator spans 83.6 to 115.5 kHz over the simulated corners. It is a reference only
   after one measurement per chip against an external signal (datasheet section "Trimming the oscillator").
7. The system tests with the internal oscillator (USB, UART) used the model `tb/osc_model.v` at 15 MHz. They
   are not repeated with a model of the ring at 60 MHz. `test/rpe_clk_analog_model.v` exists for the pin test.
8. There is no sleep state on the slow clock in the digital part.

Other open points: line cell functions C1 to C6 are specified and not implemented; the verification plan
(`src/rsoc8/doc/verification_plan.md`) is not started; the introduction and the TODO sections of
`README.md` are empty on purpose.

## 7. Documents

Specification draft 0.37, datasheet revision 0.4 and verification report issue 3 in `src/rsoc8/doc/pdf/`
describe the RTL of this commit. The analog report is `analog/report/analog_clock_report.pdf`.

## 8. Local hardening

The workflow `gds` runs the following (from `TinyTapeout/tt-gds-action@ttihp27a`, `action.yml`). These
commands were read from the action; I (Claude) did not execute them. The local runs of 23 and 24 November
were made by Tim S. B.

```
git clone -b integration https://github.com/cpldcpu/changeling-alpha
cd changeling-alpha
git clone https://github.com/TinyTapeout/tt-support-tools tt        # branch main, as in the action
python3.11 -m venv venv && . venv/bin/activate
pip install -r tt/requirements.txt
pip install librelane==3.1.0.dev4
./tt/tt_tool.py --create-user-config --pdk ihp-sg13cmos5l
./tt/tt_tool.py --harden --pdk ihp-sg13cmos5l
```

- `--harden` starts LibreLane in a Docker container (`--dockerized`); with `--no-docker` it uses the tools
  of the environment (Nix). If `PDK_ROOT` is set, it is passed to LibreLane.
- The run directory is `runs/wokwi/`. Timing: `*-openroad-stapostpnr/summary.rpt` and
  `nom_slow_1p08V_125C/max.rpt`; numbers: `final/metrics.json`; repair logs: `*-openroad-resizertiming*`,
  `*-openroad-repairdesign*`; congestion: `*-openroad-globalrouting`.
- `./tt/tt_tool.py --open-in-openroad` and `--open-in-klayout` open the result of the run.
- The constraints file prints two lines beginning with `[INFO] Changeling-alpha:` in every timing step and
  stops the flow if it does not find 3 memories, 32 excluded and 62 two-cycle flip-flops.
- A push to GitHub starts the `gds` workflow, which takes about three hours. `[skip ci]` in the commit
  message prevents all workflows for that push.
- Flip-flops in the timing reports have generic names. Their register names are the Q nets in
  `runs/wokwi/06-yosys-synthesis/*.nl.v`.
