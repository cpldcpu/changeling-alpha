#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Generate Liberty (.lib) timing/power views for rpe_clk_analog across typ/slow/fast corners."""

from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "layout"

CORNERS = [
    # (suffix, vdd, temp, proc, slew_scale, leak_nW, ring_uA, relax_uA)
    ("typ_1p20V_25C", 1.20, 25, 1.0, 1.00, 7.26, 73.8, 4.98),
    ("slow_1p08V_125C", 1.08, 125, 1.0, 1.45, 74.18, 62.2, 4.55),
    ("fast_1p32V_m40C", 1.32, -40, 1.0, 0.72, 11.10, 103.4, 6.74),
]

SLEW_IDX = [0.010, 0.050, 0.150, 0.400, 1.000]
CAP_IDX = [0.002, 0.010, 0.030, 0.080, 0.250]


def fmt_table(vals_2d: list[list[float]], indent: str = "\t\t\t\t\t") -> str:
    rows = [f'{indent}"' + ", ".join(f"{v:.4f}" for v in row) + '"' for row in vals_2d]
    return " \\\n".join(rows)


def gen_lib(suffix: str, vdd: float, temp: int, proc: float, slew_scale: float, leak_nW: float, ring_uA: float, relax_uA: float) -> str:
    # Modeled after XBUF4 (sg13cmos5l_buf_4) output stage of cco_core / relax_core
    slew_tbl = [[(0.025 + 0.10 * s + 0.65 * c) * slew_scale for c in CAP_IDX] for s in SLEW_IDX]
    dly_tbl = [[(0.180 + 0.35 * s + 0.85 * c) * slew_scale for c in CAP_IDX] for s in SLEW_IDX]
    slew_str = ", ".join(f"{x:.3f}" for x in SLEW_IDX)
    cap_str = ", ".join(f"{x:.3f}" for x in CAP_IDX)
    p_dyn_clk = (ring_uA * 1e-6 * vdd) / 60e6 * 1e12  # pJ per 60 MHz cycle
    p_dyn_slow = (relax_uA * 1e-6 * vdd) / 100e3 * 1e12

    in_pins = []
    for pname in ["en_ring", "en_relax"] + [f"trim{i}" for i in range(8)]:
        in_pins.append(f"""\tpin({pname}) {{
\t\tdirection : input ;
\t\tcapacitance : 0.012 ;
\t\tmax_transition : 1.5 ;
\t\trelated_power_pin : VDD ;
\t\trelated_ground_pin : VSS ;
\t}}""")

    out_pins = []
    for pname, rel_pin, max_cap, p_int in [
        ("clk", "en_ring", 0.30, p_dyn_clk),
        ("clk_slow", "en_relax", 0.20, p_dyn_slow),
    ]:
        out_pins.append(f"""\tpin({pname}) {{
\t\tdirection : output ;
\t\tcapacitance : 0.0 ;
\t\tmax_capacitance : {max_cap:.3f} ;
\t\tmax_transition : 1.5 ;
\t\trelated_power_pin : VDD ;
\t\trelated_ground_pin : VSS ;
\t\tinternal_power() {{
\t\t\trise_power("scalar") {{ values ("{p_int:.4f}") ; }}
\t\t\tfall_power("scalar") {{ values ("{p_int:.4f}") ; }}
\t\t}}
\t\ttiming() {{
\t\t\trelated_pin : "{rel_pin}" ;
\t\t\ttiming_sense : positive_unate ;
\t\t\tcell_rise(delay_template_5x5) {{
\t\t\t\tvalues ( \\
{fmt_table(dly_tbl)}
\t\t\t\t) ;
\t\t\t}}
\t\t\tcell_fall(delay_template_5x5) {{
\t\t\t\tvalues ( \\
{fmt_table(dly_tbl)}
\t\t\t\t) ;
\t\t\t}}
\t\t\trise_transition(delay_template_5x5) {{
\t\t\t\tvalues ( \\
{fmt_table(slew_tbl)}
\t\t\t\t) ;
\t\t\t}}
\t\t\tfall_transition(delay_template_5x5) {{
\t\t\t\tvalues ( \\
{fmt_table(slew_tbl)}
\t\t\t\t) ;
\t\t\t}}
\t\t}}
\t}}""")

    return f"""library(rpe_clk_analog_{suffix}) {{
\ttechnology (cmos) ;
\tdelay_model : table_lookup ;
\tvoltage_map (VDD, {vdd:.2f}) ;
\tvoltage_map (VSS, 0.00) ;
\trevision : 1.0.0 ;
\tnom_process : {proc:.1f} ;
\tnom_temperature : {temp} ;
\tnom_voltage : {vdd:.2f} ;
\toperating_conditions("{suffix}") {{
\t\tprocess : {proc:.1f} ;
\t\ttemperature : {temp} ;
\t\tvoltage : {vdd:.2f} ;
\t\ttree_type : "balanced_tree" ;
\t}}
\tdefault_operating_conditions : {suffix} ;
\tdefault_max_transition : 1.5 ;
\tdefault_fanout_load : 1.0 ;
\tdefault_inout_pin_cap : 0.0 ;
\tdefault_input_pin_cap : 0.0 ;
\tdefault_output_pin_cap : 0.0 ;
\tdefault_cell_leakage_power : {leak_nW:.2f} ;
\tdefault_leakage_power_density : 0.0 ;
\tslew_lower_threshold_pct_rise : 30 ;
\tslew_upper_threshold_pct_rise : 70 ;
\tinput_threshold_pct_rise : 50 ;
\toutput_threshold_pct_rise : 50 ;
\tslew_lower_threshold_pct_fall : 30 ;
\tslew_upper_threshold_pct_fall : 70 ;
\tinput_threshold_pct_fall : 50 ;
\toutput_threshold_pct_fall : 50 ;
\tslew_derate_from_library : 0.5 ;
\tcapacitive_load_unit (1, pf) ;
\tvoltage_unit : "1V" ;
\tcurrent_unit : "1uA" ;
\ttime_unit : "1ns" ;
\tleakage_power_unit : "1nW" ;
\tpulling_resistance_unit : "1kohm" ;
\tlibrary_features(report_delay_calculation) ;

\tlu_table_template(delay_template_5x5) {{
\t\tvariable_1 : input_net_transition ;
\t\tvariable_2 : total_output_net_capacitance ;
\t\tindex_1 ("{slew_str}") ;
\t\tindex_2 ("{cap_str}") ;
\t}}

cell(rpe_clk_analog) {{
\tarea : 23495.5 ;
\tdont_touch : true ;
\tdont_use : true ;
\tis_macro_cell : true ;
\tcell_leakage_power : {leak_nW:.2f} ;
\tpg_pin(VDD) {{
\t\tpg_type : primary_power ;
\t\tvoltage_name : VDD ;
\t}}
\tpg_pin(VSS) {{
\t\tpg_type : primary_ground ;
\t\tvoltage_name : VSS ;
\t}}
{chr(10).join(in_pins)}
{chr(10).join(out_pins)}
}}
}}
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for cfg in CORNERS:
        suffix = cfg[0]
        p = OUT_DIR / f"rpe_clk_analog_{suffix}.lib"
        p.write_text(gen_lib(*cfg))
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()
