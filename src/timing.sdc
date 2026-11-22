# Timing constraints of Changeling-alpha for the Tiny Tapeout flow (PNR_SDC_FILE and SIGNOFF_SDC_FILE).
#
# 1. The constraints of the flow (clock on clk with CLOCK_PERIOD, input and output delays, loads).
source $::env(SCRIPTS_DIR)/base.sdc

# 2. Two clock cycles for the paths from the code memories through the instruction inputs of the cores.
#
# The cores advance only in cycles in which the core clock enable (core divider) is set. Every flip-flop and
# every memory or register write that depends on an instruction is taken over only in such a cycle, and a code
# memory is read by a core only in such a cycle. With a core divider of 2 or more, an instruction is therefore
# stable for two clock cycles before anything takes it over. The reset value of the divider is 2
# (src/rsoc8/rtl/rclock.v); divider 1 is outside these constraints and is for a system clock of 33 MHz or less.
#
# Not covered by the exception and still one cycle: host reads of the memories, the data memory, and all paths
# that start at a flip-flop. The instruction inputs are the nets prd0 and prd1 of the two-core block, kept by
# an attribute in src/rsoc8/rtl/rdual.v.
set ca_mems [get_cells {chip.u.m_code0.u_mem chip.u.m_code1.u_mem}]
set ca_ins0 [get_nets chip.u.cores.prd0*]
set ca_ins1 [get_nets chip.u.cores.prd1*]
puts "\[INFO] Changeling-alpha: [llength $ca_mems] code memories, [llength $ca_ins0] + [llength $ca_ins1] instruction nets for the two-cycle exception"
if { [llength $ca_mems] != 2 || [llength $ca_ins0] != 16 || [llength $ca_ins1] != 16 } {
    error "Changeling-alpha: the cells or nets of the two-cycle exception were not found"
}
set_multicycle_path 2 -setup -from $ca_mems -through [concat $ca_ins0 $ca_ins1]
set_multicycle_path 1 -hold  -from $ca_mems -through [concat $ca_ins0 $ca_ins1]
