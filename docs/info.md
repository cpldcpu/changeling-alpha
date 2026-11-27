<!---
This file is the Tiny Tapeout project page. The Tiny Tapeout docs workflow converts it to the project
datasheet, together with the pin table of info.yaml. It is kept short on purpose; the full documentation
is in the three PDF documents linked below (sources in src/rsoc8/doc).

Images in this folder: each below 512 kB, all together below 1 MB.
-->

## How it works

Changeling-alpha is a programmable protocol emulator. Two 8-bit RISC cores run firmware from two code
memories of 1024 words each and share 2 KB of data memory. Four line cells (two receive cells and two
transmit cells) do the bit-level work of a serial protocol in hardware: timing, line code, bit stuffing,
framing with parity or a ninth bit, start and stop conditions of a two-wire bus. The firmware configures
the cells and handles frames, so a new protocol is a new program and a new set of register values.
A 16-bit timer, three PWM outputs, a CRC unit, 16 event flags and a host link complete the chip.

The cores are programmed in C with GCC. Programs are loaded through the host link, an SPI slave on three
input pins and one output pin, which also gives debug access (halt, single step, memory and register access).

Documentation:

| Document | Content |
|---|---|
| [Changeling-alpha datasheet](https://github.com/cpldcpu/changeling-alpha/blob/main/src/rsoc8/doc/pdf/rpe_datasheet.pdf) | blocks, memory map, instruction set with cycle counts, registers, configuration examples with timing diagrams, code examples |
| [Verification report](https://github.com/cpldcpu/changeling-alpha/blob/main/src/rsoc8/doc/pdf/rpe_verification.pdf) | methods, results, faults found, location of every test, known gaps |
| [Architecture specification](https://github.com/cpldcpu/changeling-alpha/blob/main/src/rsoc8/doc/pdf/rpe_spec.pdf) | rules of every block, design decisions, review history |
| [Analog clock macro report](https://github.com/cpldcpu/changeling-alpha/blob/main/analog/report/analog_clock_report.pdf) | ring oscillator and relaxation oscillator: circuits, layout, simulation after extraction, DRC and LVS |

## How to test

1. Apply the 60 MHz clock and reset. Keep `ui[3]` low (external clock).
2. Load a program into the code memory of core 0 through the host link (`ui[0]` clock, `ui[1]` chip select,
   `ui[2]` data in, `uo[0]` data out): command `0x02`, address `0x40 0x00`, then the program bytes, low byte
   of each word first. The code memory of core 1 is at address `0x4800`.
3. Release the core reset with the control command: `0x04 0x00`.
4. With the example `test/fw/uart_echo.hex` the chip returns every UART character received on `uio[4]` on
   `uio[5]` (1 Mbit/s, 8 data bits, 1 stop bit).

The host link commands are in the datasheet, chapter "Host link, mailbox and debug". The cocotb test in
`test/test.py` performs the steps above in simulation. Status and memory can be read through the host link while
the core reset is still set, so a loaded program can be checked before it runs.

## External hardware

None for the chip itself. Depending on the protocol:

- I2C: pull-up resistors on the two bus lines.
- Low-speed USB: a 1.5 kOhm pull-up on D- to 3.3 V and series resistors.
- 10BASE-T: line driver or transformer for transmit, a comparator or receiver for receive.
- WS2812: level shifter to the supply of the LEDs, if that is 5 V.

Level shifters, pull-ups and transceivers belong on a Pmod.
