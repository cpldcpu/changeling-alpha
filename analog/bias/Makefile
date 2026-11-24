include ../common.mk

BLOCK := bias
SCH   := bias.sch tb_bias.sch

.PHONY: all gen netlist sim svg pdf clean

all: gen netlist sim svg pdf

gen:
	python3 $(ANALOG_DIR)/scripts/gen_bias.py

netlist: dirs gen
	$(XSCHEM) -n -q -x -o $(BUILD_DIR) tb_bias.sch
	@echo "Netlisted $(BUILD_DIR)/tb_bias.spice"

sim: netlist
	python3 run_sims.py

svg: dirs
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/bias.svg bias.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/tb_bias.svg tb_bias.sch

pdf: dirs
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/bias.pdf bias.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/tb_bias.pdf tb_bias.sch

clean:
	rm -rf $(BUILD_DIR)
