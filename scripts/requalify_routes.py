#!/usr/bin/env python3
"""Requalify the two unique wheel contents retained by the route matrix."""
from __future__ import annotations
import argparse, datetime, hashlib, json, pathlib, statistics, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from wheelgate.runner import prepare, probe


def spec():
    common={'distribution':'wg-matrix','modules':['wg_matrix'],
            'evidence':'Authored route-matrix README: API, static resource, and command'}
    return {'schema':2,'contracts':[
        dict(common,id='api',kind='call',target='wg_matrix:consumer',equals='hello'),
        dict(common,id='resource',kind='resource',package='wg_matrix',resource='template.json',format='json',equals={'schema':1,'message':'hello'}),
        dict(common,id='cli',kind='cli',command='wg-matrix',equals='hello\n')]}


def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=pathlib.Path,default=ROOT/'results/routes/requalification.json');ap.add_argument('--repetitions',type=int,default=5);a=ap.parse_args()
    out=a.output.resolve();
    if out.exists(): ap.error('use a fresh output path')
    out.parent.mkdir(parents=True,exist_ok=True)
    prior_path=ROOT/'results/routes/matrix.json'
    prior=json.load(open(prior_path))
    rows=[r for r in prior['runs'] if r['route'].endswith('wheel')]
    representatives={}
    for row in rows:
        wheel=prior_path.parent/row['wheel']
        if digest(wheel)!=row['sha256']: raise ValueError('retained route wheel hash mismatch')
        representatives.setdefault(row['sha256'],wheel)
    record={'schema':1,'experiment':'current-code-requalification-of-retained-route-wheels','status':'RUNNING','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repetitions':a.repetitions,'source_route_record_sha256':digest(prior_path),'runs':[]}
    def save(): out.write_text(json.dumps(record,indent=2)+'\n')
    with tempfile.TemporaryDirectory(prefix='wheelgate-routes-') as td:
        temp=pathlib.Path(td)
        prepared={}
        for sha,wheel in representatives.items():
            py,env,setup=prepare(temp/sha[:12],wheel)
            if setup['status']!='READY': raise RuntimeError(setup)
            prepared[sha]=(py,env,setup)
        for rep in range(a.repetitions):
            for sha,wheel in representatives.items():
                py,env,setup=prepared[sha]
                gate=probe(spec(),py,env,temp/f'run-{rep}-{sha[:8]}',identity=setup['wheel_identity'])
                related=[row for row in rows if row['sha256']==sha]
                observed={row['ordinary_status'] for row in related}
                if len(observed)!=1: raise AssertionError(('inconsistent retained wheel semantics',sha,observed))
                expected=next(iter(observed))
                if expected not in {'PASS','FAIL'}: raise AssertionError(('unexpected retained status',expected))
                if gate['status']!=expected: raise AssertionError((sha,gate))
                record['runs'].append({'repetition':rep,'wheel':str(wheel.relative_to(ROOT)),'sha256':sha,'expected':expected,'gate':gate})
                save();print(sha[:8],rep,gate['status'],flush=True)
    record['summary']={'unique_wheels':len(representatives),'observations':len(record['runs']),'pass':sum(r['gate']['status']=='PASS' for r in record['runs']),'fail':sum(r['gate']['status']=='FAIL' for r in record['runs']),'median_gate_seconds':statistics.median(r['gate']['seconds'] for r in record['runs'])}
    record['status']='COMPLETE';record['completed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();return 0
if __name__=='__main__':raise SystemExit(main())
