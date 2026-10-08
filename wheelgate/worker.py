"""Standard-library-only consumer worker for a clean installed environment."""
from __future__ import annotations

import contextlib
import importlib
import importlib.metadata as md
import importlib.resources as resources
import io
import json
import os
import pathlib
import runpy
import subprocess
import sys
import time
import traceback
import tempfile

try:  # package import in unit tests
    from .footprint import AccessRecorder, inspect_file_access, inspect_new_modules, snapshot
except ImportError:  # copied standalone; -I intentionally omits the script directory
    import importlib.util
    _helper_path = pathlib.Path(__file__).with_name("footprint.py")
    _helper_spec = importlib.util.spec_from_file_location("wheelgate_probe_footprint", _helper_path)
    if _helper_spec is None or _helper_spec.loader is None:
        raise
    _helper = importlib.util.module_from_spec(_helper_spec)
    _helper_spec.loader.exec_module(_helper)
    AccessRecorder = _helper.AccessRecorder
    inspect_file_access = _helper.inspect_file_access
    inspect_new_modules = _helper.inspect_new_modules
    snapshot = _helper.snapshot


class InvalidRun(RuntimeError):
    """The execution did not establish the intended installed-artifact context."""


def owned(distribution: str, module: str) -> dict:
    obj = importlib.import_module(module)
    origin = getattr(obj, "__file__", None)
    if not origin:
        raise InvalidRun("Concrete owned module required; namespace/builtin anchor unsupported")
    path = pathlib.Path(origin).resolve()
    dist = md.distribution(distribution)
    files = {pathlib.Path(dist.locate_file(f)).resolve() for f in dist.files or []}
    if path not in files or not path.is_relative_to(pathlib.Path(sys.prefix).resolve()):
        raise InvalidRun(f"{module} is not an installed file owned by {distribution}: {path}")
    return {
        "module": module,
        "origin": str(path),
        "distribution": dist.metadata["Name"],
        "version": dist.version,
    }


def owned_file(distribution: str, path: pathlib.Path) -> str:
    """Only static files recorded by the selected installed distribution qualify."""
    dist = md.distribution(distribution)
    resolved = path.resolve()
    inventory = {pathlib.Path(dist.locate_file(f)).resolve() for f in dist.files or []}
    if resolved not in inventory or not resolved.is_relative_to(pathlib.Path(sys.prefix).resolve()):
        raise InvalidRun(f"File is not recorded for {distribution}: {resolved}")
    return str(resolved)


def compare(value, contract):
    if "equals" in contract and value != contract["equals"]:
        raise AssertionError(f"Expected {contract['equals']!r}; observed {value!r}")
    if "contains" in contract and contract["contains"] not in value:
        raise AssertionError(f"Missing expected substring {contract['contains']!r}")


def _allowed(c: dict) -> list[str]:
    values = c.get("_allowed_distributions", [c["distribution"]])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise InvalidRun("Runner did not provide a valid distribution allowlist")
    return values


def _console_operation(c: dict, capture=None) -> dict:
    """Run an installed Python console launcher in this already isolated child."""
    d = c["distribution"]
    name = c["command"]
    if pathlib.Path(name).name != name:
        raise ValueError("CLI must be an installed script basename")
    executable = pathlib.Path(sys.executable).parent / name
    if os.name == 'nt':
        executable = executable.with_suffix('.exe')
    entries = [
        entry
        for entry in md.distribution(d).entry_points
        if entry.group == "console_scripts" and entry.name == name
    ]
    if len(entries) != 1:
        raise AssertionError("CLI not registered by the intended distribution")
    if not executable.is_file():
        raise FileNotFoundError(str(executable))
    launcher = owned_file(d, executable)

    stdout, stderr, input_stream = capture or _console_capture()
    prior_argv, prior_stdin = sys.argv, sys.stdin
    sys.argv = [str(executable), *c.get("args", [])]
    input_stream.write(c.get("stdin", ""))
    input_stream.seek(0)
    sys.stdin = input_stream
    returncode = 0
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            origins = [owned(d, module) for module in c["modules"]]
            origins.append(owned(d, entries[0].module))
            try:
                if executable.suffix.lower() == '.exe':
                    value = entries[0].load()()
                    if value is not None:
                        raise SystemExit(value)
                else:
                    runpy.run_path(str(executable), run_name="__main__")
            except SystemExit as exc:
                if exc.code is None:
                    returncode = 0
                elif isinstance(exc.code, int):
                    returncode = exc.code
                else:
                    print(exc.code, file=sys.stderr)
                    returncode = 1
    finally:
        sys.argv, sys.stdin = prior_argv, prior_stdin
        stdout.flush(); stderr.flush()
        stdout.seek(0); stderr.seek(0)
        output, errors = stdout.read(), stderr.read()
        stdout.close(); stderr.close(); input_stream.close()
    if returncode != c.get("returncode", 0):
        raise AssertionError(f"CLI exit {returncode}: {errors}")
    compare(output, c)
    origins.extend(owned(d, module) for module in c["modules"])
    return {
        "origins": origins,
        "launcher_origin": launcher,
        "argv": [str(executable), *c.get("args", [])],
        "stdout": output,
        "stderr": errors,
        "returncode": returncode,
    }


def _console_capture():
    return tuple(tempfile.TemporaryFile(mode='w+', encoding='utf-8') for _ in range(3))


def _evaluate_console_child(c: dict) -> dict:
    start = time.perf_counter()
    # Worker-owned capture files are infrastructure, prepared before observing
    # the consumer. Package imports and all entry-point behavior remain observed.
    capture = _console_capture()
    before = snapshot()
    access_recorder = AccessRecorder()
    access_recorder.start()
    status = "PASS"
    try:
        detail = _console_operation(c, capture=capture)
    except InvalidRun as exc:
        detail = {"exception": type(exc).__name__, "message": str(exc)}
        status = "INVALID"
    except Exception as exc:
        detail = {
            "exception": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        status = "FAIL"
    finally:
        access_recorder.stop()
        for stream in capture:
            if not stream.closed:
                stream.close()
    allowed = _allowed(c)
    footprint = inspect_new_modules(before, allowed)
    file_footprint = inspect_file_access(access_recorder.paths, allowed)
    violations = footprint["violations"] or file_footprint["violations"]
    if violations and status == "PASS":
        detail["operation_status"] = status
        detail["context_message"] = (
            "Operation loaded code or read data outside the declared runtime profile"
        )
        status = "INVALID"
    elif violations and status == "FAIL":
        detail["context_warning"] = (
            "The failed operation also touched code or data outside the declared runtime profile"
        )
    return {
        "id": c["id"],
        "status": status,
        "seconds": time.perf_counter() - start,
        "footprint": footprint,
        "file_footprint": file_footprint,
        **detail,
    }


def _invoke_console_child(c: dict) -> dict:
    request = pathlib.Path.cwd() / "console-contract.json"
    request.write_text(json.dumps(c, sort_keys=True), encoding="utf-8")
    cp = subprocess.run(
        [sys.executable, "-I", pathlib.Path(__file__).resolve(), "--console-child", request],
        capture_output=True,
        text=True,
        timeout=c.get("timeout", 10) + 1,
    )
    prefix = "WHEELGATE_CONSOLE="
    lines = [line[len(prefix) :] for line in cp.stdout.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise InvalidRun("No unique console-process receipt")
    try:
        payload = json.loads(lines[0])
    except (TypeError, ValueError) as exc:
        raise InvalidRun("Invalid console-process receipt") from exc
    if not isinstance(payload, dict) or payload.get("id") != c["id"]:
        raise InvalidRun("Console-process receipt is bound to the wrong obligation")
    status = payload.get("status")
    expected = {"PASS": 0, "FAIL": 1, "INVALID": 2}.get(status)
    if expected is None or cp.returncode != expected:
        raise InvalidRun("Console-process exit and receipt disagree")
    detail = {key: value for key, value in payload.items() if key not in {"id", "status", "seconds"}}
    detail["console_process"] = {
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }
    detail["_forced_status"] = status
    return detail


def operation(c: dict) -> dict:
    d = c["distribution"]
    origins = [owned(d, module) for module in c["modules"]]
    kind = c["kind"]
    detail: dict = {}
    if kind == "import":
        pass
    elif kind == "call":
        module, attribute = c["target"].split(":", 1)
        origins.append(owned(d, module))
        target = importlib.import_module(module)
        for part in attribute.split("."):
            target = getattr(target, part)
        value = target(*c.get("args", []), **c.get("kwargs", {}))
        compare(value, c)
        detail["value"] = value
    elif kind == "resource":
        name = pathlib.PurePosixPath(c["resource"])
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("Resource must be a package-relative path")
        origins.append(owned(d, c["package"]))
        resource = resources.files(c["package"]).joinpath(str(name))
        if not isinstance(resource, pathlib.Path):
            raise InvalidRun("Non-filesystem resource loader is unsupported")
        if not resource.is_file():
            raise FileNotFoundError(str(resource))
        detail["resource_origin"] = owned_file(d, resource)
        text = resource.read_text(encoding="utf-8")
        value = json.loads(text) if c.get("format") == "json" else text
        compare(value, c)
        detail["value"] = value
    elif kind == "entrypoint":
        entries = [
            entry
            for entry in md.distribution(d).entry_points
            if entry.group == c["group"] and entry.name == c["name"]
        ]
        if len(entries) != 1:
            raise AssertionError(f"Expected one owned entry point, found {len(entries)}")
        entry = entries[0]
        origins.append(owned(d, entry.module))
        obj = entry.load()
        if not callable(obj):
            raise AssertionError("Entry point not callable")
        detail["entrypoint"] = entry.value
        if c.get("invoke", False):
            value = obj(*c.get("args", []), **c.get("kwargs", {}))
            compare(value, c)
            detail["value"] = value
    elif kind == "cli":
        detail = _invoke_console_child(c)
        return {"origins": origins, **detail}
    elif kind == "script":
        exec(compile(c["code"], "<consumer-contract>", "exec"), {"__name__": "__contract__"})
    else:
        raise ValueError(f"Unknown contract kind {kind}")
    origins.extend(owned(d, module) for module in c["modules"])
    return {"origins": origins, **detail}


def evaluate(c: dict) -> dict:
    start = time.perf_counter()
    before = snapshot()
    access_recorder = AccessRecorder()
    access_recorder.start()
    status = "PASS"
    try:
        detail = operation(c)
        status = detail.pop("_forced_status", "PASS")
    except InvalidRun as exc:
        detail = {"exception": type(exc).__name__, "message": str(exc)}
        status = "INVALID"
    except Exception as exc:
        detail = {
            "exception": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        status = "FAIL"
    finally:
        access_recorder.stop()

    allowed = _allowed(c)
    footprint = detail.get("footprint")
    if footprint is None:
        footprint = inspect_new_modules(before, allowed)
        detail["footprint"] = footprint
    file_footprint = detail.get("file_footprint")
    if file_footprint is None:
        file_footprint = inspect_file_access(access_recorder.paths, allowed)
        detail["file_footprint"] = file_footprint
    violations = footprint.get("violations") or file_footprint.get("violations")
    if violations and status == "PASS":
        detail["operation_status"] = status
        detail["context_message"] = (
            "Operation loaded code or read data outside the declared runtime profile"
        )
        status = "INVALID"
    elif violations and status == "FAIL":
        detail["context_warning"] = (
            "The failed operation also touched code or data outside the declared runtime profile"
        )
    return {"id": c["id"], "status": status, "seconds": time.perf_counter() - start, **detail}


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--console-child":
        contract = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
        result = _evaluate_console_child(contract)
        print("WHEELGATE_CONSOLE=" + json.dumps(result, sort_keys=True))
        return {"PASS": 0, "FAIL": 1, "INVALID": 2}[result["status"]]

    payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("batch") is True:
        base = pathlib.Path.cwd()
        results = []
        for index, contract in enumerate(payload["contracts"]):
            work = base / ("operation-" + str(index))
            work.mkdir()
            os.chdir(work)
            try:
                results.append(evaluate(contract))
            finally:
                os.chdir(base)
        print("WHEELGATE_BATCH=" + json.dumps(results, sort_keys=True))
        return 2 if any(row["status"] == "INVALID" for row in results) else (
            1 if any(row["status"] == "FAIL" for row in results) else 0
        )
    result = evaluate(payload)
    print("WHEELGATE_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else (2 if result["status"] == "INVALID" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
