"""Bounded core checks, separate from the 50 measured study runs."""
import copy,json,pathlib,subprocess,sys,tempfile,unittest
from unittest import mock
from wheelgate.runner import validate,probe,execute,clean_env
from wheelgate.worker import compare,owned,InvalidRun
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Schema(unittest.TestCase):
    def setUp(self):self.spec=json.loads((ROOT/'contracts/fixture.json').read_text())
    def test_valid(self):validate(self.spec)
    def test_empty(self):
        self.spec['contracts']=[]
        with self.assertRaises(ValueError):validate(self.spec)
    def test_duplicate(self):
        self.spec['contracts'].append(self.spec['contracts'][0])
        with self.assertRaises(ValueError):validate(self.spec)
    def test_missing_evidence(self):
        del self.spec['contracts'][0]['evidence']
        with self.assertRaises(ValueError):validate(self.spec)
    def test_unknown_kind(self):
        self.spec['contracts'][0]['kind']='unknown'
        with self.assertRaises(ValueError):validate(self.spec)
    def test_missing_origin_anchor(self):
        self.spec['contracts'][0]['modules']=[]
        with self.assertRaises(ValueError):validate(self.spec)
    def test_missing_expected_value(self):
        del self.spec['contracts'][1]['equals']
        with self.assertRaises(ValueError):validate(self.spec)
    def test_timeout_bounds(self):
        for value in [0,-1,61,True,'1']:
            s=copy.deepcopy(self.spec);s['contracts'][0]['timeout']=value
            with self.assertRaises(ValueError):validate(s)
    def test_missing_target(self):
        del self.spec['contracts'][1]['target']
        with self.assertRaises(ValueError):validate(self.spec)
    def test_all_skipped_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);r=probe(self.spec,sys.executable,clean_env(p,pathlib.Path(sys.executable).parent),p/'probe','unsupported')
        self.assertEqual(r['status'],'INVALID')
        self.assertTrue(all(c['status']=='NOT_APPLICABLE' for c in r['contracts']))
class Oracles(unittest.TestCase):
    def test_equal(self):compare({'x':1},{'equals':{'x':1}})
    def test_wrong_value(self):
        with self.assertRaises(AssertionError):compare({'x':2},{'equals':{'x':1}})
    def test_contains(self):compare('hello\n',{'contains':'hello'})
    def test_wrong_substring(self):
        with self.assertRaises(AssertionError):compare('bye',{'contains':'hello'})
    def test_foreign_origin(self):
        fake=mock.Mock(__file__='/tmp/not-an-installed-package/module.py')
        dist=mock.Mock(files=[])
        with mock.patch('wheelgate.worker.md.distribution',return_value=dist),mock.patch('wheelgate.worker.importlib.import_module',return_value=fake):
            with self.assertRaises(InvalidRun):owned('example','example')
    def test_namespace_anchor(self):
        with mock.patch('wheelgate.worker.importlib.import_module',return_value=mock.Mock(__file__=None)):
            with self.assertRaises(InvalidRun):owned('example','example')
class Process(unittest.TestCase):
    def test_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);r=execute([sys.executable,'-I','-c','import time;time.sleep(0.2)'],p,clean_env(p,pathlib.Path(sys.executable).parent),timeout=.01)
        self.assertTrue(r['timeout']);self.assertEqual(r['returncode'],124)
    def test_missing_executable(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);r=execute([p/'does-not-exist'],p,clean_env(p,p))
        self.assertEqual(r['returncode'],127)
    def test_environment_allowlist(self):
        e=clean_env('/tmp','/usr/bin');self.assertNotIn('PYTHONPATH',e);self.assertNotIn('PYTHONHOME',e)
    def test_isolated_import_ignores_shadow(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);(p/'json.py').write_text("raise RuntimeError('cwd shadow imported')")
            e=clean_env(p,pathlib.Path(sys.executable).parent);e['PYTHONPATH']=str(p)
            r=execute([sys.executable,'-I','-c','import json;print(json.__file__)'],p,e)
        self.assertEqual(r['returncode'],0,r['stderr']);self.assertNotIn('cwd shadow imported',r['stderr'])
if __name__=='__main__':unittest.main(verbosity=2)
