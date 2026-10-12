"""Benign owned-fixture checks for host-independent admission and evidence lookup."""
import importlib.util
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from wheelgate.paths import command_basename, resource_parts
from wheelgate.runner import clean_env, qualify, validate
from wheelgate import worker
from wheelgate.worker import _console_operation, operation

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "wheelgate_test_evidence_paths", ROOT / "scripts/evidence_paths.py"
)
_evidence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_evidence)


class ContractPathAdmission(unittest.TestCase):
    def test_child_temporary_files_stay_in_owned_home(self):
        with tempfile.TemporaryDirectory() as td:
            env = clean_env(td, pathlib.Path(td) / "bin")
            for key in ("TEMP", "TMP", "TMPDIR"):
                self.assertEqual(env[key], td)
            self.assertEqual(env["PIP_NO_CACHE_DIR"], "1")

    def contract(self, kind, value):
        fields = ({"package": "owned", "resource": value, "equals": "ok"}
                  if kind == "resource" else {"command": value, "equals": "ok"})
        return {"id": "owned", "kind": kind, "distribution": "owned",
                "modules": ["owned"], "evidence": "owned local path fixture", **fields}

    def reject_before_setup(self, kind, value):
        for schema in (1, 2):
            with self.subTest(schema=schema, value=value):
                spec = {"schema": schema, "contracts": [self.contract(kind, value)]}
                with mock.patch("wheelgate.runner.wheel_identity") as identity, \
                     mock.patch("wheelgate.runner.prepare") as prepare:
                    with self.assertRaises(ValueError):
                        qualify("not-opened.whl", spec)
                identity.assert_not_called()
                prepare.assert_not_called()

    def test_resource_nested_posix_path(self):
        self.assertEqual(resource_parts("data/message.txt"), ("data", "message.txt"))
        validate({"schema": 2, "contracts": [self.contract("resource", "data/message.txt")]})

    def test_resource_windows_absolute(self):
        self.reject_before_setup("resource", "C:/owned/message.txt")

    def test_resource_windows_drive_relative(self):
        self.reject_before_setup("resource", "C:message.txt")

    def test_resource_windows_separator(self):
        self.reject_before_setup("resource", "data\\message.txt")

    def test_resource_absolute_or_traversing(self):
        for value in ("/message.txt", "../message.txt", "data/../message.txt"):
            self.reject_before_setup("resource", value)

    def test_resource_no_silent_dot_or_empty_normalization(self):
        for value in (".", "./message.txt", "data//message.txt", "data/", "data/./message.txt"):
            self.reject_before_setup("resource", value)

    def test_resource_colon_or_nul(self):
        for value in ("message.txt:extra", "message\x00.txt"):
            self.reject_before_setup("resource", value)

    def test_command_portable_basename(self):
        for value in ("owned", "owned-tool", "owned.tool"):
            self.assertEqual(command_basename(value), value)
            validate({"schema": 2, "contracts": [self.contract("cli", value)]})

    def test_command_windows_separator(self):
        self.reject_before_setup("cli", "folder\\owned")

    def test_command_windows_drive(self):
        for value in ("C:owned", "C:/owned"):
            self.reject_before_setup("cli", value)

    def test_command_posix_separator(self):
        for value in ("/owned", "folder/owned"):
            self.reject_before_setup("cli", value)

    def test_command_special_components(self):
        for value in (".", "..", "owned:extra", "owned\x00"):
            self.reject_before_setup("cli", value)

    def test_direct_worker_resource_rejects_before_import(self):
        with mock.patch("wheelgate.worker.owned") as owned:
            with self.assertRaises(ValueError):
                operation(self.contract("resource", "C:/owned/message.txt"))
        owned.assert_not_called()

    def test_direct_worker_cli_rejects_before_import(self):
        with mock.patch("wheelgate.worker.owned") as owned:
            with self.assertRaises(ValueError):
                operation(self.contract("cli", "folder\\owned"))
        owned.assert_not_called()

    def test_console_child_rejects_before_metadata(self):
        with mock.patch("wheelgate.worker.md.distribution") as distribution:
            with self.assertRaises(ValueError):
                _console_operation(self.contract("cli", "C:owned"))
        distribution.assert_not_called()

    def test_windows_launcher_preserves_dotted_basename(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            launcher = root / "owned.tool.exe"
            launcher.write_bytes(b"")
            entry = types.SimpleNamespace(group="console_scripts", name="owned.tool",
                                          module="owned", load=lambda: lambda: print("ok", end=""))
            with mock.patch.object(worker, "os", types.SimpleNamespace(name="nt")), \
                 mock.patch.object(worker.sys, "executable", str(root / "python.exe")), \
                 mock.patch("wheelgate.worker.md.distribution",
                            return_value=types.SimpleNamespace(entry_points=[entry])), \
                 mock.patch("wheelgate.worker.owned", return_value={"module": "owned"}), \
                 mock.patch("wheelgate.worker.owned_file", side_effect=lambda d, p: str(p)):
                result = _console_operation(self.contract("cli", "owned.tool"))
            self.assertEqual(result["launcher_origin"], str(launcher))
            self.assertEqual(result["argv"], [str(launcher)])

    def test_posix_exe_named_launcher_uses_recorded_python_script(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            launcher = root / "owned.exe"
            launcher.write_bytes(b"")
            entry = types.SimpleNamespace(group="console_scripts", name="owned.exe",
                                          module="owned", load=mock.Mock())
            with mock.patch.object(worker, "os", types.SimpleNamespace(name="posix")), \
                 mock.patch.object(worker.sys, "executable", str(root / "python")), \
                 mock.patch("wheelgate.worker.md.distribution",
                            return_value=types.SimpleNamespace(entry_points=[entry])), \
                 mock.patch("wheelgate.worker.owned", return_value={"module": "owned"}), \
                 mock.patch("wheelgate.worker.owned_file", side_effect=lambda d, p: str(p)), \
                 mock.patch("wheelgate.worker.runpy.run_path",
                            side_effect=lambda *a, **k: print("ok", end="")) as run_path:
                result = _console_operation(self.contract("cli", "owned.exe"))
            run_path.assert_called_once_with(str(launcher), run_name="__main__")
            entry.load.assert_not_called()
            self.assertEqual(result["launcher_origin"], str(launcher))
            self.assertEqual(result["stdout"], "ok")

    def test_windows_launcher_uses_registered_entrypoint_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            launcher = root / "owned.exe"
            launcher.write_bytes(b"")
            entry = types.SimpleNamespace(group="console_scripts", name="owned",
                                          module="owned",
                                          load=mock.Mock(return_value=lambda: print("ok", end="")))
            with mock.patch.object(worker, "os", types.SimpleNamespace(name="nt")), \
                 mock.patch.object(worker.sys, "executable", str(root / "python.exe")), \
                 mock.patch("wheelgate.worker.md.distribution",
                            return_value=types.SimpleNamespace(entry_points=[entry])), \
                 mock.patch("wheelgate.worker.owned", return_value={"module": "owned"}), \
                 mock.patch("wheelgate.worker.owned_file", side_effect=lambda d, p: str(p)), \
                 mock.patch("wheelgate.worker.runpy.run_path") as run_path:
                result = _console_operation(self.contract("cli", "owned"))
            entry.load.assert_called_once_with()
            run_path.assert_not_called()
            self.assertEqual(result["launcher_origin"], str(launcher))
            self.assertEqual(result["stdout"], "ok")

    def test_nested_resource_join_uses_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "data").mkdir()
            (root / "data/message.txt").write_text("ok", encoding="utf-8")
            with mock.patch("wheelgate.worker.owned", return_value={"module": "owned"}), \
                 mock.patch("wheelgate.worker.owned_file", side_effect=lambda d, p: str(p)), \
                 mock.patch("wheelgate.worker.resources.files", return_value=root):
                result = operation(self.contract("resource", "data/message.txt"))
            self.assertEqual(result["value"], "ok")
            self.assertEqual(result["resource_origin"], str(root / "data/message.txt"))


class PortableEvidenceReferences(unittest.TestCase):
    def test_windows_parts_map_to_posix_components(self):
        value = "results\\routes\\assets\\owned.whl"
        self.assertEqual(pathlib.PurePosixPath(value).parts, (value,))
        self.assertEqual(_evidence.relative_parts(value),
                         ("results", "routes", "assets", "owned.whl"))
        self.assertEqual(pathlib.PurePosixPath("/bundle").joinpath(*_evidence.relative_parts(value)),
                         pathlib.PurePosixPath("/bundle/results/routes/assets/owned.whl"))

    def test_both_record_conventions_find_same_owned_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            record = root / "results/routes/matrix.json"
            wheel = record.parent / "assets/owned.whl"
            wheel.parent.mkdir(parents=True)
            wheel.write_bytes(b"owned path fixture, not an installable archive")
            for value in ("assets/owned.whl", "assets\\owned.whl",
                          "results/routes/assets/owned.whl", "results\\routes\\assets\\owned.whl"):
                with self.subTest(value=value):
                    resolved = _evidence.resolve_result_path(root, record, value)
                    self.assertEqual(resolved, wheel.resolve())
                    self.assertEqual(resolved.read_bytes(), wheel.read_bytes())

    def test_absolute_and_drive_references_rejected(self):
        for value in ("/owned.txt", "\\owned.txt", "C:/owned.txt", "C:owned.txt",
                      "\\\\host\\share\\owned.txt", "//host/share/owned.txt"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _evidence.relative_parts(value)

    def test_traversal_and_ambiguous_components_rejected(self):
        for value in ("../owned.txt", "assets\\..\\owned.txt", "assets//owned.txt",
                      "./owned.txt", "assets/", "owned.txt:extra", "owned\x00.txt", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _evidence.relative_parts(value)

    def test_record_outside_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            with self.assertRaises(ValueError):
                _evidence.resolve_result_path(root / "bundle", root / "other/matrix.json", "owned.txt")

    def test_symlink_escape_rejected_with_owned_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            bundle = root / "bundle"
            outside = root / "other-owned-fixture"
            bundle.mkdir(); outside.mkdir()
            try:
                (bundle / "link").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Directory symlink creation not supported by this host")
            with self.assertRaises(ValueError):
                _evidence.resolve_relative(bundle, "link/owned.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
