# Handover: clock generation, analog exploration

Date: 22 November 2026. For Tim S. B. (GitHub: cpldcpu), who runs the simulations locally.
State: plan only. No netlist, no testbench and no layout exists yet. All numbers below are estimates from
PDK model parameters and library tables; none is simulated.

## 1. Why

The chip is specified for an external 60 MHz clock, which the demo board supplies. The internal clock is an
extra function: operation without an external reference, low-speed USB without a crystal, and a slow clock
for a sleep state. A failure of the internal clock must not stop the chip: after reset the strap pin selects
the external clock, and the oscillator macro can be replaced by the stub `src/rsoc8/rtl/rpe_osc_stub.v`.

A custom macro has to pass the Tiny Tapeout precheck (KLayout DRC with the CMOS5L deck, layer and boundary
checks). The precheck runs no LVS; LVS is our own task. A macro that is not DRC and LVS clean by the
cut-off date (proposed: 20 December 2026) is left out.

## 2. Plan

| Block | Implementation | Role |
|---|---|---|
| Ring oscillator A, 60 MHz | standard cells, tap-selected delay line, hardened as a digital macro | baseline, no custom layout |
| Ring oscillator B, 60 MHz | current-controlled ring with current DAC, custom | candidate to replace A |
| Relaxation oscillator, about 100 kHz | current-controlled, custom | reference of the frequency loop, sleep clock |
| Bias cell | self-biased reference with start-up, custom, no bandgap | shared by B and the relaxation oscillator |
| Frequency loop | existing logic in `src/rsoc8/rtl/rclock.v` | locks the ring to a reference (pin, USB frame interval in firmware, relaxation oscillator) |

Interface of an oscillator macro today: `en`, `trim[7:0]`, `clk` (module `rpe_osc`). The relaxation
oscillator needs a second macro interface or more pins; this is not specified yet.

## 3. Options to explore

### Ring oscillator A (standard cells)
- Ring at 60 MHz directly; loop delay 8.3 ns. Fixed delay section, then about 127 buffers with a tap after
  each; the trim value selects the tap, so the frequency is monotonic in the trim value.
- One tap is about 1 % of the period (typical), about 1.5 % at the slow corner. Finer resolution by switching
  between two neighbouring taps with a first-order modulator on a few fractional trim bits.
- Reset value of the trim: longest chain, sized to stay at or below 60 MHz at the fast corner (about 27 MHz
  at the slow corner).
- Cell delays differ by a factor of about 2.2 between the slow (1.08 V, 125 C) and fast (1.32 V, -40 C)
  library corners; the trim range should cover a factor of about 3.
- Area estimate: about 4,000 um2 of cells, about 6,000 um2 as a macro.
- To simulate: frequency against trim value per corner, supply sensitivity, temperature drift, duty cycle,
  behaviour at a tap change.

### Ring oscillator B (current-controlled)
- Ring fed from a mirrored bias current through a current DAC; level shifter to full swing.
- Expected advantages over A: lower supply sensitivity, fine trim steps without tap switching, less period
  jitter from digital supply noise.
- Current estimate 5 to 20 uA for 60 MHz; mirror ratio 10 to 50 from the reference branch.
- Area estimate 4,000 to 6,000 um2 including guard rings.
- To simulate: the same list as for A, plus DAC monotonicity and the rejection of supply steps.

### Relaxation oscillator
- Principle: one current I charges C up to a threshold that is the voltage of the same current across a
  matched resistor. The period depends on R x C only; supply and bias current cancel to first order.
- Target about 100 kHz, bias current 0.3 to 1 uA. Not a design in the nA range: it has to be a reference.
- Area options for the passives at 100 kHz (R x C about 5 us in the plain form):

| Option | R and C | Passive area (estimate) | To check |
|---|---|---|---|
| Baseline: low-TC poly resistor (`rppd`, 260 Ohm/sq, +170 ppm/K), metal-finger capacitor (`cap_cmomf`, 1.29 fF/um2 for Metal1 to Metal4) | 1.4 MOhm, 3.5 pF | 5,400 um2 | the capacitor model is not validated on silicon and has no corner spread |
| MOS capacitor with thick gate oxide in place of the metal-finger capacitor | 0.73 MOhm, 6.8 pF | 2,800 um2 | density assumed about 5 fF/um2 (not read from the PDK); voltage dependence of C; use the accumulation-mode device |
| Charge current scaled down 1:M by a mirror (M = 10): period M x R x C | R x C ten times smaller | 1,700 um2 with the baseline capacitor | leakage of switches and capacitor against 40 nA at 125 C; spread of the mirror ratio |
| Both | | about 900 um2 | both |
| 400 kHz and divide by four | half of each row | | four times the current; against the sleep use |

- Not useful: the high-ohmic resistor `rhigh` (1,360 Ohm/sq) has -2,300 ppm/K; cancelling it with `rppd`
  leaves only 7 % of `rhigh`. The thin-oxide MOS capacitor may leak in the order of the bias current.
- Macro estimate with both measures: 4,000 to 6,000 um2. Untrimmed spread estimated at 20 to 30 %; the chip
  has no non-volatile memory, so the host writes the calibration value after power-up.
- Proposal for the first netlist: both measures, M and the capacitor type as parameters.

### Bias cell
- Self-biased reference (two mirrors and a resistor) with a start-up circuit. Supply-independent to first
  order; the current rises with temperature, which the frequency loop corrects for the ring and which
  cancels in the relaxation oscillator.
- No bandgap: the core supply is 1.2 V, so it would need a low-voltage current-mode circuit with an
  amplifier; neither oscillator needs an absolute voltage. The PDK has a parasitic PNP (`pnpMPA`) if this is
  wanted later for a brown-out detector or a regulator.

## 4. PDK facts used (ihp-sg13cmos5l, IHP-Open-PDK)

- Core supply 1.2 V; library corners typ 1.20 V 25 C, slow 1.08 V 125 C, fast 1.32 V -40 C.
- Metal stack in the flow: Metal1 to Metal4 and TopMetal1; routing uses Metal2 to TopMetal1.
- Devices: low-voltage and high-voltage MOS, resistors `rsil` (7 Ohm/sq, +3,100 ppm/K), `rppd`, `rhigh`,
  capacitors `cap_cmomf`, `cap_cmomi`, MOS capacitors, PNP `pnpMPA`. No MIM capacitor.
- Simulation: `libs.tech/ngspice` (models, `.spiceinit`, OSDI models for the capacitors, to be compiled with
  `libs.tech/verilog-a/openvaf-compile-va.sh`), `libs.tech/xyce`, xschem symbols in `libs.tech/xschem`.
  Resistor and SRAM model files are links to the `ihp-sg13g2` tree.
- Standard cell netlists for a transistor-level simulation of ring A:
  `libs.ref/sg13cmos5l_stdcell/spice/sg13cmos5l_stdcell.spice`.
- Library delays read from the tables (second slew and load index, load 23 fF): `buf_1` 0.146 ns typ,
  0.213 slow, 0.102 fast; `dlygate4sd3_1` 0.472 / 0.723 / 0.329; `mux4_1` 0.261 / 0.396 / 0.178.

## 5. Open points

1. Counter widths and rules of the frequency loop in `rclock.v` were written for a 15 MHz oscillator. They
   have to be rechecked for 60 MHz and a 100 kHz reference.
2. Timing margin of the logic above 60 MHz is known only after the first place and route.
3. Interface of the relaxation oscillator to the clocking block, and a third input of the clock switch for
   the sleep clock (minimal sleep: ring off, system clock from the relaxation oscillator, firmware switches
   back on an event). Optional for this tapeout.
4. The specification still describes one relaxation oscillator at 15 MHz. It has to be changed to this plan.
5. Who draws the custom layout, and with which tool. DRC and LVS cannot be run in the environment in which
   the netlists are written.
6. Tools on the local computer (native ngspice and xschem, or the IIC-OSIC-TOOLS container).

## 6. Proposed folder layout

```
analog/
  HANDOVER.md        this file
  osc_ring_std/      structural Verilog, generated SPICE netlist, testbenches     (not yet present)
  osc_ring_cc/       netlist, testbenches                                         (not yet present)
  osc_relax/         netlist, testbenches                                         (not yet present)
  bias/              netlist, testbenches                                         (not yet present)
  results/           CSV files written by the testbench scripts, committed        (not yet present)
```

Each folder gets a Makefile that takes `PDK_ROOT` and writes its results as CSV (frequency per trim value
and corner, supply and temperature sweeps), so that the results can be committed and evaluated.
