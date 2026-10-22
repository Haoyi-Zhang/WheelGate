#!/usr/bin/env python3
"""Execute a maintainer-linked replay of the django-xml packaging regression.

The public report states that release 4.0.0 contained only djxml/__init__.py;
the maintainer fix changed setuptools package selection from ["djxml"] to
finding djxml*, yanked 4.0.0, and released 4.0.1.  Network restrictions in the
execution environment prevented retrieval of the original PyPI wheel bytes.
This experiment therefore replays the exact package-selection difference on a
minimal dependency-free tree with the same distribution/package names.  It is
reported as a configuration-faithful replay, not as execution of the publisher
artifacts.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import pathlib
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import venv

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate.runner import clean_env, execute, prepare, probe
from cwc_baseline import verify_sources

ISSUE = "https://github.com/theatlantic/django-xml/issues/18"
FIX_COMMIT = "37f6ed3d6b246b129c35f8aba4dbf69b34a83b28"
AFFECTED_SOURCE_COMMIT = "30112f19d9b3f21ccfe0986350efac17098c065b"
FIXED_TAG_COMMIT = "a73655714f68093c2d22ea384585a5b26341c561"

PACKAGE_INIT = '''__version__ = VERSION\n'''
SUBPACKAGE = '''def consumer():\n    return "available"\n'''
ORDINARY = '''import importlib.metadata as metadata
import pathlib
import sys
import djxml.xmlmodels
origin = pathlib.Path(djxml.xmlmodels.__file__).resolve()
dist = metadata.distribution("django-xml")
owned = {pathlib.Path(dist.locate_file(item)).resolve() for item in dist.files or []}
assert origin in owned and origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert djxml.xmlmodels.consumer() == "available"
print("DJANGO_XML_OPERATION=available")
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_source(root: pathlib.Path, version: str, fixed: bool) -> None:
    (root / "djxml/xmlmodels/fields").mkdir(parents=True)
    (root / "djxml/__init__.py").write_text(PACKAGE_INIT.replace("VERSION", repr(version)), encoding="utf-8")
    (root / "djxml/xmlmodels/__init__.py").write_text(SUBPACKAGE, encoding="utf-8")
    (root / "djxml/xmlmodels/fields/__init__.py").write_text("FIELD_MARKER = True\n", encoding="utf-8")
    if fixed:
        setup = (
            "from setuptools import find_packages, setup\n"
            f"setup(name='django-xml', version={version!r}, packages=find_packages(include=['djxml*']))\n"
        )
    else:
        setup = (
            "from setuptools import setup\n"
            f"setup(name='django-xml', version={version!r}, packages=['djxml'])\n"
        )
    (root / "setup.py").write_text(setup, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools==78.1.1"]\nbuild-backend="setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "Maintainer-linked configuration replay for django-xml issue 18; not the original release source archive.\n",
        encoding="utf-8",
    )


def contract(version: str) -> dict:
    return {
        "schema": 2,
        "contracts": [{
            "id": "documented-subpackage-import",
            "kind": "call",
            "distribution": "django-xml",
            "version": version,
            "modules": ["djxml.xmlmodels"],
            "evidence": "django-xml issue 18 and maintainer fix commit",
            "target": "djxml.xmlmodels:consumer",
            "equals": "available",
        }],
    }


def cwc_process(wheel: pathlib.Path, package: pathlib.Path, reference: bool, work: pathlib.Path) -> dict:
    verify_sources()
    sources = ROOT / "third_party/source"
    paths = [
        str(sources / "check-wheel-contents-0.6.1/src"),
        str(sources / "wheel-filename-1.4.2/src"),
    ]
    launcher = f"import sys,runpy; sys.path[:0]={paths!r}; runpy.run_module('check_wheel_contents',run_name='__main__')"
    options = ["--no-config"]
    if reference:
        options += [
            "--toplevel", "djxml", "--package", str(package),
            "--package-omit", ".*,CVS,RCS,*.pyc,*.pyo,*.egg-info,__pycache__",
        ]
    return execute([sys.executable, "-I", "-c", launcher, *options, wheel], work, clean_env(work, pathlib.Path(sys.executable).parent), 60)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "results/historical/django-xml-replay.json")
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

    result = {
        "schema": 1,
        "experiment": "django-xml-maintainer-linked-configuration-replay",
        "classification": "configuration-faithful replay; original publisher wheel bytes unavailable",
        "status": "RUNNING",
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "repetitions": args.repetitions,
        "evidence": {
            "issue": ISSUE,
            "affected_source_commit": AFFECTED_SOURCE_COMMIT,
            "fix_commit": FIX_COMMIT,
            "fixed_tag_commit": FIXED_TAG_COMMIT,
            "maintainer_fix": "setuptools packages=['djxml'] replaced by package discovery include=['djxml*']",
            "published_artifact_metadata": {
                "4.0.0": {"sha256":"3fa132b819725f21427e05efaf799100f34f5003a9ad26906824985127dfc48e", "reported_size_bytes":5530, "yanked_reason":"Packaging issue"},
                "4.0.1": {"sha256":"e44ef3466d2c516163b57f31c1838cb622315cdfc95e4665064809814c3a6114", "reported_size_bytes":26624},
            },
            "retrieval_limit": "PyPI binary URLs were inaccessible from the execution environment; hashes are metadata only and were not treated as locally verified bytes.",
        },
        "script_sha256": digest(pathlib.Path(__file__)),
        "commands": [],
        "runs": [],
    }

    def save() -> None:
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    def required(argv, cwd, env, timeout=120):
        process = execute(argv, cwd, env, timeout)
        result["commands"].append(process)
        if process["returncode"]:
            save()
            raise RuntimeError(process)
        return process

    with tempfile.TemporaryDirectory(prefix="wheelgate-django-xml-") as temporary:
        temp = pathlib.Path(temporary)
        venv.EnvBuilder(with_pip=True).create(temp / "builder")
        from wheelgate.runner import venv_python
        builder = venv_python(temp / "builder")
        (temp / "home").mkdir()
        builder_env = clean_env(temp / "home", builder.parent)
        builder_env["SOURCE_DATE_EPOCH"] = "1704067200"
        required([
            builder, "-I", "-m", "pip", "install", "--no-index", "--no-deps",
            ROOT / "third_party/setuptools-78.1.1-py3-none-any.whl",
        ], temp, builder_env)

        variants = {
            "affected": {"version":"4.0.0", "fixed":False, "ordinary":"FAIL", "gate":"FAIL", "cwc_default":"PASS", "cwc_reference":"REJECT"},
            "fixed": {"version":"4.0.1", "fixed":True, "ordinary":"PASS", "gate":"PASS", "cwc_default":"PASS", "cwc_reference":"PASS"},
        }
        prepared = {}
        for name, description in variants.items():
            source = assets / "sources" / name
            wheel_dir = assets / "wheels" / name
            wheel_dir.mkdir(parents=True)
            write_source(source, description["version"], description["fixed"])
            clean = temp / ("build-" + name)
            shutil.copytree(source, clean)
            required([
                builder, "-I", "-c",
                f"from setuptools.build_meta import build_wheel; build_wheel({str(wheel_dir)!r})",
            ], clean, builder_env)
            wheel = next(wheel_dir.glob("*.whl"))
            description["wheel"] = wheel
            description["wheel_sha256"] = digest(wheel)

            # Native checkout behavior: both trees expose the intended subpackage.
            checkout = execute([
                sys.executable, "-c",
                "import djxml.xmlmodels; assert djxml.xmlmodels.consumer() == 'available'; print(djxml.xmlmodels.__file__)",
            ], source, clean_env(temp / ("checkout-home-" + name), pathlib.Path(sys.executable).parent), 30)
            # clean_env HOME must exist for reproducibility even though the operation does not use it.
            if checkout["returncode"] != 0:
                # Retry after creating the home; retain both receipts.
                home = temp / ("checkout-home-" + name); home.mkdir(exist_ok=True)
                checkout = execute([
                    sys.executable, "-c",
                    "import djxml.xmlmodels; assert djxml.xmlmodels.consumer() == 'available'; print(djxml.xmlmodels.__file__)",
                ], source, clean_env(home, pathlib.Path(sys.executable).parent), 30)
            if checkout["returncode"] != 0:
                raise RuntimeError(checkout)
            description["checkout"] = checkout

            environment_root = temp / ("prepared-" + name)
            subject, subject_env, setup = prepare(environment_root, wheel)
            if setup["status"] != "READY":
                raise RuntimeError(setup)
            prepared[name] = (subject, subject_env, setup)

            cwc_work = temp / ("cwc-" + name); cwc_work.mkdir()
            default = cwc_process(wheel, source / "djxml", False, cwc_work)
            reference = cwc_process(wheel, source / "djxml", True, cwc_work)
            description["cwc"] = {
                "default": {"status":"PASS" if default["returncode"] == 0 else "REJECT", "process":default},
                "reference": {"status":"PASS" if reference["returncode"] == 0 else "REJECT", "process":reference},
            }
            if description["cwc"]["default"]["status"] != description["cwc_default"]:
                raise AssertionError((name, description["cwc"]))
            if description["cwc"]["reference"]["status"] != description["cwc_reference"]:
                raise AssertionError((name, description["cwc"]))

            # check-manifest evaluates source-distribution membership, not wheel package discovery.
            repository = temp / ("manifest-" + name)
            shutil.copytree(source, repository)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "replay@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Replay"], cwd=repository, check=True)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repository, check=True)
            manifest_process = execute([
                builder, "-I", ROOT / "third_party/source/check-manifest-0.50/check_manifest.py",
                "--no-build-isolation", repository,
            ], repository, builder_env, 120)
            if manifest_process["returncode"] == 0:
                manifest_status = "PASS"
            elif "No module named build" in ((manifest_process.get("stderr") or "") + (manifest_process.get("stdout") or "")) or manifest_process['timeout']:
                manifest_status = "BLOCKED"
            else:
                manifest_status = "REJECT"
            description["check_manifest"] = {
                "status": manifest_status,
                "process": manifest_process,
            }

        (assets / "ordinary.py").write_text(ORDINARY, encoding="utf-8")
        for name, description in variants.items():
            subject, subject_env, setup = prepared[name]
            for repetition in range(args.repetitions):
                work = temp / f"run-{name}-{repetition}"; work.mkdir()
                ordinary_work = work / "ordinary"; ordinary_work.mkdir()
                ordinary_process = execute([subject, "-I", assets / "ordinary.py"], ordinary_work, subject_env, 30)
                ordinary_status = "PASS" if ordinary_process["returncode"] == 0 else "FAIL"
                gate = probe(
                    contract(description["version"]), subject, subject_env, work / "gate",
                    identity=setup["wheel_identity"],
                )
                if ordinary_status != description["ordinary"]:
                    raise AssertionError((name, ordinary_status, ordinary_process))
                if gate["status"] != description["gate"]:
                    raise AssertionError((name, gate))
                result["runs"].append({
                    "variant": name,
                    "version": description["version"],
                    "repetition": repetition,
                    "replay_wheel_sha256": description["wheel_sha256"],
                    "checkout": description["checkout"],
                    "setup": setup,
                    "ordinary": {"status":ordinary_status, "process":ordinary_process},
                    "gate": gate,
                    "cwc": description["cwc"],
                    "check_manifest": description["check_manifest"],
                })
                save()
                print(name, repetition, ordinary_status, gate["status"], flush=True)

        result["summary"] = {
            "observations": len(result["runs"]),
            "checkout_pass_variants": 2,
            "affected_installed_status": variants["affected"]["ordinary"],
            "fixed_installed_status": variants["fixed"]["ordinary"],
            "default_cwc_affected": variants["affected"]["cwc"]["default"]["status"],
            "reference_cwc_affected": variants["affected"]["cwc"]["reference"]["status"],
            "check_manifest_statuses": {name: data["check_manifest"]["status"] for name, data in variants.items()},
            "median_gate_seconds": statistics.median(run["gate"]["seconds"] for run in result["runs"]),
        }
        result["status"] = "COMPLETE"
        result["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
