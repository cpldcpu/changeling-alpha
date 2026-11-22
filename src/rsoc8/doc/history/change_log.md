# rcore8 protocol emulator: system RTL so far

    rtl/rcore8d.v      one core
    rtl/rdual.v        two cores, bus arbiter, code memory routing, CORECTL, LOCK, WAIT, ARB
    rtl/rlinecells.v   receive cell rlc_rx, transmit cell rlc_tx
    rtl/rlcports.v     pins, synchronisers, pin multiplexer, the two pairs of line cells, owner check
    rtl/revents.v      event flags, interrupt enable masks, time base, wake-up times
    tb/tb_sys.v        cores + ports + events + memories; runs firmware images
    tb/tb_sync.v       order of the rising- and falling-edge pin samples
    fw/rpe.h           register header (specification draft 0.19)
    fw/fw1.c           one core: UART through line cells, time base, pin change interrupt, flags
    fw/fw2_c0.c, fw2_c1.c   two cores: UART between the cores, shared memory, flags, lock
    fw/fw3.c           10BASE-T frame at 6 clock cycles per bit, both-edge sampling
    fw/build.sh        build.sh name [core]; core 1 images get __RODATA_PM_OFFSET__ = 0x4800
    tests/run_fw.sh    builds and runs everything

The simulation is compiled with -DSIM so that the registers r16..r31 start at zero. The start-up
code clears its zero register with an exclusive-or, which stays undefined in simulation otherwise.

The unit tests of the cores (rdual_rtl.tar.gz) and of the line cells (linecells_rtl.tar.gz) are in
their own packages. Not built yet: timer, PWM, CRC unit, clocking, host link, top level.

## Added: timer, PWM, CRC unit; core clock enable

- `rtl/rtimers.v`: 16-bit timer with capture and two compare registers, three PWM channels, CRC unit
  (rules B1-B7, F1-F7 of the specification). 1,652 IHP cells, 28,200 um2, 286 flip-flops.
- `model/timers.py`, `tb/tb_tim.v`, `tests/tim_test.py [first_seed last_seed]`: behavioural model, block
  testbench, CRC known answers, directed and random comparison of RTL and model.
- `rdual` has the input `cke` (core clock enable). `tb_sys.v` takes `+cdiv=n` to enable the cores in one
  cycle of n while the peripherals run in every cycle.
- `tb_sys.v` has a 10BASE-T signal generator on pin 1: `+eth=<bit time in ps>`, `+ethn=<payload bytes>`.
  A write to fast address 0x1E prints the high time of the three PWM pins since the previous write.
- Firmware: `fw4.c` 10BASE-T receive from the generator (built twice: 6 and 3 clock cycles per bit),
  `fw5_c0.c`/`fw5_c1.c` 10BASE-T with one core per direction, `fw6.c` timer, capture, PWM and CRC.
- `tests/run_fw.sh` runs everything, including the runs with the cores at half the clock rate.
  fw3 with `+cdiv=2` ends with exit code 110 as expected: one core at 30 MHz cannot serve both
  directions of 10BASE-T in C.

## Added: clocking block

- `rtl/rclock.v`: `rclk_src` (gates of the two source clocks, enable chains, reset synchronisers, presence
  counters, trim register on the oscillator clock), `rclk_ctl` (registers, presence check, dividers, trim
  counter with window and loop, clock output, debug signal), `rclock` (both). Rules K1-K12.
  891 IHP cells, 17,300 um2, 214 flip-flops.
- `tb/tb_clk.v`: self-checking testbench with two unrelated clocks and an oscillator model that follows the
  trim inputs. Prints the shortest high and low phase of the system clock and PASS.
- `tb/tb_sys.v` now takes clock, reset, core and peripheral clock enables from `rclock` (external clock
  only). `+ref=<half period in ps>` drives the reference pin (input pin 4). A write to fast address 0x1D
  prints the rising edges of the clock output and the debug pin since the previous write.
- `fw/fw7.c`: dividers, measurement against the reference pin, window, request for a missing clock,
  clock output and debug pin.

## Added: host link, program protection, host access in rdual

- `rtl/rhost.v`: `rhost` (SPI slave sampled with the system clock, commands, control and status, mailbox,
  core reset) and `rprot` (PMCR, PMLIM, write enables of the code memories). Rules L1-L14.
  560 + 95 IHP cells.
- `rtl/rdual.v`: host port in front of the memories and the register bus, re-read of the code memory
  output after a host access, sequencer for inject, execute and step. `rtl/rcore8d.v`: input `inj`,
  output `at_start`. 5,721 IHP cells for the two-core block.
- `tb/tb_sys.v`: model of the SPI host on input pins 0 (clock), 1 (chip select), 2 (data in) and output
  pin 0. The testbench releases the core reset with a control command. `+spiload` writes the images
  through the host link, `+htest=1 +brk=<word address>` runs the host test with `fw/fwh.c`.
- `fw/fw8.c`: program protection. `fw/rpe.h`: `PROT_WRITE(reg, value)`.
- `tests/mut_host.py <word address of tick>`: 30 inserted faults (run `tests/run_fw.sh` first).
- The random test of the two-core block with host stimulus is in the rdual package:
  `HRAND=1 python3 tests/randtest_d.py 0 60 4000`.

## Added: top level

- `rtl/rpe_top.v`: `rpe_chip` (Tiny Tapeout wrapper), `rpe_core` (all blocks), `rpe_mem` (wrapper of
  the SRAM macro `RM_IHPSG13_1P_1024x16_c2_bm_bist` with byte write). `rtl/rpe_osc_stub.v`: oscillator
  placeholder with the clock output low.
- `tb/tb_sys.v` instantiates the wrapper. `tb/ihp/` holds the simulation model of the SRAM macro from the
  IHP Open PDK (Apache 2.0); compile with `-DFUNCTIONAL`. `tb/osc_model.v` is a model of the oscillator
  for `fw/fw9.c`. `+cdiv=n` now makes the host model write CLKCDIV; `+strap` starts from the oscillator;
  `+spihalf=<ns>` sets the host clock.
- Synthesis of the whole design (yosys, IHP cells, macros as black boxes): 13,636 cells, 2,003 flip-flops,
  210,250 um2.
- `tests/run_fw.sh` runs all firmware tests on the top level.

## Added: protocol firmware, end of packet in the transmit cell

- `fw/fw10.c` WS2812 controller and LED with forwarding; `fw/fw11_c0.c`, `fw11_c1.c` SPI slave and master;
  `fw/fw12_c0.c`, `fw12_c1.c` I2C slave and firmware master; `fw/fw13_c0.c`, `fw13_c1.c` USB low-speed
  device and host. Both ends of each link are on the chip.
- `rtl/rlinecells.v`: transmit cell bit LCRUN.EOP (two bit periods with both outputs low after the last bit).
- `fw/rpe_core1.h`: start-up code for images of core 1 (stack pointer, copy of initialised variables from
  code memory 1). `fw/build.sh name 1` places the variables of core 1 at 0x0440.
- `fw/rpe.h`: `lc_setup(cell, table)`, `LCR_EOP`.
- `tb/tb_sys.v`: `+short=abcd` wires pin a to b and c to d; `+pd=<mask>` pulls undriven pins low.

## Added: stored end-of-packet flag, CRC strobe behind the match pattern

- `rtl/rlinecells.v`, receive cell: status bit 5 `EOP` is set when both pins go low and stays until a one
  is written to it. The bit strobe to the CRC unit leaves out the bits before the match pattern.
- `fw/fw13_c0.c`: uses the flag, takes the answer time from the timer capture of the end of packet, and
  starts the CRC before the packet with a start value that accounts for the packet identifier.

## Added: USB device receive loop and answer path in assembly

- `fw/usb_dev.S`: `usb_rx_token()` and `usb_rx_data_ack()`; `fw/fw13_c0.c` uses them.
  Build: `EXTRA=fw/usb_dev.S sh fw/build.sh fw13_c0 0`.
- Both answers are in time down to a core clock of 6.7 MHz (core divider 9).

## Added: CRC reference value and status, Ethernet frame check

- `rtl/rtimers.v`: `CRCREF` (0x3F4A-0x3F4D), status `CRCST` on the read side of `CRCIN` (0x2A):
  `EQF` (equal at the last frame boundary), `EQ` (equal now), `BUSY`.
- `rtl/rlinecells.v`, `rtl/rlcports.v`: the receive cell reports completed frames to the CRC unit; the bit
  strobe for the CRC unit (behind the match pattern) is separate from the strobe of the pair link (all bits).
- `fw/usb_dev.S` tests `CRCST.EQF`; `fw/fw14.c` checks a 10BASE-T frame with its check sequence
  (`+ethfcs`, `+ethbad=n` in `tb/tb_sys.v`).

## Added: CRC5 of tokens in the USB device

- `fw/usb_dev.S`: `usb_rx_token()` checks the CRC5 through `CRCST.EQF`; `usb_crc_token_mode()` and
  `usb_crc_data_mode()` switch the CRC unit between CRC5 and CRC-16 in the gap between token and data.
- Build with `-DBADTOKEN` for the variant in which the host sends an IN token with a wrong CRC5.

## Added: USB HID device and I2C sensor bridge

- `fw/usb_stack.S`, `fw/usb.h`, `fw/fwusb.c`, `fw/gen_usb_desc.py`: USB low-speed HID device with
  enumeration and one interrupt endpoint. Descriptors are stored as complete data packets.
  Build: `python3 fw/gen_usb_desc.py fw build && EXTRA=fw/usb_stack.S sh fw/build.sh fwusb 0`.
  Run: `vvp -n build/tb_sys.vvp +hex=build/fwusb.hex +usbhost +maxcyc=9000000` (about 3 minutes).
- `tb/usb_host.v`: model of a USB host (`+usbhost`); `+quick` leaves out all requests except SET_CONFIGURATION.
- `fw/sens.h`, `fw/fwsens_c1.c`, `fw/fwusb.c` with `-DSENSOR`: core 1 reads an I2C sensor when its
  interrupt line goes low and leaves complete report packets for core 0. Build: `sh fw/build_sens.sh`.
  Run: `vvp -n build/tb_sys.vvp +hex0=build/fwsens_c0.hex +hex1=build/fwsens_c1.hex +usbhost +sensor +maxcyc=14000000`.
- `tb/i2c_sensor.v`: model of the sensor (`+sensor`), pins 4 SDA, 5 SCL, 6 interrupt.
- Firmware around `usb_poll()` has to return to it within about 18 bit times.

## Added: USB device on the internal oscillator

- `rtl/rclock.v`: with a line cell as reference and `TRWIN` not 0, the trim counter does not use events that
  come earlier than target minus window, so the keep-alive interval is measured in frames with packets.
  `tb/tb_clk.v` has a case for it.
- `fw/fwusb.c` with `-DOSC -DUSB_CPB=10` (`sh fw/build_usbo.sh`): switches to the oscillator, coarse trim
  by firmware, then the loop. `fw/usb.h` and `fw/usb_stack.S` take the clock cycles per bit from `USB_CPB`.
- `tb/osc_model.v`: start error by `+oscerr=<factor>`, variable `drift`. Compile with `-DOSCMODEL`.
- `tb/usb_host.v`: `+oscusb` uses 1 ms frames and real bit times; the receiver follows the edges of the device.
  Run: `vvp -n build/tb_sys_osc.vvp +hex=build/fwusbo.hex +usbhost +oscusb +maxcyc=4000000`.
- Note: `tb/tb_sys.v` runs the external clock with a period of 10 ns. Times of tests on the external clock
  are to be read in clock cycles (one cycle is 16.7 ns on the chip).


## Added: behavioural models written from the specification, random comparison with the RTL

- `model/events.py`, `dual.py`, `clkctl.py`, `prot.py`, `host.py`; testbenches `tb/tb_ev.v`, `tb_dual.v` (with `tb/stub_core.v`
  in place of `rcore8d`), `tb_clkctl.v`, `tb_prot.v`, `tb_host.v`; tests `tests/ev_test.py`, `dual_test.py`, `clkctl_test.py`,
  `prot_test.py`, `host_test.py [first_seed last_seed]`; fault insertion on a temporary copy of the RTL: `tests/fault_run.py <ev|dual|clkctl|prot|host>`;
  everything: `tests/run_models.sh` (`LITERAL=1` for the literal specification text, `FAULTS=1` for the fault lists). Results in `../REPORT.md`.


## Added: UART against an independent model, mailbox bridge, UART to WS2812

- `tb/uart_model.v` (`+uart`): UART transmitter and receiver written from the format definition (bit time in clock
  cycles with separate percentage offsets for the two directions, 7 or 8 data bits, none/even/odd parity, 1 or 2 stop
  bits, framing error, glitch, bad parity) and the scenarios `+uscen=n`: 1 offset sweep, 2 back to back, 3 framing
  errors, 4 glitch, 5 parity, 6 two stop bits, 7 overrun, 8 burst to a slow firmware, 10-15 mailbox bridge, 20-21
  UART to WS2812. Pins: chip receives on pin 4 (driven by the model), transmits on pin 5, WS2812 output on pin 6.
  Plusargs: `+ucpb=<cycles per bit> +uoff=<percent> +unb=<count> +umodes=<mask> +uomin/+uomax/+uostep=<tenths of a percent>
  +und=7 +upar=1|2 +unstop=2 +ugap +upause +ustart=<ns> +umbsingle +upchk +ustartchk`.
- `tb/ws2812_model.v` (`+ws`): receiver of the WS2812 stream on pin 6, measures high times and bit periods in clock
  cycles against T0H 24, T1H 48, period 75 (+-9) and the reset time 3000, decodes bytes and frames.
- `fw/fwu_echo.c` (echo, framing, glitch, parity, overrun), `fw/fwu_mbx.c` (mailbox to UART and back),
  `fw/fwu_ws.c` (UART to WS2812, collect or `-DSTREAM`). Build with `sh fw/build_u.sh <source> <name> "<defines>"`.
- `tests/run_uart.sh [limits]`: all of the above with expectations (about 8 minutes). `rtl_fix/rhost.v`,
  `rtl_changes.diff`: fix of the mailbox read race (not applied to `rtl/`).


## Added: SPI and I2C against independent models
- Models in `tb/` (written from the protocol definitions, included by `tb/tb_sys.v`, enabled by plusargs):
  `spi_slave_model.v` (`+spislv`, chip is master), `spi_master_model.v` (`+spimst`, needs `+pd=10`),
  `i2c_slave_model.v` (`+i2cs`, stretching, no-ACK, stuck bus), `i2c_master_model.v` (`+i2cm`, also `+i2cm_arb`).
  Pin plumbing in `tb_sys.v`: `x_oe`/`x_val` (push-pull), `xl_a`/`xl_b` (open drain), `xcyc` (cycle counter).
- Firmware: `fw/fw15_spim.c`, `fw/fw16_spis.c`, `fw/i2cm.h` (master with SCL read-back, error codes, 9-pulse recovery,
  arbitration check), `fw/fw17_i2cm.c`, `fw/fw18_i2cs.c`, `fw/fw19_arb.c`, `fw/fw15.h`; build with `tests/spii2c_build.sh <src> <name> [-D...]`.
- Test: `tests/spii2c.sh [spim spis i2cm i2cs arb fault]` (about 15 minutes in total; every part is one simulation at a time).
  Lines start with ok / FAIL (expectation) or info (measured limit). `NOCOMPILE=1` reuses `build/tb_sys.vvp`.


## Added: independent Ethernet model, ping endpoint, clock duty cycle

- `tb/eth_model.v` (included by `tb/tb_sys.v`; plusargs in its header comment): transmitter with FCS from the CRC-32
  definition, bit time error (`+ethppm`), edge jitter (`+ethjit`), idle pulse length (`+ethidl`); receiver for the chip
  output by edge times: preamble, delimiter, FCS, idle pulse, level durations, bit time, gap of 576 cycles; link pulses
  (`+ethnlp`). `+ethm=1..5` select a scenario. The generator behind `+eth=` is unchanged. `+duty=<percent>` sets the duty cycle of the clock.
- `fw/fw15.c`, `fw/fw15_io.S`, `fw/fw15.h`: ping endpoint (ARP, ICMP echo) on one core, 1802 bytes of code.
  Build: `EXTRA=fw/fw15_io.S sh fw/build.sh fw15`. Run: `vvp -n build/tb_sys.vvp +hex=build/fw15.hex +ethm=1`.
- `tests/run_eth.sh` runs everything; `tests/eth_sweep.py` finds the receive tolerance by bisection.


### Robustness of the USB device on the oscillator (loss of lock, packet ends, suspend, start error)

- `fw/fwusb.c` (`-DOSC`): `osc_track()` runs at every keep-alive signal. It detects a lost lock (no `EV_TRIM` for
  `OSC_LOST_N` = 3 keep-alive signals, or two frames in a row more than 1.5 % off, measured with the timer capture of the
  keep-alive signal) and then corrects the trim value in firmware from the frame time, at most 3 steps per keep-alive
  signal, and switches the loop on again. `-DOSC_PROBE` writes markers to fast I/O 0x1C (testbench only),
  `-DOSC_NOTRACK` leaves the call out (fault insertion). `OSCDEF="-DOSC_PROBE" OUT=fwusbop sh fw/build_usbo.sh`.
- `tb/usb_host.v`, new plusargs (all need `+usbhost +oscusb`; `+quick +nodrift` recommended):
  `+jump=<percent>` frequency step of the oscillator after the first 8 reports; `+suspend=<ms>` no signals on the bus,
  then K state for 1 ms and a keep-alive signal (`+suspjump=<percent>`: frequency step in the middle of the suspend);
  `+txpos=<bit times>` poll that long after the keep-alive signal; `+varpkt=<bit times>` one packet for another device
  at that place of every frame, content changes (`+varmode=1`: shortest and longest packet alternate);
  `+kskip` leaves one keep-alive signal out; `+wait=<frames>` frames between the end of the bus reset and the first
  request (default 14); `+startonly` prints when the loop was switched on and ends; `+steady=<frames>`.

### HID class requests, endpoint 0 robustness, sensor bridge on the oscillator

- `fw/fwusb.c`: GET_REPORT (input report = the last report made, a copy `cur`; output report = the last SET_REPORT data), SET_REPORT
  (OUT data stage of 8 bytes; first byte goes to PWM0, the PWM0 pin is enabled with period 256; the data packet is stored as received),
  GET_CONFIGURATION, GET_IDLE, SET_IDLE (idle rate other than 0 is refused with STALL), GET_PROTOCOL, SET_PROTOCOL. `FEAT=n` (default 5)
  switches the additions off for size measurements. State `ws` of the control write: 1 data expected, 2 data taken (a repeated OUT
  data packet is acknowledged by the stack again and not applied again), 3 request refused. A GET_REPORT with a larger wLength than 8
  gets the empty DATA0 packet behind the 8 bytes. The report descriptor has an output item now (23 bytes).
- Fault insertion options of `fw/fwusb.c`: `-DFLT_CUR -DFLT_DUP -DFLT_PWM0 -DFLT_ZLP -DFLT_ZLPALL -DFLT_RESTART -DFLT_STALLCLR -DFLT_CFG`,
  and `-DFLT_NOCRC` in `fw/usb_stack.S` (the CRC-16 of a data packet is not checked).
- `fw/oscusb.h`: the oscillator code of `fwusb.c` (osc_adjust, osc_loop_on, osc_start, osc_track), `osc_track(cap)` takes the capture time.
- `fw/build_senso.sh`: two-core sensor bridge on the oscillator. Core 1 image (`fwsens_c1.c -DOSC`) has the oscillator start,
  the lock tracking (called from the idle wait and from every `hold()` of the I2C master) and the descriptor packets; core 0 reads them
  from code memory 1 (link symbols from the core 1 image, `USB_DESC_EXTERN`). Core 0 sets `S_CAP` and SW0 at every keep-alive signal.
  `S_OSC` (sens.h): core 1 reports that the loop is on. Options `EXTRA0`, `EXTRA1`, `OUT`.
- `tb/usb_host.v`: `+feat` (HID class requests, 6 groups of checks, PWM0 register, write count and pin duty are observed),
  `+ep0` (SETUP in the middle of a transfer, lengths 8/16/24/32, STALL), `+sbgap=<ns> +scgap=<ns>` event spacing of the sensor test
  (set automatically with `+oscusb`), pass-time probe (`-DOSC_PROBE` build, marker 0x20+event / 0x13 on fast I/O 0x1C).
  `tb/i2c_sensor.v` measures the SCL period.


## Added: two protocols at once (stress tests)

- Merged from the working copies of the UART and the SPI/I2C agents: `tb/uart_model.v`, `tb/ws2812_model.v`, `tb/spi_slave_model.v`,
  `tb/spi_master_model.v`, `tb/i2c_slave_model.v`, `tb/i2c_master_model.v` are included by `tb/tb_sys.v` (changes of both origins merged by
  hand; the UART model got the pin variables `+urx=`, `+utx=` and the WS2812 model `+wpin=`, defaults as before: 4, 5, 6).
- `tb/stress.v` (`+stress=n`): monitors for the held cycles of each core (arbiter), service times of the line cell registers, PWM edges
  (event driven, period and high time per pin), compare A and B events of the timer; scenarios 1 (UART echo core 0 + SPI master core 1),
  2 (UART core 0 + I2C firmware master core 1), 3 (SPI slave core 0 + WS2812 frames core 1), 6 (one core: UART + SPI slave), 7 (WS2812
  controller, 100 LEDs), 8 (WS2812 LED with forwarding fed by a testbench sender with bit time error and jitter); host link actions
  (`+sxhost=1..5`) during scenario 1.
- Firmware: `fw/fwx.h`, `fw/fwx_c0.c` (core 0: echo, SPI slave, idle, bus hog; PWM + compare A stamps with `-DEXTRAS`), `fw/fwx_c1.c`
  (core 1: SPI master, I2C master, WS2812 controller, bus hog, compare B stamps), `fw/fwx_one.c` (one core, two protocols),
  `fw/fwx_ws.c`, `fw/fwx_wsfwd.c`; build with `sh fw/build_x.sh <source> <out> <core> "<defines>"`.
- Drivers: `tests/stress_t1.py` (1a), `tests/stress_t2.py` (1b, 1c), `tests/stress_t3.py` (3), `tests/stress_t4.py` (2, 4, 5, hog, faults),
  helpers `tests/sx.py`, build `tests/stress_build.sh`, batches `tests/stress_queue.sh`, `tests/stress_queue2.sh`. Results: `REPORT.md` in
  the parent directory.

## Draft 0.32: second verification round merged, four RTL fixes

- `rtl/rclock.v`: the oscillator enable includes the requested source (rule K1); bit 7 of CLKCTL reads 0.
- `rtl/rhost.v`: the decision to take the mailbox byte is captured with the status byte; a refused read leaves
  zero in the following bytes. `tb/old/rhost_before_032.v` is the host link before the fix (used by one test).
- New test suites: `tests/run_models.sh` (models against RTL, 5 blocks), `tests/run_uart.sh`, `tests/spii2c.sh <part>`,
  `tests/run_eth.sh` (firmware `fw/fweth.c`), `tests/run_waitirq.sh`, `tests/stress_t1.py` ... `stress_t4.py`.
  `tests/run_fw.sh` stays the base regression (now with the HID class requests and the sensor bridge on the oscillator).
- The review of the architecture is section "Second verification round and architectural review" of the specification.

## Added: example programs for the datasheet

- `fw/examples/`: `ex_uart_echo.c` (simulated against `tb/uart_model.v`), `ex_spi_master.c`, `ex_ws2812.c`,
  `ex_pwm_timer.c`, `ex_two_c0.c` / `ex_two_c1.c` / `ex_shared.h`, `ex_i2c_read.c`, `ex_clock.c`, `ex_crc.c` (compiled, not simulated).
  Build like any other image, for instance
  `avr-gcc -mmcu=attiny40 -Os -Ifw -Wl,--defsym=__RODATA_PM_OFFSET__=0x4000 -Wl,--defsym=__DATA_REGION_LENGTH__=0x800 -o build/ex.elf fw/examples/ex_uart_echo.c`.

## Added: timing diagrams of the datasheet from simulation

- `tb/tb_sys.v`: `+wave=<file>` writes one line per clock cycle (pins, strobes and status of the line cells)
  between a write of a value other than 0 and a write of 0 to fast address 0x19.
- `fw/fwwave.c`: five scenarios (`-DSCEN=1..5`: UART, SPI master, compare mode, Manchester, NRZI with stuffing
  and end sequence) at few clock cycles per bit. Run with `+pd=03`.
- `tests/gen_waves.py <dir with w1.txt..w5.txt> <output dir>`: draws the diagrams as TikZ files.
- `tests/gen_lcex.py <same arguments>`: writes the register settings table of each scenario; the logger records
  the configuration registers of the cells as comment lines at the start of a recording.

## Added with specification draft 0.36: additional frame bit, start at the shift edge, bus conditions

RTL change, `rtl/rlinecells.v` only. New registers: `LCX` at offset 0xF of every cell, `LCEC` at offset 7 of a
receive cell; new status bit `FERR` (bit 6 of `LRnSTAT`). With both registers at 0 the cells behave as before.

- Additional bit (`PAR` in `LCX`): odd parity, even parity or a ninth data bit after the data bits. The transmit
  cell generates it, the receive cell stores it with the frame (`LCX` bit 7) and sets `FERR` on a wrong parity.
  A ninth bit that is always 1 gives two stop bits on transmit.
- `ESTR` (transmit cell clocked by a pin): the first bit of a frame goes out at the first shift edge after the write.
- `BCD` (receive cell with a clock pin): a data edge while the clock pin is high sets `STA` or `STP` in `LCX` and
  resets the bit count. `LCEC`: count of falling data edges while the clock pin is low, flag `ECF`.
- `fw/rpe.h`: `LC_X`, `LC_EC`, `LCX_*`, `LCS_FERR`. `LCX` is not part of the 15-byte tables of `lc_setup`.
- Tests: `fw/fwu_par.c` with `tb/uart_model.v` (scenario 9, `+urnstop=2`), tests A10 and A11 in
  `tests/run_uart.sh` (`ONLY="A1[01]" sh tests/run_uart.sh` runs only these); `fw/fw20_i2cs9.c` (I2C slave with
  `BCD` and `ESTR`) in `tests/spii2c.sh i2cs`. The model comparison and the directed tests of the new logic are
  in the `linecells` package.
- `tests/spii2c.sh`: the fault insertion into `rlinecells.v` now selects the lines by their text and not by line number.
- Synthesis: 14,308 cells, 2,058 flip-flops, 87 clock gates, 221,326 um2 (before: 13,697 / 2,004 / 81 / 215,062).
