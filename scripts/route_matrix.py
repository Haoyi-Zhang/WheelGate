#!/usr/bin/env python3
"""Execute an authored route matrix with real setuptools, CM, and CWC code.

No network, no external repository modification, no publisher/industrial claim.
Pass a new --output path for independent validation; existing records are never
silently overwritten. Timings belong only to this experiment.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import pathlib
import shutil
import sys
import tarfile
import tempfile
import traceback
import venv
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wheelgate.runner import clean_env, execute, prepare, probe, venv_python
from cwc_baseline import verify_sources

API = '''from importlib.resources import files
import json
__version__ = "0.1.0"
def consumer():
    return json.loads(files(__package__).joinpath("template.json").read_text())["message"]
def main():
    print(consumer())
'''
README = '''# Authored route-sensitivity fixture
This is not a historical release or a maintained project deployment.
The supported consumer() API, wg-matrix command, and template.json resource
must provide the message hello and JSON schema value 1. Developer notes in
docs/ are intentionally excluded and are not consumer obligations.
'''
CONSUMER = '''import json, pathlib, sys
import wg_matrix
value = wg_matrix.consumer()
assert value == "hello", repr(value)
from importlib.resources import files
assert json.loads(files("wg_matrix").joinpath("template.json").read_text()) == {"schema":1,"message":"hello"}
print("MATRIX_JSON=" + json.dumps({"value":value,"origin":wg_matrix.__file__,"prefix":sys.prefix}))
'''
WHEEL_OWNERSHIP = '''
import importlib.metadata as metadata
owner = metadata.distribution('wg-matrix')
assert any(pathlib.Path(owner.locate_file(item)).resolve() == pathlib.Path(wg_matrix.__file__).resolve()
           for item in (owner.files or ())), 'Imported module is not owned by selected distribution'
'''


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def write_states(destination):
    states = {}
    for state in ['U', 'X', 'R']:
        source = destination / state
        source.mkdir(parents=True)
        (source/'wg_matrix').mkdir(); (source/'docs').mkdir()
        (source/'wg_matrix/__init__.py').write_text(API)
        (source/'wg_matrix/template.json').write_text('{"schema":1,"message":"hello"}\n')
        (source/'README.md').write_text(README)
        (source/'docs/developer.txt').write_text('Intentionally not part of the public delivery contract.\n')
        data = '{}' if state == 'U' else "{'wg_matrix':['template.json']}"
        (source/'setup.py').write_text(
            "from setuptools import setup\n"
            "setup(name='wg-matrix', version='0.1.0', packages=['wg_matrix'],\n"
            f"      package_data={data}, include_package_data=False,\n"
            "      description='Authored route-sensitivity fixture',\n"
            "      entry_points={'console_scripts':['wg-matrix=wg_matrix:main']})\n")
        manifest = 'prune docs\n'
        if state == 'X': manifest += 'exclude wg_matrix/template.json\n'
        if state == 'R': manifest += 'include wg_matrix/template.json\n'
        (source/'MANIFEST.in').write_text(manifest)
        states[state] = source
    return states


def contracts():
    common = {'distribution':'wg-matrix', 'modules':['wg_matrix'],
              'evidence':'Authored route-matrix README: API, static resource, and command'}
    return {'schema':2, 'contracts':[
        dict(common, id='api', kind='call', target='wg_matrix:consumer', equals='hello'),
        dict(common, id='resource', kind='resource', package='wg_matrix', resource='template.json',
             format='json', equals={'schema':1,'message':'hello'}),
        dict(common, id='cli', kind='cli', command='wg-matrix', equals='hello\n')]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT/'results/routes/matrix.json')
    parser.add_argument('--repetitions', type=int, default=3)
    args=parser.parse_args()
    if args.repetitions < 1: parser.error('repetitions must be positive')
    out=args.output.resolve()
    if out.exists(): parser.error('Output already exists; use a new output path')
    out.parent.mkdir(parents=True, exist_ok=True)
    assets=out.parent/(out.stem+'-assets'); assets.mkdir(exist_ok=False)
    states=write_states(assets/'sources'); spec=contracts()
    (assets/'contracts.json').write_text(json.dumps(spec,indent=2)+'\n')
    verify_sources()
    cm=ROOT/'third_party/source/check-manifest-0.50/check_manifest.py'
    paths=[str(ROOT/'third_party/source/check-wheel-contents-0.6.1/src'),
           str(ROOT/'third_party/source/wheel-filename-1.4.2/src')]
    cwc_launcher=f'import sys,runpy;sys.path[:0]={paths!r};runpy.run_module("check_wheel_contents",run_name="__main__")'
    result={'schema':1,'experiment':'authored-route-matrix','status':'RUNNING',
            'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'python':sys.version,'setuptools_input_sha256':digest(ROOT/'third_party/setuptools-78.1.1-py3-none-any.whl'),
            'cwc_dependency_versions':{p:importlib.metadata.version(p) for p in ['attrs','click','packaging','pydantic']},
            'script_sha256':digest(__file__), 'ordinary_scope':'API and resource on every route; also actual console command on both wheel routes, matching the gate obligations',
            'scope':'One authored project, three packaging states; zero historical published defect pairs.',
            'repetitions':args.repetitions,'commands':[],'manifest_runs':[], 'runs':[]}
    def save(): out.write_text(json.dumps(result,indent=2)+'\n')
    def run(argv,cwd,env,timeout=120):
        record=execute(argv,cwd,env,timeout=timeout);result['commands'].append(record)
        if record['returncode']:
            save();raise RuntimeError(f"Required setup/build command failed: {record}")
        return record
    try:
        with tempfile.TemporaryDirectory(prefix='wheelgate-route-') as td:
            temp=pathlib.Path(td);builder=temp/'builder';venv.EnvBuilder(with_pip=True).create(builder)
            py=venv_python(builder);home=temp/'home';home.mkdir();env=clean_env(home,py.parent)
            env['SOURCE_DATE_EPOCH']='1704067200'
            run([py,'-I','-m','pip','install','--no-index','--no-deps',
                 ROOT/'third_party/setuptools-78.1.1-py3-none-any.whl'],temp,env)
            run([py,'-I',cm,'--version'],temp,env)
            result['builder_version']=run([py,'-I','-c','import setuptools,sys;print(setuptools.__version__);print(sys.version)'],temp,env)
            for repetition in range(args.repetitions):
                for state, original in states.items():
                    cm_source=temp/f'cm-{repetition}-{state}';shutil.copytree(original,cm_source)
                    run(['git','init','-q',str(cm_source)],temp,env)
                    run(['git','add','.'],cm_source,env)
                    cp=execute([py,'-I',cm,'-v','--no-build-isolation',cm_source],temp,env,timeout=120)
                    classification='PASS' if cp['returncode']==0 else ('REJECT' if cp['returncode']==1 else 'BLOCKED')
                    result['manifest_runs'].append({'state':state,'repetition':repetition,'tool':'check-manifest',
                        'version':'0.50','build_route':'legacy setup.py sdist (both internal builds)',
                        'status':classification,'process':cp})
                    if classification=='BLOCKED':save();raise RuntimeError('check-manifest could not execute its comparison')
                    for route in ['checkout','editable','strict-editable','direct-wheel','sdist-wheel']:
                        source=temp/f'src-{repetition}-{state}-{route}';shutil.copytree(original,source)
                        work=temp/f'work-{repetition}-{state}-{route}';work.mkdir()
                        row={'state':state,'route':route,'repetition':repetition}
                        if route=='checkout':
                            code='import sys;sys.path.insert(0,'+repr(str(source))+')\n'+CONSUMER
                            cp=execute([py,'-I','-c',code],work,env)
                            row['setup_kind']='explicit source reference, not an installed release'
                            row['ordinary']=cp
                        else:
                            dist=assets/'wheels'/state/route/str(repetition);dist.mkdir(parents=True)
                            hook='build_editable' if route in {'editable','strict-editable'} else 'build_wheel'
                            config={'editable_mode':'strict'} if route=='strict-editable' else {}
                            if route=='sdist-wheel':
                                sdist=work/'sdist';sdist.mkdir()
                                run([py,'-I','-c',f'from setuptools.build_meta import build_sdist;build_sdist({str(sdist)!r})'],source,env)
                                archive=next(sdist.glob('*.tar.gz'));target=work/'unpacked';target.mkdir()
                                with tarfile.open(archive) as tf:tf.extractall(target,filter='data')
                                row['sdist_sha256']=digest(archive)
                                shutil.copyfile(archive,dist/archive.name)
                                source=next(target.iterdir())
                            run([py,'-I','-c',f'from setuptools.build_meta import {hook};{hook}({str(dist)!r},config_settings={config!r})'],source,env)
                            wheel=next(dist.glob('*.whl'))
                            row['wheel']=str(wheel.relative_to(out.parent));row['sha256']=digest(wheel)
                            isolated=work/'subject';isolated.mkdir()
                            subject,subject_env,setup=prepare(isolated,wheel)
                            row['setup']=setup
                            if setup['status']!='READY':save();raise RuntimeError('Subject environment not ready')
                            neutral=work/'consumer';neutral.mkdir()
                            row['smoke']=execute([subject,'-I','-c','import wg_matrix;print(wg_matrix.__file__)'],neutral,subject_env)
                            ordinary_code=CONSUMER
                            if route.endswith('wheel'):
                                ordinary_code += WHEEL_OWNERSHIP
                                ordinary_code += '\nimport subprocess\ncommand = pathlib.Path(sys.executable).parent / (\"wg-matrix.exe\" if sys.platform == \"win32\" else \"wg-matrix\")\ncp = subprocess.run([str(command)], capture_output=True, text=True, timeout=10)\nassert cp.returncode == 0, cp.stderr\nassert cp.stdout == \"hello\\n\", repr(cp.stdout)\n'
                            row['ordinary']=execute([subject,'-I','-c',ordinary_code],neutral,subject_env)
                            if route.endswith('wheel'):
                                row['gate']=probe(spec,subject,subject_env,work/'gate',identity=setup['wheel_identity'])
                                row['content_checks']={}
                                for preset in ['default','reference-tree']:
                                    opts=['--no-config']
                                    if preset=='reference-tree':
                                        opts+=['--toplevel','wg_matrix','--package',str(original/'wg_matrix'),
                                               '--package-omit','.*,CVS,RCS,*.pyc,*.pyo,*.egg-info,__pycache__']
                                    proc=execute([sys.executable,'-I','-c',cwc_launcher,*opts,wheel],neutral,env)
                                    row['content_checks'][preset]={'status':'PASS' if proc['returncode']==0 else 'REJECT', 'process':proc}
                            else:
                                row['gate']={'status':'NOT_APPLICABLE','reason':'This is a development installation, not the selected wheel-release profile.'}
                        row['ordinary_status']='PASS' if row['ordinary']['returncode']==0 else 'FAIL'
                        messages=[line[len('MATRIX_JSON='):] for line in row['ordinary']['stdout'].splitlines() if line.startswith('MATRIX_JSON=')]
                        row['observation']=json.loads(messages[0]) if len(messages)==1 else None
                        if row['observation'] and route.endswith('wheel'):
                            origin=pathlib.Path(row['observation']['origin'])
                            if not origin.is_relative_to(pathlib.Path(row['observation']['prefix'])):
                                raise RuntimeError('Ordinary installed comparison imported outside subject environment')
                        result['runs'].append(row);save()
                        print(state,repetition,route,row['ordinary_status'],flush=True)
            # Keep a separate actual unavailable modern frontend receipt; no miss is inferred.
            modern=temp/'modern';shutil.copytree(states['R'],modern)
            (modern/'pyproject.toml').write_text('[build-system]\nrequires=["setuptools==78.1.1"]\nbuild-backend="setuptools.build_meta"\n')
            run(['git','init','-q',modern],temp,env);run(['git','add','.'],modern,env)
            cp=execute([py,'-I',cm,'-v','--no-build-isolation',modern],temp,env)
            result['modern_frontend_attempt']={'status':'BLOCKED' if cp['returncode']==2 else ('PASS' if cp['returncode']==0 else 'REJECT'),
                'process':cp,'included_in_legacy_comparison':False}
        result['status']='COMPLETE'
    except Exception as exc:
        result['status']='INCOMPLETE';result['error']=str(exc);result['traceback']=traceback.format_exc();save();raise
    result['completed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    return 0


if __name__=='__main__':raise SystemExit(main())
