#!/usr/bin/env python3
"""Compare the supplied WheelGate package's direct and sdist-derived releases.

This is a self-package packaging workflow, not a new external maintainer case.
Only the reviewed local package is built/installed. CWC reads the same wheels
and, in its reference preset, the same public module tree. Ordinary installed
operations and the gate use identical values and invoke the version command.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import platform
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate import __version__
from wheelgate.runner import clean_env, execute, prepare, probe
from cwc_baseline import verify_sources
from evidence_paths import resolve_relative


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contracts():
    common = {"distribution": "wheelgate", "version": __version__, "modules": ["wheelgate"],
              "evidence": "Supplied WheelGate runtime API, canonical name rule, and version command"}
    return {"schema": 2, "contracts": [
        dict(common, id="import", kind="import"),
        dict(common, id="canonical-name", kind="call", target="wheelgate.runner:normalized_name",
             args=["Wheel_Gate"], equals="wheel-gate"),
        dict(common, id="version-command", kind="cli", command="wheelgate", args=["--version"],
             equals="WheelGate " + __version__ + "\n"),
    ]}


ORDINARY = '''import importlib.metadata as md,json,pathlib,subprocess,sys
import wheelgate
from wheelgate.runner import normalized_name
dist=md.distribution("wheelgate")
inventory={pathlib.Path(dist.locate_file(p)).resolve() for p in dist.files or ()}
origin=pathlib.Path(wheelgate.__file__).resolve()
assert origin in inventory and origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert dist.version == wheelgate.__version__ == EXPECTED_VERSION
assert normalized_name("Wheel_Gate") == "wheel-gate"
command=pathlib.Path(sys.executable).parent / ("wheelgate.exe" if sys.platform=="win32" else "wheelgate")
assert command.resolve() in inventory
cp=subprocess.run([str(command),"--version"],capture_output=True,text=True,timeout=10)
assert cp.returncode==0, cp.stderr
assert cp.stdout == "WheelGate " + EXPECTED_VERSION + "\\n", repr(cp.stdout)
print(json.dumps({"origin":str(origin),"value":"wheel-gate","version_stdout":cp.stdout}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--comparison-wheel-dir", type=pathlib.Path,
                        help="Optional pure-Python dependency wheels read through zipimport, not installed")
    args = parser.parse_args()
    out = args.output.resolve()
    package_record = out.parent / "self-check.json"
    if any(p.exists() for p in (out, package_record, out.parent / "self-check-assets")):
        parser.error("use a fresh output and packaging record directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    verify_sources()
    dependency_paths = []
    dependencies = []
    if args.comparison_wheel_dir:
        for name in ("attrs-26.1.0-py3-none-any.whl", "click-8.1.8-py3-none-any.whl",
                     "colorama-0.4.6-py2.py3-none-any.whl", "packaging-25.0-py3-none-any.whl"):
            path = args.comparison_wheel_dir.resolve() / name
            with zipfile.ZipFile(path) as archive:
                if any(n.endswith((".pth", ".pyd", ".so")) for n in archive.namelist()):
                    raise ValueError("Comparison dependencies must be pure Python without startup hooks")
            dependency_paths.append(str(path))
            dependencies.append({"wheel": name, "sha256": digest(path)})
    sources = ROOT / "third_party/source"
    source_paths = [str(sources / "check-wheel-contents-0.6.1/src"),
                    str(sources / "wheel-filename-1.4.2/src")]
    cwc_launcher = (f"import runpy,sys;sys.path[:0]={source_paths + dependency_paths!r};"
                    "runpy.run_module('check_wheel_contents',run_name='__main__')")
    result = {"schema": 1, "experiment": "supplied-wheelgate-self-package-flow",
              "scope": "One owned software package, two release routes, no external maintainer deployment",
              "status": "RUNNING", "script_sha256": digest(pathlib.Path(__file__)),
              "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "python": sys.version, "platform": platform.platform(),
              "comparison_dependencies": dependencies,
              "source_manifest_sha256": digest(sources / "manifest.json"), "runs": []}
    def save():
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    save()
    with tempfile.TemporaryDirectory(prefix="wheelgate-self-flow-") as td:
        temp = pathlib.Path(td)
        home = temp / "home"; home.mkdir()
        env = clean_env(home, pathlib.Path(sys.executable).parent)
        # Share the caller's temporary root instead of nesting a builder venv
        # under this flow's temporary home (Windows path-length limits matter).
        env.update({key: tempfile.gettempdir() for key in ("TEMP", "TMP", "TMPDIR")})
        package = execute([sys.executable, "-B", ROOT / "scripts/package_check.py",
                           "--output", package_record], ROOT, env, timeout=120)
        result["package_process"] = package
        if package["returncode"] != 0 or package["timeout"]:
            result["status"] = "INCOMPLETE"; save(); return 1
        record = json.loads(package_record.read_text(encoding="utf-8"))
        if record["status"] != "COMPLETE" or not record["payloads_equal"]:
            raise AssertionError("Package-flow precondition failed")
        result["package_record"] = {"file": "self-check.json", "sha256": digest(package_record)}
        version_code = (f"import importlib.metadata as m,sys;sys.path[:0]={dependency_paths!r};"
                        "import json;print(json.dumps({n:m.version(n) for n in ['attrs','click','packaging','pydantic']}))")
        versions = execute([sys.executable, "-I", "-B", "-c", version_code], temp, env)
        if versions["returncode"] != 0: raise RuntimeError(versions)
        result["dependency_versions"] = json.loads(versions["stdout"])
        for index, row in enumerate(record["routes"]):
            wheel = resolve_relative(package_record.parent, row["wheel"])
            if digest(wheel) != row["sha256"]: raise ValueError("Software wheel hash drift")
            subject, subject_env, setup = prepare(temp / str(index), wheel)
            if setup["status"] != "READY": raise RuntimeError(setup)
            neutral = temp / f"ordinary-{index}"; neutral.mkdir()
            ordinary = execute([subject, "-I", "-c", "EXPECTED_VERSION=" + repr(__version__) + "\n" + ORDINARY],
                               neutral, subject_env)
            gate = probe(contracts(), subject, subject_env, temp / f"gate-{index}", identity=setup["wheel_identity"])
            checks = {}
            for preset in ("default", "reference"):
                opts = ["--no-config"]
                if preset == "reference":
                    opts += ["--toplevel", "wheelgate", "--package", str(ROOT / "wheelgate"),
                             "--package-omit", ".*,CVS,RCS,*.pyc,*.pyo,*.egg-info,__pycache__"]
                cp = execute([sys.executable, "-I", "-B", "-c", cwc_launcher, *opts, wheel], neutral, env)
                status = ("INVALID" if cp["timeout"] else
                          {0: "PASS", 1: "REJECT"}.get(cp["returncode"], "BLOCKED"))
                checks[preset] = {"status": status, "process": cp}
            result["runs"].append({"route": row["route"], "wheel": row["wheel"], "sha256": row["sha256"],
                                   "setup": setup, "unit_tests": row["unit_tests"],
                                   "ordinary": {"status": "PASS" if ordinary["returncode"] == 0 else "FAIL", "process": ordinary},
                                   "gate": gate, "cwc": checks})
            save()
            print(row["route"], result["runs"][-1]["ordinary"]["status"], gate["status"],
                  {p: c["status"] for p, c in checks.items()}, flush=True)
    result["status"] = "COMPLETE"
    result["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
