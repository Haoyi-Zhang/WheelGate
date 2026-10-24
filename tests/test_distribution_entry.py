"""Owned offline regressions for software/source and installed metadata binding."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def helper(name):
    path = ROOT/'scripts'/f'{name}.py'
    if not path.is_file(): return None
    sys.path.insert(0,str(ROOT/'scripts'))
    try:
        spec = importlib.util.spec_from_file_location('owned_'+name,path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


build, audit = helper('build_distribution'), helper('audit')


@unittest.skipIf(build is None or audit is None,'Artifact-only distribution helpers are not runtime modules')
class DistributionEntry(unittest.TestCase):
    def fixture(self, root, version='1.1.0'):
        wheel = root/'owned.whl'
        with zipfile.ZipFile(wheel,'w') as z:
            z.writestr('wheelgate/__init__.py',f'__version__ = "{version}"\n')
            z.writestr('wheelgate/contractio.py','external_inputs = True\n')
            z.writestr(f'wheelgate-{version}.dist-info/METADATA',f'Name: wheelgate\nVersion: {version}\n')
        expected = {'wheelgate/__init__.py':build.digest(f'__version__ = "{version}"\n'.encode()),
                    'wheelgate/contractio.py':build.digest(b'external_inputs = True\n')}
        return wheel, expected

    def test_exact_module_payload_required(self):
        with tempfile.TemporaryDirectory() as td:
            wheel, expected = self.fixture(Path(td))
            self.assertEqual(build.verify_wheel(wheel,expected,'1.1.0'),expected)
            expected['wheelgate/contractio.py'] = build.digest(b'older module\n')
            with self.assertRaisesRegex(ValueError,'payload differs'):
                build.verify_wheel(wheel,expected,'1.1.0')

    def test_extra_module_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            wheel, expected = self.fixture(Path(td))
            with zipfile.ZipFile(wheel,'a') as z: z.writestr('wheelgate/extra.py','pass\n')
            with self.assertRaisesRegex(ValueError,'payload differs'):
                build.verify_wheel(wheel,expected,'1.1.0')

    def test_distribution_version_must_match_current_source(self):
        with tempfile.TemporaryDirectory() as td:
            wheel, expected = self.fixture(Path(td))
            with self.assertRaisesRegex(ValueError,'metadata does not match'):
                build.verify_wheel(wheel,expected,'1.0.0')

    def test_installed_identity_matches_each_recorded_wheel(self):
        with tempfile.TemporaryDirectory() as td:
            for version in ('1.0.0','1.1.0'):
                wheel, _ = self.fixture(Path(td),version)
                identity = {'version':version,'module':'/env/lib/site-packages/wheelgate/__init__.py'}
                self.assertEqual(audit.audit_installed_identity(wheel,identity),version)
                identity['version']='9.9.9'
                with self.assertRaisesRegex(AssertionError,'differs from its wheel'):
                    audit.audit_installed_identity(wheel,identity)


if __name__ == '__main__': unittest.main()
