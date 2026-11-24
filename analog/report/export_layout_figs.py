#!/usr/bin/env python3
"""Export flattened GDS polygons via KLayout and render vector layout PDFs + 300-DPI PNG figures."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

ANALOG_DIR = Path(__file__).resolve().parents[1]
GDS_PATH = ANALOG_DIR / "clk_macro" / "layout" / "rpe_clk_analog.gds"
LEF_PATH = ANALOG_DIR / "clk_macro" / "layout" / "rpe_clk_analog.lef"
FIG_DIR = ANALOG_DIR / "report" / "figures"
RES_DIR = ANALOG_DIR / "results"
RES_PDF_DIR = RES_DIR / "pdf"
KLAYOUT = "/nix/store/cw81fji9f4zsggnpi3h42c3smyzj4iq7-klayout-0.30.12/bin/klayout"

# Extract layers in painter's order (bottom -> top)
LAYERS = [
    ("prBoundary", (189, 4)),
    ("NWell",      (31, 0)),
    ("TGO",        (44, 0)),
    ("SalBlock",   (28, 0)),
    ("Activ",      (1, 0)),
    ("GatPoly",    (5, 0)),
    ("Cont",       (6, 0)),
    ("Metal1",     (8, 0)),
    ("Via1",       (19, 0)),
    ("Metal2",     (10, 0)),
    ("Via2",       (29, 0)),
    ("Metal3",     (30, 0)),
    ("Via3",       (49, 0)),
    ("Metal4",     (50, 0)),
]

CELLS = ["rpe_clk_analog", "bias_lay", "idac_8b_lay", "cco_core_lay", "comp_lay", "relax_core_lay"]


def klayout_dump(json_path: Path) -> None:
    """Run inside KLayout (`klayout -zz -r`) when KLAYOUT_DUMP=1, or spawn KLayout."""
    import pya  # type: ignore

    ly = pya.Layout()
    ly.read(str(GDS_PATH))
    out = {}
    for cname in CELLS:
        cell = ly.cell(cname)
        bb = cell.bbox().to_dtype(0.001)
        layer_polys = {}
        for lname, (lnum, ldt) in LAYERS:
            li = ly.find_layer(lnum, ldt)
            if li is None:
                layer_polys[lname] = []
                continue
            polys = []
            it = cell.begin_shapes_rec(li)
            while not it.at_end():
                sh = it.shape()
                if not sh.is_text():
                    sp = None
                    if sh.is_box():
                        b = sh.box.transformed(it.trans()).to_dtype(0.001)
                        polys.append([[b.left, b.bottom], [b.right, b.bottom], [b.right, b.top], [b.left, b.top]])
                    elif sh.is_polygon():
                        sp = sh.polygon.transformed(it.trans()).to_simple_polygon()
                    elif sh.is_path():
                        sp = sh.path.transformed(it.trans()).polygon().to_simple_polygon()
                    if sp is not None:
                        pts = [[round(p.x * 0.001, 4), round(p.y * 0.001, 4)] for p in sp.each_point()]
                        if len(pts) >= 3:
                            polys.append(pts)
                it.next()
            layer_polys[lname] = polys

        sub_boxes = []
        if cname == "rpe_clk_analog":
            for inst in cell.each_inst():
                sc = ly.cell(inst.cell_index)
                if sc.name.endswith("_lay"):
                    tr = inst.trans
                    sbb = sc.bbox().transformed(tr).to_dtype(0.001)
                    sub_boxes.append({"name": sc.name, "box": [sbb.left, sbb.bottom, sbb.right, sbb.top]})
        out[cname] = {"bbox": [bb.left, bb.bottom, bb.right, bb.top], "layers": layer_polys, "subs": sub_boxes}
    json_path.write_text(json.dumps(out))


def parse_lef_pins() -> list[dict]:
    import re
    txt = LEF_PATH.read_text()
    pins = []
    for m in re.finditer(r"PIN\s+(\S+)\s+(.*?)END\s+\1", txt, re.S):
        name, body = m.group(1), m.group(2)
        rm = re.search(r"LAYER\s+(\w+)\s*;\s*RECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", body)
        if rm:
            pins.append({"name": name, "layer": rm.group(1), "rect": list(map(float, rm.groups()[1:]))})
    return pins


def render_all(data: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Patch, Rectangle
    from matplotlib.backends.backend_pdf import PdfPages

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    RES_PDF_DIR.mkdir(parents=True, exist_ok=True)

    # Clean, high-contrast light-background IHP layer palette
    STYLE = {
        "prBoundary": {"fc": "none",    "ec": "#222222", "lw": 1.0, "ls": "--", "a": 1.0, "label": "prBoundary"},
        "NWell":      {"fc": "#FFF2B2", "ec": "#C99A00", "lw": 0.45,"ls": "-",  "a": 0.45, "label": "NWell (31/0)"},
        "TGO":        {"fc": "#FCE4EC", "ec": "#C2185B", "lw": 0.7, "ls": "-.", "a": 0.35, "label": "ThickGateOx (HV)"},
        "SalBlock":   {"fc": "#E8F5E9", "ec": "#2E7D32", "lw": 0.5, "ls": ":",  "a": 0.40, "label": "SalBlock (rppd)"},
        "Activ":      {"fc": "#81C784", "ec": "#1B5E20", "lw": 0.30,"ls": "-",  "a": 0.70, "label": "Activ (1/0)"},
        "GatPoly":    {"fc": "#E57373", "ec": "#B71C1C", "lw": 0.30,"ls": "-",  "a": 0.75, "label": "GatPoly (5/0)"},
        "Cont":       {"fc": "#424242", "ec": "none",    "lw": 0.0, "ls": "-",  "a": 0.85, "label": None},
        "Metal1":     {"fc": "#4FC3F7", "ec": "#0277BD", "lw": 0.25,"ls": "-",  "a": 0.55, "label": "Metal1 (8/0)"},
        "Via1":       {"fc": "#1565C0", "ec": "none",    "lw": 0.0, "ls": "-",  "a": 0.85, "label": None},
        "Metal2":     {"fc": "#9575CD", "ec": "#4527A0", "lw": 0.28,"ls": "-",  "a": 0.55, "label": "Metal2 (10/0)"},
        "Via2":       {"fc": "#4527A0", "ec": "none",    "lw": 0.0, "ls": "-",  "a": 0.85, "label": None},
        "Metal3":     {"fc": "#FFB74D", "ec": "#E65100", "lw": 0.30,"ls": "-",  "a": 0.65, "label": "Metal3 (30/0)"},
        "Via3":       {"fc": "#E65100", "ec": "none",    "lw": 0.0, "ls": "-",  "a": 0.90, "label": None},
        "Metal4":     {"fc": "#F06292", "ec": "#880E4F", "lw": 0.40,"ls": "-",  "a": 0.68, "label": "Metal4 (50/0)"},
    }

    top_bb = data["rpe_clk_analog"]["bbox"]
    top_w, top_h = top_bb[2] - top_bb[0], top_bb[3] - top_bb[1]
    CELL_TITLES = {
        "rpe_clk_analog": f"rpe_clk_analog — Unified Analog Clock Macro ({top_w:.1f} × {top_h:.1f} µm = {top_w*top_h:,.1f} µm²)",
        "bias_lay": "bias_lay — Shared 0.5 µA PtP Self-Biased Bandgap-less Core + Startup",
        "idac_8b_lay": "idac_8b_lay — 8-Bit Segmented Thermometer + Binary Current DAC (48:15:248)",
        "cco_core_lay": "cco_core_lay — 5-Stage CMOM-Loaded Current-Controlled Ring Core",
        "comp_lay": "comp_lay — Low-Power 2-Stage Continuous-Time Comparator",
        "relax_core_lay": "relax_core_lay — Dual-Slope HV SVaricap + RPPD Relaxation Oscillator",
    }

    lef_pins = parse_lef_pins()

    def draw_cell(ax, cname: str, show_contacts: bool = True, annotate_top: bool = False, show_legend: bool = False):
        cinfo = data[cname]
        bx1, by1, bx2, by2 = cinfo["bbox"]
        for lname, _ in LAYERS:
            if not show_contacts and lname in ("Cont", "Via1", "Via2", "Via3"):
                continue
            polys = cinfo["layers"].get(lname, [])
            if not polys:
                continue
            st = STYLE[lname]
            pc = PolyCollection(
                polys,
                facecolors=st["fc"],
                edgecolors=st["ec"],
                linewidths=st["lw"] if st["ec"] != "none" else 0.0,
                linestyles=st["ls"],
                alpha=st["a"],
                zorder=LAYERS.index((lname, next(ld for n, ld in LAYERS if n == lname))),
            )
            ax.add_collection(pc)

        w = bx2 - bx1
        h = by2 - by1
        pad_x = 0.11 * w if annotate_top else 0.03 * w
        pad_y = 0.05 * h if annotate_top else 0.04 * h
        ax.set_xlim(bx1 - pad_x, bx2 + pad_x)
        ax.set_ylim(by1 - pad_y, by2 + pad_y)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("X (µm)", fontsize=8)
        ax.set_ylabel("Y (µm)", fontsize=8)
        ax.tick_params(labelsize=7.5)
        ax.set_facecolor("#FAFAFA")

        if annotate_top and cname == "rpe_clk_analog":
            sub_boxes: dict[str, list[float]] = {}
            for s in cinfo["subs"]:
                sx1, sy1, sx2, sy2 = s["box"]
                sub_boxes[s["name"]] = [sx1, sy1, sx2, sy2]
                ax.add_patch(Rectangle((sx1, sy1), sx2 - sx1, sy2 - sy1, fill=False, ec="#111111", lw=0.85, ls="--", zorder=20))
                lbl = f"{s['name']}\n({sx2 - sx1:.1f}×{sy2 - sy1:.1f} µm)"
                ax.text(
                    sx2 - 1.2, sy2 - 1.2, lbl, fontsize=7.5, fontweight="bold", ha="right", va="top", color="#111111",
                    bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#333333", alpha=0.88, lw=0.6), zorder=25,
                )
            # Callout for en_or & HV region computed from compacted subblock placements
            bb_bias = sub_boxes.get("bias_lay", [63.5, 8.2, 105.0, 33.4])
            bb_rel = sub_boxes.get("relax_core_lay", [70.5, 56.0, 164.0, 118.5])
            ax.text(bb_bias[0] + 5.5, bb_bias[3] + 8.5, "en_or\n(NOR2+INV)", fontsize=7, ha="center", va="bottom", color="#111111",
                    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#666666", alpha=0.88, lw=0.5), zorder=25)
            ax.text(bb_rel[0] + 0.72 * (bb_rel[2] - bb_rel[0]), bb_rel[1] + 2.5, "HV 3.3V Zone\n(SVaricap + nmosHV)", fontsize=6.8, ha="center", va="bottom", color="#880E4F",
                    bbox=dict(boxstyle="round,pad=0.18", fc="#FFF0F5", ec="#C2185B", alpha=0.90, lw=0.5), zorder=25)

            # Label all 14 pins cleanly using dynamic bbox coordinates
            west_pins = sorted([p for p in lef_pins if p["rect"][0] < bx1 + 10.0 and p["layer"] == "Metal3"], key=lambda p: p["rect"][1])
            n_wp = len(west_pins)
            y_lo = max(14.0, by1 + 0.10 * h)
            y_hi = by2 - 0.10 * h
            y_slots = [y_lo + i * ((y_hi - y_lo) / max(1, n_wp - 1)) for i in range(n_wp)]
            for idx, p in enumerate(west_pins):
                x1, y1, x2, y2 = p["rect"]
                cy = 0.5 * (y1 + y2)
                ax.annotate(
                    p["name"], xy=(x1, cy), xytext=(bx1 - 3.5, y_slots[idx]),
                    fontsize=6.8, fontweight="bold", ha="right", va="center", color="#E65100",
                    arrowprops=dict(arrowstyle="-", color="#E65100", lw=0.55), zorder=26,
                )
            for p in lef_pins:
                x1, y1, x2, y2 = p["rect"]
                cy = 0.5 * (y1 + y2)
                if p["name"] in ("VDD", "VSS"):
                    ax.annotate(
                        p["name"], xy=(x1, cy), xytext=(bx1 - 3.5, by1 + 1.5 if p["name"] == "VSS" else by1 + 8.5),
                        fontsize=7.2, fontweight="bold", ha="right", va="center", color="#880E4F",
                        arrowprops=dict(arrowstyle="->", color="#880E4F", lw=0.7), zorder=26,
                    )
                elif x2 > bx2 - 12.0:
                    ax.annotate(
                        p["name"], xy=(x2, cy), xytext=(bx2 + 3.5, cy),
                        fontsize=7.2, fontweight="bold", ha="left", va="center", color="#E65100",
                        arrowprops=dict(arrowstyle="->", color="#E65100", lw=0.7), zorder=26,
                    )

        # Scale bar in bottom-right inside axes
        sb_len = 25.0 if w > 120 else (10.0 if w > 40 else 5.0)
        sb_x2 = bx2 - 0.04 * w
        sb_x1 = sb_x2 - sb_len
        sb_y = by1 + 0.03 * h
        ax.plot([sb_x1, sb_x2], [sb_y, sb_y], color="#111111", lw=2.0, zorder=30)
        ax.text(0.5 * (sb_x1 + sb_x2), sb_y + 0.015 * h, f"{sb_len:.0f} µm", fontsize=7.5, fontweight="bold",
                ha="center", va="bottom", bbox=dict(fc="white", ec="none", alpha=0.8, pad=0.1), zorder=30)

        if show_legend:
            handles = []
            for lname, _ in LAYERS:
                st = STYLE[lname]
                if st["label"] and cinfo["layers"].get(lname):
                    handles.append(Patch(facecolor="none" if st["fc"] == "none" else st["fc"], edgecolor=st["ec"], lw=0.8, label=st["label"]))
            ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7.2, frameon=True, title="SG13CMOS5L Layers", title_fontsize=7.5)

    # 1. Combined 6-page vector PDF booklet: analog/results/layouts.pdf
    booklet_path = RES_DIR / "layouts.pdf"
    with PdfPages(booklet_path) as pdf:
        for cname in CELLS:
            fig, ax = plt.subplots(figsize=(11.0, 7.5))
            draw_cell(ax, cname, show_contacts=(cname != "rpe_clk_analog"), annotate_top=(cname == "rpe_clk_analog"), show_legend=True)
            bb = data[cname]["bbox"]
            sub_info = f"{bb[2]-bb[0]:.1f} × {bb[3]-bb[1]:.1f} µm"
            ax.set_title(CELL_TITLES.get(cname, f"{cname} ({sub_info})"), fontsize=10.5, fontweight="bold", pad=8)
            fig.tight_layout()
            pdf.savefig(fig)
            # Also save individual vector PDF
            fig.savefig(RES_PDF_DIR / f"layout_{cname}.pdf")
            if cname == "rpe_clk_analog":
                fig.savefig(FIG_DIR / "fig_layout_full.png", dpi=300)
            plt.close(fig)

    # 2. 2x2 Subblock Zoom Panel: fig_layout_zooms.png (300 DPI)
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 9.2))
    zoom_specs = [
        ("bias_lay", "(a) bias_lay (0.5 µA Self-Bias + RPPD)"),
        ("idac_8b_lay", "(b) idac_8b_lay (L-NWell + 18-Cell Thermo Decode)"),
        ("cco_core_lay", "(c) cco_core_lay (5-Stage CCO + cap_cmomf Array)"),
        ("relax_core_lay", "(d) relax_core_lay (4×RPPD + HV SVaricap/nmosHV + 2×comp)"),
    ]
    for ax, (cname, title) in zip(axes.flat, zoom_specs):
        draw_cell(ax, cname, show_contacts=False, annotate_top=False, show_legend=False)
        ax.set_title(title, fontsize=9.2, fontweight="bold")
    handles = [
        Patch(facecolor=STYLE[ln]["fc"], edgecolor=STYLE[ln]["ec"], lw=0.7, label=STYLE[ln]["label"])
        for ln, _ in LAYERS if STYLE[ln]["label"]
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=7.5, frameon=True, bbox_to_anchor=(0.5, 0.005))
    fig.tight_layout(rect=[0.0, 0.06, 1.0, 1.0])
    fig.savefig(FIG_DIR / "fig_layout_zooms.png", dpi=300)
    plt.close(fig)
    print(f"Wrote {booklet_path}, 6 individual layout_*.pdf, fig_layout_full.png, and fig_layout_zooms.png")


def main() -> None:
    json_path = FIG_DIR / "_gds_dump.json"
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get("KLAYOUT_DUMP") == "1":
        klayout_dump(json_path)
        return
    # Step A: dump flattened GDS polygons via KLayout
    env = dict(os.environ, KLAYOUT_DUMP="1")
    subprocess.run([KLAYOUT, "-zz", "-r", str(Path(__file__).resolve())], env=env, check=True)
    data = json.loads(json_path.read_text())
    json_path.unlink(missing_ok=True)
    render_all(data)


if __name__ == "__main__":
    main()
