"""Owned boundary regressions; no subject installation or study execution."""
import ast
import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from wheelgate import footprint, worker
from wheelgate.runner import parsed_report, qualify, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WindowsStdlibRoots(unittest.TestCase):
    def classify(self, relative):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td).resolve()
            (base / "DLLs").mkdir()
            paths = {"stdlib": str(base / "Lib"), "platstdlib": str(base / "Lib"),
                     "purelib": str(base / "env/Lib/site-packages"),
                     "platlib": str(base / "env/Lib/site-packages")}
            with mock.patch.object(footprint.sys, "platform", "win32"), \
                 mock.patch.object(footprint.sys, "base_prefix", str(base)), \
                 mock.patch.object(footprint.sysconfig, "get_paths", return_value=paths):
                sites, standards = footprint._roots()
            self.assertNotIn(base, standards)
            self.assertNotIn(base / "env", standards)
            return footprint._classify_path(base / relative, set(), {}, sites,
                                            standards, base / "env")

    def test_base_dlls_extension_is_stdlib(self):
        row, invalid = self.classify("DLLs/_sqlite3.pyd")
        self.assertEqual(row["classification"], "stdlib")
        self.assertFalse(invalid)

    def test_base_prefix_is_not_allowed(self):
        row, invalid = self.classify("unowned.py")
        self.assertEqual(row["classification"], "external-file")
        self.assertTrue(invalid)

    def test_base_site_packages_stays_invalid(self):
        row, invalid = self.classify("Lib/site-packages/helper.py")
        self.assertEqual(row["classification"], "unowned-installed-file")
        self.assertTrue(invalid)

    def test_dlls_site_packages_stays_invalid(self):
        row, invalid = self.classify("DLLs/site-packages/helper.py")
        self.assertEqual(row["classification"], "unowned-installed-file")
        self.assertTrue(invalid)

    def test_venv_dlls_is_not_base_stdlib(self):
        row, invalid = self.classify("env/DLLs/helper.pyd")
        self.assertEqual(row["classification"], "unowned-environment-file")
        self.assertTrue(invalid)

    def fresh_import(self, module, extension):
        code = (
            "import importlib,json,sys;"
            f"sys.path.insert(0,{str(ROOT)!r});"
            "from wheelgate import footprint as f;"
            "f.distribution_inventory=lambda:{};"
            f"assert {extension!r} not in sys.modules;"
            "before=f.snapshot();"
            f"importlib.import_module({module!r});"
            "print(json.dumps(f.inspect_new_modules(before,[])))"
        )
        with tempfile.TemporaryDirectory() as td:
            cp = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=td,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        report = json.loads(cp.stdout)
        rows = [row for row in report["modules"] if row["module"] == extension]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["classification"], "stdlib")
        self.assertTrue(pathlib.Path(rows[0]["origin"]).is_relative_to(
            (pathlib.Path(sys.base_prefix) / "DLLs").resolve()))
        self.assertEqual(report["violations"], [])

    @unittest.skipUnless(sys.platform == "win32", "Windows interpreter DLLs regression")
    def test_fresh_sqlite3_import(self):
        self.fresh_import("sqlite3", "_sqlite3")

    @unittest.skipUnless(sys.platform == "win32", "Windows interpreter DLLs regression")
    def test_fresh_decimal_import(self):
        self.fresh_import("decimal", "_decimal")


class SchemaOneApplicability(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "contracts/fixture.json").read_text(encoding="utf-8"))
        self.assertEqual(self.spec["schema"], 1)

    def reject(self, kind, **fields):
        spec = copy.deepcopy(self.spec)
        next(c for c in spec["contracts"] if c["kind"] == kind).update(fields)
        self.reject_spec(spec)

    def reject_spec(self, spec):
        with mock.patch("wheelgate.runner.prepare") as prepare, \
             mock.patch("wheelgate.runner.wheel_identity",
                        side_effect=AssertionError("Validation reached wheel metadata access")) as identity:
            with self.assertRaises(ValueError):
                qualify("not-read-or-installed.whl", spec)
        identity.assert_not_called()
        prepare.assert_not_called()

    def test_delivered_schema1_stays_valid(self):
        validate(self.spec)

    def test_unknown_document_field_before_setup(self):
        self.spec["contract"] = []
        self.reject_spec(self.spec)

    def test_unknown_operation_field_before_setup(self):
        self.reject("call", equal="ignored typo")

    def test_import_equals_before_setup(self):
        self.reject("import", equals="not evaluated")

    def test_import_contains_before_setup(self):
        self.reject("import", contains="not evaluated")

    def test_uninvoked_entrypoint_fields_before_setup(self):
        for field, value in [("equals", "hello"), ("contains", "hello"),
                             ("args", []), ("kwargs", {})]:
            with self.subTest(field=field):
                spec = copy.deepcopy(self.spec)
                entry = next(c for c in spec["contracts"] if c["kind"] == "entrypoint")
                entry.pop("equals")
                entry.update(invoke=False, **{field: value})
                self.reject_spec(spec)

    def test_entrypoint_invoke_must_be_boolean(self):
        self.reject("entrypoint", invoke="false")

    def test_script_assertion_field_before_setup(self):
        self.spec["contracts"] = [dict(self.spec["contracts"][0], kind="script",
                                        code="assert True", equals=True)]
        self.reject_spec(self.spec)

    def test_cli_assertion_types_before_setup(self):
        for field, value in [("equals", 1), ("contains", []), ("returncode", True)]:
            with self.subTest(field=field):
                self.reject("cli", **{field: value})

    def test_duplicate_schema1_json_key_rejected(self):
        from wheelgate.contractio import loads
        with self.assertRaises(ValueError):
            loads('{"schema":1,"contracts":[],"contracts":[]}')


class ConsoleTimeoutReceipt(unittest.TestCase):
    contract = {"id": "console", "kind": "cli", "distribution": "owned",
                "modules": ["owned"], "evidence": "owned regression",
                "command": "owned", "timeout": 0.25}

    def evaluate_process(self, *, process=None, error=None):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch("wheelgate.worker.pathlib.Path.cwd", return_value=pathlib.Path(td)), \
             mock.patch("wheelgate.worker.owned", return_value={"module": "owned"}), \
             mock.patch("wheelgate.worker.inspect_new_modules", return_value={"violations": []}), \
             mock.patch("wheelgate.worker.inspect_file_access", return_value={"violations": []}), \
             mock.patch("wheelgate.worker.subprocess.run", return_value=process,
                        side_effect=error) as run:
            result = worker.evaluate(self.contract)
        self.assertEqual(run.call_args.kwargs["timeout"], 1.25)
        return result

    def assert_worker_receipt(self, result, expected_exit):
        with mock.patch.object(worker.sys, "argv", ["worker.py", "contract.json"]), \
             mock.patch("wheelgate.worker.pathlib.Path.read_text",
                        return_value=json.dumps(self.contract)), \
             mock.patch("wheelgate.worker.evaluate", return_value=result), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            exit_code = worker.main()
        self.assertEqual(exit_code, expected_exit)
        cp = {"stdout": output.getvalue(), "returncode": exit_code, "timeout": False}
        rows = parsed_report(cp, "WHEELGATE_JSON=", [self.contract["id"]])
        self.assertIsNotNone(rows)
        self.assertEqual(rows[0]["status"], result["status"])
        cp["returncode"] = 1 if expected_exit == 2 else 2
        self.assertIsNone(parsed_report(cp, "WHEELGATE_JSON=", [self.contract["id"]]))

    def test_console_timeout_keeps_partial_byte_streams(self):
        error = subprocess.TimeoutExpired(["owned-python", "--console-child"], 1.25,
                                           output=b"partial\xff", stderr=b"diagnostic")
        result = self.evaluate_process(error=error)
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["exception"], "TimeoutExpired")
        process = result["console_process"]
        self.assertTrue(process["timeout"])
        self.assertEqual(process["timeout_seconds"], 1.25)
        self.assertEqual(process["returncode"], 124)
        self.assertEqual(process["stdout"], "partial\ufffd")
        self.assertEqual(process["stderr"], "diagnostic")
        self.assertEqual(process["argv"], error.cmd)
        self.assert_worker_receipt(result, 2)

    def test_console_timeout_keeps_text_streams(self):
        error = subprocess.TimeoutExpired(["owned-python"], 1.25,
                                           output="partial text", stderr="text diagnostic")
        result = self.evaluate_process(error=error)
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["console_process"]["stdout"], "partial text")
        self.assertEqual(result["console_process"]["stderr"], "text diagnostic")

    def test_console_timeout_without_streams(self):
        result = self.evaluate_process(error=subprocess.TimeoutExpired(["owned-python"], 1.25))
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["console_process"]["stdout"], "")
        self.assertEqual(result["console_process"]["stderr"], "")

    def test_completed_console_assertion_failure_stays_fail(self):
        payload = {"id": "console", "status": "FAIL", "exception": "AssertionError",
                   "message": "CLI exit 1: owned command completed"}
        process = subprocess.CompletedProcess([], 1,
                    "WHEELGATE_CONSOLE=" + json.dumps(payload) + "\n", "")
        result = self.evaluate_process(process=process)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exception"], "AssertionError")
        self.assert_worker_receipt(result, 1)

    def completed_console(self, exit_code, expected):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            launcher = root / ("owned.exe" if sys.platform == "win32" else "owned")
            launcher.write_bytes(b"")
            def command():
                print("completed output")
                raise SystemExit(exit_code)
            entry = types.SimpleNamespace(group="console_scripts", name="owned",
                                          module="owned", load=lambda: command)
            contract = dict(self.contract, equals=expected)
            with mock.patch("wheelgate.worker.sys.executable", str(root / "python.exe")), \
                 mock.patch("wheelgate.worker.md.distribution",
                            return_value=types.SimpleNamespace(entry_points=[entry])), \
                 mock.patch("wheelgate.worker.owned", return_value={"module": "owned"}), \
                 mock.patch("wheelgate.worker.owned_file", return_value=str(launcher)), \
                 mock.patch("wheelgate.worker.runpy.run_path", side_effect=lambda *a, **k: command()), \
                 mock.patch("wheelgate.worker.inspect_new_modules", return_value={"violations": []}), \
                 mock.patch("wheelgate.worker.inspect_file_access", return_value={"violations": []}):
                return worker._evaluate_console_child(contract)

    def test_completed_nonzero_command_stays_fail(self):
        result = self.completed_console(1, "completed output\n")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exception"], "AssertionError")
        self.assertIn("CLI exit 1", result["message"])

    def test_completed_stdout_oracle_failure_stays_fail(self):
        result = self.completed_console(0, "different expected output\n")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exception"], "AssertionError")
        self.assertIn("Expected", result["message"])


class ReproductionEntrypoint(unittest.TestCase):
    def test_paper_build_uses_current_python_entrypoint_without_executing_it(self):
        tree = ast.parse((ROOT / "scripts/reproduce.py").read_text(encoding="utf-8"))
        stages = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                  and node.elts and isinstance(node.elts[0], ast.Constant)
                  and node.elts[0].value == "paper-build"]
        self.assertEqual(len(stages), 1)
        argv = stages[0].elts[1]
        self.assertIsInstance(argv, ast.List)
        self.assertEqual(ast.unparse(argv.elts[0]), "sys.executable")
        self.assertEqual(ast.literal_eval(argv.elts[1]), "build.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
