# Timing constraints of Changeling-alpha for the Tiny Tapeout flow (PNR_SDC_FILE and SIGNOFF_SDC_FILE).
#
# 1. The constraints of the flow (clock on clk with CLOCK_PERIOD, input and output delays, loads).
source $::env(SCRIPTS_DIR)/base.sdc

# 2. Two clock cycles for the paths that start at a code memory.
#
# The cores advance only in cycles in which the core clock enable (core divider) is set. Every flip-flop and
# every memory or register write that depends on an instruction is taken over only in such a cycle, and a code
# memory is read by a core only in such a cycle. With a core divider of 2 or more, the output of a code memory
# is therefore stable for two clock cycles before anything in the cores or the peripherals takes it over. The
# reset value of the divider is 2 (src/rsoc8/rtl/rclock.v); divider 1 is outside these constraints and is for a
# system clock of 33 MHz or less.
#
# One consumer needs the output after one cycle: a read of a code memory by the host link, which goes into the
# registers tx_next and tx_hold of the host link (src/rsoc8/rtl/rhost.v, names kept by an attribute). These
# endpoints are taken out of the exception. Paths from the data memory and from flip-flops are not affected.
set ca_mems [get_cells {chip.u.m_code0.u_mem chip.u.m_code1.u_mem}]
set ca_hostq [get_pins -of_objects [get_nets {chip.u.host.tx_next* chip.u.host.tx_hold*}] -filter "direction == output"]
set ca_hostff [get_cells -of_objects $ca_hostq]
puts "\[INFO] Changeling-alpha: [llength $ca_mems] code memories with the two-cycle exception, [llength $ca_hostff] flip-flops of the host link excluded"
if { [llength $ca_mems] != 2 || [llength $ca_hostff] != 16 } {
    error "Changeling-alpha: the cells of the two-cycle exception were not found"
}
set_multicycle_path 2 -setup -from $ca_mems
set_multicycle_path 1 -hold  -from $ca_mems
set_multicycle_path 1 -setup -from $ca_mems -to $ca_hostff
set_multicycle_path 0 -hold  -from $ca_mems -to $ca_hostff
