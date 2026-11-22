# rsoc8: the design, independent of the implementation flow

This folder holds everything that does not depend on Tiny Tapeout: RTL, testbenches, behavioural models,
test scripts, firmware and the documents. Another flow needs this folder, a top module that instantiates
`rpe_chip`, and its own macro and clock set-up.

| Path | Content |
|---|---|
| `rtl/` | `rcore8d.v` core, `rdual.v` two cores with arbiter and locks, `rlinecells.v` line cells, `rlcports.v` ports and pin multiplexer, `revents.v` event flags and wait, `rtimers.v` timer, PWM and CRC unit, `rclock.v` clocking, `rhost.v` host link and protection, `rpe_top.v` chip level `rpe_chip`, `rpe_osc_stub.v` placeholder of the oscillator |
| `tb/` | system testbench `tb_sys.v` with the protocol models (UART, SPI, I2C, USB host, 10BASE-T, WS2812, I2C sensor, oscillator), block testbenches, `ihp/` behavioural model of the SRAM macro |
| `model/` | behavioural models in Python of the blocks timers, events, two cores, clock control, protection, host link |
| `tests/` | regression scripts (`run_fw.sh`, `run_models.sh`, `run_uart.sh`, `spii2c.sh`, `run_eth.sh`, `run_waitirq.sh`, stress tests), fault insertion, generators of the datasheet timing diagrams |
| `fw/` | header `rpe.h`, firmware of the tests, protocol libraries, `examples/` |
| `blocks/linecells/` | line cells alone: behavioural model `model/linecell.py`, testbenches, `tests/run_all.sh` |
| `blocks/dual/` | two-core block alone: cycle model, lockstep random tests, arbitration tests, `tests/run_all.sh`, `tests/run_arb.sh` |
| `syn/` | synthesis script for an area estimate with yosys |
| `doc/` | LaTeX sources of specification, datasheet and verification report, generators, `pdf/` built documents, `history/` records of the development |

All scripts change into their own package directory, so they can be started from anywhere. Generated files
go to `build/` (not committed).

## Running the tests

Needed: Icarus Verilog, Python 3, GCC for the core with its C library (`gcc-avr`, `avr-libc` on Debian and
Ubuntu; version 7.3.0 was used).

```
sh src/rsoc8/tests/run_fw.sh                  # base regression of the whole chip, about 15 minutes
sh src/rsoc8/tests/run_models.sh              # five blocks against their Python models
sh src/rsoc8/tests/run_uart.sh                # UART against the independent model
sh src/rsoc8/tests/spii2c.sh                  # SPI and I2C, all parts
sh src/rsoc8/tests/run_eth.sh                 # 10BASE-T endpoint; the tolerance sweeps take long
sh src/rsoc8/tests/run_waitirq.sh             # interrupt during a wait, about 25 minutes
sh src/rsoc8/blocks/linecells/tests/run_all.sh
sh src/rsoc8/blocks/dual/tests/run_all.sh
sh src/rsoc8/blocks/dual/tests/run_arb.sh     # arbitration matrix, about 1.5 hours
```

The verification report (`doc/pdf/rpe_verification.pdf`) lists every test with its files and results. Its
folder table uses the earlier package names: `rsys` is this folder, `rdual` is `blocks/dual`, `linecells` is
`blocks/linecells`.

## Library cells

`rtl/rlinecells.v` instantiates a library clock gate when `IHP_CELLS` is defined: `sg13cmos5l_lgcp_1`, or
`sg13g2_lgcp_1` when `IHP_SG13G2` is defined as well. Without `IHP_CELLS` a behavioural latch is used
(simulation). No other file names a library cell. The SRAM macro `RM_IHPSG13_1P_1024x16_c2_bm_bist` is
instantiated in `rtl/rpe_top.v` (module `rpe_mem`).

## Documents

```
cd src/rsoc8/doc
python3 build_ds.py                           # regenerates ds_gen/ from the register map of the specification
latexmk -pdf rpe_spec.tex rpe_datasheet.tex rpe_verification.tex
```

The timing diagrams and settings tables in `doc/figs/` are generated from simulation logs by
`tests/gen_waves.py` and `tests/gen_lcex.py` (see `doc/history/change_log.md`, last section).

## RTL changes after specification draft 0.36

The specification and the verification report describe draft 0.36. Changes made in this repository since:

| Change | File | Reason |
|---|---|---|
| Chip level module renamed from `tt_um_cpldcpu_rpe` to `rpe_chip` | `rtl/rpe_top.v` | the Tiny Tapeout top module is a separate file outside this folder |
| Instance `clocking` renamed to `u_clock` | `rtl/rpe_top.v` | `clocking` is a SystemVerilog keyword |
| Clock gate cell `sg13cmos5l_lgcp_1` with `IHP_CELLS` | `rtl/rlinecells.v` | library of the target process |
| The output register of the dedicated outputs is reset by the system reset, no longer by the core reset | `rtl/rlcports.v`, `rtl/rpe_top.v` | the data output of the host link was held at zero during the core reset, so status and memory could not be read back before a program was started. Found by the cocotb test; the system testbench (`+spiload`) and the cocotb test now read in the core reset |
| Reset value of the core divider `CLKCDIV` is 1 (divider 2) instead of 0 | `rtl/rclock.v`, `rtl/rlinecells.v` (`rlc_reg` with a reset value) | at 60 MHz the paths from the code memories into the cores need two clock cycles at the slow corner; with divider 2 the cores have them. The testbench writes divider 1 where the tests assume it (`+cdiv`, `+cdivreset`) |
| Keep attribute on the instruction inputs `prd0`, `prd1` | `rtl/rdual.v` | net names for the two-cycle timing exception in `src/timing.sdc` |

Side effect of the change of the output register: the clock output and the debug signal, whose enables belong to the clocking
block, are no longer forced low while the core reset is set.
