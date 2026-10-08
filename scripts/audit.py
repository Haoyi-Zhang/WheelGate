#!/usr/bin/env python3
"""Audit the retained WheelGate evidence, software package, and manuscript."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAPER = ROOT.parent / "paper"
VALIDATION = ROOT / "results/validation"
TEST_COUNT = unittest.TestLoader().discover(str(ROOT/'tests')).countTestCases()


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_process(process: dict, expected: int | None) -> None:
    require(process.get("timeout") is False, f"unexpected timeout: {process.get('argv')}")
    require(process.get("returncode") == expected, f"unexpected exit: {process.get('argv')}")


def audit_wheel(path: Path) -> None:
    require(path.is_file(), f"missing wheel: {path}")
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, f"CRC error: {path}")
        names = archive.namelist()
        require(len(names) == len(set(names)), f"duplicate ZIP members: {path}")
        record_names = [name for name in names if name.endswith(".dist-info/RECORD") and name.count("/") == 1]
        require(len(record_names) == 1, f"one root RECORD required: {path}")
        rows = list(csv.reader(io.StringIO(archive.read(record_names[0]).decode("utf-8"))))
        recorded = set()
        for row in rows:
            require(len(row) == 3, f"invalid RECORD row in {path}: {row}")
            name, checksum, size = row
            require(name in names, f"RECORD member missing from archive: {path}: {name}")
            recorded.add(name)
            content = archive.read(name)
            if size:
                require(len(content) == int(size), f"RECORD size mismatch: {path}: {name}")
            if checksum:
                algorithm, encoded = checksum.split("=", 1)
                require(algorithm == "sha256", f"unsupported RECORD hash: {path}: {algorithm}")
                actual = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
                require(actual == encoded, f"RECORD hash mismatch: {path}: {name}")
        require(all(name.endswith("/") or name in recorded for name in names), f"unrecorded archive member: {path}")


def resolve_result_path(record_file: Path, value: str) -> Path:
    relative = Path(value)
    if relative.parts and relative.parts[0] == "results":
        return (ROOT / relative).resolve()
    return (record_file.parent / relative).resolve()


def audit_third_party() -> dict[str, int]:
    manifest = load(ROOT / "third_party/manifest.json")
    require(isinstance(manifest, list) and len(manifest) == 4, "four retained wheel inputs required")
    wheel_names = set()
    for row in manifest:
        path = ROOT / "third_party" / row["file"]
        require(path.stat().st_size == row["bytes"], f"third-party size mismatch: {path.name}")
        require(sha256(path) == row["sha256"], f"third-party hash mismatch: {path.name}")
        audit_wheel(path)
        wheel_names.add(row["file"])
    licences = load(ROOT / "third_party/license-index.json")
    require({row["wheel"] for row in licences} == wheel_names, "licence index does not cover retained wheels")
    for row in licences:
        with zipfile.ZipFile(ROOT / "third_party" / row["wheel"]) as archive:
            for member in row["license_members"]:
                require(member in archive.namelist(), f"missing retained licence member: {member}")
    comparison = load(ROOT / "corpus/registry-comparison.json")
    require(len(comparison) == 4, "registry comparison requires four records")
    manifest_by_name = {row["file"]: row for row in manifest}
    for row in comparison:
        local = manifest_by_name[row["file"]]
        require(row["local_sha256"] == local["sha256"], f"registry comparison local hash drift: {row['file']}")
        require(row["archive_equal"] == (row["local_sha256"] == row["pypi_reported_sha256"]), f"registry comparison classification mismatch: {row['file']}")
    sources = load(ROOT / "third_party/source/manifest.json")
    require(isinstance(sources, list) and len(sources) == 14, "fourteen retained upstream source files required")
    for row in sources:
        path = ROOT / "third_party/source" / row["path"]
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == row["sha256"], f"source SHA-256 mismatch: {row['path']}")
        git_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(git_blob == row["git_blob_sha1"], f"source Git blob mismatch: {row['path']}")
    return {"retained_wheels": len(manifest), "upstream_source_files": len(sources)}


def audit_footprint() -> dict[str, int]:
    path = ROOT / "results/footprint/matrix.json"
    record = load(path)
    require(record["status"] == "COMPLETE", "footprint experiment incomplete")
    require(record["script_sha256"] == sha256(ROOT / "scripts/footprint_matrix.py"), "footprint script drift")
    runs = record["runs"]
    require(len(runs) == 24, "footprint matrix must contain 24 observations")
    require(len({(row["case"], row["repetition"]) for row in runs}) == 24, "duplicate footprint observation")
    ordinary = Counter(row["ordinary"]["status"] for row in runs)
    gate = Counter(row["gate"]["status"] for row in runs)
    require(dict(ordinary) == {"PASS": 21, "BLOCKED": 3}, f"footprint ordinary counts changed: {ordinary}")
    require(dict(gate) == {"PASS": 6, "INVALID": 15, "BLOCKED": 3}, f"footprint gate counts changed: {gate}")
    module_invalid = 0
    file_only_invalid = 0
    for row in runs:
        contract = row["gate"].get("contracts", [{}])[0]
        module_violations = contract.get("footprint", {}).get("violations", [])
        file_violations = contract.get("file_footprint", {}).get("violations", [])
        if row["gate"]["status"] == "INVALID" and module_violations:
            module_invalid += 1
        if row["gate"]["status"] == "INVALID" and not module_violations and file_violations:
            file_only_invalid += 1
        expected_exit = {"PASS": 0, "BLOCKED": 2}[row["ordinary"]["status"]]
        check_process(row["ordinary"]["process"], expected_exit)
    require(module_invalid == 9, f"module-footprint invalid count changed: {module_invalid}")
    require(file_only_invalid == 6, f"file-footprint invalid count changed: {file_only_invalid}")
    for wheel in (ROOT / "results/footprint/assets/wheels").rglob("*.whl"):
        audit_wheel(wheel)
    return {
        "observations": len(runs),
        "ordinary_pass": ordinary["PASS"],
        "gate_invalid": gate["INVALID"],
        "module_invalid": module_invalid,
        "file_only_invalid": file_only_invalid,
    }


def audit_historical() -> dict[str, int]:
    path = ROOT / "results/historical/django-xml-replay.json"
    record = load(path)
    require(record["status"] == "COMPLETE", "historical replay incomplete")
    require(record["classification"].startswith("configuration-faithful replay"), "historical replay classification changed")
    require(record["script_sha256"] == sha256(ROOT / "scripts/historical_replay.py"), "historical replay script drift")
    evidence = record["evidence"]
    require(evidence["affected_source_commit"] == "30112f19d9b3f21ccfe0986350efac17098c065b", "affected source commit changed")
    require(evidence["fix_commit"] == "37f6ed3d6b246b129c35f8aba4dbf69b34a83b28", "fix commit changed")
    require(evidence["fixed_tag_commit"] == "a73655714f68093c2d22ea384585a5b26341c561", "fixed tag commit changed")
    runs = record["runs"]
    require(len(runs) == 6, "historical replay must contain six observations")
    for row in runs:
        check_process(row["checkout"], 0)
        require(row["setup"]["status"] == "READY", "historical setup failed")
        expected = "FAIL" if row["variant"] == "affected" else "PASS"
        require(row["ordinary"]["status"] == expected, f"historical ordinary status changed: {row['variant']}")
        require(row["gate"]["status"] == expected, f"historical gate status changed: {row['variant']}")
        check_process(row["ordinary"]["process"], 1 if expected == "FAIL" else 0)
        require(row["cwc"]["default"]["status"] == "PASS", "default CWC outcome changed")
        require(row["cwc"]["reference"]["status"] == ("REJECT" if row["variant"] == "affected" else "PASS"), "reference CWC outcome changed")
        require(row["check_manifest"]["status"] == "BLOCKED", "historical check-manifest block changed")
    wheel_dir = ROOT / "results/historical/assets/wheels"
    affected = wheel_dir / "affected/django_xml-4.0.0-py3-none-any.whl"
    fixed = wheel_dir / "fixed/django_xml-4.0.1-py3-none-any.whl"
    audit_wheel(affected)
    audit_wheel(fixed)
    hashes = {
        "affected": sha256(affected),
        "fixed": sha256(fixed),
    }
    for variant, expected_hash in hashes.items():
        require({row["replay_wheel_sha256"] for row in runs if row["variant"] == variant} == {expected_hash}, f"historical wheel hash drift: {variant}")
    case_register = load(ROOT / "corpus/case-register.json")
    require(case_register["maintainer_linked_configuration_replays"] == 1, "case register replay count changed")
    require(case_register["publisher_artifact_replays"] == 0, "publisher artifact replay was inferred")
    django = next(row for row in case_register["records"] if row["id"] == "D3")
    require(django["configuration_replay_completed"] is True and django["publisher_artifact_replayed"] is False, "django-xml evidence boundary changed")
    return {"observations": len(runs), "configuration_replays": 1, "publisher_artifact_replays": 0}


def audit_routes() -> dict[str, int]:
    path = ROOT / "results/routes/matrix.json"
    record = load(path)
    require(record["status"] == "COMPLETE", "route experiment incomplete")
    provenance = ROOT / "results/routes/provenance/route_matrix.py"
    if not provenance.is_file():
        provenance = ROOT / 'scripts/route_matrix.py'
    require(record["script_sha256"] == sha256(provenance), "retained route script does not match selected record")
    runs = record["runs"]
    require(len(runs) == 45, "route matrix must contain 45 observations")
    expected_ids = {(state, route, rep) for state in "UXR" for route in ["checkout", "editable", "strict-editable", "direct-wheel", "sdist-wheel"] for rep in range(3)}
    require({(row["state"], row["route"], row["repetition"]) for row in runs} == expected_ids, "route matrix identities incomplete")
    expected_status = {
        ("U", "checkout"): "PASS", ("U", "editable"): "PASS", ("U", "strict-editable"): "FAIL", ("U", "direct-wheel"): "FAIL", ("U", "sdist-wheel"): "FAIL",
        ("X", "checkout"): "PASS", ("X", "editable"): "PASS", ("X", "strict-editable"): "PASS", ("X", "direct-wheel"): "PASS", ("X", "sdist-wheel"): "FAIL",
        ("R", "checkout"): "PASS", ("R", "editable"): "PASS", ("R", "strict-editable"): "PASS", ("R", "direct-wheel"): "PASS", ("R", "sdist-wheel"): "PASS",
    }
    wheel_rows = []
    for row in runs:
        require(row["ordinary_status"] == expected_status[(row["state"], row["route"])], f"route outcome changed: {row['state']}/{row['route']}")
        check_process(row["ordinary"], 0 if row["ordinary_status"] == "PASS" else 1)
        if row["route"] in {"direct-wheel", "sdist-wheel"}:
            wheel_rows.append(row)
            wheel_path = resolve_result_path(path, row["wheel"])
            require(sha256(wheel_path) == row["sha256"], f"route wheel hash drift: {wheel_path}")
            audit_wheel(wheel_path)
            require(row["setup"]["status"] == "READY", "route wheel setup failed")
            check_process(row["smoke"], 0)
            require(row["gate"]["status"] == row["ordinary_status"], "route gate/baseline disagreement")
            require(set(row["content_checks"]) == {"default", "reference-tree"}, "route CWC presets changed")
            for preset, item in row["content_checks"].items():
                check_process(item["process"], 0 if item["status"] == "PASS" else 1)
                require(("--package" in item["process"]["argv"]) == (preset == "reference-tree"), "CWC reference preset changed")
        elif row["route"] in {"editable", "strict-editable"}:
            require(row["gate"]["status"] == "NOT_APPLICABLE", "development install was qualified as a release artifact")
    require(len(wheel_rows) == 18, "route wheel comparison count changed")
    require(sum(len(row["content_checks"]) for row in wheel_rows) == 36, "CWC command count changed")

    manifest = record["manifest_runs"]
    require(len(manifest) == 9, "check-manifest command count changed")
    for row in manifest:
        require(row["version"] == "0.50" and row["build_route"].startswith("legacy"), "check-manifest execution label changed")
        check_process(row["process"], 1 if row["state"] == "U" else 0)
        require("building an sdist" in row["process"]["stdout"] and "building a clean sdist" in row["process"]["stdout"], "check-manifest did not perform both archive builds")
    modern = record["modern_frontend_attempt"]
    require(modern["status"] == "BLOCKED" and modern["included_in_legacy_comparison"] is False, "blocked modern check-manifest path was scored")
    check_process(modern["process"], 2)
    require("No module named build" in modern["process"]["stderr"], "modern check-manifest blocking reason changed")

    requal_path = ROOT / "results/routes/requalification.json"
    requal = load(requal_path)
    require(requal["status"] == "COMPLETE" and len(requal["runs"]) == 10, "route requalification incomplete")
    require(requal["source_route_record_sha256"] == sha256(path), "route requalification is not bound to selected route record")
    statuses = Counter(row["gate"]["status"] for row in requal["runs"])
    require(statuses == Counter({"PASS": 5, "FAIL": 5}), f"route requalification outcomes changed: {statuses}")
    for row in requal["runs"]:
        wheel = resolve_result_path(path, row["wheel"])
        require(sha256(wheel) == row["sha256"], f"requalification wheel hash drift: {wheel}")
        require(row["gate"]["status"] == row["expected"], "requalification expected status changed")
    return {
        "route_observations": len(runs),
        "wheel_route_agreements": len(wheel_rows),
        "cwc_commands": 36,
        "check_manifest_legacy_commands": 9,
        "route_requalifications": len(requal["runs"]),
    }


def audit_package() -> dict[str, object]:
    path = ROOT / "results/package/self-check.json"
    record = load(path)
    require(record["status"] == "COMPLETE", "software package check incomplete")
    require(record["script_sha256"] == sha256(ROOT / "scripts/package_check.py"), "package-check script drift")
    require(record["payloads_equal"] is True and len(record["routes"]) == 2, "software package routes incomplete")
    unit_counts: list[int] = []
    wheel_hashes: set[str] = set()
    for row in record["routes"]:
        wheel = resolve_result_path(path, row["wheel"])
        require(sha256(wheel) == row["sha256"], f"software wheel hash drift: {wheel}")
        audit_wheel(wheel)
        wheel_hashes.add(row["sha256"])
        require(row["setup"]["status"] == "READY", "software wheel setup failed")
        for key in ["identity", "unit_tests", "cli"]:
            check_process(row[key], 0)
        identity = json.loads(row["identity"]["stdout"])
        require(identity["version"] == "1.0.0" and "/site-packages/wheelgate/" in identity["module"].replace('\\','/'), "installed software identity changed")
        test_output = row["unit_tests"]["stdout"] + row["unit_tests"]["stderr"]
        match = re.search(r"Ran (\d+) tests", test_output)
        require(match is not None and int(match.group(1)) == TEST_COUNT and "\nOK" in test_output, "installed test suite result changed")
        unit_counts.append(int(match.group(1)))
        for name, expected_hash in row["package_payload"].items():
            require(sha256(ROOT / name) == expected_hash, f"installed package differs from source: {name}")
        smoke = {entry["condition"]: entry for entry in row["semantic_smoke"]}
        require(smoke["good"]["process"]["returncode"] == 0, "healthy fixture smoke failed")
        require(smoke["missing"]["process"]["returncode"] == 1, "missing-resource fixture was not rejected")
        require(smoke["good"]["report"]["status"] == "PASS", "healthy report status changed")
        require(smoke["missing"]["report"]["status"] == "FAIL", "missing report status changed")
    require(len(wheel_hashes) == 1, "direct and sdist-derived software wheel bytes differ")
    sdist = ROOT / "results/package/self-check-assets/sdist/wheelgate-1.0.0.tar.gz"
    require(sdist.is_file(), "software sdist missing")
    source_log = (VALIDATION / "source-tests.txt").read_text(encoding="utf-8")
    source_match = re.search(r"Ran (\d+) tests", source_log)
    require(source_match and int(source_match.group(1)) == TEST_COUNT and "\nOK" in source_log, "source unit-test log missing or stale")
    pytest_log = (VALIDATION / "pytest.txt").read_text(encoding="utf-8")
    require(f"{TEST_COUNT} passed, 6 subtests passed" in pytest_log, "pytest/subtest log missing or stale")
    return {"installation_routes": 2, "unit_tests_per_route": unit_counts, "software_wheel_sha256": next(iter(wheel_hashes))}


def audit_paper_and_summary(*, allow_unreviewed_pdf: bool = False) -> dict[str, object]:
    summary = load(ROOT / "results/summary.json")
    expected_macros = {
        "RouteObservations": 45,
        "HistoricalObservations": 6,
        "FootprintObservations": 24,
        "RouteRequalifications": 10,
        "RegressionTests": TEST_COUNT,
        "FootprintInvalid": 15,
        "FootprintModuleInvalid": 9,
        "FootprintFileInvalid": 6,
        "FootprintOrdinaryPass": 21,
    }
    require(summary["macros"] == expected_macros, "summary macros changed")
    numbers = (PAPER / "generated/numbers.tex").read_text(encoding="utf-8")
    for name, value in expected_macros.items():
        require(f"\\newcommand{{\\{name}}}{{{value}}}" in numbers, f"paper macro drift: {name}")
    verification = load(PAPER / "verification.json")
    require(verification["status"] == "PASS", "paper verification failed")
    require(verification["total_pages"] == 12 and verification["main_content_pages"] == 10 and verification["reference_only_pages"] == 2, "paper page budget changed")
    require(verification["reference_count"] == 70 and verification["reference_categories"]["research"] == 16, "reference counts changed")
    if not allow_unreviewed_pdf:
        require(verification["visual_layout_review"]["completed"] is True, "visual PDF review not recorded")
    for name in ["main.tex", "references.bib", "main.pdf"]:
        require(verification["source_sha256"][name] == sha256(PAPER / name), f"paper verification hash drift: {name}")
    return {
        "pages": 12,
        "main_pages": 10,
        "reference_pages": 2,
        "references": 70,
        "research_references": 16,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-unreviewed-pdf", action="store_true", help="Permit a freshly compiled replay whose pages have not yet been visually inspected")
    parser.add_argument('--artifact-only', action='store_true', help='Check software and results without requiring companion manuscript files')
    args = parser.parse_args()
    third_party = audit_third_party()
    footprint = audit_footprint()
    historical = audit_historical()
    routes = audit_routes()
    package = audit_package()
    paper = None if args.artifact_only else audit_paper_and_summary(allow_unreviewed_pdf=args.allow_unreviewed_pdf)
    environment = load(ROOT / "results/environment.json")
    require(environment["implementation"] == "CPython", "execution environment record changed")
    result = {
        "status": "PASS",
        "scope": "Internal consistency and reproducibility audit; not independent peer review or a guarantee of acceptance.",
        "third_party": third_party,
        "footprint": footprint,
        "historical": historical,
        "routes": routes,
        "package": package,
        "paper": paper,
        "selected_record_sha256": {
            "footprint": sha256(ROOT / "results/footprint/matrix.json"),
            "historical": sha256(ROOT / "results/historical/django-xml-replay.json"),
            "routes": sha256(ROOT / "results/routes/matrix.json"),
            "route_requalification": sha256(ROOT / "results/routes/requalification.json"),
            "package": sha256(ROOT / "results/package/self-check.json"),
        },
    }
    VALIDATION.mkdir(parents=True, exist_ok=True)
    (VALIDATION / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        failure = {"status": "FAIL", "error": str(exc)}
        VALIDATION.mkdir(parents=True, exist_ok=True)
        (VALIDATION / "audit.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2), file=sys.stderr)
        raise SystemExit(1)
