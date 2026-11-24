include ../common.mk

BLOCK := osc_ring_std

.PHONY: all gen netlist sim svg pdf clean

all: gen netlist sim svg pdf

gen:
	python3 $(ANALOG_DIR)/scripts/gen_osc_ring_std.py

netlist: dirs gen
	$(XSCHEM) -n -q -x -o $(BUILD_DIR) tb_osc_ring_std.sch
	@echo "Netlisted $(BUILD_DIR)/tb_osc_ring_std.spice"

sim: netlist
	python3 run_sims.py

svg: dirs
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/tap_chain_16.svg tap_chain_16.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/osc_ring_std.svg osc_ring_std.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/tb_osc_ring_std.svg tb_osc_ring_std.sch

pdf: dirs
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/osc_ring_std.pdf osc_ring_std.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/tap_chain_16.pdf tap_chain_16.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/tb_osc_ring_std.pdf tb_osc_ring_std.sch

clean:
	rm -rf $(BUILD_DIR)
