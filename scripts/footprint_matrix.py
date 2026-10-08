#!/usr/bin/env python3
"""Measure runtime-footprint qualification on authored context controls.

The controls are not historical defects.  They test whether a semantically
successful installed operation can be distinguished from execution that relies
on an undeclared distribution, a current-directory module, or a file generated
inside site-packages but absent from the installed distribution RECORD.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import statistics
import sys
import tempfile
import traceback
import venv

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate.runner import clean_env, execute, prepare, probe, venv_python

TARGET = '''from __future__ import annotations
import importlib
import json
import os
from pathlib import Path
import sys

__version__ = "1.0"

def render():
    from wg_helper import render_text
    return render_text("hello")

def shadow():
    Path("local_renderer.py").write_text("def render_text(text):\\n    return text.upper()\\n", encoding="utf-8")
    sys.path.insert(0, os.getcwd())
    importlib.invalidate_caches()
    from local_renderer import render_text
    return render_text("hello")

def generated():
    generated_path = Path(__file__).with_name("dynamic_extra.py")
    generated_path.write_text("def render_text(text):\\n    return text.upper()\\n", encoding="utf-8")
    importlib.invalidate_caches()
    from .dynamic_extra import render_text
    return render_text("hello")


def declared_data():
    return Path(__file__).with_name("message.txt").read_text(encoding="utf-8").strip()

def cwd_data():
    path = Path("settings.json")
    path.write_text(json.dumps({"message": "HELLO"}), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))["message"]

def generated_data():
    path = Path(__file__).with_name("runtime.json")
    path.write_text(json.dumps({"message": "HELLO"}), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))["message"]
'''

HELPER = '''def render_text(text):
    return text.upper()
'''

ORDINARY = '''import importlib.metadata as metadata
import json
import pathlib
import sys
import wg_footprint

operation, expected_helper = sys.argv[1:3]
origin = pathlib.Path(wg_footprint.__file__).resolve()
dist = metadata.distribution("wg-footprint")
owned = {pathlib.Path(dist.locate_file(item)).resolve() for item in dist.files or []}
assert origin in owned and origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
if expected_helper != "none":
    try:
        observed = metadata.version("wg-helper")
    except metadata.PackageNotFoundError:
        observed = None
    if observed != expected_helper:
        print("ORDINARY_FOOTPRINT=" + json.dumps({"status":"BLOCKED", "observed":observed}))
        raise SystemExit(2)
value = getattr(wg_footprint, operation)()
assert value == "HELLO", value
print("ORDINARY_FOOTPRINT=" + json.dumps({"status":"PASS", "value":value, "origin":str(origin)}))
'''


def contract(operation: str, declare_helper: bool) -> dict:
    profile = operation
    common = {
        "id": operation,
        "kind": "call",
        "distribution": "wg-footprint",
        "version": "1.0",
        "modules": ["wg_footprint"],
        "evidence": "Authored support contract for the runtime-footprint experiment",
        "profiles": [profile],
        "target": f"wg_footprint:{operation}",
        "equals": "HELLO",
    }
    spec = {"schema": 2, "contracts": [common]}
    if declare_helper:
        spec["profile_dependencies"] = {
            profile: [{
                "distribution": "wg-helper",
                "version": "1.0",
                "evidence": "Authored render-profile support statement",
            }]
        }
    return spec


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "results/footprint/matrix.json")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    output = args.output.resolve()
    if output.exists():
        parser.error("use a fresh output path")
    assets = output.parent / "assets"
    output.parent.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=False)

    record = {
        "schema": 1,
        "experiment": "runtime-code-and-data-footprint-controls",
        "scope": "Authored context-validity controls; not historical package defects",
        "status": "RUNNING",
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "repetitions": args.repetitions,
        "script_sha256": digest(pathlib.Path(__file__)),
        "commands": [],
        "runs": [],
    }

    def save() -> None:
        output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def required(argv, cwd, env):
        process = execute(argv, cwd, env, 120)
        record["commands"].append(process)
        if process["returncode"]:
            save()
            raise RuntimeError(process)
        return process

    try:
        with tempfile.TemporaryDirectory(prefix="wheelgate-footprint-") as temporary:
            temp = pathlib.Path(temporary)
            venv.EnvBuilder(with_pip=True).create(temp / "builder")
            python = venv_python(temp / "builder")
            (temp / "home").mkdir()
            environment = clean_env(temp / "home", python.parent)
            environment["SOURCE_DATE_EPOCH"] = "1704067200"
            required([
                python, "-I", "-m", "pip", "install", "--no-index", "--no-deps",
                ROOT / "third_party/setuptools-78.1.1-py3-none-any.whl",
            ], temp, environment)

            wheels: dict[str, pathlib.Path] = {}
            definitions = {
                "target": ("wg-footprint", "1.0", "wg_footprint", TARGET),
                "helper-1": ("wg-helper", "1.0", "wg_helper", HELPER),
                "helper-2": ("wg-helper", "2.0", "wg_helper", HELPER),
            }
            for key, (name, version, module, source_text) in definitions.items():
                source = assets / "sources" / key
                wheel_dir = assets / "wheels" / key
                (source / module).mkdir(parents=True)
                wheel_dir.mkdir(parents=True)
                (source / module / "__init__.py").write_text(source_text, encoding="utf-8")
                package_data = {}
                if key == "target":
                    (source / module / "message.txt").write_text("HELLO\n", encoding="utf-8")
                    package_data = {module: ["message.txt"]}
                (source / "setup.py").write_text(
                    "from setuptools import setup\n"
                    f"setup(name={name!r}, version={version!r}, packages=[{module!r}], "
                    f"package_data={package_data!r}, include_package_data=False)\n",
                    encoding="utf-8",
                )
                (source / "README.md").write_text(
                    "Authored runtime-footprint control; not a historical package.\n",
                    encoding="utf-8",
                )
                clean = temp / ("clean-" + key)
                shutil.copytree(source, clean)
                required([
                    python, "-I", "-c",
                    f"from setuptools.build_meta import build_wheel; build_wheel({str(wheel_dir)!r})",
                ], clean, environment)
                wheels[key] = next(wheel_dir.glob("*.whl"))

            (assets / "ordinary.py").write_text(ORDINARY, encoding="utf-8")
            cases = [
                {"id":"declared-helper", "operation":"render", "helper":"helper-1", "declare":True,
                 "ordinary_expected":"PASS", "gate_expected":"PASS", "guard":"1.0"},
                {"id":"undeclared-helper", "operation":"render", "helper":"helper-1", "declare":False,
                 "ordinary_expected":"PASS", "gate_expected":"INVALID", "guard":"none"},
                {"id":"wrong-helper-version", "operation":"render", "helper":"helper-2", "declare":True,
                 "ordinary_expected":"BLOCKED", "gate_expected":"BLOCKED", "guard":"1.0"},
                {"id":"cwd-shadow", "operation":"shadow", "helper":None, "declare":False,
                 "ordinary_expected":"PASS", "gate_expected":"INVALID", "guard":"none"},
                {"id":"generated-site-file", "operation":"generated", "helper":None, "declare":False,
                 "ordinary_expected":"PASS", "gate_expected":"INVALID", "guard":"none"},
                {"id":"declared-package-data", "operation":"declared_data", "helper":None, "declare":False,
                 "ordinary_expected":"PASS", "gate_expected":"PASS", "guard":"none"},
                {"id":"cwd-data-file", "operation":"cwd_data", "helper":None, "declare":False,
                 "ordinary_expected":"PASS", "gate_expected":"INVALID", "guard":"none"},
                {"id":"generated-site-data", "operation":"generated_data", "helper":None, "declare":False,
                 "ordinary_expected":"PASS", "gate_expected":"INVALID", "guard":"none"},
            ]
            for case in cases:
                (assets / f"contract-{case['id']}.json").write_text(
                    json.dumps(contract(case["operation"], case["declare"]), indent=2) + "\n",
                    encoding="utf-8",
                )

            # Environment creation dominates runtime and is not part of the measured
            # operation.  Reuse one clean prepared environment per dependency state;
            # every ordinary and gate operation still receives a fresh working directory
            # and a fresh interpreter process.
            prepared = {}
            for dependency_key in [None, "helper-1", "helper-2"]:
                environment_root = temp / ("prepared-" + (dependency_key or "none"))
                dependencies = [wheels[dependency_key]] if dependency_key else []
                subject, subject_env, setup = prepare(environment_root, wheels["target"], dependencies)
                if setup["status"] != "READY":
                    raise RuntimeError(setup)
                prepared[dependency_key] = (subject, subject_env, setup)

            for repetition in range(args.repetitions):
                for case in cases:
                    subject, subject_env, setup = prepared[case["helper"]]
                    work = temp / f"run-{repetition}-{case['id']}"
                    work.mkdir()
                    neutral = work / "ordinary"
                    neutral.mkdir()
                    ordinary_process = execute([
                        subject, "-I", assets / "ordinary.py", case["operation"], case["guard"],
                    ], neutral, subject_env)
                    ordinary_status = (
                        "PASS" if ordinary_process["returncode"] == 0 else
                        "BLOCKED" if ordinary_process["returncode"] == 2 else "FAIL"
                    )
                    specification = contract(case["operation"], case["declare"])
                    gate = probe(
                        specification, subject, subject_env, work / "gate",
                        profile=case["operation"], identity=setup["wheel_identity"],
                    )
                    if ordinary_status != case["ordinary_expected"]:
                        raise AssertionError((case, ordinary_status, ordinary_process))
                    if gate["status"] != case["gate_expected"]:
                        raise AssertionError((case, gate))
                    record["runs"].append({
                        "case": case["id"],
                        "repetition": repetition,
                        "operation": case["operation"],
                        "declared_helper": case["declare"],
                        "helper": case["helper"],
                        "target_sha256": digest(wheels["target"]),
                        "helper_sha256": digest(wheels[case["helper"]]) if case["helper"] else None,
                        "setup": setup,
                        "ordinary": {"status": ordinary_status, "process": ordinary_process},
                        "gate": gate,
                    })
                    save()
                    print(case["id"], repetition, ordinary_status, gate["status"], flush=True)

            gate_times = [run["gate"]["seconds"] for run in record["runs"]]
            record["summary"] = {
                "observations": len(record["runs"]),
                "ordinary_counts": {
                    value: sum(run["ordinary"]["status"] == value for run in record["runs"])
                    for value in ["PASS", "FAIL", "BLOCKED"]
                },
                "gate_counts": {
                    value: sum(run["gate"]["status"] == value for run in record["runs"])
                    for value in ["PASS", "FAIL", "INVALID", "BLOCKED"]
                },
                "median_gate_seconds": statistics.median(gate_times),
            }
            record["status"] = "COMPLETE"
    except Exception as exc:
        record["status"] = "INCOMPLETE"
        record["error"] = str(exc)
        record["traceback"] = traceback.format_exc()
        save()
        raise
    record["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
