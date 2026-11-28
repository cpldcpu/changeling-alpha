![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/regression/badge.svg)

# Changeling-alpha

<!-- TEMPLATE. Headings and placeholders only. The introduction is written by Tim S. B. -->

## Introduction

<!-- TODO (Tim): introduction for the competition. -->

## What the chip is

<!-- TODO: five lines. Two 8-bit RISC cores, line cells, memories, host link, clock. Block diagram. -->

## Protocols

<!-- TODO: table protocol / roles / rates / how verified / status. Source: datasheet and verification report. -->

## Toolchain and example programs

<!-- TODO: compiler and options, header file, how to build and load, list of the examples in src/rsoc8/fw/examples. -->

## Verification

<!-- TODO: summary of methods and results with a link to the verification report. -->

## How AI tools were used

<!-- TODO: required by the competition rules. -->

## Documentation

| Document | Content |
|---|---|
| [Changeling-alpha datasheet](src/rsoc8/doc/pdf/rpe_datasheet.pdf) | user documentation: blocks, instruction set, registers, examples |
| [Verification report](test/report/rpe_verification.pdf) | methods, results, location of every test |
| [Architecture specification](src/rsoc8/doc/pdf/rpe_spec.pdf) | rules, design decisions, review history |
| [Tiny Tapeout project page](docs/info.md) | short description, how to test, external hardware |

## Repository map

| Path | Content |
|---|---|
| `src/rsoc8/` | the design: RTL (`rtl/`), firmware, headers and examples (`fw/`), area synthesis script (`syn/`), specification and datasheet (`doc/`). See [src/rsoc8/README.md](src/rsoc8/README.md) |
| `src/tt_um_cpldcpu_changeling_alpha.v`, `src/sram_bb.v`, `src/rpe_clk_analog_bb.v`, `src/timing.sdc`, `src/config.json`, `src/pdn_cfg.tcl` | Tiny Tapeout top module, SRAM blackbox, flow configuration with the three SRAM macros |
| `librelane_plugin_sram_pdn.py`, `odb_stripes.py` | power connection of the SRAM macros, from the Tiny Tapeout CMOS5L SRAM example |
| `info.yaml`, `docs/info.md` | Tiny Tapeout project data and project page |
| `test/` | verification suites (`tests/`, `tb/`, `model/`, `blocks/`, `formal/`), cocotb tests through the pins (`test.py`), [verification report](test/report/rpe_verification.pdf) and [plan](test/report/verification_plan.md). See [test/README.md](test/README.md) |
| `analog/` | clock macro `rpe_clk_analog` (ring oscillator, relaxation oscillator): schematics, layout generator, simulation results, [report](analog/report/analog_clock_report.pdf); status in [analog/HANDOVER.md](analog/HANDOVER.md) |
| `HANDOVER.md` | [state of the repository and of the hardening](HANDOVER.md), run history, open issues, local flow |
| `.github/workflows/` | Tiny Tapeout flow (gds, precheck, gate-level test, docs, fpga), `regression` and `doc` |

## Status and known limitations

<!-- TODO: state of GDS and precheck, timing, what is not implemented, what is not verified. -->

## Licence and credits

Apache-2.0, see [LICENSE](LICENSE). The SRAM integration (`src/pdn_cfg.tcl`, `librelane_plugin_sram_pdn.py`,
`odb_stripes.py` and the SRAM section of `src/config.json`) is taken from the Tiny Tapeout example
[ttcodebot/ttihp-cmos5l-sram-example](https://github.com/ttcodebot/ttihp-cmos5l-sram-example), which is adapted
from Ken Pettit's CMOS5L SRAM design. The behavioural SRAM models are from the IHP Open PDK. Files from other projects and the notices for
the compiled firmware images are listed in [NOTICE](NOTICE). Source files of this project carry an SPDX tag.
