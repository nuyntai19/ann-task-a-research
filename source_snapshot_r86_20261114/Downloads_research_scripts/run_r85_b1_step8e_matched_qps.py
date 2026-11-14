#!/usr/bin/env python3
"""R85-B1 Step8E matched-Recall QPS on the existing paired SIFT100K P1/P2.

No graph BUILD, dataset creation, source compilation, or modification of
historical H70/A4/A4b/A4c/B1 graph and QUALITY artifacts.

Use the exact pinned native 100K evaluator from Step8E and selected beams from
its saved 83-beam quality sweeps. Repeat interleaved 1-P-core QPS passes, then
interpolate microseconds/query within each graph's measured Recall bracket.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
import time
from datetime import datetime

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
B1 = ROOT / 'experiments/H85/r85_b1_controlled'
ORIGINAL = HOME / 'Downloads/run_r85_b1_step8e_native_eval.py'
ORIGINAL_SHA = '1ce98cfe4adea2b9192e681b8442b7747c61e5a658e1ecb5a68d92094875b625'
EVAL_SHA = '3698f915ef3b7369aee527b6bb126512c0e31eb677a46480a5526cf4f909c64a'
OUT_ROOT = B1 / 'step8e_matched_qps'
TARGETS = (0.89, 0.96, 0.99, 0.998)
REPEATS = 5
PINNED_RECALL_TOL = 0.00011
PINNED_CMPS_TOL = 2.0


def fail(s):
    raise RuntimeError(s)


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load_runner():
    if ORIGINAL.is_symlink() or not ORIGINAL.is_file() or sha(ORIGINAL) != ORIGINAL_SHA:
        fail('PINNED_STEP8E_ORIGINAL_RUNNER_MISSING_OR_SHA_DRIFT')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('r85_b1_native_eval_pinned', ORIGINAL)
    if spec is None or spec.loader is None:
        fail('NATIVE_RUNNER_IMPORT_FAILED')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bracket(rows, target):
    # Use measured Recall, not modeled/extrapolated Recall; fail on anomalous
    # nonmonotonicity large enough to invalidate the chosen direct bracket.
    if target < rows[0]['recall'] or target > rows[-1]['recall']:
        return None
    for i, row in enumerate(rows):
        if row['recall'] >= target:
            if i == 0:
                return (row['beam'], row['beam'])
            prev = rows[i-1]
            if prev['recall'] > target or row['recall'] < prev['recall']:
                fail('BAD_LOCAL_RECALL_BRACKET')
            return (prev['beam'], row['beam'])
    return None


def select_beams(rows, targets):
    seq = [r['beam'] for r in rows]
    chosen = set()
    brackets = {}
    for target in targets:
        pair = bracket(rows, target)
        if pair is None:
            fail(f'TARGET_UNCOVERED_NO_EXTRAPOLATION target={target}')
        brackets[str(target)] = list(pair)
        for beam in pair:
            j = seq.index(beam)
            for dj in (-1, 0, 1):
                if 0 <= j+dj < len(seq):
                    chosen.add(seq[j+dj])
    return sorted(chosen), brackets


def validate_quality(mod, name):
    p = mod.OUT / 'quality' / (name+'.json')
    if p.is_symlink() or not p.is_file():
        fail(f'QUALITY_FILE_MISSING_OR_LINK {p}')
    d = json.loads(p.read_text())
    expected = {'graph_sha256':mod.PIN[name], 'evaluator_sha256':EVAL_SHA,
                'base_sha256':mod.PIN['base'], 'query_sha256':mod.PIN['query'],
                'gt_sha256':mod.PIN['gt']}
    if any(d.get(k) != v for k,v in expected.items()):
        fail(f'QUALITY_PROVENANCE_DRIFT {name}')
    if d.get('graph') != name or d.get('beams') != list(mod.DENSE):
        fail(f'QUALITY_BEAM_GRID_DRIFT {name}')
    rows = d.get('rows', [])
    if len(rows) != len(mod.DENSE) or [r['beam'] for r in rows] != list(mod.DENSE):
        fail(f'QUALITY_ROWS_DRIFT {name}')
    for r in rows:
        if (not 0 <= r['recall'] <= 1 or not math.isfinite(r['recall'])
            or not math.isfinite(r['qps']) or r['qps'] <= 0
            or not math.isfinite(r['avg_cmps']) or r['avg_cmps'] < 0):
            fail(f'QUALITY_BAD_ROW {name}')
    return rows, sha(p)


def audit():
    mod = load_runner()
    mod.verify_binary()  # also pins P1/P2/base/query/GT/compiled source
    if sha(mod.BIN) != EVAL_SHA:
        fail('NATIVE_EVALUATOR_SHA_DRIFT')
    if os.name != 'posix' or 0 not in os.sched_getaffinity(0) or not shutil.which('taskset'):
        fail('CPU0_TASKSET_UNAVAILABLE')
    if shutil.disk_usage(B1).free < 2 * (1024**3):
        fail('FREE_DISK_BELOW_2_GIB')
    if OUT_ROOT.is_symlink() or (OUT_ROOT.exists() and not OUT_ROOT.is_dir()):
        fail('UNSAFE_OUTPUT_DIRECTORY')
    info={}
    for name in ('P1','P2'):
        rows, qsha=validate_quality(mod,name)
        selected, brackets=select_beams(rows,TARGETS)
        info[name]={'quality_sha256':qsha,'rows':rows,'selected':selected,'brackets':brackets}
        print(f'R85_B1_STEP8E_QPS_PLAN {name} beams={len(selected)} '
              + json.dumps({'selected':selected,'target_brackets':brackets},sort_keys=True),flush=True)
    print('R85_B1_STEP8E_MATCHED_QPS_PREFLIGHT_PASS_NO_WRITE',flush=True)
    return mod,info


def interp_latency(lookup, pair, target):
    low,high = pair
    a=lookup[low]
    if low==high:
        return (1e6/a['qps'],a['avg_cmps'])
    b=lookup[high]
    ra,rb=a['recall'],b['recall']
    if not (ra <= target <= rb and rb > ra):
        fail(f'REPEAT_BRACKET_NOT_COVERED_NO_EXTRAPOLATION target={target} low={ra} high={rb}')
    w=(target-ra)/(rb-ra)
    return (1e6/a['qps']+(1e6/b['qps']-1e6/a['qps'])*w,
            a['avg_cmps']+(b['avg_cmps']-a['avg_cmps'])*w)


def atomic_json(path, content):
    if path.exists() or path.is_symlink():
        fail('REFUSE_OVERWRITE '+str(path))
    with path.open('x') as f:
        json.dump(content,f,indent=2,sort_keys=True)
        f.write('\n')


def qps_pass(mod,name,beams,outdir,rep):
    order = beams if rep % 2 else list(reversed(beams))
    cmd=['taskset','-c','0',str(mod.BIN),str(mod.PAIR/(name+'.graph')),
         str(mod.DATA),str(mod.QUERY),str(mod.GT),','.join(map(str,order))]
    env=dict(os.environ,PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
             MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    out=outdir/(f'rep{rep:02d}_{name}.log')
    started=time.monotonic()
    with out.open('x') as f:
        result=subprocess.run(cmd,env=env,cwd=mod.OUT,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode!=0:
        fail(f'NATIVE_SEARCH_FAILED rep={rep} graph={name} rc={result.returncode} log={out}')
    text=out.read_text(errors='replace')
    parsed=mod.parse(text,order,name)
    d={r['beam']:r for r in parsed}
    if set(d)!=set(beams):fail('INCOMPLETE_SEARCH_ROWS '+name)
    return d,round(time.monotonic()-started,3),sha(out)


def run():
    mod,info=audit()
    OUT_ROOT.mkdir(parents=True,exist_ok=True)
    out=OUT_ROOT/('qps_'+datetime.now().strftime('%Y%m%d-%H%M%S')+'_'+str(os.getpid()))
    out.mkdir(exist_ok=False)
    print('R85_B1_STEP8E_MATCHED_QPS_SESSION '+str(out),flush=True)
    manifest={'protocol':'one paired P1/P2 graph; 5 interleaved temporal QPS passes on CPU0; same native C++ checkRecall; NO independent graph replicates',
              'quality_beams':list(mod.DENSE),'targets':list(TARGETS),'repeats':REPEATS,
              'evaluator_sha256':EVAL_SHA,'original_runner_sha256':ORIGINAL_SHA,
              'input_sha256':mod.PIN,
              'quality_sha256':{n:info[n]['quality_sha256'] for n in info},
              'selected_beams':{n:info[n]['selected'] for n in info},
              'brackets':{n:info[n]['brackets'] for n in info}}
    atomic_json(out/'manifest.json',manifest)
    measured={'P1':[],'P2':[]}
    for rep in range(1,REPEATS+1):
        graph_order=('P1','P2') if rep%2 else ('P2','P1')
        for name in graph_order:
            print(f'R85_B1_STEP8E_MATCHED_QPS_START rep={rep}/{REPEATS} graph={name}',flush=True)
            data,wall,logsha=qps_pass(mod,name,info[name]['selected'],out,rep)
            ref={r['beam']:r for r in info[name]['rows']}
            for beam,row in data.items():
                old=ref[beam]
                if abs(row['recall']-old['recall'])>PINNED_RECALL_TOL or abs(row['avg_cmps']-old['avg_cmps'])>PINNED_CMPS_TOL:
                    fail(f'RECALL_OR_CMPS_DRIFT graph={name} rep={rep} beam={beam} measured={row} quality={old}')
            matched={}
            for t in TARGETS:
                latency,cmps=interp_latency(data,info[name]['brackets'][str(t)],t)
                matched[str(t)]={'latency_us':latency,'avg_cmps':cmps}
            payload={'rep':rep,'graph':name,'log_sha256':logsha,'wall_total_s_advisory':wall,
                     'beam_order':list(data),'rows':[data[b] for b in data], 'matched':matched}
            atomic_json(out/f'rep{rep:02d}_{name}.json',payload)
            measured[name].append(payload)
            print(f'R85_B1_STEP8E_MATCHED_QPS_PASS rep={rep} graph={name} beams={len(data)}',flush=True)
    summary={'scope':'SIFT100K one paired BUILD, two graphs, 5 temporal QPS repeats; not graph-level replication',
             'unit':'latency_us_per_query', 'targets':{}}
    for t in TARGETS:
        by={}
        for name in ('P1','P2'):
            samples=[entry['matched'][str(t)]['latency_us'] for entry in measured[name]]
            cmps=[entry['matched'][str(t)]['avg_cmps'] for entry in measured[name]]
            by[name]={'median_latency_us':median(samples),'range_latency_us':[min(samples),max(samples)],
                      'temporal_samples_latency_us':samples,'median_avg_cmps':median(cmps),
                      'bracket_beams':info[name]['brackets'][str(t)]}
        by['p2_latency_change_percent_vs_p1']=100*(by['P2']['median_latency_us']/by['P1']['median_latency_us']-1)
        summary['targets'][str(t)]=by
        print('R85_B1_STEP8E_MATCHED_QPS_TARGET '+json.dumps({'target':t,**by},sort_keys=True),flush=True)
    atomic_json(out/'matched_qps_summary.json',summary)
    print('R85_B1_STEP8E_MATCHED_QPS_PILOT_PASS_SINGLE_PAIR '+str(out),flush=True)


def selftest():
    rows=[{'beam':10,'recall':.80},{'beam':20,'recall':.90},{'beam':30,'recall':.98}]
    selected, pairs=select_beams(rows,(.89,.96))
    assert selected==[10,20,30] and pairs['0.89']==[10,20] and pairs['0.96']==[20,30]
    v={10:{'recall':.80,'qps':10000,'avg_cmps':200},
       20:{'recall':.90,'qps':5000,'avg_cmps':300},
       30:{'recall':.98,'qps':2500,'avg_cmps':400}}
    x,c=interp_latency(v,[10,20],.85)
    assert abs(x-150)<1e-8 and abs(c-250)<1e-8
    assert bracket(rows,.99) is None
    print('R85_B1_STEP8E_MATCHED_QPS_SELFTEST_PASS_NO_PROJECT_IO',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    x=ap.add_mutually_exclusive_group(required=True)
    x.add_argument('--selftest',action='store_true')
    x.add_argument('--preflight',action='store_true')
    x.add_argument('--run',action='store_true')
    args=ap.parse_args()
    if args.selftest:selftest()
    elif args.preflight:audit()
    elif args.run:run()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R85_B1_STEP8E_MATCHED_QPS_FAIL_CLOSED '+repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
