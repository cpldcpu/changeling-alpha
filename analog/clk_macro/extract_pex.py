#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Run Magic 8.3.677 true hierarchical parasitic extraction (PEX) on compacted rpe_clk_analog.gds."""

import os
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_PEX = HERE / "build" / "pex"
GDS_PATH = HERE / "layout" / "rpe_clk_analog.gds"

PDK_ROOT = Path(
    os.environ.get(
        "PDK_ROOT",
        "/home/tim/.ciel/ciel/ihp-sg13/versions/89d42ee6d2fd9b50b86a1aada6fee6673c3e6008",
    )
)
PDK = os.environ.get("PDK", "ihp-sg13cmos5l")
MAGICRC = PDK_ROOT / PDK / "libs.tech" / "magic" / f"{PDK}.magicrc"
MAGIC_BIN = os.environ.get(
    "MAGIC_BIN",
    "/nix/store/7ar043dk92xygs16rwqivrzv8s467rg0-magic-vlsi-8.3.677/bin/magic",
)

CANON_PORTS = [
    "VDD", "VSS", "en_ring", "en_relax",
    "trim0", "trim1", "trim2", "trim3", "trim4", "trim5", "trim6", "trim7",
    "clk", "clk_slow",
]


def _parse_val_ff(tok: str) -> float:
    """Convert SPICE cap value token (e.g., 3.826f, 0.12p) into fF."""
    s = tok.strip().lower()
    mult = {"f": 1.0, "p": 1e3, "n": 1e6, "u": 1e9, "a": 1e-3}
    if s and s[-1] in mult:
        return float(s[:-1]) * mult[s[-1]]
    return float(s) * 1e15


def run_magic_pex() -> None:
    BUILD_PEX.mkdir(parents=True, exist_ok=True)
    raw_spice = BUILD_PEX / "raw_rpe_clk_analog_pex.spice"
    tcl_path = BUILD_PEX / "extract_pex.tcl"
    # Keep true subcircuit hierarchy (do NOT run `ext2spice hierarchy off`) so diffusion areas ad/as/pd/ps
    # stay accurate per device instead of being lumped onto single transistors.
    tcl_path.write_text(
        "\n".join([
            "drc off",
            f"gds read {GDS_PATH}",
            "load rpe_clk_analog",
            "select top cell",
            "extract all",
            "ext2spice lvs",
            "ext2spice cthresh 0.01",
            f"ext2spice -o {raw_spice}",
            "quit -noprompt",
        ]) + "\n"
    )
    env = os.environ.copy()
    env["PDK_ROOT"] = str(PDK_ROOT)
    env["PDK"] = PDK
    res = subprocess.run(
        [MAGIC_BIN, "-dnull", "-noconsole", "-rcfile", str(MAGICRC), str(tcl_path)],
        cwd=BUILD_PEX,
        env=env,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0 or not raw_spice.exists():
        raise RuntimeError(
            f"Magic PEX failed (rc={res.returncode}):\n{res.stdout[-1500:]}\n{res.stderr[-1500:]}"
        )

    clean_and_wrap(raw_spice)


def clean_and_wrap(raw_spice: Path) -> None:
    raw_text = raw_spice.read_text()
    # Unwrap SPICE '+' continuation lines into logical lines
    merged: list[str] = []
    for line in raw_text.splitlines():
        if line.startswith("+") and merged:
            merged[-1] = merged[-1] + " " + line[1:].strip()
        else:
            merged.append(line)

    # 1. Pair Magic's two N* half-varicap devices inside `.subckt SVaricap` into PDK `.subckt sg13_hv_svaricap`
    text = "\n".join(merged)
    svar_blocks_converted = 0

    def _rewrite_svar_subckt(m: re.Match) -> str:
        nonlocal svar_blocks_converted
        hdr, body, end = m.group(1), m.group(2), m.group(3)
        sub_ports = hdr.split()[2:]
        ns = re.findall(
            r"^N\d+\s+(\S+)\s+(\S+)\s+sg13_hv_svaricap\s+l=(\S+)\s+w=([0-9.eE+-]+)u\b",
            body,
            flags=re.M,
        )
        if len(ns) != 2:
            return m.group(0)
        (g1, w1, l_str, wt1), (g2, w2, _l2, wt2) = ns
        w_node = w1
        bn_cands = [p for p in sub_ports if p not in (g1, g2, w_node)]
        bn_node = bn_cands[0] if bn_cands else "VSS"
        w_avg = (float(wt1) + float(wt2)) / 2.0
        nx = max(1, round(w_avg / 9.74))
        w_finger = w_avg / float(nx)
        body_clean = re.sub(r"^N\d+.*\bsg13_hv_svaricap\b.*\n?", "", body, flags=re.M).strip("\n")
        xvar_line = f"XSVAR {g1} {w_node} {g2} {bn_node} sg13_hv_svaricap w={w_finger:.3f}u l={l_str} Nx={nx}"
        svar_blocks_converted += 1
        return f"{hdr}\n{xvar_line}\n{body_clean}\n{end}"

    text = re.sub(
        r"(^\.subckt\s+SVaricap[^\n]*)\n(.*?)(^\.ends\b[^\n]*)",
        _rewrite_svar_subckt,
        text,
        flags=re.M | re.S,
    )
    assert svar_blocks_converted >= 1, "Expected at least one .subckt SVaricap definition"

    # 2. Rename subcircuit `.subckt rppd` -> `.subckt rppd_cell` (and instance calls ending in ` rppd`)
    #    so the wrapper subckt name does not shadow the PDK `rppd` resistor subckt called inside.
    text = re.sub(r"^\.subckt\s+rppd(\s+)", r".subckt rppd_cell\1", text, flags=re.M)
    text = re.sub(r"^(Xrppd_\d+\s+[^\n]*?\s)rppd$", r"\1rppd_cell", text, flags=re.M)

    # 3. Rename top `.subckt rpe_clk_analog <ports>` to `rpe_clk_analog_raw` and add canonical wrapper
    m_top = re.search(r"^\.subckt\s+rpe_clk_analog\s+([^\n]+)$", text, flags=re.M)
    assert m_top, "Could not find .subckt rpe_clk_analog in Magic PEX output"
    extracted_ports = m_top.group(1).split()
    missing_ports = set(CANON_PORTS) - set(extracted_ports)
    assert not missing_ports, f"Missing PEX ports: {missing_ports}"

    text = re.sub(
        r"^\.subckt\s+rpe_clk_analog\s+",
        ".subckt rpe_clk_analog_raw ",
        text,
        count=1,
        flags=re.M,
    )
    # Remove trailing .end (since canonical wrapper will follow)
    text = re.sub(r"\n\.end\s*$", "", text.strip(), flags=re.IGNORECASE)

    wrapper = "\n".join([
        "",
        f".subckt rpe_clk_analog {' '.join(CANON_PORTS)}",
        f"XRAW {' '.join(extracted_ports)} rpe_clk_analog_raw",
        ".ends rpe_clk_analog",
        "",
    ])
    final_text = f"* Post-layout hierarchical PEX netlist for rpe_clk_analog (Magic 8.3.677, ihp-sg13cmos5l)\n\n{text}\n{wrapper}"

    pex_spice = BUILD_PEX / "rpe_clk_analog_pex.spice"
    pex_spice.write_text(final_text)

    # 4. Collect hierarchical extraction statistics (walking subcircuit instantiations from rpe_clk_analog_raw)
    sub_defs: dict[str, list[str]] = {}
    cur_name: str | None = None
    for line in final_text.splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt "):
            cur_name = s.split()[1]
            sub_defs[cur_name] = []
        elif s.lower().startswith(".ends"):
            cur_name = None
        elif cur_name and s and not s.startswith("*"):
            sub_defs[cur_name].append(s)

    prim_models = {"sg13_lv_nmos", "sg13_lv_pmos", "sg13_hv_nmos", "rppd", "sg13_hv_svaricap"}
    dev_counts: Counter[str] = Counter()
    cap_stats = {"count": 0, "tot_ff": 0.0, "gnd_ff": 0.0, "cpl_ff": 0.0}

    def _walk(sname: str) -> None:
        for stmt in sub_defs.get(sname, []):
            toks = stmt.split()
            if stmt.startswith("C") and len(toks) >= 4:
                n1, n2, val_tok = toks[1], toks[2], toks[3]
                cff = _parse_val_ff(val_tok)
                cap_stats["count"] += 1
                cap_stats["tot_ff"] += cff
                if n1 in ("VSS", "0", "GND", "sub") or n2 in ("VSS", "0", "GND", "sub"):
                    cap_stats["gnd_ff"] += cff
                else:
                    cap_stats["cpl_ff"] += cff
            elif stmt.startswith("X"):
                model = next((t for t in reversed(toks[1:]) if "=" not in t), None)
                if model in prim_models:
                    dev_counts[model] += 1
                elif model in sub_defs:
                    _walk(model)

    _walk("rpe_clk_analog_raw")

    stats_txt = (
        f"Magic Hierarchical PEX Statistics (ihp-sg13cmos5l, cthresh=0.01 fF)\n"
        f"===================================================================\n"
        f"GDS File        : {GDS_PATH}\n"
        f"PEX Netlist     : {pex_spice}\n"
        f"Extraction Mode : Hierarchical subcircuits (per-transistor diffusion areas preserved)\n"
        f"Extracted Ports : {len(CANON_PORTS)} ({', '.join(CANON_PORTS)})\n"
        f"Subckt Defs     : {len(sub_defs)}\n"
        f"Devices Extracted (flattened across hierarchy):\n"
        f"  sg13_lv_nmos      : {dev_counts['sg13_lv_nmos']}\n"
        f"  sg13_lv_pmos      : {dev_counts['sg13_lv_pmos']}\n"
        f"  sg13_hv_nmos      : {dev_counts['sg13_hv_nmos']}\n"
        f"  rppd (resistors)  : {dev_counts['rppd']}\n"
        f"  sg13_hv_svaricap  : {dev_counts['sg13_hv_svaricap']} (paired in {svar_blocks_converted} SVaricap subckt)\n"
        f"Extracted Capacitors (threshold >= 0.01 fF, summed across instances):\n"
        f"  Total C elements  : {cap_stats['count']}\n"
        f"  Total Capacitance : {cap_stats['tot_ff']:.2f} fF ({cap_stats['tot_ff']/1000.0:.3f} pF)\n"
        f"    Ground/Sub-ref  : {cap_stats['gnd_ff']:.2f} fF\n"
        f"    Coupling (C-C)  : {cap_stats['cpl_ff']:.2f} fF (includes 5x CMOMF stage caps)\n"
    )
    stats_path = BUILD_PEX / "pex_stats.txt"
    stats_path.write_text(stats_txt)
    print(stats_txt)


if __name__ == "__main__":
    run_magic_pex()
