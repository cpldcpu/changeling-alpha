# rsoc8: the design, independent of the implementation flow

This folder holds the flow-independent design sources: RTL, firmware and examples, area synthesis script, and
the specification and datasheet. The verification suites, testbenches, behavioural models, formal checks, and
verification report live in [`test/`](../../test/README.md). Another flow needs this folder, a top module that
instantiates `rpe_chip`, and its own macro and clock set-up.

| Path | Content |
|---|---|
| `rtl/` | `rcore8d.v` core, `rdual.v` two cores with arbiter and locks, `rlinecells.v` line cells, `rlcports.v` ports and pin multiplexer, `revents.v` event flags and wait, `rtimers.v` timer, PWM and CRC unit, `rclock.v` clocking, `rhost.v` host link and protection, `rpe_top.v` chip level `rpe_chip`, `rpe_osc_stub.v` placeholder of the oscillator |
| `fw/` | header `rpe.h`, firmware of the tests, protocol libraries, build scripts `build*.sh`, `examples/` |
| `syn/` | synthesis script for an area estimate with yosys |
| `doc/` | LaTeX sources of specification and datasheet, generators, `pdf/` built documents, `history/` records of the development |

Generated files go to `test/build/` (not committed).

## Running the tests

Needed: Icarus Verilog, Python 3, GCC for the core with its C library (`gcc-avr`, `avr-libc` on Debian and
Ubuntu; version 7.3.0 was used).

```
sh test/tests/ci.sh                              # CI base regression against test/tests/expected/
sh test/tests/run_fw.sh                          # base regression of the whole chip, about 15 minutes
sh test/tests/run_models.sh                      # five blocks against their Python models
sh test/tests/run_uart.sh                        # UART against the independent model
sh test/tests/spii2c.sh                          # SPI and I2C, all parts
sh test/tests/run_eth.sh                         # 10BASE-T endpoint; the tolerance sweeps take long
sh test/tests/run_waitirq.sh                     # interrupt during a wait, about 25 minutes
sh test/blocks/linecells/tests/run_all.sh
sh test/blocks/dual/tests/run_all.sh
sh test/blocks/dual/tests/run_arb.sh             # arbitration matrix, about 1.5 hours
sh test/formal/run.sh                            # formal check of the two-cycle exception (needs Yosys)
```

The verification report ([`test/report/rpe_verification.pdf`](../../test/report/rpe_verification.pdf)) lists
every test with its files and results. Its folder table uses the earlier package names: `rsys` is `test/`,
`rdual` is `test/blocks/dual`, `linecells` is `test/blocks/linecells`.

## Library cells

`rtl/rlinecells.v` instantiates a library clock gate when `IHP_CELLS` is defined: `sg13cmos5l_lgcp_1`, or
`sg13g2_lgcp_1` when `IHP_SG13G2` is defined as well. Without `IHP_CELLS` a behavioural latch is used
(simulation). No other file names a library cell. The SRAM macro `RM_IHPSG13_1P_1024x16_c2_bm_bist` is
instantiated in `rtl/rpe_top.v` (module `rpe_mem`).

## Documents

```
cd src/rsoc8/doc
python3 build_ds.py                           # regenerates ds_gen/ from the register map of the specification
latexmk -pdf rpe_spec.tex rpe_datasheet.tex
cd ../../../test/report
latexmk -pdf rpe_verification.tex
```

The timing diagrams and settings tables in `doc/figs/` are generated from simulation logs by
`test/tests/gen_waves.py` and `test/tests/gen_lcex.py` (see `doc/history/change_log.md`, last section).

## RTL changes after specification draft 0.36 (described in draft 0.37)

The specification and the verification report describe draft 0.36. Changes made in this repository since:

| Change | File | Reason |
|---|---|---|
| Chip level module renamed from `tt_um_cpldcpu_rpe` to `rpe_chip` | `rtl/rpe_top.v` | the Tiny Tapeout top module is a separate file outside this folder |
| Instance `clocking` renamed to `u_clock` | `rtl/rpe_top.v` | `clocking` is a SystemVerilog keyword |
| Clock gate cell `sg13cmos5l_lgcp_1` with `IHP_CELLS` | `rtl/rlinecells.v` | library of the target process |
| The output register of the dedicated outputs is reset by the system reset, no longer by the core reset | `rtl/rlcports.v`, `rtl/rpe_top.v` | the data output of the host link was held at zero during the core reset, so status and memory could not be read back before a program was started. Found by the cocotb test; the system testbench (`+spiload`) and the cocotb test now read in the core reset |
| Reset value of the core divider `CLKCDIV` is 1 (divider 2) instead of 0 | `rtl/rclock.v`, `rtl/rlinecells.v` (`rlc_reg` with a reset value) | at 60 MHz the paths from the code memories into the cores need two clock cycles at the slow corner; with divider 2 the cores have them. The testbench writes divider 1 where the tests assume it (`+cdiv`, `+cdivreset`) |
| Keep attribute on the registers `tx_next`, `tx_hold` and on `dq` of the cores | `rtl/rhost.v`, `rtl/rcore8d.v` | names for the timing constraints in `src/timing.sdc`: these registers take a host read of a code memory after one cycle and are excluded from the two-cycle exception |
| Injection state (`jst`, `jmode`, `jcore`, `jword`) changes only in cycles with the core clock enable; an injection command in another cycle is held in `jreq` | `rtl/rdual.v` | condition of the two-cycle timing exception; with a divider above 1 an injection starts up to divider − 1 clock cycles later |
| The read that restores a code memory output after a host access takes place only in a cycle with the core clock enable | `rtl/rdual.v` | the restored output is then stable for a full core period before a core takes it |
| `dq` of the cores takes the data memory output in the cycle after a read without regard to `cen` | `rtl/rcore8d.v` | removes the path from the code memory through `cen` to `dq`; the value the core uses is unchanged |
| Keep attribute on `state`, `ir` of the cores and on the injection registers | `rtl/rcore8d.v`, `rtl/rdual.v` | names for the timing constraints; the state encoding stays binary |
| `RELAXEN` (bit 7 of `CLKCTL`), input `clk_slow` with synchroniser, `REFSEL` = 3, debug signal 15; second enable and second clock output at the oscillator | `rtl/rclock.v`, `rtl/rpe_top.v`, `rtl/rpe_osc_stub.v` | relaxation oscillator of the macro `rpe_clk_analog` as a reference of the trim counter (specification draft 0.37) |
| Status `inj_busy` and `h_quiet` from the new register `jbusy` and from `jreq`, not from `jst`; `jto` changes only in cycles with the core clock enable | `rtl/rdual.v` | findings of the formal check of the timing exception (`formal/README.md`). The status stays active one enabled cycle longer after an injection |

Side effect of the change of the output register: the clock output and the debug signal, whose enables belong to the clocking
block, are no longer forced low while the core reset is set.
