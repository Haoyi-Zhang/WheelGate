"""Console output and base-interpreter attribution regressions."""
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

from wheelgate.worker import _console_operation
from wheelgate.footprint import _roots, _classify_path


class ConsoleBoundaries(unittest.TestCase):
    def run_console(self, output, expected):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            executable = root / ('example.exe' if sys.platform == 'win32' else 'example')
            executable.write_bytes(b'')
            entry = types.SimpleNamespace(group='console_scripts', name='example', module='example')
            def main():
                sys.stdout.flush()
                sys.stdout.buffer.write(b'body\n')
                self.assertGreaterEqual(sys.stdout.fileno(), 0)
            entry.load = lambda: main
            dist = types.SimpleNamespace(entry_points=[entry])
            def owned(*args):
                if output:
                    print(output)
                return {'module': 'example'}
            with mock.patch('wheelgate.worker.sys.executable', str(root/'python.exe')), \
                 mock.patch('wheelgate.worker.md.distribution', return_value=dist), \
                 mock.patch('wheelgate.worker.owned', side_effect=owned), \
                 mock.patch('wheelgate.worker.owned_file', return_value=str(executable)), \
                 mock.patch('wheelgate.worker.runpy.run_path', side_effect=lambda *a,**k: main()):
                return _console_operation({'distribution':'example','command':'example',
                                           'modules':['example'],'equals':expected})

    def test_import_output_is_in_contract(self):
        result = self.run_console('import', 'import\nimport\nbody\n')
        self.assertEqual(result['returncode'], 0)

    def test_binary_output_and_file_descriptor(self):
        result = self.run_console('', 'body\n')
        self.assertEqual(result['stdout'], 'body\n')

    def test_base_third_party_is_not_stdlib(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td).resolve()
            std = root/'Lib'
            with mock.patch('wheelgate.footprint.sysconfig.get_paths', return_value={
                    'stdlib':str(std), 'platstdlib':str(std),
                    'purelib':str(root/'env/Lib/site-packages'),
                    'platlib':str(root/'env/Lib/site-packages')}):
                sites, standards = _roots()
            row, invalid = _classify_path(std/'site-packages/helper/data.json',
                                         set(), {}, sites, standards, root/'env')
            self.assertTrue(invalid)
            self.assertEqual(row['classification'], 'unowned-installed-file')

if __name__ == '__main__':
    unittest.main()
