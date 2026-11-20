#!/usr/bin/env python3
"""R90 P2.1: pinned 100K Stock N1/N2 vs stock+A5 dryrun/gate(1%).

Runs ONLY on the user's Ubuntu host with the pinned R90 P0 ELF files and
historical R70 300-query search evaluator. This file is prepared and locally
syntax/self-tested, NOT native-executed on the user's Ubuntu environment.

Usage: python3 FILE {selftest,preflight,pilot,audit}
Outputs are written exclusively under a previously nonexistent P2 root.
Source code and all historical graphs/data are READ-ONLY.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path.home() / 'ann-task-a'
OUT = ROOT / 'experiments/R90/r90_p2_sift100k_pass2_value_gate1_v1'
BUILD = ROOT / 'experiments/R90/r90_p0_stock_a5_compile_gate_v1'
EVAL = ROOT / 'experiments/H70/build-r70/algorithms/PipNN/r70_graph_recall'
BASE = ROOT / 'data/sift100k.fbin'
QUERY = ROOT / 'data/sift100k_queries_300.fbin'
GT = ROOT / 'data/sift100k_gt300.ibin'
BIN = {
 'stock': (BUILD / 'stock_build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN',
   '31b337316f69c5945dc78a14be16217e7f0bf901e7af5d752a3af17bdb337225'),
 'a5': (BUILD / 'a5_build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN',
   'aebdae764f3e79ff709546787c22e3df910dbb1934851ce7ddfaf4927ff10fa2'),
}
INPUTS = {
 'base': (BASE, 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'),
 'query': (QUERY, '9e9328e3f0488840d3f12efcc3b0f6af940dd398fb7b6d178d72bd1e1c0f9d74'),
 'gt': (GT, 'e038aff5970977d0ee925b4357295bd81817b99b35e11bbab783fd64e0715e7f'),
 'evaluator': (EVAL, 'f3999051c6cc96434ea26d2faedd3ac632ed8d20be342e15c92fd4b905a33fe9'),
}
ARMS = [
 ('stock_N1', 'stock', 1, 'off', None),
 ('stock_N2', 'stock', 2, 'off', None),
 ('a5_dryrun_q001_N2', 'a5', 2, 'dryrun', '0.01'),
 ('a5_gate_q001_N2', 'a5', 2, 'gate', '0.01'),
]
BEAMS = [10, 20, 40, 80, 160]
RE_ROW = re.compile(r'^R70_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$', re.M)
RE_SCREEN = re.compile(r'R90_A5_LEAF_SCREEN total=(\d+) eligible=(\d+) WL_total=(\d+) WL_eligible=(\d+) gate=(\d+)')


def ck(cond, label):
    if not cond:
        raise RuntimeError('R90_P2_HOLD_' + label)


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def file_shape(path, kind):
    with path.open('rb') as f: header=f.read(8)
    ck(len(header)==8, 'TRUNCATED_'+kind)
    n,d=struct.unpack('<II',header)
    entry_bytes = 4 if kind!='gt' else 8
    ck(path.stat().st_size == 8+n*d*entry_bytes, 'BAD_SIZE_'+kind)
    return n,d


def graph_shape(path):
    with path.open('rb') as f: h=f.read(8)
    ck(len(h)==8,'GRAPH_HEADER_SHORT')
    n,r=struct.unpack('<II',h)
    ck((n,r)==(100000,64),'GRAPH_HEADER_N_R')
    ck(path.stat().st_size>8+n*4,'GRAPH_TOO_SMALL')
    return n,r


def preflight(cpu, out):
    ck(out.parent.is_dir(), 'OUTPUT_PARENT')
    ck(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    ck(shutil.which('taskset') is not None,'TASKSET_MISSING')
    ck(Path('/usr/bin/time').is_file(),'TIME_MISSING')
    ck(cpu in os.sched_getaffinity(0),'CPU_UNAVAILABLE')
    for name,(p,expected) in {**INPUTS,**BIN}.items():
        ck(p.is_file(),'MISSING_'+name.upper())
        actual=sha(p)
        ck(actual==expected, 'SHA_'+name.upper())
        print('R90_P2_INPUT_SHA_PASS',name,actual,flush=True)
    ck(file_shape(BASE,'base')==(100000,128),'BASE_SHAPE')
    ck(file_shape(QUERY,'query')==(300,128),'QUERY_SHAPE')
    ck(file_shape(GT,'gt')==(300,100),'GT_SHAPE')
    ck(sha(Path(__file__).resolve()) != '', 'SCRIPT_SHA_READ')
    ck(os.access(EVAL,os.X_OK),'EVALUATOR_NOT_EXECUTABLE')
    for k,(p,_) in BIN.items():ck(os.access(p,os.X_OK),'BIN_NOT_EXECUTABLE_'+k)
    print('R90_P2_PREFLIGHT_PASS_100K_300Q_PINNED_ELF_EVAL_GT',flush=True)
    return {'cpu':cpu,'input_sha':{k:expected for k,(p,expected) in {**INPUTS,**BIN}.items()},
            'base':str(BASE),'queries':str(QUERY),'gt':str(GT),'evaluator':str(EVAL),
            'parameters':{'C':160,'K':1024,'N':[1,2],'MST_DEG':2,'R':64,'top_level_leaders':100,'fanout_scheme':'10,3,1','hash_bits':12,'alpha':1.1},
            'cautions':['SIFT100K 300-query screening: single graph per arm, NOT formal reproducible QPS',
                        'same-base/GT/beam; recall-at-fixed-beam, NOT exactly matched recall',
                        'R70 evaluator originally pinned to SIFT100K 100k base / 300 queries',
                        'all Build runs use one core; A5 selector overhead is included in timed build',
                        'A5 dryrun/gate still perform full Pass2 partition work',
                        'A5 q1% is degree-based with ID tie break; NOT a validated optimal policy']}


def build_cmd(binary, graph, n):
    return [str(binary), '-base_path',str(BASE),'-graph_outfile',str(graph),
            '-num_clusters',str(n),'-cluster_size','1024','-table_size','160',
            '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
            '-prune','1','-prune_all','1','-prune_degree','64','-hash_bits','12',
            '-alpha','1.1','-k','0']


def parse_screen(s):
    a=RE_SCREEN.findall(s)
    ck(len(a)==1,'SCREEN_COUNT')
    t,e,wt,we,g=map(int,a[0])
    ck(0<=e<=t and 0<=we<=wt and wt>0,'SCREEN_VALUES')
    return {'total_leaves':t,'eligible_leaves':e,'eligible_leaf_pct':100*e/t,
            'wl_total':wt,'wl_eligible':we,'eligible_wl_pct':100*we/wt,'gate':g}


def parse_search(s):
    ck('R70_RECALL_INPUT_PASS' in s and 'R70_RECALL_EVAL_PASS' in s,'EVALUATOR_LOG_PASS')
    rs=RE_ROW.findall(s)
    ck(len(rs)==5,'EVALUATOR_BEAM_COUNT')
    ret=[]
    for i,row in enumerate(rs):
        b=int(row[0]);rec,qps,cmps,visited=map(float,row[1:])
        ck(b==BEAMS[i] and 0<=rec<=1 and qps>0 and cmps>=0 and visited>=0,'EVAL_ROW_BAD')
        ret.append({'beam':b,'recall':rec,'qps':qps,'avg_cmps':cmps,'avg_visited':visited})
    return ret


def invoke(cmd, env, out_log, time_log=None, timeout=900):
    with out_log.open('x',encoding='utf8') as f:
        if time_log is not None:
            cmd=['/usr/bin/time','-v','-o',str(time_log),*cmd]
        start=time.perf_counter()
        p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=timeout,check=False)
        duration=time.perf_counter()-start
    ck(p.returncode==0, 'NATIVE_RETURN_CODE_'+out_log.stem)
    return duration


def pilot(cpu,out,reps):
    meta=preflight(cpu,out)
    out.mkdir(parents=False)
    (out/'graphs').mkdir()
    (out/'logs').mkdir()
    meta['test_script_sha256']=sha(Path(__file__).resolve())
    builds=[]; all_search=[]
    env_base=os.environ.copy()
    env_base['PARLAY_NUM_THREADS']='1'
    env_base['LC_ALL']='C'
    env_base.pop('R90_A5_MODE',None);env_base.pop('R90_A5_FRACTION',None)
    for tag,which,n,mode,frac in ARMS:
        binary=BIN[which][0]
        graph=out/'graphs'/(tag+'.graph')
        ck(not graph.exists(),'GRAPH_OUTPUT_EXISTS_'+tag)
        cmd=build_cmd(binary,graph,n)
        env=env_base.copy()
        if which=='a5':
            env['R90_A5_MODE']=mode
            env['R90_A5_FRACTION']=frac
        stdout=out/'logs'/(tag+'.build.stdout')
        stderr=out/'logs'/(tag+'.build.time')
        print('R90_P2_BUILD_START',tag,'N',n,'mode',mode,'frac',frac,flush=True)
        duration=invoke(['taskset','-c',str(cpu),*cmd],env,stdout,stderr,timeout=1200)
        graph_shape(graph)
        txt=stdout.read_text(errors='replace')
        # Confirm that the intended A5 mode was actually printed.
        if which=='a5':ck('R90_A5_MODE='+mode in txt,'A5_MODE_NOT_CONFIRMED_'+tag)
        else: ck('R90_A5_MODE=' not in txt,'STOCK_HAS_A5_MARKER')
        if which=='a5': coverage=parse_screen(txt)
        else:coverage=None
        entry={'arm':tag,'n_passes':n,'mode':mode,'frac':frac,
            'graph_path':str(graph),'graph_sha256':sha(graph),
            'graph_bytes':graph.stat().st_size,'wall_s_external_including_output':duration,
            'build_log':str(stdout),'build_log_sha256':sha(stdout),
            'time_log':str(stderr),'time_log_sha256':sha(stderr),'coverage':coverage,
            'binary_sha256':BIN[which][1], 'native_command':cmd}
        builds.append(entry)
        (out/'builds.partial.json').write_text(json.dumps(builds,indent=2)+'\n')
        print('R90_P2_BUILD_PASS',tag,'sha',entry['graph_sha256'],'s',round(duration,3),'coverage',coverage,flush=True)
    # Compare new stock N2 against a5 dryrun 1%: this is a hard equivalence gate.
    b={x['arm']:x for x in builds}
    ck(b['stock_N2']['graph_sha256']==b['a5_dryrun_q001_N2']['graph_sha256'],
       'STOCK_N2_VS_A5_DRYRUN_GRAPH_PARITY')
    ck(b['a5_dryrun_q001_N2']['coverage']['gate']==0,'DRYRUN_GATE_NOT_ZERO')
    ck(b['a5_gate_q001_N2']['coverage']['gate']==1,'GATE_NOT_ONE')
    print('R90_P2_STOCK_N2_A5_DRYRUN_GRAPH_BYTE_PARITY_PASS',flush=True)

    search_reps=int(reps)
    # Rotate order to reduce order-specific cache and load confounding.
    order=['stock_N1','stock_N2','a5_dryrun_q001_N2','a5_gate_q001_N2']
    for rep in range(1,search_reps+1):
        arranged=order[(rep-1)%4:]+order[:(rep-1)%4]
        if rep%2==0:arranged=list(reversed(arranged))
        for tag in arranged:
            graph=b[tag]['graph_path']
            log=out/'logs'/f'{tag}.search_r{rep}.stdout'
            print('R90_P2_SEARCH_START',tag,'rep',rep,flush=True)
            duration=invoke(['taskset','-c',str(cpu),str(EVAL),graph,str(BASE),str(QUERY),str(GT)],
                            env_base,log,timeout=900)
            rows=parse_search(log.read_text(errors='replace'))
            e={'arm':tag,'search_rep':rep,'rows':rows,'search_wall_s':duration,
               'graph_sha256':b[tag]['graph_sha256'],'log_path':str(log),
               'log_sha256':sha(log)}
            all_search.append(e)
            (out/'search.partial.json').write_text(json.dumps(all_search,indent=2)+'\n')
            print('R90_P2_SEARCH_PASS',tag,'rep',rep,'recall_beam80',rows[3]['recall'],flush=True)
    meta.update({'status':'NATIVE_SCREEN_COMPLETED','builds':builds,'search':all_search,
                 'build_reps_per_arm':1,'search_reps_per_graph':search_reps})
    manifest=out/'result_manifest.json'
    manifest.write_text(json.dumps(meta,indent=2)+'\n')
    print_summary(meta,out)
    print('R90_P2_100K_N1_N2_A5_GATE1_NATIVE_PILOT_PASS',manifest,flush=True)


def print_summary(meta,out):
    import statistics
    vals={}
    for e in meta['search']:
        for x in e['rows']:
            vals.setdefault((e['arm'],x['beam']),[]).append(x)
    csvfile=out/'screen_summary.csv'
    with csvfile.open('x',newline='',encoding='utf8') as f:
        w=csv.writer(f)
        w.writerow(['arm','beam','recall_median','qps_median','avg_cmps_median','avg_visited_median','search_rep_count'])
        for arm,_,_,_,_ in ARMS:
            for beam in BEAMS:
                rs=vals[(arm,beam)]
                arr=[statistics.median(x[k] for x in rs) for k in ('recall','qps','avg_cmps','avg_visited')]
                w.writerow([arm,beam,*arr,len(rs)])
                if beam in (40,80,160):
                    print('R90_P2_SCREEN',arm,'beam',beam,
                          'recall',round(arr[0],8),'QPS',round(arr[1],3),
                          'cmps',round(arr[2],2),flush=True)
    print('R90_P2_SCREEN_CSV',csvfile,flush=True)


def audit(out):
    ck(out.is_dir(),'AUDIT_ROOT_MISSING')
    m=out/'result_manifest.json'
    ck(m.is_file(),'RESULT_MANIFEST_MISSING')
    doc=json.loads(m.read_text())
    ck(doc['status']=='NATIVE_SCREEN_COMPLETED','INCOMPLETE')
    ck(len(doc['builds'])==4,'BUILD_COUNT')
    ck(len(doc['search'])==4*doc['search_reps_per_graph'],'SEARCH_COUNT')
    for b in doc['builds']:
        p=Path(b['graph_path']);graph_shape(p)
        ck(sha(p)==b['graph_sha256'],'AUDIT_GRAPH_SHA_'+b['arm'])
        for k,pk in [('build_log_sha256','build_log'),('time_log_sha256','time_log')]:
            ck(sha(Path(b[pk]))==b[k],'AUDIT_LOG_SHA_'+b['arm'])
    for s in doc['search']:
        ck(sha(Path(s['log_path']))==s['log_sha256'],'AUDIT_SEARCH_LOG_SHA_'+s['arm'])
        ck(len(parse_search(Path(s['log_path']).read_text(errors='replace')))==5,'AUDIT_SEARCH_PARSE')
    print('R90_P2_AUDIT_COMPLETE_4_GRAPHS_AND_SEARCH_RECEIPTS_PASS',flush=True)


def selftest():
    s='R90_A5_LEAF_SCREEN total=10 eligible=3 WL_total=100 WL_eligible=40 gate=0\n'
    x=parse_screen(s);ck(abs(x['eligible_wl_pct']-40)<1e-9,'TEST_COVERAGE')
    s='R70_RECALL_INPUT_PASS\n'+''.join(f'R70_RECALL_ROW beam={b} recall=0.99 qps=1000 avg_cmps=200 avg_visited=100\n' for b in BEAMS)+'R70_RECALL_EVAL_PASS\n'
    ck(len(parse_search(s))==5,'TEST_EVAL')
    ck(build_cmd(Path('/bin/true'),Path('/tmp/new.graph'),2).count('-num_clusters')==1,'TEST_CMD')
    print('R90_P2_LOCAL_SELFTEST_PASS_READONLY_PARSER_AND_CMD',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('selftest','preflight','pilot','audit'))
    p.add_argument('--cpu',type=int,default=0)
    p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--search-reps',type=int,default=3)
    a=p.parse_args()
    ck(a.search_reps in range(1,6),'SEARCH_REPS_RANGE')
    out=a.out.expanduser().resolve(strict=False)
    if a.mode=='selftest':selftest()
    elif a.mode=='preflight':preflight(a.cpu,out)
    elif a.mode=='pilot':pilot(a.cpu,out,a.search_reps)
    else:audit(out)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P2_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
