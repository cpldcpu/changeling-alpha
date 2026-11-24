include ../common.mk

BLOCK := osc_relax

.PHONY: all gen netlist sim svg pdf clean

all: gen netlist sim svg pdf

gen:
	python3 $(ANALOG_DIR)/scripts/gen_osc_relax.py

netlist: dirs gen
	$(XSCHEM) -n -q -x -o $(BUILD_DIR) tb_osc_relax.sch
	$(XSCHEM) -n -q -x -o $(BUILD_DIR) tb_osc_relax_moscap.sch
	@echo "Netlisted $(BUILD_DIR)/tb_osc_relax*.spice"

sim: netlist
	python3 run_sims.py

svg: dirs
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/comp.svg comp.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/osc_relax.svg osc_relax.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/osc_relax_moscap.svg osc_relax_moscap.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/tb_osc_relax.svg tb_osc_relax.sch

pdf: dirs
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/osc_relax.pdf osc_relax.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/osc_relax_moscap.pdf osc_relax_moscap.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/comp.pdf comp.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/tb_osc_relax.pdf tb_osc_relax.sch

clean:
	rm -rf $(BUILD_DIR)
