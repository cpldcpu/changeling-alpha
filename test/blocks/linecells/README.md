# Line cells of the rcore8 protocol emulator: receive cell and transmit cell

Implements the section "Line cell behaviour" of the architecture specification (draft 0.18).

    rtl/rlinecells.v     rlc_rx (receive cell), rlc_tx (transmit cell), rlc_step (one base unit of
                         receive timing), rlc_reg / rlc_cg (configuration register with gated clock)
    tb/tb_lc.v           one pair, replays stimulus files and logs frames, sample points, waveforms
    tb/tb_lc2.v          two pairs on a pin bus, directed and self-checking
    model/linecell.py    behavioural model
    model/test_cell.py   the model's own protocol tests and clock tolerance figures
    tests/lc_test.py     RTL against the model: protocol cases and random configurations
    tests/run_all.sh     runs everything (CASES=n sets the number of random configurations)

Synthesis with the IHP sg13g2 library (yosys, slow corner, no timing-driven sizing; define IHP_CELLS
to instantiate the clock gate cell sg13g2_lgcp_1):
receive cell 1012 cells / 15900 um2 / 156 flip-flops, transmit cell 624 cells / 11400 um2 / 126.

Outside the cells and not built yet: pin synchronisers, pin multiplexer, output registers, address
decoding and owners.

## Draft 0.36: additional frame bit, start at the shift edge, bus conditions

`rtl/rlinecells.v` is the file of the `rsys` package (registers `LCX` at offset 0xF, `LCEC` at receive offset 7,
status bit `FERR`). `rtl/rlinecells_v034.v` is the file before this change.

- `model/linecell.py`: parameter `PAR` (additional bit, rules N1 to N4). `write()` takes a 9-bit value; received
  frames have the additional bit in bit 8. The model does not contain `ESTR`, `BCD` and the edge count.
- `tb/tb_lc.v`: writes offset 15 of both cells (lines 15 and 31 of the configuration file), 9-bit transmit queue,
  logs the ninth bit with each frame and the bit strobes of the receive cell (`X` lines).
- `tests/lc_test.py`: 20 UART cases with even parity, odd parity and ninth data bit; `PAR` in the random
  configurations (three in five).
- `tb/tb_lc2.v`: directed tests of the bus condition detector and the edge count (block C9) and of the start at
  the shift edge (block C8), at the end of the file.
- Result of `sh tests/run_all.sh`: 48 cases ok, 200 + 200 random configurations without difference, directed tests pass.
