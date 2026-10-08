#!/usr/bin/env python3
"""Verify manuscript structure, references, template integrity, and rendered PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parents[1]
PAPER = ARTIFACT.parent / "paper"
EXPECTED_CLASS_SHA256 = "da751920a317ed318b7b5cd7fa585a6cc7d28502d457856382e9be24b10a3bd7"
EXPECTED_BST_SHA256 = "314f0ece704568faf827011bac498650691b2b5ee06320720830e782416d5a5f"
AUTHORS = [
    {
        "name": "Haoyi Zhang",
        "orcid": "0009-0009-3693-786X",
        "institution": "Xi'an Jiaotong-Liverpool University",
        "city_country": "Suzhou, China",
        "emails": ["hyeliozhang@gmail.com"],
        "corresponding": False,
    },
    {
        "name": "Huaijin Ran",
        "orcid": "0009-0009-2482-2344",
        "institution": "Nanyang Technological University",
        "city_country": "Singapore, Singapore",
        "emails": ["huaijin003@e.ntu.edu.sg"],
        "corresponding": False,
    },
    {
        "name": "Xunzhu Tang",
        "orcid": "0000-0002-6377-0884",
        "institution": "AutoTrust AI",
        "city_country": None,
        "emails": ["realdanieltang@gmail.com"],
        "corresponding": True,
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=PAPER, capture_output=True, text=True, check=False)


def bib_keys(text: str) -> set[str]:
    return set(re.findall(r"@(?!IEEEtranBSTCTL)\w+\s*\{\s*([^,\s]+)", text, re.I))


def cited_keys(text: str) -> set[str]:
    groups = re.findall(r"\\cite\w*(?:\[[^\]]*\])?\{([^}]+)\}", text)
    return {key.strip() for group in groups for key in group.split(",") if key.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--visual-reviewed", action="store_true")
    args = parser.parse_args()

    tex_path = PAPER / "main.tex"
    bib_path = PAPER / "references.bib"
    pdf_path = PAPER / "main.pdf"
    for path in [tex_path, bib_path, pdf_path, PAPER / "IEEEtran.cls", PAPER / "IEEEtran.bst"]:
        require(path.is_file(), f"missing manuscript file: {path}")

    tex = tex_path.read_text(encoding="utf-8")
    bib = bib_path.read_text(encoding="utf-8")
    require("\\documentclass[10pt,conference]{IEEEtran}" in tex, "wrong document class or options")
    require("compsoc" not in tex.lower(), "unsupported compsoc option")
    require(sha256(PAPER / "IEEEtran.cls") == EXPECTED_CLASS_SHA256, "IEEEtran.cls changed")
    require(sha256(PAPER / "IEEEtran.bst") == EXPECTED_BST_SHA256, "IEEEtran.bst changed")
    for forbidden in ["\\geometry", "\\setstretch", "\\baselinestretch", "\\fontsize"]:
        require(forbidden not in tex, f"layout override present: {forbidden}")
    require(
        re.search(
            r"\\(?:setlength|addtolength)\s*\{\\(?:textwidth|textheight|oddsidemargin|evensidemargin|topmargin)\}",
            tex,
        )
        is None,
        "page dimensions overridden",
    )
    require(
        tex.index("\\section{Conclusion}")
        < tex.index("\\section{Data Availability}")
        < tex.index("\\bibliography{references}"),
        "Conclusion/Data Availability/reference order changed",
    )

    for author in AUTHORS:
        for value in [author["name"], author["orcid"], author["institution"], author["city_country"], *author["emails"]]:
            if value is not None:
                require(value in tex, f"author metadata missing: {value}")
    require(tex.count("Corresponding author") == 1, "corresponding-author marker must appear exactly once")

    keys = bib_keys(bib)
    cited = cited_keys(tex)
    require(len(keys) == 70, f"expected 70 bibliography entries, found {len(keys)}")
    require(keys == cited, f"bibliography/citation mismatch: unused={sorted(keys-cited)}, missing={sorted(cited-keys)}")
    audit_rows = json.loads((ARTIFACT / "corpus/reference-audit.json").read_text(encoding="utf-8"))
    require({row["key"] for row in audit_rows} == keys, "reference ledger keys do not match bibliography")
    category_counts: dict[str, int] = {}
    for row in audit_rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    require(category_counts.get("research") == 16, "research reference count changed")

    info = command(["pdfinfo", str(pdf_path)])
    require(info.returncode == 0, f"pdfinfo failed: {info.stderr}")
    fields: dict[str, str] = {}
    for line in info.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    require(fields.get("Pages") == "12", f"expected 12 pages, found {fields.get('Pages')}")
    require(fields.get("Encrypted", "no").lower().startswith("no"), "PDF is encrypted")
    require("letter" in fields.get("Page size", "").lower() or "612 x 792" in fields.get("Page size", ""), "PDF is not US Letter")

    with subprocess.Popen(
        ["pdftotext", "-f", "10", "-l", "10", str(pdf_path), "-"],
        cwd=PAPER,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as proc:
        page10, err10 = proc.communicate()
        require(proc.returncode == 0, f"pdftotext page 10 failed: {err10}")
    with subprocess.Popen(
        ["pdftotext", "-f", "11", "-l", "11", str(pdf_path), "-"],
        cwd=PAPER,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as proc:
        page11, err11 = proc.communicate()
        require(proc.returncode == 0, f"pdftotext page 11 failed: {err11}")
    page10_compact = re.sub(r"\s+", "", page10.upper())
    page11_compact = re.sub(r"\s+", "", page11.upper())
    require("DATAAVAILABILITY" in page10_compact, "Data Availability is not on page 10")
    require("REFERENCES" in page11_compact, "References do not start on page 11")

    log_path = PAPER / "main.log"
    log_checks = {"available": log_path.is_file(), "overfull": None, "undefined": None}
    if log_path.is_file():
        log = log_path.read_text(encoding="utf-8", errors="replace")
        log_checks["overfull"] = "Overfull \\hbox" in log or "Overfull \\vbox" in log
        undefined_patterns = [
            "There were undefined references",
            "Citation `",
            "Reference `",
            "undefined citations",
        ]
        log_checks["undefined"] = any(pattern in log for pattern in undefined_patterns)
        require(not log_checks["overfull"], "LaTeX log contains overfull boxes")
        require(not log_checks["undefined"], "LaTeX log contains undefined citations or references")

    fonts = command(["pdffonts", str(pdf_path)]) if shutil.which("pdffonts") else None
    font_rows: list[str] = []
    if fonts is not None:
        require(fonts.returncode == 0, f"pdffonts failed: {fonts.stderr}")
        font_rows = [line for line in fonts.stdout.splitlines()[2:] if line.strip()]
        for line in font_rows:
            columns = line.split()
            if len(columns) >= 5:
                require(columns[-5].lower() == "yes", f"font is not embedded: {line}")

    rendered_pages = 0
    if args.render_dir is not None:
        render_dir = args.render_dir.resolve()
        if render_dir.exists():
            raise ValueError("Use a new render directory; existing contents are preserved.")
        render_dir.mkdir(parents=True)
        render = subprocess.run(
            ["pdftoppm", "-png", "-r", "120", str(pdf_path), str(render_dir / "page")],
            cwd=PAPER,
            capture_output=True,
            text=True,
            check=False,
        )
        require(render.returncode == 0, f"PDF rendering failed: {render.stderr}")
        rendered_pages = len(list(render_dir.glob("page-*.png")))
        require(rendered_pages == 12, f"expected 12 rendered pages, found {rendered_pages}")

    verification = {
        "status": "PASS",
        "title": "WheelGate: Context-Valid Qualification of Python Release Artifacts",
        "total_pages": 12,
        "main_content_pages": 10,
        "reference_only_pages": 2,
        "references_start_page": 11,
        "data_availability_page": 10,
        "reference_count": len(keys),
        "reference_categories": category_counts,
        "all_references_cited": True,
        "template_sha256": {
            "IEEEtran.cls": sha256(PAPER / "IEEEtran.cls"),
            "IEEEtran.bst": sha256(PAPER / "IEEEtran.bst"),
        },
        "source_sha256": {
            "main.tex": sha256(tex_path),
            "references.bib": sha256(bib_path),
            "main.pdf": sha256(pdf_path),
        },
        "pdfinfo": fields,
        "latex_log": log_checks,
        "embedded_font_rows": len(font_rows),
        "rendered_pages": rendered_pages,
        "visual_layout_review": {
            "completed": bool(args.visual_reviewed),
            "scope": "all 12 rendered pages" if args.visual_reviewed else "not asserted by automated verification",
            "result": "no visible clipping, overlap, or connector collision" if args.visual_reviewed else None,
        },
        "authors": AUTHORS,
    }
    (PAPER / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1)
