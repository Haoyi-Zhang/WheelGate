"""Retained route-source identity checks; no package execution or rebuilding."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / 'results/routes/matrix.json'
AUDIT = ROOT / 'scripts/audit.py'


@unittest.skipUnless(RECORD.is_file() and AUDIT.is_file(),
                     'Requires retained artifact study records, not the runtime wheel')
class RetainedRouteSourceBinding(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('route_binding_audit', AUDIT)
        self.audit = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
            spec.loader.exec_module(self.audit)
        self.expected = json.loads(RECORD.read_text(encoding='utf-8'))['script_sha256']
        self.source = ROOT / 'results/routes/provenance/route_matrix.py'

    def test_retained_source_matches_the_selected_execution_record(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),
                         self.expected)

    def test_audit_selects_the_retained_source_not_an_unbound_generator(self):
        tree = ast.parse(AUDIT.read_text(encoding='utf-8'))
        body = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'audit_routes')
        calls = [n for n in ast.walk(body) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'record_script']
        self.assertEqual(len(calls), 1)
        candidates = eval(compile(ast.Expression(calls[0].args[1]), str(AUDIT), 'eval'),
                          {'__builtins__': {}}, {'ROOT': ROOT})
        self.assertIn(self.source, candidates)
        self.assertEqual(self.audit.record_script(self.expected, candidates), self.source)

    def test_existing_but_incorrect_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.py'
            source.write_text('# not the recorded source\n', encoding='utf-8')
            with self.assertRaisesRegex(AssertionError, 'matches the selected record'):
                self.audit.record_script(self.expected, [source])

    def test_correct_source_after_wrong_candidate_is_still_found(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.py'
            source.write_text('# not the recorded source\n', encoding='utf-8')
            self.assertEqual(self.audit.record_script(self.expected,
                             [source, self.source]), self.source)


if __name__ == '__main__':
    unittest.main()
