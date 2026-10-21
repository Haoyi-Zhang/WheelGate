"""Owned no-build wrapper regressions: all build/install/process boundaries mocked."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/packaging_flow.py'
flow = None
if HELPER.is_file():
    spec = importlib.util.spec_from_file_location('owned_packaging_flow', HELPER)
    flow = importlib.util.module_from_spec(spec)
    with mock.patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
        spec.loader.exec_module(flow)


def process(returncode=0, timeout=False):
    return {'argv': ['owned-fixture'], 'returncode': returncode,
            'stdout': 'retained stdout', 'stderr': 'retained stderr',
            'timeout': timeout, 'seconds': 0.001}


@unittest.skipIf(flow is None, 'Artifact-only comparison helper is not in the runtime wheel')
class PackagingFlowExit(unittest.TestCase):
    def run_flow(self, *, ordinary_rc=0, ordinary_timeout=False,
                 gate_status='PASS', cwc_rc=0, cwc_timeout=False):
        calls = {'ordinary': 0, 'gate': 0, 'cwc': 0}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'results/comparison.json'

            def execute(argv, cwd, env, timeout=60):
                if any(str(arg).endswith('package_check.py') for arg in argv):
                    record_path = Path(argv[-1])
                    wheel = record_path.parent / 'owned.whl'
                    wheel.write_bytes(b'Owned no-build fixture; prepare is mocked')
                    row = {'wheel': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                           'unit_tests': process()}
                    record_path.write_text(json.dumps({'status': 'COMPLETE', 'payloads_equal': True,
                        'routes': [dict(row, route='direct-wheel'), dict(row, route='sdist-wheel')]}),
                        encoding='utf-8')
                    return process()
                if 'm.version(n)' in str(argv[-1]):
                    return dict(process(), stdout=json.dumps({'attrs': 'owned', 'click': 'owned',
                                                              'packaging': 'owned', 'pydantic': 'owned'}))
                if 'EXPECTED_VERSION=' in str(argv[-1]):
                    calls['ordinary'] += 1
                    return process(ordinary_rc, ordinary_timeout)
                calls['cwc'] += 1
                return process(cwc_rc, cwc_timeout)

            def probe(*args, **kwargs):
                calls['gate'] += 1
                return {'status': gate_status, 'contracts': [], 'owned_detail': 'do not erase'}

            with mock.patch.object(flow, 'execute', side_effect=execute), \
                 mock.patch.object(flow, 'prepare', return_value=(Path(sys.executable), {},
                     {'status': 'READY', 'wheel_identity': {'name': 'wheelgate', 'version': '1.0.0'}})), \
                 mock.patch.object(flow, 'probe', side_effect=probe), \
                 mock.patch.object(flow, 'verify_sources'), \
                 mock.patch.object(flow.sys, 'argv', ['packaging_flow.py', '--output', str(out)]), \
                 mock.patch('subprocess.run', side_effect=AssertionError('No native processes allowed')) as native, \
                 contextlib.redirect_stdout(io.StringIO()):
                code = flow.main()
            native.assert_not_called()
            result = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(calls, {'ordinary': 2, 'gate': 2, 'cwc': 4})
        self.assertEqual([r['route'] for r in result['runs']], ['direct-wheel', 'sdist-wheel'])
        for row in result['runs']:
            self.assertEqual(row['ordinary']['process']['stdout'], 'retained stdout')
            self.assertEqual(row['gate']['owned_detail'], 'do not erase')
            self.assertEqual(row['cwc']['default']['process']['stderr'], 'retained stderr')
        return code, result

    def assert_outcome(self, expected, code, result, method, observed):
        self.assertEqual(code, 1 if expected == 'FAIL' else 2)
        self.assertEqual(result['status'], expected)
        self.assertTrue(result['execution_completed'])
        self.assertFalse(result['all_expected'])
        self.assertTrue(any(r['method'] == method and r['status'] == observed
                            for r in result['unexpected_results']))

    def test_all_pass_keeps_zero_complete_and_all_observations(self):
        code, result = self.run_flow()
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertTrue(result['execution_completed'])
        self.assertTrue(result['all_expected'])
        self.assertEqual(result['unexpected_results'], [])
        self.assertTrue(all(r['ordinary']['status'] == r['gate']['status'] == 'PASS'
                            for r in result['runs']))

    def test_ordinary_failure_is_not_success(self):
        code, result = self.run_flow(ordinary_rc=1)
        self.assert_outcome('FAIL', code, result, 'ordinary', 'FAIL')

    def test_gate_failure_is_not_success(self):
        code, result = self.run_flow(gate_status='FAIL')
        self.assert_outcome('FAIL', code, result, 'gate', 'FAIL')

    def test_cwc_block_is_not_a_subject_rejection(self):
        code, result = self.run_flow(cwc_rc=2)
        self.assert_outcome('BLOCKED', code, result, 'cwc:default', 'BLOCKED')
        self.assertTrue(all(r['cwc']['reference']['status'] == 'BLOCKED' for r in result['runs']))

    def test_cwc_rejection_is_a_failed_comparison(self):
        code, result = self.run_flow(cwc_rc=1)
        self.assert_outcome('FAIL', code, result, 'cwc:reference', 'REJECT')

    def test_cwc_timeout_is_invalid(self):
        code, result = self.run_flow(cwc_rc=124, cwc_timeout=True)
        self.assert_outcome('INVALID', code, result, 'cwc:default', 'INVALID')

    def test_ordinary_timeout_is_invalid_not_a_semantic_failure(self):
        code, result = self.run_flow(ordinary_rc=124, ordinary_timeout=True)
        self.assert_outcome('INVALID', code, result, 'ordinary', 'INVALID')
        self.assertTrue(all(r['ordinary']['status'] == 'INVALID' for r in result['runs']))

    def test_gate_block_is_preserved(self):
        code, result = self.run_flow(gate_status='BLOCKED')
        self.assert_outcome('BLOCKED', code, result, 'gate', 'BLOCKED')

    def test_gate_invalid_is_preserved(self):
        code, result = self.run_flow(gate_status='INVALID')
        self.assert_outcome('INVALID', code, result, 'gate', 'INVALID')

    def test_mixed_failure_and_block_keeps_both_reasons(self):
        code, result = self.run_flow(ordinary_rc=1, cwc_rc=2)
        self.assert_outcome('BLOCKED', code, result, 'cwc:default', 'BLOCKED')
        self.assertTrue(any(r['method'] == 'ordinary' and r['status'] == 'FAIL'
                            for r in result['unexpected_results']))


if __name__ == '__main__':
    unittest.main()
