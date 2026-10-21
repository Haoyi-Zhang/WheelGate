"""Replay three retained publisher subjects through the unchanged public CLI.

Default: verify local bytes and print a plan, with no installation/execution.
--execute is a separate, explicitly requested native run. It needs seven pinned
local dependency wheels and a fresh short TEMP root on CPython3.12/Windows AMD64.
It does not download, time a new campaign, or rewrite retained study records.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate.runner import canonical_contract_digest, wheel_identity

CASES = (("django-xml", "4.0.0", "FAIL"), ("django-xml", "4.0.1", "PASS"),
         ("latex2pydata", "0.5.0", "PASS"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_file(path, row):
    path = Path(path).resolve()
    if path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
        raise ValueError("Input size/hash mismatch: " + path.name)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Input CRC mismatch: " + path.name)
    return path


def plan(dependency_dir):
    evidence = ROOT / "evidence/publisher-wheels"
    inventory = json.loads((evidence / "source-inventory.json").read_text(encoding="utf-8"))
    bindings = inventory["runtime_source_bindings"]
    for binding in bindings:
        runtime = ROOT / binding["file"].removeprefix("artifact/")
        if sha(runtime) != binding["sha256"]:
            raise ValueError("Retained runtime source differs: " + binding["file"])
    prerequisites = [row for row in inventory["inputs"] if row.get("input_kind") == "publisher-download"]
    if len(prerequisites) != 7:
        raise ValueError("Expected the seven selected prerequisite downloads")
    dependencies = [verified_file(Path(dependency_dir) / Path(row["download_destination"]).name, row)
                    for row in prerequisites]
    subjects = {(row["project"], row["version"]): row for row in inventory["inputs"]
                if row["role"] == "selected original subject wheel"}
    rows = []
    for name, version, expected in CASES:
        row = subjects[(name, version)]
        wheel = verified_file(evidence / row["file"], row)
        contract = ROOT / "contracts" / ("publisher-" + name + "-" + version + ".json")
        spec = json.loads(contract.read_text(encoding="utf-8"))
        profile = "replay-cp312-win-amd64" if name == "django-xml" else "base"
        identity = wheel_identity(wheel)
        if identity["version"] != version:
            raise ValueError("Unexpected original subject version")
        rows.append({"case": name + "-" + version, "wheel": str(wheel),
                     "sha256": row["sha256"], "contract": str(contract),
                     "contract_sha256": canonical_contract_digest(spec), "profile": profile,
                     "dependencies": [str(p) for p in dependencies] if name == "django-xml" else [],
                     "expected_status": expected})
    return {"status": "verified-local-input-plan", "cases": rows,
            "dependency_inputs": [{"file": str(p), "sha256": row["sha256"], "bytes": row["bytes"]}
                                  for p, row in zip(dependencies, prerequisites, strict=True)],
            "runtime_source_bindings": bindings,
            "scope": "Public CLI reachability on3 original inputs, no repetitions. Seven dependencies are external local inputs, not bundled by the artifact."}


def child_environment(temp_root):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(TEMP=str(temp_root), TMP=str(temp_root), TMPDIR=str(temp_root),
               PYTHONDONTWRITEBYTECODE="1", PIP_NO_INDEX="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_CACHE_DIR="1")
    return env


def case_matches(case, receipt, returncode):
    expected = case["expected_status"]
    return (receipt.get("status") == expected
            and returncode == {"PASS": 0, "FAIL": 1}[expected]
            and receipt.get("setup", {}).get("status") == "READY"
            and receipt.get("profile_preflight", {}).get("status") == "READY"
            and receipt.get("sha256") == case["sha256"]
            and receipt.get("contract_sha256") == case["contract_sha256"]
            and len(receipt.get("contracts", [])) == 1
            and receipt["contracts"][0].get("status") == expected)


def execute_plan(planned, output_dir, temp_root):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise ValueError("Execution requires the selected CPython3.12 Windows AMD64 profile")
    output_dir, temp_root = Path(output_dir).resolve(), Path(temp_root).resolve()
    if output_dir.exists() or temp_root.exists():
        raise ValueError("Output and short TEMP directories must both be fresh")
    # Only caller-selected fresh directories are created; no existing tree is removed.
    temp_root.mkdir(parents=False)
    output_dir.mkdir(parents=True)
    env = child_environment(temp_root)
    rows = []
    for case in planned["cases"]:
        target = output_dir / (case["case"] + "-public-cli.json")
        argv = [sys.executable, "-B", "-m", "wheelgate", case["wheel"], case["contract"],
                "--profile", case["profile"], "--output", str(target)]
        for dependency in case["dependencies"]:
            argv.extend(["--dependency", dependency])
        row = {"case": case["case"], "expected_status": case["expected_status"], "argv": argv,
               "cwd": str(ROOT), "temp_root": str(temp_root), "entry_route": "public python -m wheelgate"}
        try:
            completed = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", timeout=300)
            row.update(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
            captured = target.read_bytes() if target.exists() else None
            receipt = json.loads(captured.decode("utf-8")) if captured is not None else {}
            row.update(status=receipt.get("status", "INVALID"),
                       matches_expected=case_matches(case, receipt, completed.returncode),
                       raw_receipt=str(target))
            if captured is not None:
                row.update(raw_receipt_sha256=hashlib.sha256(captured).hexdigest(),
                           raw_receipt_bytes=len(captured))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            row.update(status="BLOCKED", matches_expected=False, error=type(exc).__name__ + ": " + str(exc))
        rows.append(row)
        (output_dir / "progress.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = {**planned, "status": "executed", "python": sys.version, "platform": platform.platform(),
              "script_sha256": sha(__file__), "results": rows,
              "all_expected": all(row["matches_expected"] for row in rows),
              "receipt_representation": "execution-capture",
              "receipt_identity_scope": "raw_receipt_sha256 and raw_receipt_bytes bind the fresh child output as read. This generator does not normalize receipt paths. A subsequently path-normalized public copy needs its own current byte identity, distinct from any recorded pre-normalization identity.",
              "scope": "3 public CLI observations, kept separate from retained6/45/24studies and previous manual-stage results. Child receipts contain their ordinary elapsed fields; no new performance claim."}
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--temp-root", type=Path)
    args = parser.parse_args()
    planned = plan(args.dependency_dir)
    if not args.execute:
        print(json.dumps(planned, indent=2))
        return 0
    if args.output_dir is None or args.temp_root is None:
        parser.error("--execute needs --output-dir and a fresh short --temp-root")
    result = execute_plan(planned, args.output_dir, args.temp_root)
    print(json.dumps({"status": result["status"], "all_expected": result["all_expected"]}, indent=2))
    return 0 if result["all_expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
