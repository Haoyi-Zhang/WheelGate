"""Portable artifact-helper tests: no installs, subject imports or native runs.

The helper is artifact tooling, not part of the installed WheelGate API. Tests
staged beside an installed software wheel skip when artifact scripts are absent.
"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "publisher_cli_replay.py"
module = None
if HELPER.is_file():
    spec = importlib.util.spec_from_file_location("publisher_cli_replay_under_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


@unittest.skipIf(module is None, "Artifact-only helper is not shipped in the runtime wheel")
class PublicCliReplayHelper(unittest.TestCase):
    def test_child_temp_is_local_and_does_not_keep_ambient_path_overrides(self):
        short_temp = Path(tempfile.gettempdir()) / "wheelgate-owned-helper-temp"
        with patch.dict(os.environ, {"PYTHONPATH": "ambient", "PYTHONHOME": "ambient"}):
            before = os.environ.copy()
            with patch.object(module.subprocess, "run") as run:
                env = module.child_environment(short_temp)
                run.assert_not_called()
            self.assertEqual(os.environ, before)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        for name in ("TEMP", "TMP", "TMPDIR"):
            self.assertEqual(env[name], str(short_temp))
        self.assertEqual(env["PIP_NO_INDEX"], "1")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_bad_input_identity_stops_before_native_execution(self):
        with tempfile.TemporaryDirectory() as td, patch.object(module.subprocess, "run") as run:
            wheel = Path(td) / "owned.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("owned.txt", "benign")
            with self.assertRaises(ValueError):
                module.verified_file(wheel, {"bytes": wheel.stat().st_size, "sha256": "0" * 64})
            run.assert_not_called()

    def test_expected_subject_fail_requires_valid_setup_and_receipt_binding(self):
        case = {"expected_status": "FAIL", "sha256": "wheel", "contract_sha256": "contract"}
        receipt = {"status": "FAIL", "sha256": "wheel", "contract_sha256": "contract",
                   "setup": {"status": "READY"}, "profile_preflight": {"status": "READY"},
                   "contracts": [{"status": "FAIL"}]}
        with patch.object(module.subprocess, "run") as run:
            self.assertTrue(module.case_matches(case, receipt, 1))
            self.assertFalse(module.case_matches(case, receipt, 0))
            receipt["setup"]["status"] = "BLOCKED"
            self.assertFalse(module.case_matches(case, receipt, 1))
            receipt["setup"]["status"] = "READY"
            receipt["contract_sha256"] = "other"
            self.assertFalse(module.case_matches(case, receipt, 1))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
