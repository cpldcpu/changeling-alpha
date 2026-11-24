#!/usr/bin/env python3
"""Helper to generate clean, grid-aligned xschem schematics (.sch) and symbols (.sym)."""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Point = Tuple[float, float]


def read_sym_pins(path: str | Path) -> Dict[str, Point]:
    """Parse exact pin centers from an xschem .sym file (`B 5 x1 y1 x2 y2 {name=...}`)."""
    pins: Dict[str, Point] = {}
    pat = re.compile(r"^B\s+5\s+([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\{[^}]*name=([^\s}]+)")
    for line in Path(path).read_text().splitlines():
        m = pat.match(line.strip())
        if m:
            x1, y1, x2, y2, pname = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5)
            pins[pname] = ((x1 + x2) * 0.5, (y1 + y2) * 0.5)
    return pins


def _xform_point(px: float, py: float, x: float, y: float, rot: int, flip: int) -> Point:
    """Transform symbol-local coordinates (px, py) to schematic coordinates."""
    if flip:
        px = -px
    # xschem rotation is clockwise in screen coords (Y down):
    # rot=0: (px, py), rot=1 (90 CW): (-py, px), rot=2 (180): (-px, -py), rot=3 (270 CW): (py, -px)
    r = rot % 4
    if r == 1:
        px, py = -py, px
    elif r == 2:
        px, py = -px, -py
    elif r == 3:
        px, py = py, -px
    return (x + px, y + py)


# Exact pin offsets in local symbol coords for verified PDK / devices symbols
PIN_OFFSETS: Dict[str, Dict[str, Point]] = {
    "sg13cmos5l_pr/sg13_lv_nmos.sym": {"D": (20, -30), "G": (-20, 0), "S": (20, 30), "B": (20, 0)},
    "sg13cmos5l_pr/sg13_hv_nmos.sym": {"D": (20, -30), "G": (-20, 0), "S": (20, 30), "B": (20, 0)},
    "sg13cmos5l_pr/sg13_lv_pmos.sym": {"S": (20, -30), "G": (-20, 0), "D": (20, 30), "B": (20, 0)},
    "sg13cmos5l_pr/sg13_hv_pmos.sym": {"S": (20, -30), "G": (-20, 0), "D": (20, 30), "B": (20, 0)},
    "sg13cmos5l_pr/rppd.sym": {"P": (0, -30), "M": (0, 30)},
    "sg13cmos5l_pr/rhigh.sym": {"P": (0, -30), "M": (0, 30)},
    "sg13cmos5l_pr/cap_cmomf.sym": {"c0": (0, -30), "c1": (0, 30)},
    "sg13cmos5l_pr/sg13_svaricap.sym": {"G2": (-40, 0), "NW": (0, -30), "G1": (40, 0)},
    "sg13cmos5l_pr/moscap_n.sym": {"G": (0, -30), "SUB": (0, 30)},
    "sg13cmos5l_pr/moscap_p.sym": {"G": (0, -30), "NW": (0, 30)},
    "sg13cmos5l_stdcells/sg13cmos5l_buf_1.sym": {"A": (-40, 0), "X": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_buf_2.sym": {"A": (-40, 0), "X": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_buf_4.sym": {"A": (-40, 0), "X": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_inv_1.sym": {"A": (-40, 0), "Y": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_inv_2.sym": {"A": (-40, 0), "Y": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_inv_4.sym": {"A": (-40, 0), "Y": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_nand2_2.sym": {"A": (-60, -20), "B": (-60, 20), "Y": (60, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_nor2_1.sym": {"A": (-60, -20), "B": (-60, 20), "Y": (60, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_mux2_1.sym": {"A0": (-40, -20), "A1": (-40, 20), "S": (-40, 60), "X": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_dlygate4sd1_1.sym": {"A": (-40, 0), "X": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_dlygate4sd2_1.sym": {"A": (-40, 0), "X": (40, 0)},
    "sg13cmos5l_stdcells/sg13cmos5l_dlygate4sd3_1.sym": {"A": (-40, 0), "X": (40, 0)},
    "devices/ipin.sym": {"p": (0, 0)},
    "devices/opin.sym": {"p": (0, 0)},
    "devices/iopin.sym": {"p": (0, 0)},
    "devices/lab_pin.sym": {"p": (0, 0)},
    "devices/gnd.sym": {"p": (0, 0)},
    "devices/vdd.sym": {"p": (0, 0)},
    "devices/vsource.sym": {"p": (0, -30), "m": (0, 30)},
    "devices/capa.sym": {"p": (0, -30), "m": (0, 30)},
    "devices/res.sym": {"p": (0, -30), "m": (0, 30)},
}


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _fmt_props(props: Dict[str, str]) -> str:
    lines = []
    for k, v in props.items():
        s = str(v)
        if "\n" in s or " " in s or s == "" or any(c in s for c in "{}[];\"'=$"):
            esc = s.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}="{esc}"')
        else:
            lines.append(f"{k}={s}")
    return "\n".join(lines)


@dataclass
class Component:
    sym: str
    x: float
    y: float
    rot: int = 0
    flip: int = 0
    props: Dict[str, str] = field(default_factory=dict)
    custom_pins: Dict[str, Point] = field(default_factory=dict)

    def pin(self, pin_name: str) -> Point:
        table = self.custom_pins or PIN_OFFSETS.get(self.sym, {})
        if pin_name not in table:
            raise KeyError(f"Unknown pin '{pin_name}' for symbol '{self.sym}'")
        px, py = table[pin_name]
        return _xform_point(px, py, self.x, self.y, self.rot, self.flip)


class Schematic:
    """Builder for xschem .sch files."""

    def __init__(self, author: str = "changeling-alpha") -> None:
        self.author = author
        self.wires: List[Tuple[float, float, float, float, str]] = []
        self.texts: List[Tuple[str, float, float, int, int, float, str]] = []
        self.components: List[Component] = []
        self._label_idx = 0

    def add(
        self,
        sym: str,
        x: float,
        y: float,
        rot: int = 0,
        flip: int = 0,
        custom_pins: Optional[Dict[str, Point]] = None,
        **props: str,
    ) -> Component:
        c = Component(
            sym=sym,
            x=x,
            y=y,
            rot=rot,
            flip=flip,
            props={k: str(v) for k, v in props.items()},
            custom_pins=custom_pins or {},
        )
        self.components.append(c)
        return c

    def wire(self, p1: Point, p2: Point, lab: str = "") -> None:
        x1, y1 = p1
        x2, y2 = p2
        if x1 == x2 and y1 == y2:
            return
        self.wires.append((x1, y1, x2, y2, lab))

    def route_hv(self, p1: Point, p2: Point, lab: str = "") -> None:
        """Horizontal then vertical Manhattan wire."""
        x1, y1 = p1
        x2, y2 = p2
        if x1 != x2 and y1 != y2:
            self.wire((x1, y1), (x2, y1), lab)
            self.wire((x2, y1), (x2, y2), lab)
        else:
            self.wire(p1, p2, lab)

    def route_vh(self, p1: Point, p2: Point, lab: str = "") -> None:
        """Vertical then horizontal Manhattan wire."""
        x1, y1 = p1
        x2, y2 = p2
        if x1 != x2 and y1 != y2:
            self.wire((x1, y1), (x1, y2), lab)
            self.wire((x1, y2), (x2, y2), lab)
        else:
            self.wire(p1, p2, lab)

    def label(self, lab: str, pt: Point, rot: int = 0, flip: int = 0, sym: str = "devices/lab_pin.sym") -> Component:
        self._label_idx += 1
        return self.add(sym, pt[0], pt[1], rot=rot, flip=flip, name=f"l{self._label_idx}", lab=lab)

    def out_label(self, lab: str, pt: Point, dx: float = 40) -> Component:
        """Draw a rightward stub wire from pt and attach a right-extending lab_pin (flip=1)."""
        end = (pt[0] + dx, pt[1])
        self.wire(pt, end)
        return self.label(lab, end, flip=1)

    def in_label(self, lab: str, pt: Point, dx: float = 40) -> Component:
        """Draw a leftward stub wire to pt and attach a left-extending lab_pin (flip=0)."""
        start = (pt[0] - dx, pt[1])
        self.wire(start, pt)
        return self.label(lab, start, flip=0)

    def pin(self, kind: str, lab: str, pt: Point, rot: int = 0, flip: int = 0) -> Component:
        assert kind in ("ipin", "opin", "iopin")
        self._label_idx += 1
        return self.add(f"devices/{kind}.sym", pt[0], pt[1], rot=rot, flip=flip, name=f"p{self._label_idx}", lab=lab)

    def title(self, x: float = 0, y: float = 600) -> None:
        self.add("devices/title.sym", x, y, name="title1", author=self.author)

    def text(self, s: str, x: float, y: float, scale: float = 0.25, layer: int = 3) -> None:
        self.texts.append((s, x, y, 0, 0, scale, f"layer={layer}"))

    def write(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "v {xschem version=3.4.4 file_version=1.2}",
            "G {}",
            "K {}",
            "V {}",
            "S {}",
            "E {}",
        ]
        for s, x, y, r, f, sc, attr in self.texts:
            lines.append(f"T {{{s}}} {_fmt_num(x)} {_fmt_num(y)} {r} {f} {_fmt_num(sc)} {_fmt_num(sc)} {{{attr}}}")
        for x1, y1, x2, y2, lab in self.wires:
            prop = f"lab={lab}" if lab else ""
            lines.append(f"N {_fmt_num(x1)} {_fmt_num(y1)} {_fmt_num(x2)} {_fmt_num(y2)} {{{prop}}}")
        for c in self.components:
            pstr = _fmt_props(c.props)
            lines.append(f"C {{{c.sym}}} {_fmt_num(c.x)} {_fmt_num(c.y)} {c.rot} {c.flip} {{{pstr}}}")
        out.write_text("\n".join(lines) + "\n")
        return out


def write_block_symbol(
    path: str | Path,
    block_name: str,
    left_pins: List[Tuple[str, str]],
    right_pins: List[Tuple[str, str]],
    top_pins: Optional[List[Tuple[str, str]]] = None,
    bottom_pins: Optional[List[Tuple[str, str]]] = None,
    width: int = 200,
    pin_pitch: int = 40,
    spice_order: Optional[List[str]] = None,
) -> Dict[str, Point]:
    """Create a clean rectangular hierarchical .sym and return {pin_name: (x, y)}."""
    top_pins = top_pins or []
    bottom_pins = bottom_pins or []
    n_rows = max(len(left_pins), len(right_pins), 1)
    height = max(80, (n_rows + 1) * pin_pitch)
    # Snap half-height to multiple of 20
    hh = ((height // 2) + 19) // 20 * 20
    hw = ((width // 2) + 19) // 20 * 20

    all_pins = [p for p, _ in (left_pins + right_pins + top_pins + bottom_pins)]
    if spice_order is None:
        spice_order = all_pins
    pin_tokens = " ".join(f"@@{p}" for p in spice_order)

    lines = [
        "v {xschem version=3.4.4 file_version=1.2}",
        "G {}",
        f'K {{type=subcircuit\nformat="@name {pin_tokens} @symname"\ntemplate="name=X1"}}',
        "V {}",
        "S {}",
        "E {}",
        f"L 4 {-hw} {-hh} {hw} {-hh} {{}}",
        f"L 4 {hw} {-hh} {hw} {hh} {{}}",
        f"L 4 {hw} {hh} {-hw} {hh} {{}}",
        f"L 4 {-hw} {hh} {-hw} {-hh} {{}}",
        f"T {{{block_name}}} {hw} {-hh - 15} 0 1 0.25 0.25 {{}}",
        f"T {{@name}} {-hw} {-hh - 15} 0 0 0.22 0.22 {{}}",
    ]

    pin_coords: Dict[str, Point] = {}
    stub = 20

    def add_pin_box(pname: str, pdir: str, x: int, y: int) -> None:
        pin_coords[pname] = (x, y)
        lines.append(f"B 5 {x - 2.5:g} {y - 2.5:g} {x + 2.5:g} {y + 2.5:g} {{name={pname} dir={pdir}}}")

    # Left pins
    y0 = -((len(left_pins) - 1) * pin_pitch) // 2
    y0 = (y0 // 20) * 20
    for i, (pname, pdir) in enumerate(left_pins):
        py = y0 + i * pin_pitch
        px = -hw - stub
        lines.append(f"L 4 {px} {py} {-hw} {py} {{}}")
        add_pin_box(pname, pdir, px, py)
        lines.append(f"T {{{pname}}} {-hw + 6} {py - 5} 0 0 0.18 0.18 {{}}")

    # Right pins
    y0 = -((len(right_pins) - 1) * pin_pitch) // 2
    y0 = (y0 // 20) * 20
    for i, (pname, pdir) in enumerate(right_pins):
        py = y0 + i * pin_pitch
        px = hw + stub
        lines.append(f"L 4 {hw} {py} {px} {py} {{}}")
        add_pin_box(pname, pdir, px, py)
        lines.append(f"T {{{pname}}} {hw - 6} {py - 5} 0 1 0.18 0.18 {{}}")

    # Top pins
    x0 = -((len(top_pins) - 1) * pin_pitch) // 2
    x0 = (x0 // 20) * 20
    for i, (pname, pdir) in enumerate(top_pins):
        px = x0 + i * pin_pitch
        py = -hh - stub
        lines.append(f"L 4 {px} {py} {px} {-hh} {{}}")
        add_pin_box(pname, pdir, px, py)
        lines.append(f"T {{{pname}}} {px + 4} {-hh + 12} 0 0 0.16 0.16 {{}}")

    # Bottom pins
    x0 = -((len(bottom_pins) - 1) * pin_pitch) // 2
    x0 = (x0 // 20) * 20
    for i, (pname, pdir) in enumerate(bottom_pins):
        px = x0 + i * pin_pitch
        py = hh + stub
        lines.append(f"L 4 {px} {hh} {px} {py} {{}}")
        add_pin_box(pname, pdir, px, py)
        lines.append(f"T {{{pname}}} {px + 4} {hh - 6} 0 0 0.16 0.16 {{}}")

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    return pin_coords
