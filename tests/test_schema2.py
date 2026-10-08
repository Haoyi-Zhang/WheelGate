"""Configuration and prerequisite regressions, not external package defects."""
import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from wheelgate.contractio import load, loads
from wheelgate.profile_worker import inspect
from wheelgate.runner import bind_contracts, profile_preflight, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]


class StrictLoading(unittest.TestCase):
    def test_object(self):
        self.assertEqual(loads('{"a":1}'), {"a": 1})

    def test_duplicate_root_key(self):
        with self.assertRaises(ValueError): loads('{"schema":1,"schema":2}')

    def test_duplicate_nested_key(self):
        with self.assertRaises(ValueError): loads('{"x":{"a":1,"a":2}}')

    def test_nonfinite(self):
        for value in ['NaN', 'Infinity', '-Infinity']:
            with self.subTest(value=value), self.assertRaises(ValueError): loads(value)

    def test_root_array(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / 'c.json'; p.write_text('[]')
            with self.assertRaises(ValueError): load(p)

    def test_utf8(self):
        self.assertEqual(loads('{"name":"Zoë 東京"}')["name"], "Zoë 東京")


class SchemaTwo(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT/'contracts/fixture.json').read_text())
        self.spec['schema'] = 2

    def changed(self, kind, key, value):
        spec = copy.deepcopy(self.spec)
        next(c for c in spec['contracts'] if c['kind'] == kind)[key] = value
        return spec

    def rejects(self, kind, key, value):
        with self.assertRaises(ValueError): validate(self.changed(kind, key, value))

    def test_valid(self): validate(self.spec)
    def test_kind_array(self): self.rejects('import', 'kind', [])
    def test_format_array(self): self.rejects('resource', 'format', [])
    def test_boolean_schema(self):
        self.spec['schema'] = True
        with self.assertRaises(ValueError): validate(self.spec)
    def test_float_schema(self):
        self.spec['schema'] = 2.0
        with self.assertRaises(ValueError): validate(self.spec)
    def test_unknown_document_field(self):
        self.spec['contract'] = []
        with self.assertRaises(ValueError): validate(self.spec)
    def test_unknown_contract_field(self): self.rejects('call', 'equal', 'hello')
    def test_ignored_import_expectation(self): self.rejects('import', 'equals', 'not evaluated')
    def test_blank_id(self): self.rejects('import', 'id', '  ')
    def test_distribution_path(self): self.rejects('import', 'distribution', 'a/b')
    def test_invalid_module(self): self.rejects('import', 'modules', ['a..b'])
    def test_duplicate_module(self): self.rejects('import', 'modules', ['wg_fixture', 'wg_fixture'])
    def test_keyword_module(self): self.rejects('import', 'modules', ['class'])
    def test_incomplete_target(self): self.rejects('call', 'target', 'wg_fixture')
    def test_invalid_target_attribute(self): self.rejects('call', 'target', 'wg_fixture:()')
    def test_nonstring_kwargs_key(self): self.rejects('call', 'kwargs', {1: 'x'})
    def test_unknown_resource_format(self): self.rejects('resource', 'format', 'yaml')
    def test_resource_directory(self): self.rejects('resource', 'resource', 'directory/')
    def test_invalid_resource_package(self): self.rejects('resource', 'package', 'bad/name')
    def test_uninvoked_entry_expectation(self): self.rejects('entrypoint', 'invoke', False)
    def test_nonbool_invoke(self): self.rejects('entrypoint', 'invoke', 'false')
    def test_numeric_cli_arg(self): self.rejects('cli', 'args', [7])
    def test_nontext_cli_stdin(self): self.rejects('cli', 'stdin', [])
    def test_bool_returncode(self): self.rejects('cli', 'returncode', True)
    def test_nontext_cli_equals(self): self.rejects('cli', 'equals', 0)
    def test_nontext_cli_contains(self): self.rejects('cli', 'contains', 0)
    def test_nonfinite_expectation(self): self.rejects('call', 'equals', float('nan'))
    def test_nonjson_expectation(self): self.rejects('call', 'equals', {'a', 'b'})
    def test_version_range(self): self.rejects('import', 'version', '>=0.1')
    def test_literal_version(self): validate(self.changed('import', 'version', '0.1.0'))
    def test_wrong_version_binding(self):
        spec = self.changed('import', 'version', '99')
        with self.assertRaises(ValueError): bind_contracts(spec, {'name':'wg-fixture', 'version':'0.1.0'}, 'base')
    def test_matching_version_binding(self):
        bind_contracts(self.changed('import', 'version', '0.1.0'), {'name':'wg-fixture', 'version':'0.1.0'}, 'base')
    def test_script_syntax(self):
        self.spec['contracts'] = [dict(self.spec['contracts'][0], kind='script', code='def :')]
        with self.assertRaises(ValueError): validate(self.spec)
    def test_unused_script_expectation(self):
        self.spec['contracts'] = [dict(self.spec['contracts'][0], kind='script', code='assert True', equals=False)]
        with self.assertRaises(ValueError): validate(self.spec)


class DependencySchema(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT/'contracts/fixture.json').read_text()); self.spec['schema'] = 2
        self.dep = {'distribution':'wg-renderer', 'version':'1.0', 'evidence':'author-defined fixture README'}
        self.spec['profile_dependencies'] = {'base':[self.dep]}
    def test_valid(self): validate(self.spec)
    def test_empty_base(self):
        self.spec['profile_dependencies']['base'] = []; validate(self.spec)
    def test_not_object(self):
        self.spec['profile_dependencies'] = []
        with self.assertRaises(ValueError): validate(self.spec)
    def test_unknown_profile(self):
        self.spec['profile_dependencies'] = {'typo':[self.dep]}
        with self.assertRaises(ValueError): validate(self.spec)
    def test_no_list(self):
        self.spec['profile_dependencies'] = {'base':self.dep}
        with self.assertRaises(ValueError): validate(self.spec)
    def test_missing_evidence(self):
        del self.dep['evidence']
        with self.assertRaises(ValueError): validate(self.spec)
    def test_duplicate_normalized_name(self):
        self.spec['profile_dependencies']['base'].append(dict(self.dep, distribution='WG_renderer'))
        with self.assertRaises(ValueError): validate(self.spec)
    def test_no_range(self):
        self.dep['version'] = '>=1'
        with self.assertRaises(ValueError): validate(self.spec)
    def test_nontext_name(self):
        self.dep['distribution'] = 1
        with self.assertRaises(ValueError): validate(self.spec)
    def test_blank_evidence(self):
        self.dep['evidence'] = ' '
        with self.assertRaises(ValueError): validate(self.spec)


class DependencyWorker(unittest.TestCase):
    req = [{'distribution':'wg-renderer', 'version':'1.0', 'evidence':'README'}]
    def test_empty(self): self.assertEqual(inspect([])['status'], 'READY')
    def test_matching(self):
        with mock.patch('wheelgate.profile_worker.metadata.version', return_value='1.0'):
            self.assertEqual(inspect(self.req)['status'], 'READY')
    def test_wrong_version(self):
        with mock.patch('wheelgate.profile_worker.metadata.version', return_value='2.0'):
            self.assertEqual(inspect(self.req)['status'], 'BLOCKED')
    def test_missing(self):
        from importlib.metadata import PackageNotFoundError
        with mock.patch('wheelgate.profile_worker.metadata.version', side_effect=PackageNotFoundError):
            self.assertEqual(inspect(self.req)['status'], 'BLOCKED')
    def receipt(self, payload, rc=0):
        return {'stdout':'WHEELGATE_PROFILE='+json.dumps(payload)+'\n', 'returncode':rc,
                'stderr':'', 'timeout':False, 'seconds':0.01, 'argv':[]}
    def preflight(self, cp):
        with tempfile.TemporaryDirectory() as td, mock.patch('wheelgate.runner.execute', return_value=cp):
            return profile_preflight({'profile_dependencies':{'base':self.req}}, 'base', 'python', {}, pathlib.Path(td))
    def row(self, satisfied=True):
        return {'distribution':'wg-renderer', 'expected_version':'1.0', 'observed_version':'1.0' if satisfied else None, 'satisfied':satisfied}
    def test_consistent_ready_receipt(self):
        self.assertEqual(self.preflight(self.receipt({'status':'READY','requirements':[self.row()]}))['status'], 'READY')
    def test_consistent_blocked_receipt(self):
        self.assertEqual(self.preflight(self.receipt({'status':'BLOCKED','requirements':[self.row(False)]},2))['status'], 'BLOCKED')
    def test_contradictory_ready(self):
        self.assertEqual(self.preflight(self.receipt({'status':'READY','requirements':[self.row(False)]}))['status'], 'INVALID')
    def test_missing_rows(self):
        self.assertEqual(self.preflight(self.receipt({'status':'READY','requirements':[]}))['status'], 'INVALID')
    def test_bad_exit(self):
        self.assertEqual(self.preflight(self.receipt({'status':'READY','requirements':[self.row()]},2))['status'], 'INVALID')
    def test_bad_json(self):
        cp=self.receipt({});cp['stdout']='WHEELGATE_PROFILE={'
        self.assertEqual(self.preflight(cp)['status'], 'INVALID')
    def test_timeout(self):
        cp=self.receipt({'status':'READY','requirements':[self.row()]});cp['timeout']=True
        self.assertEqual(self.preflight(cp)['status'], 'INVALID')
    def test_duplicate_receipts(self):
        cp=self.receipt({'status':'READY','requirements':[self.row()]});cp['stdout'] *= 2
        self.assertEqual(self.preflight(cp)['status'], 'INVALID')


if __name__ == '__main__': unittest.main(verbosity=2)
