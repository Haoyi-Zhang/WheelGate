"""Offline checks of selected publisher bytes and actual replay bindings.

No package installation, third-party imports, native execution, or benchmarks.
"""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate.runner import canonical_contract_digest, validate

EVIDENCE = ROOT / 'evidence/publisher-wheels'
RESULTS = ROOT / 'results/publisher-wheel-replay'
CASES = {'django-xml-4.0.0': 'FAIL', 'django-xml-4.0.1': 'PASS',
         'latex2pydata-0.5.0': 'PASS'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(root, value):
    path = (root / value).resolve()
    if not isinstance(value, str) or Path(value).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('Nonrelative publisher input')
    return path


class PublisherInputs(unittest.TestCase):
    def test_original_subject_bytes_members_and_license_notices(self):
        inv = load(EVIDENCE / 'source-inventory.json')
        subjects = [r for r in inv['inputs'] if r['role'] == 'selected original subject wheel']
        self.assertEqual({r['project']+'-'+r['version'] for r in subjects}, set(CASES))
        for row in subjects:
            with self.subTest(subject=row['project'], version=row['version']):
                wheel = relative(EVIDENCE, row['file'])
                self.assertEqual(wheel.stat().st_size, row['bytes'])
                self.assertEqual(digest(wheel), row['sha256'])
                self.assertTrue(row['publisher_url'].startswith('https://files.pythonhosted.org/'))
                with zipfile.ZipFile(wheel) as z:
                    self.assertIsNone(z.testzip())
                    members = {m['member']: m for m in row['archive_inventory']}
                    self.assertEqual(set(z.namelist()), set(members))
                    self.assertEqual(len(z.namelist()), len(members))
                    for name, member in members.items():
                        data = z.read(name)
                        self.assertEqual(len(data), member['bytes'])
                        self.assertEqual(hashlib.sha256(data).hexdigest(), member['sha256'])
                    for notice in row['license_notice_copies']:
                        copied = relative(EVIDENCE, notice['file'])
                        self.assertEqual(copied.read_bytes(), z.read(notice['archive_member']))
                        self.assertEqual(digest(copied), notice['sha256'])

    def test_protocol_and_inventory_bind_unchanged_runtime_sources(self):
        inv, protocol = load(EVIDENCE/'source-inventory.json'), load(RESULTS/'protocol.json')
        self.assertEqual(inv['runtime_source_bindings'], protocol['existing_runtime_source_bindings'])
        bindings = inv['runtime_source_bindings']
        self.assertEqual(len(bindings), 7)
        for binding in bindings:
            rel = binding['file']
            self.assertTrue(rel.startswith('artifact/'))
            self.assertEqual(digest(relative(ROOT, rel[len('artifact/'):])), binding['sha256'])

    def test_selected_contracts_and_same_ordinary_gate_decisions(self):
        protocol = load(RESULTS/'protocol.json')
        self.assertEqual({r['case'] for r in protocol['results']}, set(CASES))
        inputs = {r['project']+'-'+r['version']: r for r in load(EVIDENCE/'source-inventory.json')['inputs']}
        for case, verdict in CASES.items():
            with self.subTest(case=case):
                record = load(RESULTS/(case+'.json'))
                summary = record['summary']
                self.assertEqual(summary['case'], case)
                self.assertEqual(summary['ordinary_setup'], 'READY')
                self.assertEqual(summary['gate_setup'], 'READY')
                self.assertEqual(summary['ordinary_status'], verdict)
                self.assertEqual(summary['gate_status'], verdict)
                self.assertEqual(record['ordinary']['status'], verdict)
                self.assertTrue(record['ordinary']['operation_ran'])
                self.assertTrue(record['ordinary']['exit_consistent'])
                self.assertEqual(record['ordinary']['receipt']['status'], verdict)
                self.assertEqual(record['gate']['status'], verdict)
                contract = relative(ROOT, summary['contract'][len('artifact/'):])
                spec = load(contract)
                validate(spec)
                canonical = canonical_contract_digest(spec)
                self.assertEqual(summary['contract_sha256'], canonical)
                self.assertEqual(record['gate']['contract_sha256'], canonical)
                self.assertEqual(record['gate']['sha256'], inputs[case]['sha256'])
                checks = record['gate']['contracts']
                checks = checks if isinstance(checks, list) else [checks]
                self.assertEqual(len(checks), 1)
                self.assertEqual(checks[0]['status'], verdict)
                self.assertFalse(checks[0]['footprint']['violations'])
                self.assertFalse(checks[0]['file_footprint']['violations'])

    def test_selected_django_prerequisites_are_exact_and_satisfied(self):
        expected = {r['distribution']: r['version'] for r in load(RESULTS/'protocol.json')
                    ['selected_profile_not_historical']['django_prerequisites']}
        self.assertEqual(len(expected), 7)
        for case in ('django-xml-4.0.0','django-xml-4.0.1'):
            r = load(RESULTS/(case+'.json'))
            checks = r['gate']['profile_preflight']['requirements']
            self.assertEqual({c['distribution']: c['expected_version'] for c in checks}, expected)
            self.assertTrue(all(c['satisfied'] is True and c['observed_version'] == c['expected_version'] for c in checks))
            self.assertEqual(r['gate']['profile_preflight']['status'], 'READY')
            self.assertEqual(r['ordinary']['receipt']['prerequisites'], checks)

    def test_blocked_wrapper_attempts_remain_distinct(self):
        for case in ('django-xml-4.0.0','django-xml-4.0.1'):
            r = load(RESULTS/(case+'.json'))
            self.assertEqual(r['qualify_convenience_wrapper_attempt']['status'], 'BLOCKED')
            self.assertEqual(r['summary']['convenience_wrapper_status'], 'BLOCKED')
            self.assertEqual(r['summary']['gate_entry_route'], 'existing controller stages with short environment basename')
        latex = load(RESULTS/'latex2pydata-0.5.0.json')
        self.assertEqual(latex['ordinary']['receipt']['value'], {'main': {'count': 7}, 'label': 'HELLO'})

    def test_original_django_release_omission_and_repair(self):
        inputs = {r['project']+'-'+r['version']: r for r in load(EVIDENCE/'source-inventory.json')['inputs']}
        members = lambda key: {m['member'] for m in inputs[key]['archive_inventory'] if m['member'].startswith('djxml/')}
        self.assertEqual(members('django-xml-4.0.0'), {'djxml/__init__.py'})
        self.assertEqual(len(members('django-xml-4.0.1')), 16)
        self.assertIn('djxml/xmlmodels/fields/__init__.py', members('django-xml-4.0.1'))


if __name__ == '__main__':
    unittest.main()
