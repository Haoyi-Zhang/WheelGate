"""Original latex2pydata wheel + upstream data, unchanged file-loading oracle.

Only reviewed original Python modules execute. The upstream test JSON is read
as data, not compiled or executed. This is a documented-API release rehearsal,
not a publisher defect, historical repair, or maintainer adoption claim.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate.runner import canonical_contract_digest, execute, prepare, qualify

SOURCE = "ceee4aa242b1f2f42063b5abcd75a7bc36530bf3"
UPSTREAM_PATH = "latex/test/toplevel_dict_test_pass.json"
URL = f"https://raw.githubusercontent.com/gpoore/latex2pydata/{SOURCE}/{UPSTREAM_PATH}"
WHEEL_SHA = "7c4092562082985453f47f52db31e1f8c2edcf5d7f855f4c614cfba12808675b"
INPUT_SHA = "5caf7af779906e28787bcb47b45640f4981bc1c5ed9011370f178bbbc67214d3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input", type=Path, help="Retained upstream JSON for a wholly offline replay")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.input:
        input_bytes = args.input.read_bytes()
    else:
        with urlopen(Request(URL, headers={"User-Agent": "WheelGate-context-replay"}), timeout=45) as response:
            input_bytes = response.read()
    if hashlib.sha256(input_bytes).hexdigest() != INPUT_SHA:
        raise ValueError("Upstream test-data identity differs")
    data_path = out / "upstream-data.json"
    data_path.write_bytes(input_bytes)
    expected = json.loads(input_bytes)
    wheel = ROOT / "evidence/publisher-wheels/inputs/latex2pydata-0.5.0-py3-none-any.whl"
    if sha(wheel) != WHEEL_SHA:
        raise ValueError("Original wheel identity differs")
    code = ("from pathlib import Path\nimport latex2pydata\n"
            f"value = latex2pydata.load(Path({str(data_path)!r}))\n"
            f"assert value == {expected!r}\n")
    contract = {"schema": 2, "contracts": [{"id": "publisher-file-load", "kind": "script",
                "distribution": "latex2pydata", "version": "0.5.0",
                "modules": ["latex2pydata", "latex2pydata.loading"], "code": code,
                "evidence": "https://pypi.org/project/latex2pydata/0.5.0/ documents load(pathlib.Path); " + URL}]}
    declared = deepcopy(contract)
    declared["contracts"][0]["external_inputs"] = [{"path": str(data_path), "sha256": sha(data_path),
        "evidence": "Caller-selected upstream data file for the documented Path-loading API, not wheel-owned package data. " + URL}]
    (out / "undeclared-contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    (out / "declared-contract.json").write_text(json.dumps(declared, indent=2), encoding="utf-8")
    # Ordinary baseline has the same exact wheel, neutral cwd, module ownership
    # anchors, input bytes and assertion. It does not evaluate dynamic file policy.
    with tempfile.TemporaryDirectory(prefix="wg-context-ordinary-") as td:
        base = Path(td)
        py, env, setup = prepare(base, wheel)
        if setup["status"] != "READY":
            raise RuntimeError("Ordinary baseline setup blocked")
        neutral = base / "operation"; neutral.mkdir()
        origin = ("import importlib.metadata as m, pathlib, latex2pydata\n"
                  "d=m.distribution('latex2pydata')\n"
                  "assert pathlib.Path(latex2pydata.__file__).resolve() in {pathlib.Path(d.locate_file(f)).resolve() for f in d.files}\n")
        process = execute([py, "-I", "-c", origin + code], neutral, env)
        ordinary = {"status": "PASS" if process["returncode"] == 0 else "FAIL", "setup": setup, "process": process}
    no_input = qualify(wheel, contract)
    with_input = qualify(wheel, declared)
    (out / "ordinary.json").write_text(json.dumps(ordinary, indent=2), encoding="utf-8")
    (out / "undeclared-receipt.json").write_text(json.dumps(no_input, indent=2), encoding="utf-8")
    (out / "declared-receipt.json").write_text(json.dumps(with_input, indent=2), encoding="utf-8")
    same_oracle = contract["contracts"][0]["code"] == declared["contracts"][0]["code"]
    summary = {"scope": "documented original-wheel Path API on original upstream test data; policy declaration rehearsal, not field incident",
               "python": sys.version, "platform": platform.platform(),
               "execution_helper_sha256": sha(Path(__file__)),
               "source": {"commit": SOURCE, "path": UPSTREAM_PATH, "url": URL, "input_sha256": sha(data_path),
                          "api_documentation": "https://pypi.org/project/latex2pydata/0.5.0/"},
               "wheel_sha256": sha(wheel), "ordinary": ordinary["status"],
               "gate_undeclared": no_input["status"], "gate_declared": with_input["status"],
               "same_oracle": same_oracle, "extra_declarations": {"files": 1, "fields": ["path", "sha256", "evidence"]},
               "contract_hashes": {"undeclared": canonical_contract_digest(contract), "declared": canonical_contract_digest(declared)},
               "reused_receipt_fields": ["wheel identity", "module anchors", "environment inventory", "process consistency", "operation oracle"],
               "disposition": "Declare the legitimate external input; do not modify the publisher wheel or weaken the assertion.",
               "runtime_sources": [{"file": f"wheelgate/{name}", "sha256": sha(ROOT/"wheelgate"/name)}
                                   for name in ("runner.py", "worker.py", "footprint.py", "contractio.py", "paths.py")],
               "valid": ordinary["status"] == "PASS" and no_input["status"] == "INVALID" and with_input["status"] == "PASS" and same_oracle}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["valid"] else 1


if __name__ == "__main__": raise SystemExit(main())
