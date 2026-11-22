# SPDX-FileCopyrightText: © 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
#
# Tests of Changeling-alpha through its pins only, so that the same file runs on the RTL and on the
# gate-level netlist. The firmware is loaded through the host link, as on the demo board.
#
#   test_load_and_uart_echo   loads fw/uart_echo.hex (src/rsoc8/fw/fwu_echo.c, 60 clock cycles per bit),
#                             reads the code memory back, starts core 0 and checks the echo of four characters
#
# The complete regression (firmware tests against protocol models, block tests against Python models)
# is in src/rsoc8/tests and src/rsoc8/blocks; see src/rsoc8/README.md.

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

    # The data output of the host link is an output register of the port block, which is held in the core
    # reset. Reading back therefore needs the reset released; the halt requests keep both cores stopped.
    dut._log.info("Release the core reset with both cores halted, read the code memory back")
    await host.control(0x03)
    await ClockCycles(dut.clk, 20)
    back = await host.read(0x4000, len(image))
    assert back == image, "code memory differs from the image"

    dut._log.info("Let the cores run")
    await host.control(0x00)
    await ClockCycles(dut.clk, 2000)             # the firmware sets up the line cells
    assert bit(dut.uio_oe, TX_PIN) == 1, "transmit pin is not an output"

    for ch in (0x55, 0xA3, 0x00, 0xFF):
        rx = cocotb.start_soon(uart_receive(dut))
        await uart_send(dut, state, ch)
        got = await rx
        assert got == ch, f"sent {ch:#04x}, echo {got}"
        dut._log.info(f"echo of {ch:#04x} ok")
