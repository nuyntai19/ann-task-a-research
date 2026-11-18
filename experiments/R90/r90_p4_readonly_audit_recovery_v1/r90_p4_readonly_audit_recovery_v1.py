#!/usr/bin/env python3
"""R90-P4 read-only recovery of the nine already completed MS-Turing1M BUILDs.

Fixes ONLY the tuple/list JSON normalization during physical-core provenance
comparison. Imports the exact SHA-pinned P4 runner and graph-semantic comparator;
reuses their verification helpers but never calls original audit()/pilot()/save().
All output goes into a NEW independent HOME report directory.

This does NOT run BUILD, Search, mutate any original R86/R90 evidence, or claim
Recall parity. Original P4 exit=2 remains in the historical log, unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile

HOME=Path.home()
ORIG=HOME/'Downloads/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1.py'
ORIG_SHA='c28ffbb20f729ce4d88f06da3c2be54d8d8b87c0e8ebef379528c93d22b30e43'
OUT=HOME/'R90_P4_RESCUE_AUDIT_v1'


def fail(tag):
    raise RuntimeError('R90_P4_RESCUE_HOLD_'+tag)


def require(cond,tag):
    if not cond: fail(tag)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4<<20), b''): h.update(b)
    return h.hexdigest()


def load_original():
    require(ORIG.is_file() and not ORIG.is_symlink(), 'ORIGINAL_RUNNER_MISSING')
    require(sha(ORIG)==ORIG_SHA, 'ORIGINAL_RUNNER_SHA')
    spec=importlib.util.spec_from_file_location('r90_p4_original_SHA_PINNED', str(ORIG))
    require(spec is not None and spec.loader is not None,'IMPORT_SPEC')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.OUT.name=='r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1','ROOT_NAME_DRIFT')
    return module


def normalized_physical_core_ids(raw):
    """Only normalize JSON tuple->list for the unique frozen topology field."""
    require(type(raw) is list and len(raw)==4,'TOPOLOGY_FOUR_ITEMS')
    require(all(type(pair) in (tuple,list) and len(pair)==2 and
                all(type(v) is int and v>=0 for v in pair) for pair in raw),
            'TOPOLOGY_TYPES')
    norm=[list(pair) for pair in raw]
    require(len(set(map(tuple,norm)))==4, 'TOPOLOGY_DISTINCT')
    return norm


def validate_topology(frozen, current):
    a=normalized_physical_core_ids(frozen)
    b=normalized_physical_core_ids(current)
    require(a==b,'PROVENANCE_DRIFT_physical_core_identifiers')
    return a


def verify_core(o):
    # This calls the original pinned helper that verifies LIVE dataset/ELF/source
    # hashes and 4 distinct physical CPU cores. No resource minimum applies to audit.
    cur=o.provenance(check_resource=False)
    st=o.load_manifest() # fixed original OUT, frozen 9-run manifest; SHA-bound to original
    frozen=st.get('provenance')
    require(isinstance(frozen,dict),'FROZEN_PROVENANCE_MISSING')
    for key in ('data_sha','elf_sha','p38_script_sha','h17_source_sha',
                'semantic_diff_script_sha','r86_stock_manifest_sha',
                'r86_mst_campaign_manifest_sha','cpus','threads','flags'):
        require(frozen.get(key)==cur.get(key),'PROVENANCE_DRIFT_'+key)
    topology=validate_topology(frozen.get('physical_core_identifiers'),
                               cur.get('physical_core_identifiers'))
    require(st.get('campaign')=='R90_P4_MSTURING1M_THREE_ARM_4CPU_BUILD',
            'CAMPAIGN_NAME')
    require(st.get('quality_status')=='NATIVE_MST1M_SEARCH_NOT_RUN',
            'QUALITY_PRETEND_STATUS')
    require(st.get('Latin_square_orders')=={str(k):list(v) for k,v in o.ORDERS.items()},
            'LATIN_SQUARE_PROVENANCE')
    return st,cur,topology


def verify_runs(o,st):
    seen=set()
    for row in st['runs']:
        arm,rep=row.get('arm'),row.get('rep')
        require(arm in o.ELF and type(rep) is int and rep in (1,2,3),
                'UNKNOWN_RUN_ID')
        key=(arm,rep)
        require(key not in seen, 'DUPLICATE_RUN_ID')
        seen.add(key)
        require(row.get('builder_sha')==o.ELF_SHA[arm], 'ELF_SHA_'+str(key))
        require(type(row.get('cpu_pct')) in (int,float) and 300<=row['cpu_pct']<=450,
                'CPU_PERCENT_'+str(key))
        require(type(row.get('wall_s')) in (int,float) and
                math.isfinite(row['wall_s']) and row['wall_s']>0,
                'WALL_'+str(key))
        require(type(row.get('peak_rss_kib')) is int and row['peak_rss_kib']>0,
                'RSS_'+str(key))
        tag=f'mst1m_{arm}_r{rep}'
        paths={
            'graph':(o.OUT/'graphs'/(tag+'.graph'),'graph_sha'),
            'stdout':(o.OUT/'logs'/(tag+'.stdout'),'stdout_sha'),
            'timefile':(o.OUT/'logs'/(tag+'.time'),'timefile_sha'),
        }
        for kind,(expected,hashfield) in paths.items():
            p=Path(row[kind])
            require(p==expected and o.safe_file(p),'EVIDENCE_PATH_'+tag+'_'+kind)
            require(sha(p)==row[hashfield],'EVIDENCE_SHA_'+tag+'_'+kind)
        expected_argv=[str(o.ELF[arm]),'-base_path',str(o.BASE),
                       '-graph_outfile',str(paths['graph'][0]),*o.FLAGS]
        require(row.get('args')==expected_argv,'BUILD_FLAGS_'+tag)
        require(row.get('env_threads')=={'PARLAY_NUM_THREADS':'4','OMP_NUM_THREADS':'4'},
                'BUILD_THREADS_'+tag)
        require(row.get('graph_info')==o.graph_info(paths['graph'][0]),
                'GRAPH_STRUCTURE_'+tag)
        require(row.get('dataset')=='MSTuring1M','DATASET_'+tag)
        # /usr/bin/time -v controls: check status and printed CPU pct metadata
        tm=paths['timefile'][0].read_text(errors='replace')
        require('Exit status: 0' in tm,'NATIVE_EXIT_NONZERO_'+tag)
    require(seen=={(arm,rep) for arm in o.ELF for rep in (1,2,3)},
            'NINE_ARM_REP_COVERAGE')
    return True


def report(o,st,cur,topology):
    stats,pairs=o.paired_stats(st)
    diffmod=o.load_diff() # second script SHA verified in original provenance
    semantic=[]
    for rep in (1,2,3):
        by={r['arm']:r for r in st['runs'] if r['rep']==rep}
        for a,b in (('stock','h17'),('h17','fast'),('stock','fast')):
            A=diffmod.Graph(Path(by[a]['graph']),o.N,o.CAP)
            try:
                B=diffmod.Graph(Path(by[b]['graph']),o.N,o.CAP)
                try:
                    comparison=diffmod.compare(A,B,detail_limit=5)
                finally:B.close()
            finally:A.close()
            semantic.append({'rep':rep,'baseline_arm':a,'comparison_arm':b,
                'baseline_graph_sha':by[a]['graph_sha'],
                'comparison_graph_sha':by[b]['graph_sha'],
                'semantic':comparison})
            print('R90_P4_RESCUE_GRAPH_COMPARE',rep,a,'vs',b,
                  comparison['classification'],'changed_vertices',
                  comparison['different_neighbor_multiset_vertices'],flush=True)
    return {
        'status':'PASS_READONLY_RESCUE_AUDIT_9_P4_BUILDS__SEARCH_NOT_RUN',
        'original_pilot_status':'NINE_4CPU_BUILDS_COMPLETE_QUALITY_PENDING',
        'original_audit_status':'HOLD_physical_core_identifiers_tuple_vs_JSON_list',
        'original_runner_sha':ORIG_SHA,
        'original_build_manifest_path':str(o.OUT/'build_manifest.json'),
        'original_build_manifest_sha':sha(o.OUT/'build_manifest.json'),
        'original_progress_sha':sha(o.OUT/'progress.json'),
        'original_dataset':'MSTuring1M','n':o.N,'d':100,
        'physical_core_identifiers_normalized':topology,
        'normalization_scope':'ONLY physical_core_identifiers tuple/list JSON round trip',
        'native_evidence_sha_checked_for_all_nine_runs':True,
        'source_elf_data_4core_provenance_checked':True,
        'arms':stats, 'comparisons':pairs,'graph_semantic':semantic,
        'quality_status':'NATIVE_MS_TURING1M_100KQ_SEARCH_NOT_RUN',
        'limitations':[
            'This report independently audits pre-existing evidence; original P4 runner and failed audit log stay unchanged.',
            'Stock ELF from R86, H17/Fast ELFs from R90; source/toolchain vintage differs.',
            'Four-CPU graph SHA/neighbor differences cannot by themselves establish Recall parity.',
            'No MS-Turing1M native Search Recall/QPS or matched-Recall evidence yet.',
            'Time is native uninstrumented BUILD; audit does not rebuild or retime.'
        ]}


def selftest():
    o=load_original()
    assert normalized_physical_core_ids([(0,0),(0,4),(0,8),(0,12)])==[
        [0,0],[0,4],[0,8],[0,12]]
    assert validate_topology([[0,0],[0,4],[0,8],[0,12]],
                             [(0,0),(0,4),(0,8),(0,12)])==[
        [0,0],[0,4],[0,8],[0,12]]
    try:
        validate_topology([[0,0],[0,4],[0,8],[0,12]],
                          [(0,0),(0,4),(0,9),(0,12)])
        raise AssertionError('topology drift gate did not fail')
    except RuntimeError as e:
        assert 'PROVENANCE_DRIFT_physical_core_identifiers' in str(e)
    raw=json.loads(json.dumps({'physical_core_identifiers':[(0,0),(0,4),(0,8),(0,12)]}))
    assert validate_topology(raw['physical_core_identifiers'],
                             [(0,0),(0,4),(0,8),(0,12)])
    assert len(o.ORDERS)==3 and set(o.ELF)=={'stock','h17','fast'}
    print('R90_P4_RESCUE_SELFTEST_PASS_TOPOLOGY_JSON_NORMALIZE_REAL_DRIFT_HOLD',flush=True)


def preflight():
    require(not OUT.exists() and not OUT.is_symlink(),'RESCUE_OUTPUT_EXISTS')
    o=load_original();st,cur,topo=verify_core(o)
    require(len(st['runs'])==9,'NOT_NINE_BUILDS')
    print('R90_P4_RESCUE_PREFLIGHT_PASS_PINNED_ORIGINAL_SOURCE_9BUILDS_CPU_TOPO',
          topo,flush=True)


def audit():
    preflight()
    o=load_original();st,cur,topo=verify_core(o)
    verify_runs(o,st)
    print('R90_P4_RESCUE_NINE_NATIVE_RUNS_SOURCE_ELF_GRAPH_LOG_TIME_SHA_PASS',flush=True)
    res=report(o,st,cur,topo)
    # Independent output, newly created only after every evidence gate and compare passed.
    OUT.mkdir(mode=0o700)
    dest=OUT/'build_summary_rescue_v1.json'
    with dest.open('x') as f: json.dump(res,f,indent=2,sort_keys=True);f.write('\n')
    receipt={'status':'PASS_READONLY_RESCUE_AUDIT',
             'original_build_manifest_sha':res['original_build_manifest_sha'],
             'recovered_report_sha':sha(dest),'report':str(dest),
             'original_runner_sha':ORIG_SHA}
    with (OUT/'audit_receipt_v1.json').open('x') as f:
        json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
    for name,p in res['comparisons'].items():
        print('R90_P4_RESCUE_SPEED',name,
              'mean_paired_saving_pct',round(p['mean_pair_pct_saving'],5),
              'ratio_of_means_pct',round(p['ratio_of_mean_wall_pct_saving'],5),flush=True)
    print('R90_P4_RESCUE_AUDIT_PASS_9_NATIVE_BUILD_GRAPH_SEMANTICS',flush=True)
    print('R90_P4_RESCUE_REPORT',dest,flush=True)
    print('R90_P4_RESCUE_RECEIPT',OUT/'audit_receipt_v1.json',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('selftest','preflight','audit'))
    args=p.parse_args()
    {'selftest':selftest,'preflight':preflight,'audit':audit}[args.phase]()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P4_RESCUE_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        raise SystemExit(2)
