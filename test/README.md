# Changeling-alpha Verification & Test Suites

This directory contains all verification suites, pin-level cocotb tests, standalone block regressions, formal checks, and the verification report for Changeling-alpha (`src/rsoc8/rtl`).

## 1. Tiny Tapeout pin-level cocotb tests

Runs `tb.v` (`tt_um_cpldcpu_changeling_alpha` with `sram_model/` and `rpe_clk_analog_model.v`) driven by `test.py` (`test_load_and_uart_echo` loading `fw/uart_echo.hex`, and `test_internal_osc_and_relax`):

```sh
cd test
make -B                # RTL simulation
make -B GATES=yes      # Gate-level simulation (requires gate_level_netlist.v and PDK_ROOT)
```

View waveforms with `gtkwave tb.fst tb.gtkw` or `surfer tb.fst`. Runs automatically in `.github/workflows/test.yaml` and `gl_test` in `.github/workflows/gds.yaml`.

## 2. CI & system regression suites (`tests/`)

Needs `iverilog`, `python3`, `gcc-avr` (`mmcu=attiny40`), and `avr-libc`:

```sh
sh test/tests/ci.sh                # CI regression (linecells, dual, models, fw) compared against tests/expected/
sh test/tests/run_fw.sh            # whole-chip firmware, host link, timer model, clocking & sync (~15 min)
sh test/tests/run_models.sh        # events, dual, clkctl, prot, host RTL vs Python models in model/ (100 seeds)
sh test/tests/run_uart.sh          # UART echo, parity, mailbox & WS2812 bridges against protocol models
sh test/tests/spii2c.sh            # SPI master/slave, I2C master/slave, multi-master arbitration, RTL faults
sh test/tests/run_eth.sh           # 10BASE-T ARP/ping endpoint & tolerance sweeps
sh test/tests/run_waitirq.sh       # interrupt during wait sweep across core dividers and arbitration modes
```

`tests/` also contains multi-protocol stress suites (`stress_t1.py`..`stress_t4.py`), fault-injection runners (`fault_run.py`, `mut_host.py`, `waitfault.sh`), and datasheet diagram/example generators (`gen_waves.py`, `gen_lcex.py`). Firmware C/assembly sources live in `../src/rsoc8/fw/`, and generated testbench/firmware build outputs go to `test/build/`.

## 3. Standalone block suites (`blocks/`)

- `blocks/linecells/` — line cell RTL (`rlinecells.v`) vs Python model `model/linecell.py` and directed multi-pair testbench `tb/tb_lc2.v`:
  ```sh
  sh test/blocks/linecells/tests/run_all.sh
  ```
- `blocks/dual/` — two-core block (`rdual.v` + `rcore8d.v`) vs cycle models `model/rmodel.py` and `model/rmodel_d.py`:
  ```sh
  sh test/blocks/dual/tests/run_all.sh
  sh test/blocks/dual/tests/run_arb.sh     # arbitration matrix (~1 h)
  ```

## 4. Formal check (`formal/`)

Bounded model checking and 3-step induction proof (Yosys SAT) of the `src/timing.sdc` two-cycle exception on `rdual.v` and `rcore8d.v`:

```sh
sh test/formal/run.sh
sh test/formal/faults.sh
```

See [formal/README.md](formal/README.md) for proved properties, assumptions, and fault checks.

## 5. Verification report & plan (`report/`)

- [Verification report (PDF)](report/rpe_verification.pdf) ([LaTeX source](report/rpe_verification.tex)) — methods, block/protocol test tables, faults found, reproduction commands, and current regression status.
- [Verification plan](report/verification_plan.md) — planned formal, coverage, mutation, and gate-level extensions.
