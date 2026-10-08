#!/usr/bin/env python3
"""Replay the selected WheelGate studies in a fresh package copy."""
from __future__ import annotations

import argparse
import datetime
import importlib.metadata as metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parents[1]
HAS_PAPER = ARTIFACT.name == 'artifact' and (ARTIFACT.parent / 'paper').is_dir()
PACKAGE = ARTIFACT.parent if HAS_PAPER else ARTIFACT
HOST_REQUIREMENTS = ("attrs", "click", "packaging", "pydantic")


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--compile-paper", action="store_true")
    parser.add_argument("--full-route", action="store_true")
    args = parser.parse_args()
    if args.compile_paper and not HAS_PAPER:
        parser.error('--compile-paper requires the companion paper directory')

    destination = args.workdir.expanduser().resolve()
    if destination.exists():
        parser.error("--workdir must not already exist")
    if destination == PACKAGE or destination in PACKAGE.parents or PACKAGE in destination.parents:
        parser.error("--workdir must be outside the delivered package")
    missing: list[str] = []
    for name in HOST_REQUIREMENTS:
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
    if missing:
        parser.error("missing host comparison dependencies: " + ", ".join(missing))

    copy_root = destination / "wheelgate"
    ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        "*.aux",
        "*.bbl",
        "*.blg",
        "*.log",
        "*.out",
        "*.fls",
        "*.fdb_latexmk",
        "reproduction-logs",
    )
    shutil.copytree(PACKAGE, copy_root, ignore=ignore)
    artifact = copy_root / "artifact" if HAS_PAPER else copy_root
    paper = copy_root / "paper"
    logs = copy_root / "reproduction-logs"
    logs.mkdir()
    (logs / "metadata.json").write_text(
        json.dumps(
            {
                "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": str(PACKAGE),
                "destination": str(copy_root),
                "python": sys.version,
                "full_route": args.full_route,
                "compile_paper": args.compile_paper,
                "scope": "Fresh-copy validation; regenerated observations are not pooled with retained study statistics.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    stages: list[tuple[str, list[str], Path]] = []
    stages.append(("source-unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], artifact))
    stages.append(("source-pytest", [sys.executable, "-m", "pytest", "-q"], artifact))

    remove(artifact / "results/footprint/matrix.json")
    remove(artifact / "results/footprint/assets")
    stages.append(("footprint", [sys.executable, "scripts/footprint_matrix.py"], artifact))

    remove(artifact / "results/historical/django-xml-replay.json")
    remove(artifact / "results/historical/assets")
    stages.append(("historical", [sys.executable, "scripts/historical_replay.py"], artifact))

    if args.full_route:
        remove(artifact / "results/routes/matrix.json")
        remove(artifact / "results/routes/routes-complete-assets")
        shutil.copyfile(artifact / "scripts/route_matrix.py", artifact / "results/routes/provenance/route_matrix.py")
        stages.append(("route-matrix", [sys.executable, "scripts/route_matrix.py"], artifact))

    remove(artifact / "results/routes/requalification.json")
    stages.append(("route-requalification", [sys.executable, "scripts/requalify_routes.py"], artifact))

    remove(artifact / "results/package/self-check.json")
    remove(artifact / "results/package/self-check-assets")
    stages.append(("installed-package", [sys.executable, "scripts/package_check.py"], artifact))
    stages.append(("summary", [sys.executable, "scripts/summarize.py"], artifact))
    if args.compile_paper:
        stages.append(("paper-build", ["sh", "build.sh"], paper))
        stages.append(
            (
                "paper-verify",
                [sys.executable, "scripts/verify_paper.py", "--render-dir", str(logs / "rendered-pages")],
                artifact,
            )
        )
    stages.append(
        (
            "audit",
            [sys.executable, "scripts/audit.py", *( ["--allow-unreviewed-pdf"] if args.compile_paper else ["--artifact-only"] )],
            artifact,
        )
    )

    outcomes: list[dict[str, object]] = []
    for name, argv, cwd in stages:
        started = time.perf_counter()
        process = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
        duration = time.perf_counter() - started
        log = (process.stdout or "") + ("\n--- STDERR ---\n" + process.stderr if process.stderr else "")
        (logs / f"{name}.txt").write_text(log, encoding="utf-8")
        if name == "source-unittest":
            (artifact / "results/validation").mkdir(parents=True, exist_ok=True)
            (artifact / "results/validation/source-tests.txt").write_text(log, encoding="utf-8")
        if name == "source-pytest":
            (artifact / "results/validation").mkdir(parents=True, exist_ok=True)
            (artifact / "results/validation/pytest.txt").write_text(log, encoding="utf-8")
        outcomes.append({"stage": name, "argv": argv, "returncode": process.returncode, "seconds": duration})
        (logs / "stages.json").write_text(json.dumps(outcomes, indent=2) + "\n", encoding="utf-8")
        if process.returncode != 0:
            print(f"stage failed: {name}; see {logs / (name + '.txt')}", file=sys.stderr)
            return process.returncode
        print(f"{name}: PASS ({duration:.2f}s)", flush=True)

    print(f"replay completed: {copy_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
