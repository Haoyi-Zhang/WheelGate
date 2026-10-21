"""Portable artifact-helper tests: no installs, subject imports or native runs.

The helper is artifact tooling, not part of the installed WheelGate API. Tests
staged beside an installed software wheel skip when artifact scripts are absent.
"""
import importlib.util
import hashlib
import json
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

    def test_fresh_report_binds_execution_capture_bytes_without_normalizing(self):
        cases = []
        for name, version, expected in module.CASES:
            cases.append({'case': name + '-' + version, 'expected_status': expected,
                          'wheel': 'owned.whl', 'contract': 'owned.json', 'profile': 'base',
                          'dependencies': [], 'sha256': 'wheel', 'contract_sha256': 'contract'})
        captured = {}
        with tempfile.TemporaryDirectory() as td:
            output, temporary = Path(td) / 'output', Path(td) / 'short-temp'

            def child(argv, **kwargs):
                target = Path(argv[argv.index('--output') + 1])
                case = next(c for c in cases if target.name == c['case'] + '-public-cli.json')
                receipt = {'status': case['expected_status'], 'sha256': 'wheel',
                           'contract_sha256': 'contract', 'setup': {'status': 'READY'},
                           'profile_preflight': {'status': 'READY'},
                           'contracts': [{'status': case['expected_status']}],
                           'observed_path': str(temporary / 'owned-observation')}
                raw = (json.dumps(receipt, indent=1) + '\n').encode('utf-8')
                target.write_bytes(raw)
                captured[str(target)] = raw
                return type('OwnedProcess', (), {'returncode': 1 if case['expected_status'] == 'FAIL' else 0,
                                                 'stdout': 'owned capture', 'stderr': ''})()

            with patch.object(module.sys, 'platform', 'win32'), \
                 patch.object(module.sys, 'version_info', (3, 12)), \
                 patch.object(module.struct, 'calcsize', return_value=8), \
                 patch.object(module.subprocess, 'run', side_effect=child) as native:
                result = module.execute_plan({'cases': cases}, output, temporary)
            self.assertEqual(native.call_count, 3)
            self.assertTrue(result['all_expected'])
            self.assertEqual(result.get('receipt_representation'), 'execution-capture')
            self.assertEqual(result['script_sha256'], hashlib.sha256(HELPER.read_bytes()).hexdigest())
            for row in result['results']:
                raw = captured[row['raw_receipt']]
                self.assertEqual(Path(row['raw_receipt']).read_bytes(), raw)
                self.assertEqual(row['raw_receipt_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(row['raw_receipt_bytes'], len(raw))

    @unittest.skipUnless((ROOT / 'results/publisher-public-cli/report.json').is_file(),
                         'Published receipt projection is not staged with installed-software tests')
    def test_retained_projection_labels_normalized_bytes_and_original_identities(self):
        folder = ROOT / 'results/publisher-public-cli'
        report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report.get('receipt_representation'), 'path-normalized-public-copy')
        self.assertEqual(report['execution_helper']['binding_scope'], 'recorded-execution-source')
        self.assertEqual(report['execution_helper']['sha256'],
                         'fd2bbc52ae4a123176a385eda0d8036bedeb2bb0f5f02574ba3417b6284eb131')
        recorded = {
            'django-xml-4.0.0': ('080f83ab4b9cbc171687e85851847c46f65a318eb5db3ef9cea41a5ba08f362f', 17744),
            'django-xml-4.0.1': ('f8756c5c801370abbcc6804b4e900bc8840431979cff98dfdc6b4de61b1f3ceb', 163832),
            'latex2pydata-0.5.0': ('5c87c8c7a621719236542528d8d7b5c098b2b3269932877fb7577e0f73915c86', 14151),
        }
        for row in report['results']:
            identity = row['raw_receipt']
            raw = (folder / identity['file']).read_bytes()
            self.assertIn(b'<PYTHON_ROOT>', raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), identity['sha256'])
            self.assertEqual(len(raw), identity['bytes'])
            self.assertEqual((identity['recorded_sha256'], identity['recorded_bytes']), recorded[row['case']])
            self.assertNotEqual(identity['sha256'], identity['recorded_sha256'])
        descriptions = ' '.join(report['transformations'])
        self.assertIn('path-normalized', descriptions)
        self.assertNotIn('byte-preserved from the actual run', descriptions)
        self.assertNotIn('No raw operation receipt fields were removed or rewritten', descriptions)


if __name__ == "__main__":
    unittest.main()
