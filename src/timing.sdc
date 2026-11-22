# Timing constraints of Changeling-alpha for the Tiny Tapeout flow (PNR_SDC_FILE and SIGNOFF_SDC_FILE).
#
# 1. The constraints of the flow (clock on clk with CLOCK_PERIOD, input and output delays, loads).
source $::env(SCRIPTS_DIR)/base.sdc

# 2. Two clock cycles for the paths that start at a memory or at a core register listed below.
#
# The cores advance only in cycles in which the core clock enable (core divider) is set. Every flip-flop and
# every memory or register write that depends on an instruction is taken over only in such a cycle, and a
# memory is read by a core only in such a cycle. With a core divider of 2 or more, the output of a memory is
# therefore stable for two clock cycles before anything in the cores or the peripherals takes it over. The
# reset value of the divider is 2 (src/rsoc8/rtl/rclock.v); divider 1 is outside these constraints and is for a
# system clock of 33 MHz or less.
#
# Consumers that take a memory output after one cycle are taken out of the exception:
# - tx_next and tx_hold of the host link (src/rsoc8/rtl/rhost.v): read of a memory by the host;
# - dq of each core (src/rsoc8/rtl/rcore8d.v): capture of the data memory output in the cycle after a read.
#   With a divider of 2 or more the cores use the data memory output only through dq.
# Their names are kept by attributes in the RTL.
proc ca_flops {pattern {skip ""}} {
    # flip-flops whose outputs drive the nets that match the pattern; nets with $skip in their name are left out
    set nets {}
    foreach n [get_nets $pattern] {
        if { $skip eq "" || [string first $skip [get_full_name $n]] < 0 } { lappend nets $n }
    }
    return [get_cells -of_objects [get_pins -of_objects $nets -filter "direction == output"]]
}
set ca_mems [get_cells {chip.u.m_code0.u_mem chip.u.m_code1.u_mem chip.u.m_data.u_mem}]
set ca_one  [concat [ca_flops chip.u.host.tx_next*] [ca_flops chip.u.host.tx_hold*] \
                    [ca_flops chip.u.cores.core0.dq* dq_v] [ca_flops chip.u.cores.core1.dq* dq_v]]
puts "\[INFO] Changeling-alpha: [llength $ca_mems] memories with the two-cycle exception, [llength $ca_one] flip-flops excluded"
if { [llength $ca_mems] != 3 || [llength $ca_one] != 32 } {
    error "Changeling-alpha: the cells of the two-cycle exception were not found"
}
# Registers of the cores and of the instruction injection that change only in cycles with the core clock
# enable (rcore8d: state, ir; rdual: jst, jmode, jcore, jword). Their paths have two clock cycles as well.
set ca_core [concat [ca_flops chip.u.cores.core0.state*] [ca_flops chip.u.cores.core1.state*] \
                    [ca_flops chip.u.cores.core0.ir* irq] [ca_flops chip.u.cores.core1.ir* irq] \
                    [ca_flops chip.u.cores.jst*]  [ca_flops chip.u.cores.jmode*] \
                    [ca_flops chip.u.cores.jcore*] [ca_flops chip.u.cores.jword*]]
puts "\[INFO] Changeling-alpha: [llength $ca_core] core and injection flip-flops with the two-cycle exception"
if { [llength $ca_core] != 62 } { error "Changeling-alpha: expected 62 core and injection flip-flops, found [llength $ca_core]" }
set_multicycle_path 2 -setup -from $ca_mems
set_multicycle_path 1 -hold  -from $ca_mems
set_multicycle_path 1 -setup -from $ca_mems -to $ca_one
set_multicycle_path 0 -hold  -from $ca_mems -to $ca_one
set_multicycle_path 2 -setup -from $ca_core
set_multicycle_path 1 -hold  -from $ca_core
