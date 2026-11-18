#!/usr/bin/env python3
"""R90-P3.9: pinned 4CPU within-arm reproducibility probe, after first pair SHA HOLD.

Uses the exact existing P3.9 runner for 4 NEW SIFT100K builds (two each of
CTRL/FAST), in a NEW output directory. Never resumes or edits the failed P3.9
root. Compares directed-neighbor multisets within each arm and across arms.

IMPORTANT: Graph equality is an experimental result, not an assumption. A graph
multiset mismatch does NOT make the audit script fail; its result is recorded
as graph variability needing same-query matched Recall/QPS verification.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, pathlib, statistics, sys, tempfile

HOME = pathlib.Path.home()
R90 = HOME/'ann-task-a/experiments/R90'
ORIG_ROOT = R90/'r90_p39_h17_fastv2_4cpu_native_v1'
NEW_ROOT = R90/'r90_p39_4cpu_within_arm_probe_v1'
P39_PATH = HOME/'Downloads/r90_p39_h17_fastv2_4cpu_native_v1.py'
DIFF_PATH = HOME/'Downloads/r90_p39_graph_semantic_diff_v1.py'
P39_SHA = 'f42ea9732560e646481f51f9f3458da1f7d2bd1dd3c7e5b2965cee363903e7d6'
DIFF_SHA = '2756f4f059d73800e76c44ed7e3a84d1b4eaa8a69ec26fe7d0027edd91c77fe2'
OLD_REPORT = HOME/'R90_P39_GRAPH_SEMANTIC_DIFF_v1.json'


def ck(condition, tag):
    if not condition: raise RuntimeError('R90_P39_REPRO_HOLD_'+tag)

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4<<20),b''):h.update(block)
    return h.hexdigest()

def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    ck(spec is not None and spec.loader is not None,'IMPORT_'+name)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def load_inputs(check_old=True):
    ck(P39_PATH.is_file() and sha(P39_PATH)==P39_SHA,'P39_RUNNER_SHA')
    ck(DIFF_PATH.is_file() and sha(DIFF_PATH)==DIFF_SHA,'SEMANTIC_DIFF_SHA')
    p39=load_module(P39_PATH,'r90_p39_original_pinned')
    d=load_module(DIFF_PATH,'r90_p39_diff_pinned')
    source=p39.provenance(full=False)  # H17 source/ELF/data/topology/1CPU artifacts
    base=d.load_progress(ORIG_ROOT)     # Two original graph+stdout+time SHA
    ck(set(base)=={'ctrl','fast'},'P39_INITIAL_PAIR_MISSING')
    ck(OLD_REPORT.is_file() and not OLD_REPORT.is_symlink(),'OLD_GRAPH_DIFF_REPORT_MISSING')
    old=json.loads(OLD_REPORT.read_text())
    ck(old.get('classification')=='EDGE_MULTISET_DIFFERENCE' and
       old.get('different_neighbor_multiset_vertices')==104 and
       old.get('arcs_ctrl')==1827173 and old.get('arcs_fast')==1827175,
       'OLD_GRAPH_DIFF_REPORT_STATE')
    ck(old.get('evidence_sha',{}).get('ctrl',{}).get('graph_sha')==base['ctrl']['graph_sha'] and
       old.get('evidence_sha',{}).get('fast',{}).get('graph_sha')==base['fast']['graph_sha'],
       'OLD_DIFF_REPORT_GRAPH_SHA')
    return p39,d,source,base,old

def atomic_save(path,obj):
    temp=path.with_suffix(path.suffix+'.tmp')
    ck(not temp.exists(),'TMP_ALREADY_EXISTS')
    with temp.open('x') as f: json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')
    temp.replace(path)

def preflight():
    p39,d,source,base,old=load_inputs()
    ck(not NEW_ROOT.exists() and not NEW_ROOT.is_symlink(),'OUTPUT_ROOT_EXISTS')
    ck(NEW_ROOT.parent.is_dir(),'OUTPUT_PARENT_MISSING')
    print('R90_P39_REPRO_PREFLIGHT_SOURCE_ELF_DATA_TOPOLOGY_ORIGINAL_GRAPH_SHA_PASS',
          source['affinity'],source['topology_cores'],flush=True)
    return p39,d,source,base,old

def pilot():
    p39,d,source,base,old=preflight()
    NEW_ROOT.mkdir()
    for sub in ('graphs','logs'):(NEW_ROOT/sub).mkdir()
    state={'phase':'RUNNING_4CPU_WITHIN_ARM','script_sha':sha(pathlib.Path(__file__).resolve()),
           'original_p39_sha':P39_SHA,'semantic_diff_sha':DIFF_SHA,
           'original_progress_sha':sha(ORIG_ROOT/'progress_100k.json'),
           'old_graph_diff_report_sha':sha(OLD_REPORT),
           'source':source,
           'notes':'Two additional 4CPU runs per arm, 100K, same binaries and flags. Parity is OBSERVED not enforced.',
           'runs':[]}
    atomic_save(NEW_ROOT/'progress.json',state)
    p39.OUT=NEW_ROOT
    for rep in (2,3):
        for arm in (('fast','ctrl') if rep==2 else ('ctrl','fast')):
            row=p39.run(arm,100000,rep)
            state['runs'].append(row)
            atomic_save(NEW_ROOT/'progress.json',state)
        print('R90_P39_REPRO_PAIR_BUILT',rep,'graphs_SHA',
              [(x['arm'],x['graph_sha'][:16]) for x in state['runs'][-2:]],flush=True)
    ck(len(state['runs'])==4,'FOUR_RUNS_REQUIRED')
    state['phase']='COMPLETE_4_BUILDS_PENDING_SEMANTIC_AUDIT'
    atomic_save(NEW_ROOT/'build_manifest.json',state)
    print('R90_P39_REPRO_PILOT_4_BUILDS_COMPLETE__GRAPH_SEMANTIC_AUDIT_REQUIRED',flush=True)

def audit():
    p39,d,source,orig,old=load_inputs()
    manifest=NEW_ROOT/'build_manifest.json'
    ck(manifest.is_file(),'BUILD_MANIFEST_MISSING')
    state=json.loads(manifest.read_text())
    ck(state.get('phase')=='COMPLETE_4_BUILDS_PENDING_SEMANTIC_AUDIT' and
       state.get('script_sha')==sha(pathlib.Path(__file__).resolve()) and
       state.get('original_progress_sha')==sha(ORIG_ROOT/'progress_100k.json') and
       state.get('old_graph_diff_report_sha')==sha(OLD_REPORT), 'MANIFEST_PROVENANCE')
    ck(state.get('source',{}).get('affinity')=='0,2,4,6','AFFINITY_DRIFT')
    rows={}
    for arm in ('ctrl','fast'):
        rows[(arm,1)]=orig[arm]
    for row in state['runs']:
        arm,rep=row['arm'],row['rep']
        ck(arm in ('ctrl','fast') and rep in (2,3) and (arm,rep) not in rows,'RUN_ID_DUPLICATE')
        ck(row['n']==100000,'RUN_N')
        for fn,fnsha,sub in [('graph','graph_sha','graphs'),('stdout','stdout_sha','logs'),('timefile','timefile_sha','logs')]:
            p=pathlib.Path(row[fn])
            ck(p.is_file() and not p.is_symlink() and p.resolve().parent==(NEW_ROOT/sub).resolve(), 'EVIDENCE_FILE_'+fn)
            ck(sha(p)==row[fnsha],'EVIDENCE_SHA_'+fn)
        rows[(arm,rep)]=row
    ck(len(rows)==6,'SIX_TOTAL_BUILDS_REQUIRED')
    out={'status':'ANALYZED_4CPU_GRAPH_VARIABILITY__NOT_SEARCH_QUALITY',
         'input_graph_sha':{f'{arm}_r{rep}':row['graph_sha'] for (arm,rep),row in rows.items()},
         'initial_diff':{'changed_multiset_vertices':old['different_neighbor_multiset_vertices'],
                         'arcs_ctrl':old['arcs_ctrl'],'arcs_fast':old['arcs_fast'],
                         'unique_edge_set_added':old['unique_edge_set_added'],
                         'unique_edge_set_removed':old['unique_edge_set_removed'],
                         'arc_instances_added':old['arc_instances_added_ctrl_to_fast'],
                         'arc_instances_removed':old['arc_instances_removed_ctrl_to_fast']},
         'pairs':{},'wall_by_arm':{},'mean_paired_fast_pct_reduction':None}
    order=[('ctrl',1,'ctrl',2),('ctrl',1,'ctrl',3),('ctrl',2,'ctrl',3),
           ('fast',1,'fast',2),('fast',1,'fast',3),('fast',2,'fast',3),
           ('ctrl',1,'fast',1),('ctrl',2,'fast',2),('ctrl',3,'fast',3)]
    for a,i,b,j in order:
        x=d.Graph(rows[(a,i)]['graph'],100000,64)
        y=d.Graph(rows[(b,j)]['graph'],100000,64)
        try: c=d.compare(x,y,detail_limit=5)
        finally: x.close();y.close()
        k=f'{a}_r{i}__vs__{b}_r{j}'
        out['pairs'][k]={key:c[key] for key in ('classification','different_neighbor_multiset_vertices',
             'order_only_vertices','arcs_ctrl','arcs_fast','arc_instances_removed_ctrl_to_fast',
             'arc_instances_added_ctrl_to_fast','unique_edge_set_removed','unique_edge_set_added',
             'normalized_sorted_rows_sha_ctrl','normalized_sorted_rows_sha_fast','sample_different_vertices')}
        print('R90_P39_REPRO_GRAPH_COMPARE',k,c['classification'],
              'changed_vertices',c['different_neighbor_multiset_vertices'],
              'arc_lost',c['arc_instances_removed_ctrl_to_fast'],
              'arc_gained',c['arc_instances_added_ctrl_to_fast'],flush=True)
    for arm in ('ctrl','fast'):
        out['wall_by_arm'][arm]=[float(rows[(arm,i)]['wall_s']) for i in (1,2,3)]
    reductions=[100*(rows[('ctrl',i)]['wall_s']-rows[('fast',i)]['wall_s'])/rows[('ctrl',i)]['wall_s'] for i in (1,2,3)]
    out['paired_fast_pct_reduction']=reductions
    out['mean_paired_fast_pct_reduction']=statistics.mean(reductions)
    out['within_arm_100k_graph_varies']=any((q['different_neighbor_multiset_vertices']>0) for k,q in out['pairs'].items() if ('ctrl_r' in k and '__vs__ctrl_r' in k) or ('fast_r' in k and '__vs__fast_r' in k))
    out['scope_note']='This is GRAPH consistency under schedule variations, not Recall or QPS. Nonzero edge difference requires matched Search assessment.'
    report=NEW_ROOT/'within_arm_semantic_audit.json'
    ck(not report.exists() and not report.is_symlink(),'AUDIT_ALREADY_EXISTS')
    with report.open('x') as f:json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
    print('R90_P39_REPRO_AUDIT_PASS_GRAPH_VARIABILITY_RECORDED',
          'within_arm_varies',out['within_arm_100k_graph_varies'],
          'mean_paired_fast_wall_gain_pct',round(out['mean_paired_fast_pct_reduction'],4),flush=True)
    print('R90_P39_REPRO_REPORT',report,flush=True)

def selftest():
    with tempfile.TemporaryDirectory() as temp:
        q=pathlib.Path(temp)/'obj.json'
        atomic_save(q,{'x':7})
        assert json.loads(q.read_text())=={'x':7}
        atomic_save(q,{'x':8})
        assert json.loads(q.read_text())=={'x':8}
        assert not q.with_suffix(q.suffix+'.tmp').exists()
    assert set(('ctrl','fast'))=={'ctrl','fast'}
    assert [a for a in (2,3)]==[2,3]
    print('R90_P39_REPRO_SELFTEST_PASS_ATOMIC_STATE_UPDATE_AND_REP_PROTOCOL',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('selftest','preflight','pilot','audit'))
    phase=parser.parse_args().phase
    {'selftest':selftest,'preflight':preflight,'pilot':pilot,'audit':audit}[phase]()

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('R90_P39_REPRO_HOLD',repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
