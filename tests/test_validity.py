"""Regression tests for qualification scope; none are third-party vulnerability tests."""
import copy, json, pathlib, sys, tempfile, unittest, zipfile
from unittest import mock
from wheelgate.runner import bind_contracts, normalized_name, parsed_report, validate, wheel_identity
from wheelgate.worker import InvalidRun, owned_file, operation
ROOT=pathlib.Path(__file__).resolve().parents[1]

class IdentityTests(unittest.TestCase):
    def setUp(self):self.spec=json.loads((ROOT/'contracts/fixture.json').read_text())
    def test_exact_root(self):bind_contracts(self.spec,{'name':'wg-fixture','version':'0.1.0'},'base')
    def test_canonical_names(self):
        for name in ['WG-Fixture','wg_fixture','wg.fixture']:self.assertEqual(normalized_name(name),'wg-fixture')
    def test_wrong_root(self):
        with self.assertRaises(ValueError):bind_contracts(self.spec,{'name':'other','version':'1'},'base')
    def test_empty_profile(self):
        with self.assertRaises(ValueError):bind_contracts(self.spec,{'name':'wg-fixture'},'')
    def test_inactive_profile(self):
        with self.assertRaises(ValueError):bind_contracts(self.spec,{'name':'wg-fixture'},'unknown')
    def test_inactive_foreign_contract(self):
        self.spec['contracts'].append({'id':'inactive','distribution':'other','profiles':['optional']})
        bind_contracts(self.spec,{'name':'wg-fixture'},'base')
    def test_wheel_metadata(self):
        p=ROOT/'inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl'
        self.assertEqual(wheel_identity(p),{'name':'wg-fixture','version':'0.1.0'})
    def test_missing_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'a.whl'
            with zipfile.ZipFile(p,'w') as z:z.writestr('a.py','')
            with self.assertRaises(ValueError):wheel_identity(p)
    def test_duplicate_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'a.whl'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('a.dist-info/METADATA','Name: a\nVersion: 1\n')
                z.writestr('b.dist-info/METADATA','Name: b\nVersion: 1\n')
            with self.assertRaises(ValueError):wheel_identity(p)
    def test_incomplete_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'a.whl'
            with zipfile.ZipFile(p,'w') as z:z.writestr('a.dist-info/METADATA','Name: a\n')
            with self.assertRaises(ValueError):wheel_identity(p)

class ReceiptTests(unittest.TestCase):
    def receipt(self,rows,rc=0,prefix='WHEELGATE_JSON='):
        return {'stdout':prefix+json.dumps(rows)+'\n','returncode':rc,'timeout':False}
    def test_pass_receipt(self):self.assertIsNotNone(parsed_report(self.receipt({'id':'a','status':'PASS'}),'WHEELGATE_JSON=',['a']))
    def test_fail_receipt(self):self.assertIsNotNone(parsed_report(self.receipt({'id':'a','status':'FAIL'},1),'WHEELGATE_JSON=',['a']))
    def test_invalid_receipt(self):self.assertIsNotNone(parsed_report(self.receipt({'id':'a','status':'INVALID'},2),'WHEELGATE_JSON=',['a']))
    def test_nonzero_pass(self):self.assertIsNone(parsed_report(self.receipt({'id':'a','status':'PASS'},1),'WHEELGATE_JSON=',['a']))
    def test_zero_fail(self):self.assertIsNone(parsed_report(self.receipt({'id':'a','status':'FAIL'}),'WHEELGATE_JSON=',['a']))
    def test_unknown_status(self):self.assertIsNone(parsed_report(self.receipt({'id':'a','status':'MAYBE'}),'WHEELGATE_JSON=',['a']))
    def test_wrong_id(self):self.assertIsNone(parsed_report(self.receipt({'id':'b','status':'PASS'}),'WHEELGATE_JSON=',['a']))
    def test_duplicate_receipts(self):
        p=self.receipt({'id':'a','status':'PASS'});p['stdout']*=2
        self.assertIsNone(parsed_report(p,'WHEELGATE_JSON=',['a']))
    def test_timeout_receipt(self):
        p=self.receipt({'id':'a','status':'PASS'});p['timeout']=True
        self.assertIsNone(parsed_report(p,'WHEELGATE_JSON=',['a']))
    def test_broken_json(self):self.assertIsNone(parsed_report({'stdout':'WHEELGATE_JSON={','returncode':0,'timeout':False},'WHEELGATE_JSON=',['a']))
    def test_batch_all_pass(self):self.assertIsNotNone(parsed_report(self.receipt([{'id':'a','status':'PASS'},{'id':'b','status':'PASS'}],prefix='WHEELGATE_BATCH='),'WHEELGATE_BATCH=',['a','b'],True))
    def test_batch_partial_fail(self):self.assertIsNotNone(parsed_report(self.receipt([{'id':'a','status':'PASS'},{'id':'b','status':'FAIL'}],1,'WHEELGATE_BATCH='),'WHEELGATE_BATCH=',['a','b'],True))
    def test_batch_reordered(self):self.assertIsNone(parsed_report(self.receipt([{'id':'b','status':'PASS'},{'id':'a','status':'PASS'}],prefix='WHEELGATE_BATCH='),'WHEELGATE_BATCH=',['a','b'],True))
    def test_batch_incomplete(self):self.assertIsNone(parsed_report(self.receipt([{'id':'a','status':'PASS'}],prefix='WHEELGATE_BATCH='),'WHEELGATE_BATCH=',['a','b'],True))

class StrictSchemaTests(unittest.TestCase):
    def setUp(self):self.spec=json.loads((ROOT/'contracts/fixture.json').read_text())
    def change(self,k,v):
        s=copy.deepcopy(self.spec);s['contracts'][0][k]=v;return s
    def test_whitespace_distribution(self):
        with self.assertRaises(ValueError):validate(self.change('distribution','  '))
    def test_nonstring_distribution(self):
        with self.assertRaises(ValueError):validate(self.change('distribution',13))
    def test_blank_evidence(self):
        with self.assertRaises(ValueError):validate(self.change('evidence','  '))
    def test_nonstring_evidence(self):
        with self.assertRaises(ValueError):validate(self.change('evidence',{}))
    def test_profiles_wrong_type(self):
        with self.assertRaises(ValueError):validate(self.change('profiles','base'))
    def test_profiles_member_type(self):
        with self.assertRaises(ValueError):validate(self.change('profiles',[1]))
    def test_profiles_duplicates(self):
        with self.assertRaises(ValueError):validate(self.change('profiles',['base','base']))
    def test_profiles_blank(self):
        with self.assertRaises(ValueError):validate(self.change('profiles',['']))
    def test_args_mapping(self):
        with self.assertRaises(ValueError):validate(self.change('args',{}))
    def test_kwargs_list(self):
        with self.assertRaises(ValueError):validate(self.change('kwargs',[]))
    def test_bad_resource_paths(self):
        for value in ['/tmp/a','../a','a\\b']:
            s=copy.deepcopy(self.spec);c=next(c for c in s['contracts'] if c['kind']=='resource');c['resource']=value
            with self.subTest(value=value), self.assertRaises(ValueError):validate(s)
    def test_nan_timeout(self):
        with self.assertRaises(ValueError):validate(self.change('timeout',float('nan')))
    def test_infinite_timeout(self):
        with self.assertRaises(ValueError):validate(self.change('timeout',float('inf')))

class StaticOwnershipTests(unittest.TestCase):
    def test_unrecorded_file(self):
        with mock.patch('wheelgate.worker.md.distribution',return_value=mock.Mock(files=[])):
            with self.assertRaises(InvalidRun):owned_file('a',pathlib.Path(sys.prefix)/'unrecorded.txt')
    def test_recorded_file(self):
        p=pathlib.Path(sys.prefix)/'recorded.txt';d=mock.Mock(files=['recorded.txt']);d.locate_file=lambda x:p
        with mock.patch('wheelgate.worker.md.distribution',return_value=d):self.assertEqual(owned_file('a',p),str(p.resolve()))
    def test_outside_prefix_even_if_recorded(self):
        p=pathlib.Path('/not/the/venv/a.txt');d=mock.Mock(files=['a.txt']);d.locate_file=lambda x:p
        with mock.patch('wheelgate.worker.md.distribution',return_value=d):
            with self.assertRaises(InvalidRun):owned_file('a',p)
    def test_resource_package_is_checked(self):
        c={'id':'r','kind':'resource','distribution':'a','modules':['a'],'package':'b','resource':'data.txt','equals':'x'}
        def owner(d,m):
            if m=='b':raise InvalidRun('wrong owner')
            return {'module':m}
        with mock.patch('wheelgate.worker.owned',side_effect=owner):
            with self.assertRaises(InvalidRun):operation(c)

if __name__=='__main__':unittest.main(verbosity=2)
