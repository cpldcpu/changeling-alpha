include ../common.mk

BLOCK := osc_ring_cc

.PHONY: all gen netlist sim svg pdf clean

all: gen netlist sim svg pdf

gen:
	python3 $(ANALOG_DIR)/scripts/gen_osc_ring_cc.py

netlist: dirs gen
	$(XSCHEM) -n -q -x -o $(BUILD_DIR) tb_osc_ring_cc.sch
	@echo "Netlisted $(BUILD_DIR)/tb_osc_ring_cc.spice"

sim: netlist
	python3 run_sims.py

svg: dirs
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/idac_8b.svg idac_8b.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/cco_core.svg cco_core.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/osc_ring_cc.svg osc_ring_cc.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/tb_osc_ring_cc.svg tb_osc_ring_cc.sch

pdf: dirs
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/osc_ring_cc.pdf osc_ring_cc.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/idac_8b.pdf idac_8b.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/cco_core.pdf cco_core.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/tb_osc_ring_cc.pdf tb_osc_ring_cc.sch

clean:
	rm -rf $(BUILD_DIR)
