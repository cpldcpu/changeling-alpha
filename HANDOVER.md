# Handover: state of the repository and of the hardening

Date: 22 November 2026. For Tim S. B. (GitHub: cpldcpu), who continues the hardening on a local machine.
Branch `integration` (pull request #1). `main` holds the unchanged template.

Other handover files: [analog/HANDOVER.md](analog/HANDOVER.md) (clock macro, plan only) and
[src/rsoc8/doc/history/handover_2026-11-21.md](src/rsoc8/doc/history/handover_2026-11-21.md) (design
package before the move into this repository; partly superseded by this file).

## 1. Summary

- RTL, tests and documents are in the repository and the workflows `test`, `docs`, `doc` and `regression`
  pass on the last commit.
- No hardening run has passed. Floorplan, power grid, LVS, antenna and hold are solved. Setup timing at the
  slow corner and routing congestion are not.
- Hardening is halted. Decision of 22 November: continue with local runs and reconsider the architecture
  (section 6) before more trials.

## 2. What passes

| Item | State |
|---|---|
| Base regression (`sh src/rsoc8/tests/ci.sh`: line cells, two cores, models, firmware) | passes, output equal to `tests/expected/` |
| Host link test (halt, memory access, step, inject, break) | passes at core dividers 1, 2 and 3 |
| cocotb test through the pins (`test/`, load through the host link, UART echo) | passes on RTL |
| Document build (specification, datasheet, verification report) | passes; content is at draft 0.36, see section 7 |

Not rerun since the RTL changes in this repository: `run_uart.sh`, `spii2c.sh`, `run_eth.sh`,
`run_waitirq.sh`, `blocks/dual/tests/run_arb.sh`, the stress tests. The gate-level test has never run,
because no hardening run finished.

## 3. Hardening setup

| Parameter | Value |
|---|---|
| Process, library | `ihp-sg13cmos5l`, `sg13cmos5l_stdcell`; LibreLane 3.1.0.dev4 |
| Area | 8x4 tiles, die 1724.16 x 710.64 µm, core area 1.208 mm² |
| Macros | three `RM_IHPSG13_1P_1024x16_c2_bm_bist` (236.8 x 336.46 µm each, 0.239 mm² together), in a row at the bottom edge at x = 3.36, 599.08, 1194.8 µm |
| Standard cells | about 23,000 cells, 322,000 µm², 33 % of the core area |
| Routing layers | Metal2 to Metal4 |
| Clock | 60 MHz (16.67 ns). Peripherals in every cycle, cores in every second cycle by clock enable (reset value of `CLKCDIV`) |
| Constraints | `src/timing.sdc`: two clock cycles from the three memories and from 62 core and injection flip-flops; 32 flip-flops excluded |
| Flow settings | `src/config.json`: slow corner as default corner, target density 40, design and timing repair after global routing, setup margin 1 ns |

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

## 6. Open issues

Hardening:

1. Routing capacity. Three signal layers, Metal3 at 55 % usage in runs D and F. A small netlist change moved
   the global routing overflow from 16 to 1,857.
2. Floorplan. All logic lies in one strip 1.4 mm wide above the memories. Both cores, the arbiter and the
   peripherals share it, and each core uses all three memories. The worst paths of run C contain 1x cells
   that drive 0.13 to 0.30 pF of wire.
3. Logic depth of the core: about 20 ns at the slow corner without the memory. The core cannot run at 60 MHz
   at that corner.
4. The two-cycle exception is not verified. It is valid only if the capture enables stay low in the cycle
   without core clock enable and synthesis does not restructure the gating. Planned checks: gate-level
   simulation with delays, formal property on the enables. One violation of its condition was found by
   reading the RTL (section 5), not by a test.
5. The wire estimate of the repair steps is several nanoseconds better than extraction at the slow corner
   (run D: +0.03 ns estimated, −5.87 ns extracted).
6. `TRIG` to `timers.val`, single cycle, −0.92 ns in run D.
7. Not checked: whether the shuttle requires setup to pass at the slow corner. The flow's checker fails on
   any corner.

Questions for the architecture review:

- Is 60 MHz needed for all peripherals or only for the line cells that serve 10BASE-T and USB?
- Pipeline register after the code memory and a true divided core clock instead of exceptions?
- Each core placed next to its own code memory (memories on two sides, or a region per core)?
- Is a smaller second core or function enough for the flexibility criterion, given the routing limit?

Other open points: line cell functions C1 to C6 are specified and not implemented; the clocking plan of
`analog/HANDOVER.md` is not in the specification; the verification plan
(`src/rsoc8/doc/verification_plan.md`) is not started; the introduction and the TODO sections of
`README.md` are empty on purpose.

## 7. Documents behind the RTL

The three PDFs in `src/rsoc8/doc/pdf/` describe draft 0.36. Not yet in them: the divider reset value 2, the
RTL changes of section 5, the output register reset by the system reset, and the repository paths in the
folder table of the verification report.

## 8. Local hardening

The workflow `gds` runs the following (from `TinyTapeout/tt-gds-action@ttihp27a`, `action.yml`). These
commands were read from the action and not executed outside GitHub Actions for this project.

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
- A push to GitHub starts the `gds` workflow, which at present does not finish. `[skip ci]` in the commit
  message prevents it.
- Flip-flops in the timing reports have generic names. Their register names are the Q nets in
  `runs/wokwi/06-yosys-synthesis/*.nl.v`.
