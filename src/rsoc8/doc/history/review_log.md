# Review log of subagent findings (kept by the main session)

## models (reviewed, tests rerun: 5 blocks x 100 seeds, 0 mismatching)
RTL fixes to apply:
- C1 rclock.v: CLKCTL bit 7 stored and read back -> store 0.
- C2 rclock.v: osc_en lacks r_src -> SRC=1 with OSCEN=0 never starts the oscillator, request pending forever. Add r_src.
- H1 rhost.v: refused register read repeats stale tx_hold in following bytes -> clear on refused read.
Spec changes:
- C3 early-event rule: "not later than target minus window" (RTL: cnt + w <= tgt).
- H4: wait compare and wake only in core-enable cycles; flags are stored, so no event is lost; state it.
- Pending enabled interrupt at wait entry: wait is not entered. State it.
- MODE 0 first collision after reset goes to core 0; ARB value 3 undefined -> define (treat as 0?) check RTL.
- Wake-up time resets to 0 -> DLY set at first wrap of the time base without a write. Decide: document or gate.
- Host: inject/execute/step refused also while core reset set or injection running; unknown commands ignored;
  addresses with bit 15 alias to registers; mailbox read without data returns stale byte; MBDATA host read no side effect.
- Clock: MVALID not cleared by new measurement; MEAS write during measurement only clears MDONE; CLKCTL write
  without unlock does not end a measurement; period counter 7 bit; DBGSEL 15 = 0.
Merge: model/{events,dual,clkctl,prot,host}.py, tb/tb_{ev,dual,clkctl,prot,host}.v, tb/stub_core.v, tests/*_test.py,
tests/fault_run.py, tests/run_models.sh. Note tb/tb_dual.v name clash with rtl2/tb/tb_dual.v (different tree, ok).

## uart (reviewed, spot rerun A1/A5 ok; agent could not write REPORT.md, report is in the session)
RTL fix to apply: rhost.v mailbox read race (take decided with the status byte, flop take_n) -> agents/uart/rsys/rtl_changes.diff.
Architecture findings (for review):
- Receive cell has no stop-bit check and no start-bit validation for UART; workaround uses the second receive cell.
  Framing error with bit7=1 gives spurious 0xFF unless firmware restarts the cell.
- Frame max 8 bits: no 8 data + parity; transmit always exactly one stop bit.
- IDLE flag set mid stop bit of every character -> not usable as pause detection.
- Mailbox 1 byte per direction: host link is the bottleneck (152..496 cycles per byte).
- Tolerance +-5.3 % at >=16 cycles/bit; 2 cycles/bit works at 0 %.
- 115200 needs prescaler 2 (520 cycles).
Merge: tb/uart_model.v, tb/ws2812_model.v, tb_sys.v 4 lines, fw/fwu_*.c, fw/build_u.sh, tests/run_uart.sh.
Note: agent used pkill vvp once -> may have disturbed another agent's run.

## spii2c (reviewed; spis part rerun by me: 15 ok, 0 FAIL; RTL unchanged)
No RTL bug. Architecture findings:
- Transmit cell status has no underrun bit (LTnSTAT = TXE, BUSY only). SPI slave: a byte written >108 cycles late
  (byte = 128 cycles) is sent wrong, no flag. Cause of the wrong data not traced.
- Stale byte stays in the TX buffer after an aborted transfer unless the cell is set up again.
- SPI master max 8 cycles/bit (7.5 MHz); slave MISO correct down to 12 cycles/bit, MOSI down to 2.
- I2C slave: no hardware clock stretching (firmware via DDR works); ACK margin 71 cycles at 400 kHz; fails at cdiv 4 / 400 kHz.
- I2C master firmware lib fw/i2cm.h: stretching, NACK, bus recovery, timeout, arbitration loss all pass.
- SPI modes 0 and 1 not distinguished by the slave at 16 cycles/bit (sample a few cycles after the edge) -> look at.
Merge: tb/{spi_slave,spi_master,i2c_slave,i2c_master}_model.v, tb_sys.v edits, fw15-19, fw/i2cm.h, tests/spii2c*.sh.

## usbosc (reviewed; -3 % jump rerun by me: USB PASS, first correct report after 4 frames; RTL unchanged)
Firmware: osc_track() in fwusb.c (lost lock: no EV_TRIM for 3 frames or 2 frames >1.5 % off via timer capture; recovery
<=3 trim steps per keep-alive; <=119 cycles per call). Image 2,376 bytes (one-core).
Architecture findings:
- Trim counter window gating is not safe alone: after a slow step a keep-alive is "early", the next packet end
  completes a valid-looking interval (~14950) -> loop runs on wrong values. Firmware frame-time check via timer capture
  catches it in 2 frames. Options: keep-alive-only reference (REF=3, idle-qualified) or keep firmware check.
- Coarse trim range 11000..19000 counts -> start error beyond about +-26 % never trims; within 10 ms only up to ~+-20 %.
- If the first request comes while coarse trim runs, continuous traffic leaves no packet-free frame -> device never answers.
  (needs coarse trim that works with traffic, e.g. from the timer capture of keep-alives, or stored trim value)
- Packet-end reference: worst frequency range -1.06..+0.30 % (inside 1.5 %, margin 0.44 %); not fault-tested.
- Suspend 5 ms: trim value holds, answers 4 frames after resume.
Merge: fw/fwusb.c, fw/build_usbo.sh, tb/usb_host.v (usbfeat agent continues on this copy -> merge from usbfeat).

## eth (reviewed; short ping test rerun by me; RTL unchanged)
Ping endpoint fw15 (rename on merge: clashes with spii2c fw15) 1802 bytes, one core, ARP + ICMP echo, passes cdiv 1-3.
Architecture findings:
- Transmit cell cannot make a standard TP_IDL (idle pulse): output goes low after the last bit (3 cycles high).
  Workaround with LCRUN.IDLE and a firmware-timed clear works single-ended only; with the complementary output enabled
  both outputs go high -> no differential idle pulse. Needs RTL: second output idles at ~IDLE, or "idle pulse n bits".
- EQF can be set for a frame with lost bytes (CRC follows the bit strobe) -> firmware must check OVR. Spec note.
- CRC unit single owner core -> rx check + tx FCS want one core.
- No link pulse generation; time base max 0.55 ms -> 16 ms needs ~30 wake-ups. (link partner needs pulses to send)
- Receive tolerance -16.4 %..+47 %, jitter 5.3 ns; duty 10..90 % no break (zero-delay sim, setup/hold not modelled).
- Receive loop limit: core divider 3. .bss clear of big buffers costs ~8000 cycles at start -> .noinit.
Merge: tb/eth_model.v, tb_sys.v (+duty, include), fw15* -> fweth*, tests/run_eth.sh, tests/eth_sweep.py.

## arb (reviewed; slice of the matrix and of the code-memory cases rerun by me; RTL unchanged, no mismatch found)
5766-run matrix (31x31 classes, ARB 0/1/2), code memory 90 cases x cdiv 1-3, wait/interrupt 2376 runs, random 300 seeds: 0 failing.
Faults 16/17 caught by new tests, 17th (dq capture, U4) by existing HRAND test.
Spec notes:
- U7 hazard: named owner that busy-polls instead of waiting deadlocks the other core's access to its code memory.
- Interrupt pending at instruction start is taken instead of the instruction; "pending at OUT WAITL" only after SEI.
Not done: core 1 as wait subject (single), line-cell/timer flag interrupts during wait, BREAK/halt with arbitration, directed U4.
Merge: rdual/tests/arb*.py, randstress.py, run_arb.sh, tb_dual.v (+side,+cov) -> rtl2 tree; rsys/tests/waitirq.py etc, tb_sys.v +wlog.

## stress (reviewed; PWM + compare test rerun by me; RTL unchanged; agent could not write REPORT.md)
No data error in any protocol pair; alone rate limits hold together at ARB 0/1/2, cdiv 1/2, except UART at its alone
limit next to the I2C firmware master (bus slots taken by pin polling). Bus hog + fixed priority for the hog slows the
other core to a fraction. PWM/compare exact, no event lost. WS2812 100 LEDs gap-free at cdiv 1..16.
Architecture findings:
- Host memory/register access needs every enabled core halted -> halting core 1 also stalls core 0 (design property):
  debugging one core disturbs the other's protocol. Mailbox/status/inject/step do not.
- Fixed arbiter priority lets a polling core starve the other; ARB 0 is safe. Recommend wait_for instead of polling.
- WS2812 forwarding: output period follows the input period (not regenerated); below -12 % input the output period is
  under the WS2812 limit.
- Compare ISR on the same core raises UART service time to max 133..268 cycles (firmware).
Merge: tb/stress.v (+ merged tb_sys.v with uart and spii2c changes), fw/fwx*, tests/stress*.py. This copy is the
merge base for uart + spii2c testbench changes.
