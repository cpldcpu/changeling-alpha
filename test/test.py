# SPDX-FileCopyrightText: © 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
#
# Tests of Changeling-alpha through its pins only, so that the same file runs on the RTL and on the
# gate-level netlist. The firmware is loaded through the host link, as on the demo board.
#
#   test_load_and_uart_echo   loads fw/uart_echo.hex (src/rsoc8/fw/fwu_echo.c, 60 clock cycles per bit), reads the
#                             status and the code memory back in the core reset, starts core 0 and checks the
#                             echo of four characters
#
# The complete regression (firmware tests against protocol models, block tests against Python models)
# is in test/tests and test/blocks; see test/README.md.

import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

CLK_PS = 16666          # 60 MHz
SPI_HALF = 6            # half period of the host link clock in clock cycles
CPB = 60                # UART: clock cycles per bit (1 Mbit/s at 60 MHz)
RX_PIN, TX_PIN = 4, 5   # bidirectional pins used by the firmware


def bit(sig, n):
    """Bit n of a pin vector; other bits may be undefined (gate level before the cores run)."""
    return 1 if str(sig.value)[-1 - n] == "1" else 0


class Host:
    """Host link: clock ui_in[0], chip select ui_in[1] (low active), data in ui_in[2], data out uo_out[0]."""

    def __init__(self, dut):
        self.dut = dut
        self.ui = 0b00000010

    def _set(self, bit, v):
        self.ui = (self.ui & ~(1 << bit)) | (v << bit)
        self.dut.ui_in.value = self.ui

    async def start(self):
        self._set(1, 0)
        await ClockCycles(self.dut.clk, SPI_HALF)

    async def stop(self):
        await ClockCycles(self.dut.clk, SPI_HALF)
        self._set(1, 1)
        await ClockCycles(self.dut.clk, 4 * SPI_HALF)

    async def byte(self, v):
        r = 0
        for k in range(7, -1, -1):
            self._set(2, (v >> k) & 1)
            await ClockCycles(self.dut.clk, SPI_HALF)
            r = (r << 1) | bit(self.dut.uo_out, 0)
            self._set(0, 1)
            await ClockCycles(self.dut.clk, SPI_HALF)
            self._set(0, 0)
        return r

    async def control(self, v):                  # bit 7 core reset, bit 4 selected core, bits 1:0 halt requests
        await self.start(); await self.byte(0x04); await self.byte(v); await self.stop()

    async def inject(self, word):                # inject 16-bit AVR instruction into halted core and return
        await self.start(); await self.byte(0x06); await self.byte(word >> 8); await self.byte(word & 255); await self.stop()

    async def write(self, addr, data):
        await self.start(); await self.byte(0x02); await self.byte(addr >> 8); await self.byte(addr & 255)
        for b in data:
            await self.byte(b)
        await self.stop()

    async def read(self, addr, n):
        await self.start(); await self.byte(0x03); await self.byte(addr >> 8); await self.byte(addr & 255)
        await self.byte(0)
        out = [await self.byte(0) for _ in range(n)]
        await self.stop()
        return out


def load_hex(name):
    """One 16-bit word per line; returns the bytes in memory order (low byte first)."""
    path = os.path.join(os.path.dirname(__file__), "fw", name)
    out = []
    for line in open(path):
        w = int(line, 16)
        out += [w & 255, w >> 8]
    return out


async def uart_send(dut, state, ch):
    for b in [0] + [(ch >> i) & 1 for i in range(8)] + [1]:
        state["uio"] = (state["uio"] & ~(1 << RX_PIN)) | (b << RX_PIN)
        dut.uio_in.value = state["uio"]
        await ClockCycles(dut.clk, CPB)


async def uart_receive(dut, timeout_bits=40):
    """Waits for a start bit on the transmit pin and samples eight data bits in the middle of each bit."""
    def tx():
        return bit(dut.uio_out, TX_PIN)
    for _ in range(timeout_bits * CPB):
        await RisingEdge(dut.clk)
        if tx() == 0:
            break
    else:
        return None
    await ClockCycles(dut.clk, CPB // 2)
    assert tx() == 0, "start bit too short"
    v = 0
    for i in range(8):
        await ClockCycles(dut.clk, CPB)
        v |= tx() << i
    await ClockCycles(dut.clk, CPB)
    assert tx() == 1, "stop bit missing"
    return v


@cocotb.test()
async def test_load_and_uart_echo(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PS, unit="ps").start())
    host = Host(dut)
    state = {"uio": 0xFF}

    dut._log.info("Reset")
    dut.ena.value = 1
    dut.ui_in.value = host.ui                    # strap low: external clock
    dut.uio_in.value = state["uio"]
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 20)

    dut._log.info("Load the firmware into the code memory of core 0 through the host link")
    image = load_hex("uart_echo.hex")
    await host.write(0x4000, image)


    dut._log.info("Read the status and the code memory back while the core reset is still set")
    await host.start()
    st = [await host.byte(b) for b in (0x05, 0, 0, 0)]
    await host.stop()
    assert st[2] & 0x80, f"status {st[2]:#04x}: access not allowed in the core reset"
    back = await host.read(0x4000, len(image))
    assert back == image, "code memory differs from the image"

    # Seed unused SRAM output registers (dr_r) with arbitrary 2-state values via the host link.
    # On silicon SRAM outputs are always 2-state; leaving behavioral dr_r=X causes GL X-pessimism
    # across synthesized cm0_rdata/cm1_rdata muxes.
    await host.write(0x4800, [0x5A, 0xA5, 0x3C, 0xC3])
    await host.read(0x4800, 2)
    await host.write(0x0100, [0x5A, 0xA5, 0x3C, 0xC3])
    await host.read(0x0100, 2)
    await host.read(0x4000, 2)

    # Seed unreset AVR register file R[0..15] (r16..r31) with arbitrary 2-state value 0x5A via host
    # link instruction injection so 4-state GL sim matches silicon on startup EOR r17, r17.
    await host.control(0x01)                     # release core reset while halting core 0
    await ClockCycles(dut.clk, 10)
    for k in range(16):
        await host.inject(0xE50A | (k << 4))     # LDI r(16+k), 0x5A
    await host.control(0x80)                     # return PC/state/SP/SREG to reset before starting

    dut._log.info("Release the core reset")
    await host.control(0x00)
    await ClockCycles(dut.clk, 2000)             # the firmware sets up the line cells
    assert bit(dut.uio_oe, TX_PIN) == 1, "transmit pin is not an output"

    for ch in (0x55, 0xA3, 0x00, 0xFF):
        rx = cocotb.start_soon(uart_receive(dut))
        await uart_send(dut, state, ch)
        got = await rx
        assert got == ch, f"sent {ch:#04x}, echo {got}"
        dut._log.info(f"echo of {ch:#04x} ok")


@cocotb.test()
async def test_internal_osc_and_relax(dut):
    """Exercise rpe_clk_analog ring (clk) and relax (clk_slow) through the Tiny Tapeout pins."""
    cocotb.start_soon(Clock(dut.clk, CLK_PS, unit="ps").start())
    host = Host(dut)

    dut.ena.value = 1
    dut.ui_in.value = host.ui                    # strap low: external clock
    dut.uio_in.value = 0xFF
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 20)

    # 1. Enable relax oscillator (CLKCTL[7] = RELAXEN) and route clk_slow to dbg uo_out[2] (DBGSEL = 0x8F)
    await host.write(0x3F20, [0x80])
    await host.write(0x3F52, [0x8F])
    seen = set()
    for _ in range(500):
        await ClockCycles(dut.clk, 2)            # ~1000 cycles = ~16.7 us > 1 period at 98.5 kHz
        seen.add(bit(dut.uo_out, 2))
        if seen == {0, 1}:
            break
    assert seen == {0, 1}, f"clk_slow did not toggle on dbg pin uo_out[2]: seen={seen}"
    dut._log.info("relax_core clk_slow observed toggling on uo_out[2]")

    # 2. Set OSCTRIM=155 (~60 MHz post-PEX), power on ring oscillator (OSCEN=1), verify presence flag
    await host.write(0x3F21, [155])
    await host.write(0x3F20, [0x82])
    await ClockCycles(dut.clk, 2500)
    st = (await host.read(0x000F, 1))[0]
    assert st & 0x02, f"CLKSTAT={st:#04x}: ring oscillator presence (pres_o) not detected"

    # 3. Switch system clock to internal ring oscillator (SRC=1) and confirm act=1
    await host.write(0x3F20, [0x83])
    await ClockCycles(dut.clk, 200)
    st = (await host.read(0x000F, 1))[0]
    assert (st & 0x03) == 0x03, f"CLKSTAT={st:#04x}: failed to switch system clock to internal ring oscillator"
    dut._log.info(f"Switched system clock to rpe_clk_analog (CLKSTAT={st:#04x})")

    # 4. Switch back to external clock and power down both internal oscillators
    await host.write(0x3F20, [0x00])
    await host.write(0x3F52, [0x00])
    await ClockCycles(dut.clk, 2500)
    st = (await host.read(0x000F, 1))[0]
    assert (st & 0x01) == 0, f"CLKSTAT={st:#04x}: failed to return to external clock"
