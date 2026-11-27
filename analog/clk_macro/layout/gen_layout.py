#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Top-level entry point to build rpe_clk_analog.gds, .lef, and .v using KLayout."""

import sys
from pathlib import Path

LAY_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAY_DIR))

from lay_core import LayoutBuilder
from blocks_relax_top import build_top_macro, write_lef_and_verilog


def export_tt_clean_gds(lb: LayoutBuilder, out_path: Path) -> None:
    """Write a Tiny Tapeout precheck-clean GDS by copying (160, 0) NoMetFiller
    onto Metal1..4.nofill and stripping (51, 0) HeatTrans, (99, 40) Recog.momf,
    and (160, 0) NoMetFiller marker layers."""
    ly = lb.ly
    src_nofill = ly.find_layer(160, 0)
    if src_nofill is not None:
        target_layers = [
            ly.layer(8, 23),   # Metal1.nofill
            ly.layer(10, 23),  # Metal2.nofill
            ly.layer(30, 23),  # Metal3.nofill
            ly.layer(50, 23),  # Metal4.nofill
        ]
        for cell in ly.each_cell():
            shapes = cell.shapes(src_nofill)
            if shapes.size() == 0:
                continue
            for tgt in target_layers:
                for sh in shapes.each():
                    cell.shapes(tgt).insert(sh.polygon if sh.is_polygon() else sh.box)
    for lnum, dtype in ((51, 0), (99, 40), (160, 0)):
        idx = ly.find_layer(lnum, dtype)
        if idx is not None:
            ly.delete_layer(idx)
    ly.write(str(out_path))


def main() -> None:
    lb = LayoutBuilder()
    top, bb, pin_boxes = build_top_macro(lb)
    gds_path = LAY_DIR / "rpe_clk_analog.gds"
    lb.ly.write(str(gds_path))
    write_lef_and_verilog(LAY_DIR, bb, pin_boxes)
    tt_gds_path = LAY_DIR / "rpe_clk_analog_tt.gds"
    export_tt_clean_gds(lb, tt_gds_path)
    print(f"Wrote {gds_path}, {tt_gds_path} ({bb.w:.3f} x {bb.h:.3f} um = {bb.w * bb.h:.1f} um^2), .lef, and .v")


if __name__ == "__main__":
    main()
