#!/usr/bin/env python3
"""Generate manuscript tables from selected complete result records."""
from __future__ import annotations
import json,pathlib,statistics,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
PAPER=ROOT.parent/'paper' if ROOT.name == 'artifact' and (ROOT.parent/'paper').is_dir() else ROOT/'results/manuscript'
GEN=PAPER/'generated';GEN.mkdir(parents=True,exist_ok=True)
route=json.load(open(ROOT/'results/routes/matrix.json'))
foot=json.load(open(ROOT/'results/footprint/matrix.json'))
hist=json.load(open(ROOT/'results/historical/django-xml-replay.json'))
req=json.load(open(ROOT/'results/routes/requalification.json'))
package=json.load(open(ROOT/'results/package/self-check.json'))
assert route['status']=='COMPLETE' and foot['status']=='COMPLETE' and hist['status']=='COMPLETE' and req['status']=='COMPLETE' and package['status']=='COMPLETE'
macros={
'RouteObservations':len(route['runs']),'HistoricalObservations':len(hist['runs']),'FootprintObservations':len(foot['runs']),
'RouteRequalifications':len(req['runs']),'RegressionTests':int(re.search(r'Ran (\d+) tests',package['routes'][0]['unit_tests']['stdout']+package['routes'][0]['unit_tests']['stderr']).group(1)),'FootprintInvalid':sum(r['gate']['status']=='INVALID' for r in foot['runs']),
'FootprintModuleInvalid':sum(
    any(c.get('footprint',{}).get('violations') for c in r['gate'].get('contracts',[]))
    for r in foot['runs']
),
'FootprintFileInvalid':sum(
    any(c.get('file_footprint',{}).get('violations') for c in r['gate'].get('contracts',[]))
    and not any(c.get('footprint',{}).get('violations') for c in r['gate'].get('contracts',[]))
    for r in foot['runs']
),
'FootprintOrdinaryPass':sum(r['ordinary']['status']=='PASS' for r in foot['runs']),
}
(GEN/'numbers.tex').write_text('\n'.join(f'\\newcommand{{\\{k}}}{{{v}}}' for k,v in macros.items())+'\n')
# Route table
labels={'checkout':'Checkout','editable':'Editable','strict-editable':'Strict editable','direct-wheel':'Direct wheel','sdist-wheel':'sdist wheel'}
lines=['\\begin{tabular}{lccccc}','\\toprule','State & Checkout & Editable & Strict & Direct & sdist \\\\','\\midrule']
for state in ['U','X','R']:
 vals=[]
 for route_name in labels:
  rows=[r for r in route['runs'] if r['state']==state and r['route']==route_name]
  statuses={r['ordinary_status'] for r in rows};assert len(statuses)==1
  vals.append(next(iter(statuses)))
 lines.append(state+' & '+' & '.join(vals)+' \\\\')
lines+=['\\bottomrule','\\end{tabular}']
(GEN/'route-table.tex').write_text('\n'.join(lines)+'\n')
# Historical table
lines=['\\begin{tabular}{lccccc}','\\toprule','Replay & Checkout & Installed & Gate & CWC default & CWC ref. \\\\','\\midrule']
for variant in ['affected','fixed']:
 r=next(x for x in hist['runs'] if x['variant']==variant)
 lines.append(f"{variant.capitalize()} & PASS & {r['ordinary']['status']} & {r['gate']['status']} & {r['cwc']['default']['status']} & {r['cwc']['reference']['status']} \\\\")
lines+=['\\bottomrule','\\end{tabular}']
(GEN/'historical-table.tex').write_text('\n'.join(lines)+'\n')
# Footprint table
order=['declared-helper','undeclared-helper','wrong-helper-version','cwd-shadow','generated-site-file','declared-package-data','cwd-data-file','generated-site-data']
names={'declared-helper':'Declared helper 1.0','undeclared-helper':'Undeclared helper 1.0','wrong-helper-version':'Helper: required 1.0 / installed 2.0','cwd-shadow':'CWD shadow module','generated-site-file':'Generated site module','declared-package-data':'Recorded package data','cwd-data-file':'CWD data file','generated-site-data':'Unrecorded site data'}
lines=['\\begin{tabular}{p{0.42\\columnwidth}cc}','\\toprule','Context & Ordinary & WheelGate \\\\','\\midrule']
for case in order:
 rows=[r for r in foot['runs'] if r['case']==case]
 ordinary={r['ordinary']['status'] for r in rows};gate={r['gate']['status'] for r in rows};assert len(ordinary)==len(gate)==1
 lines.append(f"{names[case]} & {next(iter(ordinary))} & {next(iter(gate))} \\\\")
lines+=['\\bottomrule','\\end{tabular}']
(GEN/'footprint-table.tex').write_text('\n'.join(lines)+'\n')
# Context-policy ablation reconstructed from retained operation and receipt fields.
semantic_pass=sum(r['ordinary']['status']=='PASS' for r in foot['runs'])
blocked=sum(r['ordinary']['status']=='BLOCKED' for r in foot['runs'])
module_invalid=macros['FootprintModuleInvalid']
full_invalid=macros['FootprintInvalid']
ablation=[
 ('Semantic assertion + target anchor',semantic_pass,blocked,0),
 ('+ newly loaded module owners',semantic_pass-module_invalid,blocked,module_invalid),
 ('+ non-code file owners',semantic_pass-full_invalid,blocked,full_invalid),
]
lines=['\\begin{tabular}{p{0.54\\columnwidth}ccc}','\\toprule','Policy & PASS & BLOCKED & INVALID \\\\','\\midrule']
for name,pas,blo,inv in ablation:
 lines.append(f'{name} & {pas} & {blo} & {inv} \\\\')
lines+=['\\bottomrule','\\end{tabular}']
(GEN/'ablation-table.tex').write_text('\n'.join(lines)+'\n')
# Runtime data, milliseconds, one row per obligation class.
series=[]
for case in order:
 rows=[r for r in foot['runs'] if r['case']==case]
 series.append((names[case],1000*statistics.median(r['gate']['seconds'] for r in rows)))
series.append(('Historical replay',1000*statistics.median(r['gate']['seconds'] for r in hist['runs'])))
series.append(('Route bundle (3 ops)',1000*statistics.median(r['gate']['seconds'] for r in req['runs'])))
(GEN/'runtime.dat').write_text('label value\n'+'\n'.join(f'{{{name}}} {value:.3f}' for name,value in series)+'\n')
blocked_label=names['wrong-helper-version']
single_values=[value for name,value in series if name not in {blocked_label,'Route bundle (3 ops)'}]
summary_runtime=[('Prerequisite block',dict(series)[blocked_label]),('Single operation',statistics.median(single_values)),('Three operations',dict(series)['Route bundle (3 ops)'])]
(GEN/'runtime-summary.dat').write_text('label value\n'+'\n'.join(f'{{{name}}} {value:.3f}' for name,value in summary_runtime)+'\n')
implementation={
 'SourceLines':sum(len(p.read_text(encoding='utf-8').splitlines()) for p in (ROOT/'wheelgate').glob('*.py')),
 'TestLines':sum(len(p.read_text(encoding='utf-8').splitlines()) for p in (ROOT/'tests').glob('test_*.py')),
 'WheelBytes':(ROOT/'results/package'/package['routes'][0]['wheel']).stat().st_size,
 'SingleOperationSeconds':f"{dict(summary_runtime)['Single operation']/1000:.2f}",
 'ThreeOperationSeconds':f"{dict(summary_runtime)['Three operations']/1000:.2f}",
 'PrerequisiteMs':f"{dict(summary_runtime)['Prerequisite block']:.0f}",
}
(GEN/'implementation.tex').write_text('\n'.join(f'\\newcommand{{\\{k}}}{{{v}}}' for k,v in implementation.items())+'\n',encoding='utf-8')
# machine-readable summary
summary={'macros':macros,'runtime_ms':dict(series),'selected_records':{
 'routes':'results/routes/matrix.json','route_requalification':'results/routes/requalification.json','footprint':'results/footprint/matrix.json','historical':'results/historical/django-xml-replay.json','package':'results/package/self-check.json'}}
(ROOT/'results/summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
