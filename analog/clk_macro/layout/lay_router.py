#!/usr/bin/env python3
"""2D interval-aware Manhattan channel router on M2 (horizontal) and M3 (vertical)."""

from __future__ import annotations
from typing import List, Optional, Tuple
import pya as db

from lay_core import L_M1, L_M2, L_M3, L_M4, LayoutBuilder


class NetRouter:
    """Routes multi-terminal nets with reserved M2 horizontal tracks/jogs and 2D M3 vertical segments."""

    def __init__(
        self,
        lb: LayoutBuilder,
        cell: db.Cell,
        m2_y0: float,
        m2_pitch: float = 0.66,
        m3_pitch: float = 0.66,
        shared_vx: Optional[List[Tuple[float, float, float, Optional[Tuple[float, float]]]]] = None,
        shared_m2: Optional[List[Tuple[float, float, float, Tuple[int, int]]]] = None,
        blocked_x: Optional[List[Tuple[float, float]]] = None,
        blocked_rects: Optional[List[Tuple[float, float, float, float]]] = None,
        min_x: float = 1.8,
        pack: bool = False,
    ) -> None:
        self.lb = lb
        self.cell = cell
        self.m2_y0 = m2_y0
        self.m2_pitch = m2_pitch
        self.m3_pitch = m3_pitch
        self.pack = pack
        self._next_track = 0
        self._net_seq = 0
        # Maps track index k -> list of horizontal [x_lo, x_hi] spans on M2 when pack=True
        self._track_intervals: dict[int, List[Tuple[float, float]]] = {}
        # Each entry is (x, y_lo, y_hi, owner) covering the vertical span used on M3
        self._used_m3: List[Tuple[float, float, float, Optional[Tuple[float, float]]]] = (
            shared_vx if shared_vx is not None else []
        )
        # Each entry is (y, x_lo, x_hi, net_tag) covering M2 pads, horizontal jogs, and trunks
        self._used_m2: List[Tuple[float, float, float, Tuple[int, int]]] = (
            shared_m2 if shared_m2 is not None else []
        )
        self._blocked_x: List[Tuple[float, float]] = blocked_x if blocked_x is not None else []
        self._blocked_rects: List[Tuple[float, float, float, float]] = blocked_rects if blocked_rects is not None else []
        self.min_x = min_x

    def alloc_y(self) -> float:
        y = round(self.m2_y0 + self._next_track * self.m2_pitch, 3)
        self._next_track += 1
        return y

    def max_used_y(self) -> float:
        return round(self.m2_y0 + max(0, self._next_track - 1) * self.m2_pitch, 3)

    def _alloc_y_packed(self, x_lo: float, x_hi: float) -> Tuple[int, float]:
        """Find lowest track k clearing existing trunk spans and M2 pads over [x_lo, x_hi]."""
        pad = 0.80
        for k in range(self._next_track):
            y = round(self.m2_y0 + k * self.m2_pitch, 3)
            ivs = self._track_intervals.get(k, [])
            if any(not (x_hi + pad < ilo or x_lo - pad > ihi) for ilo, ihi in ivs):
                continue
            if any(abs(y - uy) < 0.48 and not (x_hi + 0.34 < ux1 or x_lo - 0.34 > ux2) for uy, ux1, ux2, _ in self._used_m2):
                continue
            return k, y
        k = self._next_track
        y = self.alloc_y()
        return k, y

    def reserve_x(self, x: float, y_lo: float = -1e6, y_hi: float = 1e6) -> None:
        self._used_m3.append((round(x, 3), min(y_lo, y_hi), max(y_lo, y_hi), None))

    def reserve_pin(self, px: float, py: float, y_hi: float) -> None:
        """Reserve an already-escaped M3 pin X so no other net jogs across it and its own riser stays straight."""
        rx, ry = round(px, 3), round(py, 3)
        self._used_m3.append((rx, min(ry, y_hi), max(ry, y_hi), (rx, ry)))

    def _is_seg_blocked(
        self,
        x: float,
        y_lo: float,
        y_hi: float,
        owner: Optional[Tuple[float, float]] = None,
    ) -> bool:
        if x < self.min_x - 1e-4:
            return True
        if any(lo <= x <= hi for lo, hi in self._blocked_x):
            return True
        for x1, x2, y1, y2 in self._blocked_rects:
            if x1 <= x <= x2 and not (y_hi < y1 or y_lo > y2):
                return True
        pad_y = self.m3_pitch * 0.85
        for ux, u_lo, u_hi, u_owner in self._used_m3:
            if owner is not None and u_owner is not None and u_owner == owner:
                continue
            if abs(x - ux) < self.m3_pitch - 1e-4:
                if not (y_hi + pad_y < u_lo or y_lo - pad_y > u_hi):
                    return True
        return False

    def _m2_jog_blocked(
        self,
        px: float,
        cand_x: float,
        py: float,
        net_tag: Tuple[int, int],
    ) -> bool:
        """Check whether a horizontal M2 jog [px, cand_x] at py clears other nets' M2 pads/wires."""
        jx1 = min(px, cand_x) - 0.34
        jx2 = max(px, cand_x) + 0.34
        for uy, ux1, ux2, utag in self._used_m2:
            if utag == net_tag:
                continue
            if abs(py - uy) < 0.48 and not (jx2 < ux1 or jx1 > ux2):
                return True
        return False

    def pick_free_x(
        self,
        target_x: float,
        y_lo: float,
        y_hi: float,
        owner: Optional[Tuple[float, float]] = None,
        jog_y: Optional[float] = None,
        net_tag: Tuple[int, int] = (-1, -1),
    ) -> float:
        """Pick nearest vertical M3 X whose [y_lo, y_hi] span and optional M2 jog clear existing nets."""
        lo, hi = min(y_lo, y_hi), max(y_lo, y_hi)
        cand = round(target_x, 3)
        step = 0
        while step <= 200:
            blocked = self._is_seg_blocked(cand, lo, hi, owner=owner)
            if not blocked and jog_y is not None and abs(cand - target_x) > 0.02:
                blocked = self._m2_jog_blocked(target_x, cand, jog_y, net_tag)
            if not blocked:
                if owner is not None:
                    self._used_m3[:] = [u for u in self._used_m3 if u[3] != owner]
                self._used_m3.append((cand, lo, hi, owner))
                return cand
            step += 1
            off = ((step + 1) // 2) * self.m3_pitch
            cand = round(target_x + (off if step % 2 == 1 else -off), 3)
        raise RuntimeError(f"NetRouter: no clean M3 X near {target_x} in y=[{lo}, {hi}]")

    def connect(
        self,
        pins: List[Tuple],
        y_track: Optional[float] = None,
        pad_m1_list: Optional[List[Optional[Tuple[float, float]]]] = None,
        pad_m2_list: Optional[List[Optional[Tuple[float, float]]]] = None,
        extend_to_x: Optional[List[float]] = None,
        m_trunk: int = 2,
    ) -> float:
        """Connect [(x, y, metal_lvl[, pad_m1]), ...] using horizontal trunk at y_track and 2D-clean M3 risers."""
        self._net_seq += 1
        net_tag = (id(self), self._net_seq)
        trk_idx: Optional[int] = None
        if y_track is None:
            if self.pack:
                all_x = [p[0] for p in pins] + (list(extend_to_x) if extend_to_x else [])
                est_lo = min(all_x) - 0.8 if all_x else 0.0
                est_hi = max(all_x) + 0.8 if all_x else 0.0
                trk_idx, y_track = self._alloc_y_packed(est_lo, est_hi)
            else:
                trk_idx = self._next_track
                y_track = self.alloc_y()
        xs_m3: List[float] = []
        m_ld = {1: L_M1, 2: L_M2, 3: L_M3, 4: L_M4}

        for idx, item in enumerate(pins):
            if len(item) == 4:
                px, py, plvl, inline_pad = item
            else:
                px, py, plvl = item
                inline_pad = None
            pad_m1 = inline_pad if inline_pad is not None else (pad_m1_list[idx] if (pad_m1_list and idx < len(pad_m1_list)) else None)
            pad_m2 = pad_m2_list[idx] if (pad_m2_list and idx < len(pad_m2_list)) else None

            if plvl == m_trunk and abs(py - y_track) < 0.02:
                xs_m3.append(round(px, 3))
                if m_trunk == 2:
                    self._used_m2.append((round(py, 3), px - 0.22, px + 0.22, net_tag))
                continue

            owner = (round(px, 3), round(py, 3)) if plvl == 3 else None
            jog_y = py if plvl <= 2 else None
            vx = self.pick_free_x(px, py, y_track, owner=owner, jog_y=jog_y, net_tag=net_tag)

            if abs(vx - px) > 0.02:
                if plvl == 3:
                    raise RuntimeError(
                        f"NetRouter: M3 pin ({px}, {py}) forced to jog to {vx} — widen cell/pin spacing!"
                    )
                if plvl <= 2:
                    if plvl < 2:
                        self.lb.via_stack(self.cell, px, py, plvl, 2, pad_m1=pad_m1, pad_m2=pad_m2)
                    self.lb.wire(self.cell, L_M2, [(px, py), (vx, py)], w=0.24)
                    self.lb.via_stack(self.cell, vx, py, 2, 3)
                    self._used_m2.append((round(py, 3), min(px, vx) - 0.22, max(px, vx) + 0.22, net_tag))
                else:
                    self.lb.wire(self.cell, m_ld[plvl], [(px, py), (vx, py)], w=0.24)
                    if plvl != 3:
                        self.lb.via_stack(self.cell, vx, py, 3, plvl)
            else:
                if plvl < 3:
                    self.lb.via_stack(self.cell, vx, py, plvl, 3, pad_m1=pad_m1, pad_m2=pad_m2)
                    self._used_m2.append((round(py, 3), px - 0.22, px + 0.22, net_tag))
                elif plvl > 3:
                    self.lb.via_stack(self.cell, vx, py, 3, plvl)

            if abs(py - y_track) > 0.01:
                self.lb.wire(self.cell, L_M3, [(vx, py), (vx, y_track)], w=0.24)
            if m_trunk == 2:
                self.lb.via(self.cell, vx, y_track, 2)  # M2 <-> M3
                self._used_m2.append((round(y_track, 3), vx - 0.22, vx + 0.22, net_tag))
            elif m_trunk == 4:
                self.lb.via(self.cell, vx, y_track, 3)  # M3 <-> M4
            xs_m3.append(vx)

        if extend_to_x:
            xs_m3.extend(extend_to_x)

        if len(xs_m3) >= 2:
            x_min, x_max = min(xs_m3), max(xs_m3)
            self.lb.wire(self.cell, m_ld[m_trunk], [(x_min, y_track), (x_max, y_track)], w=0.24)
            if m_trunk == 2:
                self._used_m2.append((round(y_track, 3), x_min - 0.14, x_max + 0.14, net_tag))
            if trk_idx is not None:
                self._track_intervals.setdefault(trk_idx, []).append((x_min - 0.14, x_max + 0.14))
        elif len(xs_m3) == 1 and trk_idx is not None:
            self._track_intervals.setdefault(trk_idx, []).append((xs_m3[0] - 0.25, xs_m3[0] + 0.25))
        return y_track
