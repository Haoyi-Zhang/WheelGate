"""Offline venv setup, explicit profiles, fresh working directories and raw reports."""
from __future__ import annotations
import argparse, email.parser, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time, venv, zipfile
from . import __version__
from .contractio import load as load_contracts, loads as load_json, validate_v2
KINDS = {'import','call','resource','entrypoint','cli','script'}

def validate(spec: dict) -> None:
    if not isinstance(spec, dict) or type(spec.get('schema')) is not int or spec.get('schema') not in {1, 2}: raise ValueError('schema must be 1 or 2')
    contracts = spec.get('contracts')
    if not isinstance(contracts, list) or not contracts: raise ValueError('Nonempty contract list required')
    seen = set()
    required = {'call':['target'], 'resource':['resource','package'], 'entrypoint':['group','name'],
                'cli':['command'], 'script':['code'], 'import':[]}
    for c in contracts:
        if not isinstance(c, dict): raise ValueError('Each contract must be an object')
        if not isinstance(c.get('id'),str) or not c['id'] or c['id'] in seen: raise ValueError('Unique nonempty IDs required')
        seen.add(c['id'])
        if not isinstance(c.get('kind'), str) or c['kind'] not in KINDS: raise ValueError('Unsupported kind')
        if not isinstance(c.get('distribution'), str) or not c['distribution'].strip(): raise ValueError('Distribution required')
        if not isinstance(c.get('evidence'), str) or not c['evidence'].strip(): raise ValueError('Evidence reference required')
        if not isinstance(c.get('modules'),list) or not c['modules'] or not all(isinstance(m,str) and m for m in c['modules']):
            raise ValueError('Nonempty concrete origin anchors required')
        profiles = c.get('profiles', ['base'])
        if not isinstance(profiles,list) or not profiles or not all(isinstance(p,str) and p.strip() for p in profiles): raise ValueError('Nonempty string profiles required')
        if len(set(profiles)) != len(profiles): raise ValueError('Duplicate profiles')
        for key in required[c['kind']]:
            if not isinstance(c.get(key),str) or not c[key].strip(): raise ValueError('Missing or invalid ' + key)
        if 'args' in c and not isinstance(c['args'],list): raise ValueError('args must be a list')
        if 'kwargs' in c and not isinstance(c['kwargs'],dict): raise ValueError('kwargs must be an object')
        if c['kind']=='resource':
            path=pathlib.PurePosixPath(c['resource'])
            if path.is_absolute() or '..' in path.parts or '\\' in c['resource']: raise ValueError('Resource must be package-relative')
        if c['kind']=='cli' and pathlib.PurePath(c['command']).name!=c['command']: raise ValueError('CLI must be a basename')
        if c['kind'] in {'call','resource'} and not any(k in c for k in ('equals','contains')):
            raise ValueError('Semantic expectation required')
        timeout = c.get('timeout', 10)
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0 < timeout <= 60:
            raise ValueError('timeout must be >0 and <=60 seconds')
    validate_v2(spec)

def normalized_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()


def canonical_contract_digest(spec):
    """Digest the validated contract document without claiming authenticity."""
    validate(spec)
    encoded=json.dumps(spec,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

def environment_receipt(py, cwd, env):
    code=("import importlib.metadata as m,json,platform,sys;"
          "rows=sorted([{'name':d.metadata.get('Name'),'version':d.version} for d in m.distributions() if d.metadata.get('Name')],key=lambda x:(x['name'].lower(),x['version']));"
          "print('WHEELGATE_ENV='+json.dumps({'python':sys.version,'implementation':platform.python_implementation(),'prefix':sys.prefix,'distributions':rows},sort_keys=True))")
    process=execute([py,'-I','-c',code],cwd,env)
    prefix='WHEELGATE_ENV='
    lines=[line[len(prefix):] for line in process['stdout'].splitlines() if line.startswith(prefix)]
    payload=None
    if process['returncode']==0 and not process['timeout'] and len(lines)==1:
        try: payload=load_json(lines[0])
        except ValueError: payload=None
    valid=isinstance(payload,dict) and isinstance(payload.get('python'),str) and isinstance(payload.get('prefix'),str) and isinstance(payload.get('distributions'),list)
    return {'status':'READY' if valid else 'INVALID','receipt':payload,'process':process}

def wheel_identity(wheel):
    """Read the selected local wheel's identity; this is not authenticity checking."""
    with zipfile.ZipFile(wheel) as z:
        names=[n for n in z.namelist() if len(pathlib.PurePosixPath(n).parts)==2 and n.endswith('.dist-info/METADATA')]
        if len(names)!=1: raise ValueError('Exactly one wheel METADATA is required')
        msg=email.parser.BytesParser().parsebytes(z.read(names[0]))
    if not msg.get('Name') or not msg.get('Version'): raise ValueError('Wheel identity missing')
    return {'name':msg['Name'],'version':msg['Version']}

def bind_contracts(spec, identity, profile):
    if not isinstance(profile,str) or not profile.strip(): raise ValueError('Profile must be a nonempty string')
    active=[c for c in spec['contracts'] if profile in c.get('profiles',['base'])]
    if not active: raise ValueError('No obligations active in the requested profile')
    for c in active:
        if normalized_name(c['distribution'])!=normalized_name(identity['name']):
            raise ValueError('Active obligation does not describe the selected wheel: '+c['id'])
        if 'version' in c and c['version'] != identity.get('version'):
            raise ValueError('Active obligation version does not match the selected wheel: '+c['id'])

def parsed_report(cp, prefix, ids, batch=False):
    """Reject incomplete or inconsistent process receipts, rather than silently pass."""
    if cp['timeout']: return None
    lines=[x[len(prefix):] for x in cp['stdout'].splitlines() if x.startswith(prefix)]
    if len(lines)!=1: return None
    try: payload=load_json(lines[0])
    except (ValueError,TypeError): return None
    rows=payload if batch else [payload]
    if not isinstance(rows,list) or len(rows)!=len(ids): return None
    if any(not isinstance(r,dict) or r.get('id')!=i or r.get('status') not in {'PASS','FAIL','INVALID'} for r,i in zip(rows,ids)):
        return None
    expected=2 if any(r['status']=='INVALID' for r in rows) else (1 if any(r['status']=='FAIL' for r in rows) else 0)
    return rows if cp['returncode']==expected else None

def execute(argv, cwd, env, timeout=60, stdin=None):
    start=time.perf_counter()
    try:
        cp=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,text=True,capture_output=True,input=stdin,timeout=timeout,
                          encoding='utf-8',errors='surrogateescape')
        rc=cp.returncode;out=cp.stdout;err=cp.stderr;timed=False
    except subprocess.TimeoutExpired as exc:
        rc=124;out=exc.stdout or '';err=exc.stderr or '';timed=True
        if isinstance(out,bytes): out=out.decode('utf-8',errors='surrogateescape')
        if isinstance(err,bytes): err=err.decode('utf-8',errors='surrogateescape')
    except OSError as exc:
        rc=127;out='';err=str(exc);timed=False
    return {'argv':list(map(str,argv)), 'returncode':rc, 'stdout':out, 'stderr':err,
            'seconds':time.perf_counter()-start, 'timeout':timed}

def clean_env(home, bindir):
    env = {'PATH':str(bindir)+os.pathsep+os.environ.get('PATH',os.defpath), 'HOME':str(home),'LANG':'C.UTF-8',
            'PIP_CONFIG_FILE':os.devnull,'PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1',
            'PYTHONNOUSERSITE':'1'}
    if os.name == 'nt' and 'SystemRoot' in os.environ:
        env['SystemRoot'] = os.environ['SystemRoot']
    return env


def venv_python(directory):
    return pathlib.Path(directory) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

def prepare(base: pathlib.Path, wheel: pathlib.Path, dependencies=()):
    start=time.perf_counter(); identity=wheel_identity(wheel); ve=base/'venv'
    venv.EnvBuilder(with_pip=True).create(ve)
    create_seconds=time.perf_counter()-start
    py=venv_python(ve)
    home=base/'home';home.mkdir();cwd=base/'setup';cwd.mkdir();env=clean_env(home,py.parent)
    # Dependencies must be explicit local wheel paths: never inherit host site-packages.
    cp=execute([py,'-I','-m','pip','install','--no-index','--no-deps',*dependencies,wheel],cwd,env)
    dep=execute([py,'-I','-m','pip','check'],cwd,env) if cp['returncode']==0 else None
    environment=environment_receipt(py,cwd,env) if cp['returncode']==0 and dep and dep['returncode']==0 else None
    ready=cp['returncode']==0 and dep is not None and dep['returncode']==0 and environment is not None and environment['status']=='READY'
    setup={'wheel_identity':identity,'venv_seconds':create_seconds,'install':cp,'dependency_check':dep,
           'environment':environment,'seconds':time.perf_counter()-start,'status':'READY' if ready else 'BLOCKED'}
    return py,env,setup

def profile_preflight(spec, profile, py, env, base):
    """Check only explicitly declared profile prerequisites; do not resolve extras."""
    requirements = spec.get('profile_dependencies', {}).get(profile, [])
    if not requirements:
        return {'status': 'READY', 'requirements': [], 'seconds': 0}
    folder = pathlib.Path(base) / 'profile-preflight'
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(pathlib.Path(__file__).with_name('profile_worker.py'), folder / 'worker.py')
    request = folder / 'requirements.json'
    request.write_text(json.dumps(requirements), encoding='utf-8')
    process = execute([py, '-I', folder / 'worker.py', request], folder, env)
    prefix = 'WHEELGATE_PROFILE='
    lines = [line[len(prefix):] for line in process['stdout'].splitlines() if line.startswith(prefix)]
    payload = None
    if not process['timeout'] and len(lines) == 1:
        try:
            payload = load_json(lines[0])
        except ValueError:
            pass
    valid = isinstance(payload, dict) and payload.get('status') in {'READY', 'BLOCKED'}
    if valid:
        expected_rc = 0 if payload['status'] == 'READY' else 2
        records = payload.get('requirements')
        valid = process['returncode'] == expected_rc and isinstance(records, list) and len(records) == len(requirements)
        if valid:
            valid = all(isinstance(row, dict) and row.get('distribution') == req['distribution']
                        and row.get('expected_version') == req['version']
                        and type(row.get('satisfied')) is bool
                        and row['satisfied'] == (row.get('observed_version') == req['version'])
                        for row, req in zip(records, requirements))
            valid = valid and (all(row['satisfied'] for row in records) == (payload['status'] == 'READY'))
    if not valid:
        payload = {'status': 'INVALID', 'reason': 'No consistent prerequisite report', 'requirements': []}
    return {**payload, 'process': process, 'seconds': process['seconds']}

def _runtime_contract(contract, spec, profile, identity):
    allowed = [identity['name'] if identity is not None else contract['distribution']]
    allowed.extend(req['distribution'] for req in spec.get('profile_dependencies', {}).get(profile, []))
    enriched = dict(contract)
    enriched['_allowed_distributions'] = allowed
    return enriched


def _copy_worker_bundle(folder):
    source = pathlib.Path(__file__).resolve().parent
    shutil.copyfile(source / 'worker.py', folder / 'worker.py')
    shutil.copyfile(source / 'footprint.py', folder / 'footprint.py')


def probe(spec, py, env, base, profile='base', mode='isolated', identity=None):
    validate(spec)
    if mode not in {'isolated','batch'}: raise ValueError('Unknown execution mode')
    if identity is not None: bind_contracts(spec, identity, profile)
    base=pathlib.Path(base);base.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();results=[]
    preflight=profile_preflight(spec, profile, py, env, base)
    if preflight['status'] != 'READY':
        results=[{'id':c['id'], 'status':preflight['status'] if profile in c.get('profiles',['base']) else 'NOT_APPLICABLE', 'reason':'Prerequisite check did not establish readiness; operation not run'} for c in spec['contracts']]
        return {'status':preflight['status'], 'profile':profile, 'mode':mode, 'seconds':time.perf_counter()-start, 'profile_preflight':preflight, 'contracts':results}
    if mode == 'batch':
        selected=[_runtime_contract(c, spec, profile, identity) for c in spec['contracts'] if profile in c.get('profiles',['base'])]
        if selected:
            _copy_worker_bundle(base)
            (base/'contract.json').write_text(json.dumps({'batch':True,'contracts':selected}))
            cp=execute([py,'-I',base/'worker.py',base/'contract.json'],base,env,
                       timeout=sum(c.get('timeout',10)+2 for c in selected))
            rows=parsed_report(cp,'WHEELGATE_BATCH=',[c['id'] for c in selected],batch=True)
            if rows is None:
                rows=[{'id':c['id'],'status':'TIMEOUT' if cp['timeout'] else 'INVALID','reason':'No consistent worker report'} for c in selected]
            for row in rows: row['process']=cp
            mapped={r['id']:r for r in rows}
        else: mapped={}
        for c in spec['contracts']:
            results.append(mapped.get(c['id'],{'id':c['id'],'status':'NOT_APPLICABLE','reason':'Profile not requested','seconds':0}))
    else:
        for i,c in enumerate(spec['contracts']):
            if profile not in c.get('profiles',['base']):
                results.append({'id':c['id'],'status':'NOT_APPLICABLE','reason':'Profile not requested','seconds':0});continue
            folder=base/str(i);folder.mkdir();_copy_worker_bundle(folder)
            runtime_contract=_runtime_contract(c, spec, profile, identity)
            (folder/'contract.json').write_text(json.dumps(runtime_contract))
            cp=execute([py,'-I',folder/'worker.py',folder/'contract.json'],folder,env,timeout=c.get('timeout',10)+2)
            rows=parsed_report(cp,'WHEELGATE_JSON=',[c['id']])
            result=rows[0] if rows else {'id':c['id'],'status':'TIMEOUT' if cp['timeout'] else 'INVALID','reason':'No consistent worker report'}
            result['process']=cp;results.append(result)
    active=[r for r in results if r['status']!='NOT_APPLICABLE']
    statuses={r['status'] for r in active}
    status = 'INVALID' if not active or statuses & {'INVALID','TIMEOUT'} else ('FAIL' if 'FAIL' in statuses else 'PASS')
    return {'status':status,'profile':profile,'mode':mode,'seconds':time.perf_counter()-start,'profile_preflight':preflight,'contracts':results}

def qualify(wheel, spec, profile='base', dependencies=(), mode='isolated'):
    validate(spec);wheel=pathlib.Path(wheel).resolve()
    identity=wheel_identity(wheel);bind_contracts(spec,identity,profile)
    result={'identity':identity,'wheelgate':__version__, 'artifact_kind':'wheel','wheel':wheel.name,
            'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
            'contract_sha256':canonical_contract_digest(spec),'profile':profile,'execution_mode':mode}
    with tempfile.TemporaryDirectory(prefix='wheelgate-') as td:
        base=pathlib.Path(td);py,env,setup=prepare(base,wheel,dependencies)
        result['setup']=setup
        if setup['status']!='READY': result.update(status='BLOCKED',contracts=[])
        else: result.update(probe(spec,py,env,base/'probes',profile,mode=mode,identity=identity))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--version', action='version', version='WheelGate '+__version__)
    ap.add_argument('wheel',type=pathlib.Path);ap.add_argument('contracts',type=pathlib.Path)
    ap.add_argument('--mode',choices=['isolated','batch'],default='isolated')
    ap.add_argument('--profile',default='base');ap.add_argument('--dependency',action='append',default=[],type=pathlib.Path)
    ap.add_argument('--output',type=pathlib.Path,required=True);args=ap.parse_args()
    try: result=qualify(args.wheel,load_contracts(args.contracts),args.profile,[p.resolve() for p in args.dependency],mode=args.mode)
    except (ValueError,OSError,zipfile.BadZipFile) as exc: result={'status':'INVALID','message':str(exc)}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status']);return 0 if result['status']=='PASS' else (1 if result['status']=='FAIL' else 2)
if __name__=='__main__': raise SystemExit(main())
