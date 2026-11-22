# Briefing for verification tasks on the rcore8 protocol emulator

You are closing one verification gap of a chip design. Read this file completely, then your task.
Your working copy is the directory named in your task (`.../agents/<name>/rsys`). Work only there.
Do not write to `/home/claude/work/rtl5`, `/home/claude/work/rtl2`, `/home/claude/work/spec` or `/home/claude/out`.

## The design in short

- Chip for a protocol emulator: two 8-bit cores `rcore8d` (reduced AVR, AVRrc instruction set as ATtiny40),
  each with its own code memory of 1024 x 16 bit, a shared data memory of 2 KB, a shared register bus with an
  arbiter, 8 line pins, two "line cell" pairs (receive cell R0/R1, transmit cell T0/T1) that do the bit-level
  work of serial protocols, event flags, a 16-bit timer, PWM, a CRC unit, a clocking block with trim counter,
  and an SPI host link for loading and debugging.
- External clock 60 MHz. The cores can run at a divider (`CLKCDIV`), the line cells stay at the full rate.
- RTL in `rtl/`: `rcore8d.v` (core), `rdual.v` (two cores, memories, arbiter, host port), `rlinecells.v`,
  `rlcports.v` (pins), `revents.v`, `rtimers.v`, `rclock.v`, `rhost.v`, `rpe_top.v` (top level
  `tt_um_cpldcpu_rpe`).
- The register map and all bit names are in `fw/rpe.h` (commented). This is your reference for firmware.
- `README.md` lists every block, test and plusarg added so far. Read it.
- The full specification (LaTeX, 55 pages) is `/home/claude/work/spec/rpe_spec.tex`. Read the sections you need
  (search for `\label{sec:...}`): `sec:corebeh` core rules, `sec:lcbeh` line cell rules, `sec:map` register
  map, `sec:perbeh` other blocks, `sec:host` host link, `sec:top` top level, `sec:protover` protocol firmware
  tests 10-14, `sec:sensver` USB HID + I2C sensor, `sec:oscusb` USB on the oscillator.

## Testbench and tools

- Tools: `iverilog`/`vvp`, `avr-gcc` (attiny40) with avr-libc, `python3`. No waveform viewer; debug with
  `$display`.
- System testbench `tb/tb_sys.v` (instantiates the top level with the IHP SRAM model in `tb/ihp/`).
  Compile exactly as in `tests/run_fw.sh` line 5-6 (`-g2005 -DSIM -DFUNCTIONAL`, RTL list in `$RTL`).
  The header comment of `tb/tb_sys.v` and the `$value$plusargs` lines list the plusargs
  (`+hex`, `+hex0/+hex1`, `+maxcyc`, `+cdiv=n`, `+short=abcd`, `+pd=mask`, `+loop`, `+eth...`, `+usbhost`,
  `+sensor`, `+quick`, `+oscusb`, ...).
- Firmware ends a test by writing an exit code to fast I/O address 0x1F (`_IO8(0x1F) = code`); the testbench
  prints `EXIT <code>`. 0 means pass. Write to 0x1E / 0x1D are testbench markers (see tb_sys.v).
- Build firmware with `sh fw/build.sh <name> [core]` (one image, core 0 or 1; core 1 images include
  `fw/rpe_core1.h`). `EXTRA="fw/x.S"` adds sources. See `fw/build_sens.sh` for a two-image build with defines.
- `tests/run_fw.sh` is the full regression (about 10 minutes). Existing firmware tests `fw/fw1.c` ... `fw14.c`,
  `fw12_c0.c/fw12_c1.c` (I2C), `fw11_*` (SPI), `fw10.c` (WS2812), `fw13_*` (USB), `fwusb.c`, `fwsens_c1.c` are
  working examples of how the line cells are configured. Copy from them.
- IMPORTANT: `tb/tb_sys.v` runs the external clock with a period of 10 ns. Count time in clock cycles, not in
  ns. One clock cycle is 16.7 ns on the chip. Only tests on the oscillator model (`tb/osc_model.v`, 15 MHz)
  use real time.
- The machine has 2 CPU cores and other agents run at the same time. Run one simulation at a time. Keep a
  single simulation below about 3 minutes; prefer short directed tests over long ones.

## avr-gcc pitfalls on this core (AVRrc)

- Function arguments are passed only in r25..r20; a fourth byte argument goes to the stack. Call-used:
  r20-r27, r30, r31. r16 is the temporary register, r17 is zero. No LDD, no ADIW. LDS/STS reach only
  0x40-0xBF.
- Use `PROT_WRITE(reg, val)` for protected registers; a plain unlock followed by a store is too slow.
- Core 1 images need `#include "rpe_core1.h"` and the build with core argument 1; variables of core 1 start
  at 0x0440. Shared variables are placed at fixed addresses by hand (see `fw/sens.h`).
- A pin whose output is claimed by a transmit cell (OUTEN) does not follow the port register. One direction
  bit per pin: two devices on one chip that share a wire need a pin each, wired by the testbench (`+short`).
- Code memory: 2048 bytes per core image. A one-core image (`+hex=`) may use both memories (4096 bytes).

## Rules for your work

1. Tests must be self-checking: they print a clear PASS or FAIL line or an exit code, and a failure must be
   visible without reading waveforms.
2. A test that cannot fail is worthless. For each new test, show at least once that it fails when it should:
   insert a fault (in the firmware, the model, or a temporary copy of the RTL) and record the result. Use a
   temporary copy for RTL fault insertion and restore the original.
3. Do not change the RTL in `rtl/` to make a test pass. If you believe you found an RTL bug: keep the
   reproducing test, write the smallest fix, and save it as `rtl_changes.diff` (output of
   `diff -u /home/claude/work/rtl5/rtl/<file> rtl/<file>`), with the reasoning in your report. Mark clearly
   whether your results are with or without the fix. Changes to testbench and firmware are fine; keep new
   testbench behaviour behind a new plusarg so existing tests keep their timing.
4. Do not weaken or delete existing checks. Before you finish, run the parts of `tests/run_fw.sh` that your
   changes can affect and report the result.
5. If something does not work and you run out of ideas after a reasonable effort, stop and report exactly
   what fails, with the output. A precise failure report is a good result. Do not hide a failure by changing
   the expectation, and do not report something as passing that you did not run.
6. Report measured numbers with their unit (clock cycles, bit times). Mark estimates as estimates.

## Report

Write `REPORT.md` in the parent of your working copy (`.../agents/<name>/REPORT.md`) and return its content as
your final answer. Structure:

- **Summary**: 3-6 lines, what passes, what fails, what was not done.
- **Files**: every file you added or changed, one line each.
- **Tests**: for each test: purpose, exact command line, observed output line, result of the fault insertion.
- **Findings**: suspected bugs or weaknesses in RTL, firmware or specification, each with evidence and your
  confidence. Include design limits you measured (rates, cycle counts).
- **Not done / open**: what you skipped and why.

Write plain literal prose. No metaphors.
