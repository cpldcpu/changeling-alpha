# rdual: two rcore8 cores with private code memories and a shared bus

Implements the section "Core behaviour" of the architecture specification (draft 0.16).

    rtl/rcore8d.v         one core: rcore8 with clock enable, synchronous data memory read, bus request
    rtl/rdual.v           two cores, bus arbiter, code memory routing, CORECTL, LOCK, WAIT, ARB
    rtl/rcore8_single.v   the original single-core rcore8, unchanged (source of the decode and ALU text)
    tb/tb_dual.v          testbench: three memories, register bus model, trace of instruction starts
    model/rmodel.py       instruction-level reference model of rcore8, unchanged
    model/rmodel_d.py     cycle model of the two-core arrangement on top of rmodel.py
    tests/run_all.sh      runs everything (SEEDS=n sets the number of random programs)
    tests/directed.py     directed tests: dual0/dual1, exact timing, stress in three arbitration modes

Synthesis with the IHP sg13g2 library (yosys, slow corner, no timing-driven sizing):
one core with 11-bit program counter 2280 cells / 30056 um2; rdual 4985 cells / 68976 um2.

Not tested: halt_req and brk_clr, io_prot, NIRQ = 16, a build with one core and no arbiter.
Not implemented: instruction injection by the host.

## Host port, injection and step (added with the host link)

- `rdual` has a host port in front of the three memories and the register bus (`h_*`), re-reads the
  code memory output after a host access, and has a sequencer for inject, execute and step (`inj_*`).
  `rcore8d` has the input `inj` and the output `at_start`.
- `tb/tb_dual.v +hrand=<seed>`: both cores are halted at random times; while halted the host port reads
  random memory locations and a NOP is injected. Bus model, cycle count and trace stand still, so the
  trace must equal the model. `HRAND=1 python3 tests/randtest_d.py 0 60 4000`
- `tests/mut_restore.py`: five faults in the re-read logic and the interrupt delay, checked with that test.
