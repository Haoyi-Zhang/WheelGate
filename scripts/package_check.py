#!/usr/bin/env python3
"""Build and test the actual WheelGate software distributions outside the checkout."""
from __future__ import annotations
import argparse,datetime,hashlib,json,pathlib,shutil,sys,tarfile,tempfile,traceback,venv,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from wheelgate.runner import execute,clean_env,prepare,venv_python

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=pathlib.Path,default=ROOT/'results/package/self-check.json');a=ap.parse_args();out=a.output.resolve()
 if out.exists():ap.error('use a new output path')
 out.parent.mkdir(parents=True,exist_ok=True);assets=out.parent/(out.stem+'-assets');assets.mkdir()
 result={'schema':1,'experiment':'installed-wheelgate-distribution','status':'RUNNING','script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'routes':[]}
 def save():out.write_text(json.dumps(result,indent=2)+'\n')
 def run(argv,cwd,env,expected=0):
  p=execute(argv,cwd,env,120);result['commands'].append(p)
  if p['returncode']!=expected:save();raise RuntimeError(str(p))
  return p
 try:
  with tempfile.TemporaryDirectory(prefix='wheelgate-packaging-') as td:
   t=pathlib.Path(td);venv.EnvBuilder(with_pip=True).create(t/'builder');py=venv_python(t/'builder');(t/'home').mkdir();env=clean_env(t/'home',py.parent);env['SOURCE_DATE_EPOCH']='1704067200'
   run([py,'-I','-m','pip','install','--no-index','--no-deps',ROOT/'third_party/setuptools-78.1.1-py3-none-any.whl'],t,env)
   def source(dest):
    dest.mkdir();shutil.copytree(ROOT/'wheelgate',dest/'wheelgate',ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['setup.py','pyproject.toml','MANIFEST.in','README.md','LICENSE']:shutil.copyfile(ROOT/name,dest/name)
   source(t/'direct');source(t/'sdist-source')
   direct=assets/'direct';direct.mkdir();sd=assets/'sdist';sd.mkdir();rebuilt=assets/'rebuilt';rebuilt.mkdir()
   run([py,'-I','-c',f'from setuptools.build_meta import build_wheel;build_wheel({str(direct)!r})'],t/'direct',env)
   run([py,'-I','-c',f'from setuptools.build_meta import build_sdist;build_sdist({str(sd)!r})'],t/'sdist-source',env)
   unpacked=t/'unpacked';unpacked.mkdir()
   with tarfile.open(next(sd.glob('*.tar.gz'))) as f:f.extractall(unpacked,filter='data')
   run([py,'-I','-c',f'from setuptools.build_meta import build_wheel;build_wheel({str(rebuilt)!r})'],next(unpacked.iterdir()),env)
   for name,folder in [('direct-wheel',direct),('sdist-wheel',rebuilt)]:
    wheel=next(folder.glob('*.whl'));work=t/name;work.mkdir();subject,subenv,setup=prepare(work,wheel)
    if setup['status']!='READY':raise RuntimeError(str(setup))
    neutral=work/'neutral';neutral.mkdir();tests=neutral/'tests';shutil.copytree(ROOT/'tests',tests,ignore=shutil.ignore_patterns('__pycache__'));shutil.copytree(ROOT/'contracts',neutral/'contracts')
    # The source-entrypoint test parses this file; it is not installed or run.
    (neutral/'scripts').mkdir();shutil.copyfile(ROOT/'scripts/reproduce.py',neutral/'scripts/reproduce.py')
    (neutral/'inputs/fixture-direct').mkdir(parents=True);shutil.copyfile(ROOT/'inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl',neutral/'inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl')
    identity=run([subject,'-I','-c','import wheelgate,pathlib,sys,json;assert pathlib.Path(wheelgate.__file__).is_relative_to(pathlib.Path(sys.prefix));print(json.dumps({"module":wheelgate.__file__,"version":wheelgate.__version__,"prefix":sys.prefix}))'],neutral,subenv)
    check=run([subject,'-I','-m','unittest','discover','-s',tests,'-v'],neutral,subenv)
    command=subject.parent/('wheelgate.exe' if sys.platform == 'win32' else 'wheelgate')
    cli=run([command,'--version'],neutral,subenv)
    semantic=[]
    for kind,path,status in [('good','inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl',0),('missing','inputs/fixture-rebuilt/wg_fixture-0.1.0-py3-none-any.whl',1)]:
     output=work/f'{kind}.json';cp=run([command,ROOT/path,ROOT/'contracts/fixture.json','--output',output],neutral,subenv,expected=status);semantic.append({'condition':kind,'process':cp,'report':json.loads(output.read_text())})
    with zipfile.ZipFile(wheel) as z:
     payload={p:hashlib.sha256(z.read(p)).hexdigest() for p in z.namelist() if p.startswith('wheelgate/')};names=z.namelist()
    if any(p.startswith(('tests/','results/','corpus/','paper/','third_party/')) for p in names):raise RuntimeError('research data leaked into software wheel')
    result['routes'].append({'route':name,'wheel':str(wheel.relative_to(out.parent)),'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'setup':setup,'identity':identity,'unit_tests':check,'cli':cli,'semantic_smoke':semantic,'package_payload':payload});save()
   result['payloads_equal']=result['routes'][0]['package_payload']==result['routes'][1]['package_payload']
   if not result['payloads_equal']:raise RuntimeError('WheelGate own package payload differs across routes')
  result['status']='COMPLETE'
 except Exception as e:
  result['status']='INCOMPLETE';result['error']=str(e);result['traceback']=traceback.format_exc();save();raise
 result['completed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
if __name__=='__main__':main()
