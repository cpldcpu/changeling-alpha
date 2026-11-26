#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Reusable DRC-aware KLayout layout primitives for IHP SG13CMOS5L custom analog blocks."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

import pya as db

PDK_DIR = Path("/home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008/ihp-sg13cmos5l")
STDCELL_GDS = PDK_DIR / "libs.ref" / "sg13cmos5l_stdcell" / "gds" / "sg13cmos5l_stdcell.gds"
STDCELL_LEF = PDK_DIR / "libs.ref" / "sg13cmos5l_stdcell" / "lef" / "sg13cmos5l_stdcell.lef"

# GDS layer/datatype tuples (SG13CMOS5L)
L_ACTIV = (1, 0)
L_GATPOLY = (5, 0)
L_CONT = (6, 0)
L_NSD = (7, 0)
L_M1 = (8, 0)
L_M1_PIN = (8, 2)
L_M1_TXT = (8, 25)
L_M2 = (10, 0)
L_M2_PIN = (10, 2)
L_M2_TXT = (10, 25)
L_PSD = (14, 0)
L_VIA1 = (19, 0)
L_SALBLOCK = (28, 0)
L_VIA2 = (29, 0)
L_M3 = (30, 0)
L_M3_PIN = (30, 2)
L_M3_TXT = (30, 25)
L_NWELL = (31, 0)
L_TGO = (44, 0)
L_VIA3 = (49, 0)
L_M4 = (50, 0)
L_M4_PIN = (50, 2)
L_M4_TXT = (50, 25)
L_PRBND = (189, 4)

STDCELL_H = 3.78
RAIL_H = 0.44  # VDD centered at y=3.78 (3.56..4.00), VSS centered at y=0 (-0.22..0.22)


def q5(val_um: float) -> int:
    """Snap micron coordinate to 5 nm grid and return database units (1 dbu = 1 nm)."""
    return int(round(val_um * 200.0)) * 5


def to_um(dbu_val: int) -> float:
    return dbu_val * 0.001


@dataclass
class BoxU:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return round(0.5 * (self.x1 + self.x2), 4)

    @property
    def cy(self) -> float:
        return round(0.5 * (self.y1 + self.y2), 4)

    @property
    def w(self) -> float:
        return round(self.x2 - self.x1, 4)

    @property
    def h(self) -> float:
        return round(self.y2 - self.y1, 4)


@dataclass
class FetPins:
    S: BoxU
    D: BoxU
    G: BoxU
    bbox: BoxU
    all_S: List[BoxU]
    all_D: List[BoxU]
    all_G: List[BoxU]


def _parse_stdcell_lef() -> Dict[str, Tuple[float, float, Dict[str, Tuple[BoxU, Tuple[float, float]]]]]:
    """Return {cell_name: (w, h, {pin_name: (best_rect, (via_cx, via_cy))})}."""
    txt = STDCELL_LEF.read_text()
    out: Dict[str, Tuple[float, float, Dict[str, Tuple[BoxU, Tuple[float, float]]]]] = {}
    for m in re.finditer(r"MACRO\s+(sg13cmos5l_\S+)\s*(.*?)END\s+\1", txt, re.S):
        name, body = m.group(1), m.group(2)
        sz = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", body)
        if not sz:
            continue
        w, h = float(sz.group(1)), float(sz.group(2))
        pins: Dict[str, Tuple[BoxU, Tuple[float, float]]] = {}
        for pm in re.finditer(r"PIN\s+(\w+).*?LAYER\s+Metal1\s*;(.*?)END\s+\1", body, re.S):
            pname, pbody = pm.group(1), pm.group(2)
            rects = [BoxU(*map(float, r.groups())) for r in re.finditer(r"RECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", pbody)]
            if not rects:
                continue
            if pname in ("Y", "X"):
                # Place output via near top of output bar (>= 2.1 um) so M2 pad clears inputs at y~1.7 um
                top_rects = [r for r in rects if r.y2 >= 2.2]
                best = max(top_rects, key=lambda r: (r.y2, r.w * r.h)) if top_rects else max(rects, key=lambda r: r.w * r.h)
                vy = min(best.y2 - 0.24, max(best.cy, 2.65)) if best.y2 >= 2.6 else best.cy
                pins[pname] = (best, (best.cx, round(vy, 4)))
            else:
                best = max(rects, key=lambda r: r.w * r.h)
                pins[pname] = (best, (best.cx, best.cy))
        out[name] = (w, h, pins)
    return out


def std_pin_pad(pin_box: BoxU) -> Tuple[float, float]:
    """Return DRC-safe M1 via pad (pw, ph) fitting inside a stdcell pin rectangle."""
    if pin_box.w >= 0.34 and pin_box.h >= 0.34:
        return (0.32, 0.32)
    return (0.22, 0.30) if pin_box.h >= pin_box.w else (0.30, 0.22)


class LayoutBuilder:
    def __init__(self) -> None:
        self.ly = db.Layout()
        self.ly.dbu = 0.001
        self.ly.technology_name = "sg13cmos5l"

        self._layers: Dict[Tuple[int, int], int] = {}
        self._std_cache: Dict[str, db.Cell] = {}
        self._std_lef = _parse_stdcell_lef()
        self._std_src = db.Layout()
        self._std_src.read(str(STDCELL_GDS))
        self._pcell_cache: Dict[Tuple[str, Tuple[Tuple[str, object], ...]], Tuple[db.Cell, dict]] = {}

    def layer(self, ld: Tuple[int, int]) -> int:
        if ld not in self._layers:
            self._layers[ld] = self.ly.layer(ld[0], ld[1])
        return self._layers[ld]

    def rect(self, cell: db.Cell, ld: Tuple[int, int], x1: float, y1: float, x2: float, y2: float) -> BoxU:
        a, b = q5(min(x1, x2)), q5(min(y1, y2))
        c, d = q5(max(x1, x2)), q5(max(y1, y2))
        if c > a and d > b:
            cell.shapes(self.layer(ld)).insert(db.Box(a, b, c, d))
        return BoxU(to_um(a), to_um(b), to_um(c), to_um(d))

    def label(self, cell: db.Cell, ld: Tuple[int, int], text: str, x: float, y: float) -> None:
        cell.shapes(self.layer(ld)).insert(db.Text(text, db.Trans(q5(x), q5(y))))

    def pin_rect_label(self, cell: db.Cell, metal: int, name: str, x1: float, y1: float, x2: float, y2: float) -> BoxU:
        m_map = {1: (L_M1, L_M1_PIN, L_M1_TXT), 2: (L_M2, L_M2_PIN, L_M2_TXT), 3: (L_M3, L_M3_PIN, L_M3_TXT), 4: (L_M4, L_M4_PIN, L_M4_TXT)}
        l_drw, l_pin, l_txt = m_map[metal]
        box = self.rect(cell, l_drw, x1, y1, x2, y2)
        self.rect(cell, l_pin, x1, y1, x2, y2)
        self.label(cell, l_txt, name, box.cx, box.cy)
        return box

    def wire(self, cell: db.Cell, ld: Tuple[int, int], pts: List[Tuple[float, float]], w: float = 0.24) -> None:
        """Draw flush Manhattan segments connecting pts in sequence."""
        hw = 0.5 * w
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            x1q, y1q = to_um(q5(x1)), to_um(q5(y1))
            x2q, y2q = to_um(q5(x2)), to_um(q5(y2))
            if abs(x1q - x2q) < 1e-4 and abs(y1q - y2q) < 1e-4:
                continue
            if abs(y1q - y2q) < 1e-4:
                self.rect(cell, ld, min(x1q, x2q) - hw, y1q - hw, max(x1q, x2q) + hw, y1q + hw)
            elif abs(x1q - x2q) < 1e-4:
                self.rect(cell, ld, x1q - hw, min(y1q, y2q) - hw, x1q + hw, max(y1q, y2q) + hw)
            else:
                # L-bend horizontal then vertical
                self.rect(cell, ld, min(x1q, x2q) - hw, y1q - hw, max(x1q, x2q) + hw, y1q + hw)
                self.rect(cell, ld, x2q - hw, min(y1q, y2q) - hw, x2q + hw, max(y1q, y2q) + hw)

    def via(
        self,
        cell: db.Cell,
        x: float,
        y: float,
        lvl: int,
        pad_m1: Optional[Tuple[float, float]] = None,
        pad_m2: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Drop a single DRC-clean via cut: lvl=1 (M1-M2), 2 (M2-M3), 3 (M3-M4).
        Default metal pads are 0.32x0.32 on M1 (area=0.1024 > 0.09) and 0.40x0.40 on M2/M3/M4 (area=0.16 > 0.144).
        """
        cx, cy = to_um(q5(x)), to_um(q5(y))
        v_map = {1: (L_M1, L_VIA1, L_M2), 2: (L_M2, L_VIA2, L_M3), 3: (L_M3, L_VIA3, L_M4)}
        lm_bot, lv, lm_top = v_map[lvl]
        self.rect(cell, lv, cx - 0.095, cy - 0.095, cx + 0.095, cy + 0.095)
        if lvl == 1:
            pw1, ph1 = pad_m1 if pad_m1 is not None else (0.32, 0.32)
            self.rect(cell, lm_bot, cx - 0.5 * pw1, cy - 0.5 * ph1, cx + 0.5 * pw1, cy + 0.5 * ph1)
            pw2, ph2 = pad_m2 if pad_m2 is not None else (0.40, 0.40)
            self.rect(cell, lm_top, cx - 0.5 * pw2, cy - 0.5 * ph2, cx + 0.5 * pw2, cy + 0.5 * ph2)
        elif lvl == 2:
            pw2, ph2 = pad_m2 if pad_m2 is not None else (0.40, 0.40)
            self.rect(cell, lm_bot, cx - 0.5 * pw2, cy - 0.5 * ph2, cx + 0.5 * pw2, cy + 0.5 * ph2)
            self.rect(cell, lm_top, cx - 0.20, cy - 0.20, cx + 0.20, cy + 0.20)
        else:
            self.rect(cell, lm_bot, cx - 0.20, cy - 0.20, cx + 0.20, cy + 0.20)
            self.rect(cell, lm_top, cx - 0.20, cy - 0.20, cx + 0.20, cy + 0.20)

    def via_stack(
        self,
        cell: db.Cell,
        x: float,
        y: float,
        m_bot: int,
        m_top: int,
        pad_m1: Optional[Tuple[float, float]] = None,
        pad_m2: Optional[Tuple[float, float]] = None,
    ) -> None:
        for lv in range(m_bot, m_top):
            self.via(cell, x, y, lv, pad_m1=pad_m1, pad_m2=pad_m2)

    def cont_poly(self, cell: db.Cell, cx: float, cy: float, m_top: int = 1) -> Tuple[float, float]:
        """Place a GatPoly contact at (cx, cy) with 0.36x0.36 poly pad and 0.32x0.32 M1 pad."""
        qx, qy = to_um(q5(cx)), to_um(q5(cy))
        self.rect(cell, L_CONT, qx - 0.08, qy - 0.08, qx + 0.08, qy + 0.08)
        self.rect(cell, L_GATPOLY, qx - 0.18, qy - 0.18, qx + 0.18, qy + 0.18)
        self.rect(cell, L_M1, qx - 0.16, qy - 0.16, qx + 0.16, qy + 0.16)
        if m_top > 1:
            self.via_stack(cell, qx, qy, 1, m_top)
        return (qx, qy)

    def _get_pcell(self, pcell_name: str, params: dict) -> Tuple[db.Cell, dict]:
        key = (pcell_name, tuple(sorted((k, str(v)) for k, v in params.items())))
        if key in self._pcell_cache:
            return self._pcell_cache[key]
        pc = self.ly.create_cell(pcell_name, "SG13_dev", params)
        info = {
            "bbox": self._reg_bbox(pc, None),
            "m1": self._sorted_rects(pc, L_M1),
            "gp": self._sorted_rects(pc, L_GATPOLY),
            "act": self._sorted_rects(pc, L_ACTIV),
            "nw": self._reg_bbox(pc, L_NWELL),
            "tgo": self._reg_bbox(pc, L_TGO),
            "m4_pin": self._sorted_rects(pc, L_M4_PIN),
            "m1_pin": self._sorted_rects(pc, L_M1_PIN),
        }
        self._pcell_cache[key] = (pc, info)
        return pc, info

    def _reg_bbox(self, cell: db.Cell, ld: Optional[Tuple[int, int]]) -> Optional[BoxU]:
        if ld is None:
            bb = cell.bbox().to_dtype(self.ly.dbu)
            return BoxU(bb.left, bb.bottom, bb.right, bb.top)
        r = db.Region(cell.begin_shapes_rec(self.layer(ld)))
        if r.is_empty():
            return None
        bb = r.bbox().to_dtype(self.ly.dbu)
        return BoxU(bb.left, bb.bottom, bb.right, bb.top)

    def _sorted_rects(self, cell: db.Cell, ld: Tuple[int, int]) -> List[BoxU]:
        r = db.Region(cell.begin_shapes_rec(self.layer(ld))).merged()
        boxes = [sh.bbox().to_dtype(self.ly.dbu) for sh in r.each()]
        return sorted([BoxU(b.left, b.bottom, b.right, b.top) for b in boxes], key=lambda b: (b.x1, b.y1))

    def _xform_box(self, b: BoxU, x: float, y: float, rot: int = 0) -> BoxU:
        pts = [(b.x1, b.y1), (b.x2, b.y2)]
        xpts = []
        for px, py in pts:
            if rot == 90:
                rx, ry = -py, px
            elif rot == 180:
                rx, ry = -px, -py
            elif rot == 270:
                rx, ry = py, -px
            else:
                rx, ry = px, py
            xpts.append((x + rx, y + ry))
        return BoxU(min(xpts[0][0], xpts[1][0]), min(xpts[0][1], xpts[1][1]), max(xpts[0][0], xpts[1][0]), max(xpts[0][1], xpts[1][1]))

    def place_fet_unit(self, parent: db.Cell, kind: str, x: float, y: float, w_um: float, l_um: float, rot: int = 0) -> FetPins:
        qx, qy = to_um(q5(x)), to_um(q5(y))
        pc, info = self._get_pcell(kind, {"w": w_um * 1e-6, "l": l_um * 1e-6, "ng": 1})
        angle = {0: db.Trans.R0, 90: db.Trans.R90, 180: db.Trans.R180, 270: db.Trans.R270}[rot]
        parent.insert(db.CellInstArray(pc.cell_index(), db.Trans(angle, q5(qx), q5(qy))))
        m1s = [self._xform_box(b, qx, qy, rot) for b in info["m1"]]
        gps = [self._xform_box(b, qx, qy, rot) for b in info["gp"]]
        bb = self._xform_box(info["bbox"], qx, qy, rot)
        s_box = m1s[0]
        d_box = m1s[-1]
        g_box = gps[0]
        return FetPins(S=s_box, D=d_box, G=g_box, bbox=bb, all_S=[s_box], all_D=[d_box], all_G=[g_box])

    def place_fet_array(
        self,
        parent: db.Cell,
        kind: str,
        x: float,
        y: float,
        w_um: float,
        l_um: float,
        m_count: int,
        cols: int = 1,
        dy_um: Optional[float] = None,
        dx_um: Optional[float] = None,
        gate_side: str = "bot",
    ) -> FetPins:
        """Place m_count parallel unit ng=1 FETs in cols columns, connecting S, D, and G cleanly."""
        if dy_um is None:
            dy_um = round(max(1.16, w_um + 0.68), 3)
        if dx_um is None:
            dx_um = round(l_um + 2.20, 3)

        rows_per_col = (m_count + cols - 1) // cols
        all_s: List[BoxU] = []
        all_d: List[BoxU] = []
        all_g: List[BoxU] = []
        placed = 0
        minx, miny, maxx, maxy = 1e9, 1e9, -1e9, -1e9

        col_s_x: Dict[int, float] = {}
        col_d_x: Dict[int, float] = {}
        col_g_x: Dict[int, float] = {}

        for c in range(cols):
            cx_off = x + c * dx_um
            c_s, c_d, c_g = [], [], []
            for r in range(rows_per_col):
                if placed >= m_count:
                    break
                ry = y + r * dy_um
                fp = self.place_fet_unit(parent, kind, cx_off, ry, w_um, l_um, rot=0)
                c_s.append(fp.S)
                c_d.append(fp.D)
                c_g.append(fp.G)
                all_s.append(fp.S)
                all_d.append(fp.D)
                all_g.append(fp.G)
                minx, miny = min(minx, fp.bbox.x1), min(miny, fp.bbox.y1)
                maxx, maxy = max(maxx, fp.bbox.x2), max(maxy, fp.bbox.y2)
                placed += 1

            # Strap each column's S vertically in M1, D vertically in M1 (safe: outside GatPoly)
            if c_s:
                sx = c_s[0].cx
                dx = c_d[0].cx
                gx = c_g[0].cx
                col_s_x[c], col_d_x[c], col_g_x[c] = sx, dx, gx
                if len(c_s) > 1:
                    self.wire(parent, L_M1, [(sx, c_s[0].y1), (sx, c_s[-1].y2)], w=0.22)
                    self.wire(parent, L_M1, [(dx, c_d[0].y1), (dx, c_d[-1].y2)], w=0.22)
                # Strap GatPoly vertically at exact gate length l_um to avoid any Gat.b notch
                if len(c_g) > 1:
                    self.rect(parent, L_GATPOLY, gx - 0.5 * l_um, c_g[0].y1, gx + 0.5 * l_um, c_g[-1].y2)

        # Gate contact at bottom (or top) of each column with >=0.22um clearance from gate endcap (Gat.b=0.18)
        y_g_bot = min(g.y1 for g in all_g)
        y_g_top = max(g.y2 for g in all_g)
        gy_c = round(y_g_bot - 0.40, 3) if gate_side == "bot" else round(y_g_top + 0.40, 3)
        neck_w = 0.36 if l_um >= 0.36 else l_um
        g_pts = []
        for c, gx in col_g_x.items():
            col_gs = [g for g in all_g if abs(g.cx - gx) < 0.1]
            if gate_side == "bot":
                y_bot_col = min(g.y1 for g in col_gs)
                self.rect(parent, L_GATPOLY, gx - 0.5 * neck_w, gy_c, gx + 0.5 * neck_w, y_bot_col + 0.05)
            else:
                y_top_col = max(g.y2 for g in col_gs)
                self.rect(parent, L_GATPOLY, gx - 0.5 * neck_w, y_top_col - 0.05, gx + 0.5 * neck_w, gy_c)
            self.cont_poly(parent, gx, gy_c, m_top=2 if cols > 1 else 1)
            g_pts.append((gx, gy_c))
        if cols > 1:
            self.wire(parent, L_M2, [(g_pts[0][0], gy_c), (g_pts[-1][0], gy_c)], w=0.24)
            # Bridge all column S rails on M2 at top, and all column D rails on M2 above S bus
            sy_bus = maxy + 0.50
            dy_bus = maxy + 1.25
            for c in col_s_x:
                sx, dx = col_s_x[c], col_d_x[c]
                y_s_top = max(s.y2 for s in all_s if abs(s.cx - sx) < 0.1)
                y_d_top = max(d.y2 for d in all_d if abs(d.cx - dx) < 0.1)
                self.wire(parent, L_M1, [(sx, y_s_top - 0.1), (sx, sy_bus)], w=0.24)
                self.via_stack(parent, sx, sy_bus, 1, 2)
                self.wire(parent, L_M1, [(dx, y_d_top - 0.1), (dx, dy_bus)], w=0.24)
                self.via_stack(parent, dx, dy_bus, 1, 2)
            self.wire(parent, L_M2, [(col_s_x[0], sy_bus), (col_s_x[cols - 1], sy_bus)], w=0.30)
            self.wire(parent, L_M2, [(col_d_x[0], dy_bus), (col_d_x[cols - 1], dy_bus)], w=0.30)
            s_ret = BoxU(col_s_x[0] - 0.15, sy_bus - 0.15, col_s_x[0] + 0.15, sy_bus + 0.15)
            d_ret = BoxU(col_d_x[0] - 0.15, dy_bus - 0.15, col_d_x[0] + 0.15, dy_bus + 0.15)
            bb_maxy = max(maxy, dy_bus + 0.25)
        else:
            s_ret = BoxU(min(s.x1 for s in all_s), min(s.y1 for s in all_s), max(s.x2 for s in all_s), max(s.y2 for s in all_s))
            d_ret = BoxU(min(d.x1 for d in all_d), min(d.y1 for d in all_d), max(d.x2 for d in all_d), max(d.y2 for d in all_d))
            bb_maxy = max(maxy, gy_c + 0.22)

        g_ret = BoxU(g_pts[0][0] - 0.16, gy_c - 0.16, g_pts[0][0] + 0.16, gy_c + 0.16)
        return FetPins(S=s_ret, D=d_ret, G=g_ret, bbox=BoxU(minx, min(miny, gy_c - 0.22), maxx, bb_maxy), all_S=all_s, all_D=all_d, all_G=all_g)

    def place_rppd(self, parent: db.Cell, x: float, y: float, w_um: float, l_um: float, bends: int) -> Tuple[BoxU, BoxU, BoxU]:
        qx, qy = to_um(q5(x)), to_um(q5(y))
        pc, info = self._get_pcell("rppd", {"w": w_um * 1e-6, "l": l_um * 1e-6, "b": bends})
        parent.insert(db.CellInstArray(pc.cell_index(), db.Trans(db.Trans.R0, q5(qx), q5(qy))))
        m1s = [self._xform_box(b, qx, qy, 0) for b in info["m1"]]
        bb = self._xform_box(info["bbox"], qx, qy, 0)
        return m1s[0], m1s[-1], bb

    def place_svaricap(self, parent: db.Cell, x: float, y: float, w_str: str = "9.74u", l_str: str = "0.8u", nx: int = 9) -> Tuple[BoxU, BoxU, BoxU, BoxU]:
        """Return (G1_box, G2_box, W_box, bbox)."""
        qx, qy = to_um(q5(x)), to_um(q5(y))
        pc, info = self._get_pcell("SVaricap", {"w": w_str, "l": l_str, "Nx": nx})
        parent.insert(db.CellInstArray(pc.cell_index(), db.Trans(db.Trans.R0, q5(qx), q5(qy))))
        pins = [self._xform_box(b, qx, qy, 0) for b in info["m1_pin"]]
        # G1: bottom long bar, G2: top long bar, W: left bar
        pins_by_y = sorted(pins, key=lambda b: b.cy)
        g1 = pins_by_y[0]
        w_pin = pins_by_y[1]
        g2 = pins_by_y[2]
        bb = self._xform_box(info["bbox"], qx, qy, 0)
        return g1, g2, w_pin, bb

    def place_cmomf(self, parent: db.Cell, x: float, y: float, size_um: float = 3.6) -> Tuple[BoxU, BoxU, BoxU]:
        """Return (PLUS_m4, MINUS_m4, bbox)."""
        qx, qy = to_um(q5(x)), to_um(q5(y))
        pc, info = self._get_pcell("cap_cmomf", {"w": size_um * 1e-6, "l": size_um * 1e-6, "mmin": 1, "mmax": 4, "subblock": 0})
        parent.insert(db.CellInstArray(pc.cell_index(), db.Trans(db.Trans.R0, q5(qx), q5(qy))))
        pins = sorted([self._xform_box(b, qx, qy, 0) for b in info["m4_pin"]], key=lambda b: b.cx)
        # Left edge is PLUS (c0), top edge is MINUS (c1)
        plus_p, minus_p = pins[0], pins[1]
        bb = self._xform_box(info["bbox"], qx, qy, 0)
        return plus_p, minus_p, bb

    def place_tap(self, parent: db.Cell, kind: str, x: float, y: float, w_um: float = 0.78, l_um: float = 0.78) -> BoxU:
        qx, qy = to_um(q5(x)), to_um(q5(y))
        pc, info = self._get_pcell(kind, {"w": w_um * 1e-6, "l": l_um * 1e-6})
        parent.insert(db.CellInstArray(pc.cell_index(), db.Trans(db.Trans.R0, q5(qx), q5(qy))))
        m1 = self._xform_box(info["m1"][0], qx, qy, 0)
        return m1

    def _get_stdcell_stripped(self, cell_name: str) -> db.Cell:
        if cell_name in self._std_cache:
            return self._std_cache[cell_name]
        src_cell = self._std_src.cell(cell_name)
        assert src_cell is not None, f"Missing stdcell {cell_name}"
        dst = self.ly.create_cell(f"std_{cell_name}")
        skip = {L_M1_PIN, L_M1_TXT}
        for li in self._std_src.layer_infos():
            if (li.layer, li.datatype) in skip:
                continue
            s_idx = self._std_src.layer(li)
            d_idx = self.layer((li.layer, li.datatype))
            it = src_cell.begin_shapes_rec(s_idx)
            while not it.at_end():
                sh = it.shape()
                if not sh.is_text():
                    if sh.is_polygon():
                        dst.shapes(d_idx).insert(sh.polygon.transformed(it.trans()))
                    elif sh.is_path():
                        dst.shapes(d_idx).insert(sh.path.transformed(it.trans()))
                    elif sh.is_box():
                        dst.shapes(d_idx).insert(sh.box.transformed(it.trans()))
                it.next()
        self._std_cache[cell_name] = dst
        return dst

    def place_stdcell(self, parent: db.Cell, cell_name: str, x: float, y: float) -> Tuple[float, Dict[str, Tuple[float, float, BoxU]]]:
        """Place stdcell at (x, y) and return (cell_width, {pin_name: (via_x, via_y, abs_BoxU)})."""
        qx, qy = to_um(q5(x)), to_um(q5(y))
        sc = self._get_stdcell_stripped(cell_name)
        w, _, raw_pins = self._std_lef[cell_name]
        parent.insert(db.CellInstArray(sc.cell_index(), db.Trans(db.Trans.R0, q5(qx), q5(qy))))
        pins = {
            k: (round(qx + vx, 4), round(qy + vy, 4), BoxU(qx + b.x1, qy + b.y1, qx + b.x2, qy + b.y2))
            for k, (b, (vx, vy)) in raw_pins.items()
        }
        return w, pins

    def escape_stdcell_pins(
        self,
        parent: db.Cell,
        cell_name: str,
        x_cell: float,
        pdict: Dict[str, Tuple[float, float, BoxU]],
        gut: float = 0.48,
    ) -> Dict[str, Tuple[float, float, int]]:
        """Escape stdcell signal pins to collision-free M3 points inside cell's own left/right gutters.
        Prevents NetRouter from ever drawing horizontal M2 jogs across adjacent stdcell pins.
        """
        w, _, _ = self._std_lef[cell_name]
        escaped: Dict[str, Tuple[float, float, int]] = {}
        # Sort input pins by X so leftmost escapes left, rightmost escapes right (zero M2 crossing!)
        sig_pins = [(k, v) for k, v in pdict.items() if k not in ("VDD", "VSS")]
        in_pins = sorted([(k, v) for k, v in sig_pins if k not in ("Y", "X")], key=lambda kv: kv[1][0])
        out_pins = [(k, v) for k, v in sig_pins if k in ("Y", "X")]

        for pname, (vx, vy, box) in out_pins:
            self.via_stack(parent, vx, vy, 1, 3, pad_m1=std_pin_pad(box))
            escaped[pname] = (vx, vy, 3)

        for idx, (pname, (vx, vy, box)) in enumerate(in_pins):
            if len(in_pins) == 1:
                ex = round((x_cell - gut) if (vx < x_cell + 0.5 * w) else (x_cell + w + gut), 3)
            else:
                ex = round((x_cell - gut) if idx == 0 else (x_cell + w + gut), 3)
            self.via_stack(parent, vx, vy, 1, 2, pad_m1=std_pin_pad(box))
            self.wire(parent, L_M2, [(vx, vy), (ex, vy)], w=0.24)
            self.via_stack(parent, ex, vy, 2, 3)
            escaped[pname] = (ex, vy, 3)
        return escaped

    def bridge_stdcell_row(self, parent: db.Cell, x1: float, x2: float, y0: float) -> None:
        """Merge NWell and draw continuous VDD/VSS M1 rails across a stdcell row [x1, x2] at bottom y0."""
        self.rect(parent, L_NWELL, x1 - 0.24, y0 + 1.75, x2 + 0.24, y0 + 4.17)
        self.rect(parent, L_M1, x1, y0 + 3.56, x2, y0 + 4.00)  # VDD
        self.rect(parent, L_M1, x1, y0 - 0.22, x2, y0 + 0.22)  # VSS
