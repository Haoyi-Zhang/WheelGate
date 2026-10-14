# Copyright (c) 2026 WheelGate contributors
# SPDX-License-Identifier: MIT
"""Optional retained-data vector route; no experiments or summary recomputation.

Drawing code reused from paper/figures/draw_runtime.py. See the artifact LICENSE.
Pass --source (retained input file), --output-dir and --font-root explicitly.
"""
import argparse
import re
import math
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


def require_fonts(root):
    """Use installed metrics/outlines; never search, install, or copy fonts."""
    for relative in ("afm/urw/times/utmr8a.afm", "type1/urw/times/utmr8a.pfb"):
        if not (root / relative).is_file():
            raise FileNotFoundError(f"Required installed font: {root / relative}")


def load_data(source):
    lines = source.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].split() != ["label", "value"]:
        raise ValueError("Expected label value header")
    data = []
    for line in lines[1:]:
        if not line.strip():
            continue
        match = re.fullmatch(r"\{([^}]+)\}\s+(\S+)", line.strip())
        if match is None:
            raise ValueError("Expected a braced class label and its retained median")
        value = float(match.group(2))
        if not math.isfinite(value) or not 0 <= value <= 2200:
            raise ValueError("Runtime medians must be finite and within the retained 0..2200 axis")
        data.append((match.group(1), value))
    if [row[0] for row in data] != ["Prerequisite block", "Single operation", "Three operations"]:
        raise ValueError("Expected the three retained timing classes in order")
    return data



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    data = load_data(args.source)
    require_fonts(args.font_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    face = pdfmetrics.EmbeddedType1Face(
        str(args.font_root / "afm/urw/times/utmr8a.afm"),
        str(args.font_root / "type1/urw/times/utmr8a.pfb"))
    pdfmetrics.registerTypeFace(face)
    pdfmetrics.registerFont(pdfmetrics.Font("ManuscriptRoman", face.name, "WinAnsiEncoding"))
    width, height = 252, 4.6 * 72 / 2.54
    c = canvas.Canvas(str(args.output_dir / "runtime-summary.pdf"), pagesize=(width, height), invariant=1, initialFontName="ManuscriptRoman")
    c.setTitle("")
    left, right, bottom, top = 43, width - 7, 32, height - 9
    y = lambda v: bottom + v / 2200 * (top - bottom)
    c.setFont("ManuscriptRoman", 7)
    c.setLineWidth(.35)
    c.setStrokeColor(HexColor("#d6d6d6"))
    for tick in range(0, 2001, 500):
        c.line(left, y(tick), right, y(tick))
        c.drawRightString(left - 5, y(tick) - 2.2, str(tick))
    c.setStrokeColor(HexColor("#444444"))
    c.setLineWidth(.5)
    c.line(left, bottom, left, top)
    c.line(left, bottom, right, bottom)
    c.setFont("ManuscriptRoman", 8)
    c.saveState()
    c.translate(11, (bottom + top) / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "Median time (ms)")
    c.restoreState()
    for i, (label, value) in enumerate(data):
        xp = left + (i + .5) * (right - left) / 3
        c.setFillColor(HexColor("#24629b"))
        c.rect(xp - 9 * 72 / 25.4 / 2, bottom, 9 * 72 / 25.4, y(value) - bottom, stroke=0, fill=1)
        c.setFillColor(HexColor("#222222"))
        c.setFont("ManuscriptRoman", 7)
        c.drawCentredString(xp, y(value) + 4, format(value, ".3f"))
        first, second = label.split(" ", 1)
        c.drawCentredString(xp, bottom - 12, first)
        c.drawCentredString(xp, bottom - 21, second)
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
