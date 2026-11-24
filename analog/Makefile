include common.mk

BLOCKS := bias osc_ring_std osc_ring_cc osc_relax clk_macro

PDF_PAGES := \
	$(PDF_DIR)/bias.pdf $(PDF_DIR)/tb_bias.pdf \
	$(PDF_DIR)/osc_ring_std.pdf $(PDF_DIR)/tap_chain_16.pdf $(PDF_DIR)/tb_osc_ring_std.pdf \
	$(PDF_DIR)/osc_ring_cc.pdf $(PDF_DIR)/idac_8b.pdf $(PDF_DIR)/cco_core.pdf $(PDF_DIR)/tb_osc_ring_cc.pdf \
	$(PDF_DIR)/osc_relax.pdf $(PDF_DIR)/osc_relax_moscap.pdf $(PDF_DIR)/comp.pdf $(PDF_DIR)/tb_osc_relax.pdf \
	$(PDF_DIR)/rpe_clk_analog.pdf $(PDF_DIR)/relax_core.pdf $(PDF_DIR)/tb_rpe_clk_analog.pdf

.PHONY: all gen netlist sim svg pdf clean $(BLOCKS)

all: gen netlist sim svg pdf

gen:
	@for b in $(BLOCKS); do $(MAKE) -C $$b gen; done

netlist:
	@for b in $(BLOCKS); do $(MAKE) -C $$b netlist; done

sim:
	@for b in $(BLOCKS); do $(MAKE) -C $$b sim; done

svg:
	@for b in $(BLOCKS); do $(MAKE) -C $$b svg; done

pdf: dirs
	@for b in $(BLOCKS); do $(MAKE) -C $$b pdf; done
	pdfunite $(PDF_PAGES) $(RESULTS_DIR)/schematics.pdf
	@echo "Combined $(RESULTS_DIR)/schematics.pdf"

clean:
	@for b in $(BLOCKS); do $(MAKE) -C $$b clean; done

$(BLOCKS):
	$(MAKE) -C $@ all
