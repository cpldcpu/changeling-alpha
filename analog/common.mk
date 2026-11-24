# Shared Makefile definitions for changeling-alpha analog blocks

PDK_ROOT ?= /home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008
PDK      ?= ihp-sg13cmos5l
export PDK_ROOT
export PDK

ANALOG_DIR  ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
RESULTS_DIR ?= $(ANALOG_DIR)/results
SVG_DIR     ?= $(RESULTS_DIR)/svg
PDF_DIR     ?= $(RESULTS_DIR)/pdf
BUILD_DIR   ?= build

XSCHEM  ?= env -u DISPLAY xschem --rcfile $(ANALOG_DIR)/xschemrc
NGSPICE ?= nix shell nixpkgs#ngspice --command ngspice

.PHONY: dirs
dirs:
	@mkdir -p $(BUILD_DIR) $(RESULTS_DIR) $(SVG_DIR) $(PDF_DIR)
