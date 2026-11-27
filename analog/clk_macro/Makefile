# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
include ../common.mk

BLOCK := clk_macro
KLAYOUT ?= /nix/store/cw81fji9f4zsggnpi3h42c3smyzj4iq7-klayout-0.30.12/bin/klayout

.PHONY: all gen netlist lvs_netlist sim layout drc drc_antenna lvs pex sim_pex svg pdf clean

all: gen netlist lvs_netlist sim svg pdf

gen:
	python3 $(ANALOG_DIR)/scripts/gen_clk_macro.py

netlist: dirs gen
	$(XSCHEM) -n -q -x -o $(BUILD_DIR) tb_rpe_clk_analog.sch
	@echo "Netlisted $(BUILD_DIR)/tb_rpe_clk_analog.spice"

lvs_netlist: dirs gen
	$(XSCHEM) -n -q -x --command "set lvs_netlist 1; xschem set format lvs_format; xschem netlist; exit" -o $(BUILD_DIR) rpe_clk_analog.sch
	python3 -c 'from pathlib import Path; std=Path("$(PDK_ROOT)/$(PDK)/libs.ref/sg13cmos5l_stdcell/cdl/sg13cmos5l_stdcell.cdl").read_text(); net=Path("$(BUILD_DIR)/rpe_clk_analog.spice").read_text(); net=net.replace("w=0.5e-6 l=20.0e-6 b=19 m=1", "w=0.5e-6 l=21.125e-6 ps=0.18e-6 b=19 m=1").replace("w=0.5e-6 l=40.0e-6 b=9 m=1", "w=0.5e-6 l=41.055e-6 ps=0.18e-6 b=9 m=1"); Path("$(BUILD_DIR)/rpe_clk_analog_lvs.spice").write_text(net.replace(".end\n", std + "\n.end\n") if ".end\n" in net else net + "\n" + std + "\n")'
	@echo "LVS-netlisted $(BUILD_DIR)/rpe_clk_analog_lvs.spice"

sim: netlist
	python3 run_sims.py

layout: dirs
	KLAYOUT_PATH=$(PDK_ROOT)/$(PDK)/libs.tech/klayout $(KLAYOUT) -zz -r layout/gen_layout.py

drc: layout
	$(KLAYOUT) -b -r $(PDK_ROOT)/$(PDK)/libs.tech/klayout/tech/drc/ihp-sg13cmos5l.drc \
		-rd input=$(CURDIR)/layout/rpe_clk_analog.gds \
		-rd topcell=rpe_clk_analog \
		-rd report=$(CURDIR)/build/rpe_clk_analog_drc.lyrdb \
		-rd log=$(CURDIR)/build/rpe_clk_analog_drc.log \
		-rd tables=main

drc_antenna: layout
	$(KLAYOUT) -b -r $(PDK_ROOT)/$(PDK)/libs.tech/klayout/tech/drc/ihp-sg13cmos5l.drc \
		-rd input=$(CURDIR)/layout/rpe_clk_analog.gds \
		-rd topcell=rpe_clk_analog \
		-rd report=$(CURDIR)/build/rpe_clk_analog_ant.lyrdb \
		-rd log=$(CURDIR)/build/rpe_clk_analog_ant.log \
		-rd tables="main antenna"

lvs: lvs_netlist layout
	$(KLAYOUT) -b -r $(PDK_ROOT)/$(PDK)/libs.tech/klayout/tech/lvs/sg13cmos5l.lvs \
		-rd input=$(CURDIR)/layout/rpe_clk_analog.gds \
		-rd topcell=rpe_clk_analog \
		-rd schematic=$(CURDIR)/build/rpe_clk_analog_lvs.spice \
		-rd report=$(CURDIR)/build/rpe_clk_analog_lvs.lvsdb \
		-rd log=$(CURDIR)/build/rpe_clk_analog_lvs.log \
		-rd combine_devices=true \
		-rd disable_tap_extraction=true \
		-rd top_lvl_pins=true

pex: layout
	python3 extract_pex.py

sim_pex: pex
	python3 run_pex_sims.py

svg: dirs
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/relax_core.svg relax_core.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/rpe_clk_analog.svg rpe_clk_analog.sch
	$(XSCHEM) -q -x --svg --plotfile $(SVG_DIR)/tb_rpe_clk_analog.svg tb_rpe_clk_analog.sch

pdf: dirs
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/rpe_clk_analog.pdf rpe_clk_analog.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/relax_core.pdf relax_core.sch
	$(XSCHEM) -q -x -c --pdf --plotfile $(PDF_DIR)/tb_rpe_clk_analog.pdf tb_rpe_clk_analog.sch

clean:
	rm -rf $(BUILD_DIR)
