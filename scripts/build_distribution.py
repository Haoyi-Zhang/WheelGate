#!/usr/bin/env python3
"""Build the current software, bind its payload, and test both installation routes.

Only this owned package and its pinned offline setuptools input are built.
Retained experimental distributions and measurements are not overwritten.
"""
from __future__ import annotations

import argparse
import ast
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(root):
    return {p.relative_to(root).as_posix(): digest(p.read_bytes())
            for p in sorted((root/'wheelgate').rglob('*.py'))}


def verify_wheel(wheel, expected, version):
    with zipfile.ZipFile(wheel) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Invalid wheel members')
        observed = {n: digest(archive.read(n)) for n in archive.namelist() if n.startswith('wheelgate/')}
        if observed != expected:
            raise ValueError('Installed software payload differs from the current source')
        names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA') and n.count('/') == 1]
        if len(names) != 1:
            raise ValueError('One distribution metadata record required')
        metadata = Parser().parsestr(archive.read(names[0]).decode('utf-8'))
        if metadata.get('Name') != 'wheelgate' or metadata.get('Version') != version:
            raise ValueError('Distribution metadata does not match source version')
    return observed


def python_at(root):
    return root/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Fresh distribution directory')
    parser.add_argument('--log-dir', type=Path, required=True, help='Separate raw process logs')
    args = parser.parse_args()
    out, logs = args.output.resolve(), args.log_dir.resolve()
    if out.exists() or logs.exists() or logs == out or logs.is_relative_to(out):
        parser.error('Use fresh output and separate log directories')
    out.mkdir(parents=True)
    logs.mkdir(parents=True)
    namespace = {}
    exec((ROOT/'wheelgate/__init__.py').read_text(encoding='utf-8'), namespace)
    version = namespace['__version__']
    expected = payload(ROOT)
    test_source = ROOT/'tests/test_external_inputs.py'
    test_count = sum(isinstance(node, ast.FunctionDef) and node.name.startswith('test_')
                     for cls in ast.parse(test_source.read_text(encoding='utf-8')).body
                     if isinstance(cls, ast.ClassDef) for node in cls.body)
    if test_count < 1:
        raise ValueError('External-input regression suite is empty')
    processes = []
    def run(argv, cwd, env):
        cp = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=180)
        row = {'argv':[str(x) for x in argv], 'cwd':str(cwd), 'returncode':cp.returncode,
               'stdout':cp.stdout, 'stderr':cp.stderr}
        processes.append(row)
        (logs/'processes.json').write_text(json.dumps(processes, indent=2)+'\n', encoding='utf-8')
        if cp.returncode:
            raise RuntimeError(cp.stdout+'\n'+cp.stderr)
        return cp
    with tempfile.TemporaryDirectory(prefix='wheelgate-distribution-') as td:
        work = Path(td)
        env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', SOURCE_DATE_EPOCH='1704067200')
        for name in ('PYTHONPATH','PYTHONHOME'):
            env.pop(name, None)
        venv.EnvBuilder(with_pip=True).create(work/'builder')
        py = python_at(work/'builder')
        run([py,'-I','-m','pip','install','--no-index','--no-deps',ROOT/'third_party/setuptools-78.1.1-py3-none-any.whl'],work,env)
        for name in ('direct','source'):
            folder = work/name
            folder.mkdir()
            shutil.copytree(ROOT/'wheelgate',folder/'wheelgate',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            for filename in ('setup.py','pyproject.toml','MANIFEST.in','README.md','LICENSE'):
                shutil.copy2(ROOT/filename,folder/filename)
        direct, source, rebuilt = work/'direct-output', work/'source-output', work/'rebuilt-output'
        for folder in (direct,source,rebuilt): folder.mkdir()
        run([py,'-I','-c',f'from setuptools.build_meta import build_wheel;build_wheel({str(direct)!r})'],work/'direct',env)
        run([py,'-I','-c',f'from setuptools.build_meta import build_sdist;build_sdist({str(source)!r})'],work/'source',env)
        sdist = source/f'wheelgate-{version}.tar.gz'
        with tarfile.open(sdist) as archive:
            source_payload = {m.name.split('/',1)[1]:digest(archive.extractfile(m).read())
                              for m in archive.getmembers() if m.isfile() and '/wheelgate/' in m.name and m.name.endswith('.py')}
            if source_payload != expected:
                raise ValueError('Source distribution differs from current modules')
            unpacked = work/'unpacked'
            unpacked.mkdir()
            archive.extractall(unpacked,filter='data')
        run([py,'-I','-c',f'from setuptools.build_meta import build_wheel;build_wheel({str(rebuilt)!r})'],unpacked/f'wheelgate-{version}',env)
        routes = []
        for label, folder in (('direct-wheel',direct),('sdist-wheel',rebuilt)):
            wheel = next(folder.glob('*.whl'))
            verify_wheel(wheel,expected,version)
            neutral = work/label
            neutral.mkdir()
            venv.EnvBuilder(with_pip=True).create(neutral/'env')
            subject = python_at(neutral/'env')
            run([subject,'-I','-m','pip','install','--no-index','--no-deps',wheel],neutral,env)
            identity = run([subject,'-I','-c',
                'import wheelgate,pathlib,sys,importlib.metadata as m;'
                'assert pathlib.Path(wheelgate.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve());'
                f'assert wheelgate.__version__ == m.version("wheelgate") == {version!r};'
                'print(wheelgate.__version__)'],neutral,env)
            tests = neutral/'tests'
            tests.mkdir()
            shutil.copy2(test_source,tests/'test_external_inputs.py')
            check = run([subject,'-I','-B','-m','unittest','discover','-s',tests,'-v'],neutral,env)
            found = re.findall(r'Ran (\d+) tests? in ',check.stdout+check.stderr)
            if found != [str(test_count)] or re.search(r'(?m)^OK$',check.stdout+check.stderr) is None:
                raise ValueError('Every external-input regression must execute and pass without skips')
            command = subject.parent/('wheelgate.exe' if os.name == 'nt' else 'wheelgate')
            cli = run([command,'--version'],neutral,env)
            if cli.stdout != 'WheelGate '+version+'\n':
                raise ValueError('Installed console entry point version mismatch')
            routes.append({'route':label,'payload_matches_current_source':True,'external_input_tests_passed':test_count,
                           'installed_version':identity.stdout.strip(),'console_entrypoint_passed':True})
        software = next(direct.glob('*.whl'))
        shutil.copy2(software,out/software.name)
        shutil.copy2(sdist,out/sdist.name)
        manifest = {'software':'wheelgate','version':version,'status':'PASS','source_payload':expected,
                    'files':{p.name:digest(p.read_bytes()) for p in sorted(out.iterdir())},'routes':routes,
                    'scope':'Current owned software installation and external-input regressions; retained study measurements are unchanged.'}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','version':version,'routes':len(routes),'external_input_tests_passed':test_count*len(routes)}))


if __name__ == '__main__':
    main()
