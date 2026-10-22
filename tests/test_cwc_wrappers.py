"""Owned CWC wrapper regressions; no third-party code, installs or campaigns."""
import ast
from collections import Counter
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/cwc_baseline.py"
cwc = None
if HELPER.is_file():
    spec = importlib.util.spec_from_file_location("owned_cwc_baseline", HELPER)
    cwc = importlib.util.module_from_spec(spec)
    with mock.patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
        spec.loader.exec_module(cwc)


def process(returncode=0, timeout=False):
    return {"argv": ["owned-stub"], "returncode": returncode,
            "stdout": "partial stdout", "stderr": "partial stderr",
            "seconds": 0.001, "timeout": timeout}


@unittest.skipIf(cwc is None, "Artifact-only CWC scripts are not in the runtime wheel")
class CWCWrappers(unittest.TestCase):
    def test_completed_process_exit_classification_and_raw_receipt(self):
        for code, expected in ((0, "PASS"), (1, "REJECT"), (2, "CALLERROR"),
                               (127, "BLOCKED"), (7, "INVALID"), (-9, "INVALID")):
            with self.subTest(returncode=code), mock.patch.object(cwc, "verify_sources") as verify, \
                 mock.patch.object(cwc.subprocess, "run", return_value=subprocess.CompletedProcess(
                     ["owned-stub"], code, "stub stdout", "stub stderr")) as run:
                receipt = cwc.run_check(ROOT / "owned-unopened.whl", toplevel=("owned",))
            verify.assert_called_once_with()
            self.assertEqual(receipt["status"], expected)
            self.assertEqual(receipt["returncode"], code)
            self.assertEqual(receipt["stdout"], "stub stdout")
            self.assertEqual(receipt["stderr"], "stub stderr")
            self.assertFalse(receipt["timeout"])
            self.assertEqual(receipt["argv"], run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["timeout"], 60.0)
            json.dumps(receipt)

    def test_owned_native_stub_zero_one_two_without_running_cwc(self):
        native_run = subprocess.run
        statuses = []
        for code, expected in ((0, "PASS"), (1, "REJECT"), (2, "CALLERROR")):
            # Replace the CWC launch with this entire, benign, owned program.
            stub = [sys.executable, "-I", "-c",
                    f"import sys; print('owned stdout'); print('owned stderr', file=sys.stderr); sys.exit({code})"]
            def launch(*args, **kwargs):
                return native_run(stub, capture_output=True, text=True, timeout=10, check=False)
            with self.subTest(returncode=code), mock.patch.object(cwc, "verify_sources"), \
                 mock.patch.object(cwc.subprocess, "run", side_effect=launch):
                receipt = cwc.run_check(ROOT / "owned-unopened.whl")
            self.assertEqual(receipt["returncode"], code)
            self.assertEqual(receipt["status"], expected)
            self.assertEqual(receipt["stdout"], "owned stdout\n")
            self.assertEqual(receipt["stderr"], "owned stderr\n")
            statuses.append(receipt["status"])
        self.assertEqual(Counter(statuses), {"PASS": 1, "REJECT": 1, "CALLERROR": 1})

    def test_timeout_retains_partial_streams_and_is_not_content_rejection(self):
        for stdout, stderr in (("partial stdout", "partial stderr"),
                               (b"partial stdout", b"partial stderr")):
            with self.subTest(stream_type=type(stdout).__name__), \
                 mock.patch.object(cwc, "verify_sources"), \
                 mock.patch.object(cwc.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                     ["owned-stub"], 0.1, output=stdout, stderr=stderr)):
                receipt = cwc.run_check(ROOT / "owned-unopened.whl", timeout=0.1)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertIsNone(receipt["returncode"])
            self.assertTrue(receipt["timeout"])
            self.assertEqual(receipt["stdout"], "partial stdout")
            self.assertEqual(receipt["stderr"], "partial stderr")
            json.dumps(receipt)

    def test_launch_failure_is_not_a_content_rejection(self):
        with mock.patch.object(cwc, "verify_sources"), \
             mock.patch.object(cwc.subprocess, "run", side_effect=OSError("owned launch failure")):
            receipt = cwc.run_check(ROOT / "owned-unopened.whl")
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertEqual(receipt["returncode"], 127)  # Same sentinel as runner.execute.
        self.assertEqual(receipt["stderr"], "owned launch failure")
        self.assertEqual(receipt["stdout"], "")
        self.assertFalse(receipt["timeout"])

    def test_timeout_flag_precedes_any_sentinel_exit(self):
        for code in (0, 1, 2, 124, None):
            with self.subTest(returncode=code):
                self.assertEqual(cwc.cwc_status(process(code, True)), "BLOCKED")
        self.assertEqual(cwc.cwc_status(process(None)), "INVALID")

    def test_route_and_historical_record_expressions_use_shared_classifier(self):
        # Evaluate only the three small record expressions, never either main().
        # Their sole callable is the reviewed pure classifier; process values are stubs.
        targets = (("route_matrix.py", "row['content_checks'][preset]", 1),
                   ("historical_replay.py", "description['cwc']", 2))
        for filename, target, expected_calls in targets:
            tree = ast.parse((ROOT / "scripts" / filename).read_text(encoding="utf-8"))
            imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)
                       and n.module == "cwc_baseline"]
            self.assertTrue(any(a.name == "cwc_status" for n in imports for a in n.names))
            assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                           and any(ast.unparse(t) == target for t in n.targets)]
            self.assertEqual(len(assignments), 1)
            expr = assignments[0].value
            calls = [n for n in ast.walk(expr) if isinstance(n, ast.Call)]
            self.assertEqual(len(calls), expected_calls)
            self.assertTrue(all(isinstance(n.func, ast.Name) and n.func.id == "cwc_status"
                                for n in calls))
            expression = compile(ast.Expression(expr), filename, "eval")
            for code, timed, expected in ((0, False, "PASS"), (1, False, "REJECT"),
                                          (2, False, "CALLERROR"), (127, False, "BLOCKED"),
                                          (-9, False, "INVALID"), (124, True, "BLOCKED")):
                with self.subTest(wrapper=filename, returncode=code, timeout=timed):
                    stub = process(code, timed)
                    before = dict(stub)
                    record = eval(expression, {"__builtins__": {}, "cwc_status": cwc.cwc_status},
                                  {"proc": stub, "default": stub, "reference": stub})
                    records = [record] if filename == "route_matrix.py" else list(record.values())
                    for row in records:
                        self.assertEqual(row["status"], expected)
                        self.assertIs(row["process"], stub)
                    self.assertEqual(stub, before)

    def test_cli_keeps_zero_one_and_uses_two_for_tool_errors(self):
        cases = ((["PASS"], 0), (["REJECT"], 1), (["PASS", "REJECT"], 1),
                 (["CALLERROR"], 2), (["BLOCKED"], 2), (["INVALID"], 2),
                 (["REJECT", "CALLERROR"], 2), (["REJECT", "BLOCKED"], 2))
        for statuses, expected in cases:
            with self.subTest(statuses=statuses), \
                 mock.patch.object(cwc.sys, "argv", ["cwc_baseline.py", *["owned.whl"] * len(statuses)]), \
                 mock.patch.object(cwc.Path, "read_bytes", return_value=b"owned stub, not a wheel"), \
                 mock.patch.object(cwc.importlib.metadata, "version", return_value="owned-stub"), \
                 mock.patch.object(cwc, "run_check", side_effect=[dict(process(), status=s) for s in statuses]), \
                 mock.patch.object(cwc.subprocess, "run", side_effect=AssertionError("No subprocess allowed")) as native, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = cwc.main()
            native.assert_not_called()
            self.assertEqual(code, expected)
            self.assertEqual([r["process"]["status"] for r in json.loads(output.getvalue())["runs"]], statuses)

    @unittest.skipUnless(all((ROOT / p).is_file() for p in
                         ("results/routes/matrix.json", "results/historical/django-xml-replay.json")),
                         "Requires retained study records; fresh reproduction has not generated them yet")
    def test_retained_zero_one_projections_are_unchanged(self):
        for relative, field, expected in (
            ("results/routes/matrix.json", "content_checks", {0: 27, 1: 9}),
            ("results/historical/django-xml-replay.json", "cwc", {0: 9, 1: 3}),
        ):
            with self.subTest(record=relative):
                record = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                checks = [check for row in record["runs"] for check in row.get(field, {}).values()]
                self.assertEqual(Counter(c["process"]["returncode"] for c in checks), expected)
                self.assertTrue(all(cwc.cwc_status(c["process"]) == c["status"] for c in checks))

    @unittest.skipUnless((ROOT / "results/historical/django-xml-replay.json").is_file(),
                         "Requires the retained historical receipt; wrapper regressions remain active")
    def test_historical_audit_preserves_execution_time_source_binding(self):
        # Read the actual audit body, but never call its report-writing main().
        tree = ast.parse((ROOT / "scripts/audit.py").read_text(encoding="utf-8"))
        body = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "audit_historical")
        calls = [n for n in ast.walk(body) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "record_script"]
        self.assertEqual(len(calls), 1)
        record = json.loads((ROOT / "results/historical/django-xml-replay.json").read_text(encoding="utf-8"))
        expected = record["script_sha256"]
        recorded = ROOT / "scripts/provenance/historical_replay.py"
        self.assertEqual(hashlib.sha256(recorded.read_bytes()).hexdigest(), expected)
        self.assertNotEqual(hashlib.sha256((ROOT / "scripts/historical_replay.py").read_bytes()).hexdigest(), expected)
        expressions = compile(ast.Expression(calls[0].args[1]), "audit.py", "eval")
        candidates = eval(expressions, {"__builtins__": {}}, {"ROOT": ROOT})
        self.assertIn(recorded, candidates)
        helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "record_script")
        namespace = {"Path": Path, "sha256": lambda p: hashlib.sha256(p.read_bytes()).hexdigest()}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "audit.py", "exec"), namespace)
        self.assertEqual(namespace["record_script"](expected, candidates), recorded)
        with self.assertRaises(AssertionError):
            namespace["record_script"]("0" * 64, candidates)


@unittest.skipUnless((ROOT / "contracts/fixture.json").is_file() and
                     (ROOT / "inputs/fixture-rebuilt").is_dir(), "Complete artifact smoke fixtures required")
class SmokeEvidence(unittest.TestCase):
    def test_five_evidence_targets_resolve_to_actual_archive_members(self):
        contracts = json.loads((ROOT / "contracts/fixture.json").read_text(encoding="utf-8"))["contracts"]
        self.assertEqual([c["id"] for c in contracts], ["import", "consumer", "resource", "cli", "plugin"])
        for contract in contracts:
            pointer = contract["evidence"].split(": ", 1)[0]
            relative, member = pointer.split("!", 1)
            target = (ROOT / relative).resolve()
            self.assertTrue(target.is_relative_to(ROOT.resolve()))
            self.assertTrue(target.is_file())
            self.assertEqual(relative, "inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl")
            with zipfile.ZipFile(target) as archive:
                payload = archive.read(member).decode("utf-8")
            if contract["id"] in {"import", "consumer"}:
                self.assertEqual(member, "wg_fixture/__init__.py")
                self.assertIn("def consumer", payload)
                self.assertIn("template.json", payload)
            elif contract["id"] == "resource":
                self.assertEqual(member, "wg_fixture/template.json")
                self.assertEqual(json.loads(payload), contract["equals"])
            else:
                self.assertEqual(member, "wg_fixture-0.1.0.dist-info/entry_points.txt")
                expected = "wg-fixture = wg_fixture:main" if contract["id"] == "cli" else "demo = wg_fixture:consumer"
                self.assertIn(expected, payload)
        self.assertEqual(contracts[1]["equals"], "hello")
        self.assertEqual(contracts[2]["equals"], {"schema": 1, "message": "hello"})
        self.assertEqual(contracts[3]["equals"], "hello\n")
        self.assertEqual(contracts[4]["equals"], "hello")

    def test_fixture_members_support_the_documented_difference_without_import(self):
        wheels = {}
        for route in ("fixture-direct", "fixture-rebuilt"):
            path = ROOT / "inputs" / route / "wg_fixture-0.1.0-py3-none-any.whl"
            with zipfile.ZipFile(path) as archive:
                wheels[route] = {n: archive.read(n) for n in archive.namelist()}
        direct, rebuilt = wheels["fixture-direct"], wheels["fixture-rebuilt"]
        self.assertEqual(direct["wg_fixture/__init__.py"], rebuilt["wg_fixture/__init__.py"])
        self.assertEqual(json.loads(direct["wg_fixture/template.json"]), {"schema": 1, "message": "hello"})
        self.assertNotIn("wg_fixture/template.json", rebuilt)
        entrypoints = "wg_fixture-0.1.0.dist-info/entry_points.txt"
        self.assertEqual(direct[entrypoints], rebuilt[entrypoints])
        self.assertIn(b"wg-fixture = wg_fixture:main", direct[entrypoints])
        self.assertIn(b"demo = wg_fixture:consumer", direct[entrypoints])


if __name__ == "__main__":
    unittest.main()
