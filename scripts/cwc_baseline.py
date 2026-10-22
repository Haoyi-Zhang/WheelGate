#!/usr/bin/env python3
"""Run the retained upstream check-wheel-contents implementation unchanged."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path
from evidence_paths import resolve_relative

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "third_party/source"
DEPENDENCIES = ("attrs", "click", "packaging", "pydantic")


def cwc_status(process: dict[str, object]) -> str:
    """Only exits 0/1 establish a CWC content decision; retain other failures."""
    if process.get("timeout"):
        return "BLOCKED"
    # execute() uses 127 when the process cannot be launched.
    return {0: "PASS", 1: "REJECT", 2: "CALLERROR", 127: "BLOCKED"}.get(
        process.get("returncode"), "INVALID"
    )


def verify_sources() -> None:
    """Verify every retained upstream source file against SHA-256 and Git blob ID."""
    rows = json.loads((SOURCES / "manifest.json").read_text(encoding="utf-8"))
    for row in rows:
        path = resolve_relative(SOURCES, row["path"])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError(f"Upstream source changed: {path}")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != row["git_blob_sha1"]:
            raise ValueError(f"Git blob mismatch: {path}")


def run_check(
    wheel: Path,
    *,
    package: tuple[Path, ...] = (),
    src_dir: tuple[Path, ...] = (),
    toplevel: tuple[str, ...] = (),
    package_omit: str | None = None,
    timeout: float = 60.0,
) -> dict[str, object]:
    """Execute upstream CWC from retained source and return a complete receipt."""
    verify_sources()
    source_paths = [
        str(SOURCES / "check-wheel-contents-0.6.1/src"),
        str(SOURCES / "wheel-filename-1.4.2/src"),
    ]
    launcher = (
        "import runpy,sys; "
        f"sys.path[:0]={source_paths!r}; "
        'runpy.run_module("check_wheel_contents",run_name="__main__")'
    )
    args = ["--no-config"]
    for name in toplevel:
        args += ["--toplevel", name]
    for path in package:
        args += ["--package", str(path.resolve())]
    for path in src_dir:
        args += ["--src-dir", str(path.resolve())]
    if package_omit is not None:
        args += ["--package-omit", package_omit]
    command = [sys.executable, "-I", "-c", launcher, *args, str(wheel.resolve())]
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        timed_out = False
        returncode = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="surrogateescape")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="surrogateescape")
    except OSError as exc:
        timed_out = False
        returncode = 127
        stdout = ""
        stderr = str(exc)
    receipt = {
        "argv": command,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "seconds": time.perf_counter() - started,
        "timeout": timed_out,
    }
    receipt["status"] = cwc_status(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="+", type=Path)
    parser.add_argument("--package", action="append", default=[], type=Path)
    parser.add_argument("--src-dir", action="append", default=[], type=Path)
    parser.add_argument("--toplevel", action="append", default=[])
    parser.add_argument("--package-omit")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    receipts = [
        {
            "wheel": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "process": run_check(
                path,
                package=tuple(args.package),
                src_dir=tuple(args.src_dir),
                toplevel=tuple(args.toplevel),
                package_omit=args.package_omit,
                timeout=args.timeout,
            ),
        }
        for path in args.wheel
    ]
    record = {
        "schema": 1,
        "tool": "check-wheel-contents",
        "version": "0.6.1",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_manifest": "third_party/source/manifest.json",
        "dependency_versions": {
            name: importlib.metadata.version(name) for name in DEPENDENCIES
        },
        "wheel_filename_version": "1.4.2",
        "runs": receipts,
    }
    rendered = json.dumps(record, indent=2) + "\n"
    if args.output is not None:
        if args.output.exists():
            parser.error("--output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    statuses = {row["process"]["status"] for row in receipts}
    if statuses - {"PASS", "REJECT"}:
        return 2
    return 1 if "REJECT" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
