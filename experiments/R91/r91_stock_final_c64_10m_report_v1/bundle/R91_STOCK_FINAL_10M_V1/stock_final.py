#!/usr/bin/env python3
"""Frozen Stock vs final v1.3 graph; clean search and optional offline topology."""
import argparse, json, os, sys, time, math, subprocess, shutil
from pathlib import Path
import r91_g6_matched_recall_12g_v1 as mr
v=mr.v; p=mr.p; need=p.need; sha=p.sha; pin=p.pin; load=p.load; atom=p.atom; clean=p.cleanpath
TAG='R91_STOCK_FINAL_10M_V1'; HERE=Path(__file__).resolve().parent
OUT=v.R91/'r91_stock_final_c64_10m_report_v1'; ARMS=('STOCK','FINAL_C64'); BEAMS=mr.BEAMS
GRAPHS={'STOCK':v.R91/'r91_g1stock_one_stock_flat_c160_mst10m_24g_v1/graphs/MSTuring10M_stock_off_C160_K1024_N2.graph','FINAL_C64':v.PARENT/'runs/C64/graph.bin'}
PINS={'STOCK':'6beda1aa823a49ca928e6046f411a4b6945d2eb56e125d85a50e30c8ab3deffe','FINAL_C64':v.GRAPH_PINS['C64']}
MR_AGG='6434c8f06c442cbeabc6f38415a3e84b3f5bc0818cabd1346d59bff03a7dc074'
LIMITS=['One frozen graph per arm, one clean Search invocation per arm; Stock first; timing descriptive','Matched-Recall QPS is interpolation, not exact measured QPS; no extrapolation','Historical BUILD wall 437.77 vs 357.93 s separate campaigns, not paired causal comparison','No tail latency or Counter64 from clean evaluator']
FILES=('preregister.json','native.stdout','native.stderr','native.time')
def script():return sha(Path(__file__))
def lineage():
    v.source_integrity(False)
    f=mr.OUT/'matched_recall_12g_summary.json';clean(f);pin(f,MR_AGG,'MR_AGG')
    need(load(f)['status']=='TWELVE_GRAPH_FIVE_BEAM_NATIVE_AUDIT_PASS','MR_STATUS')
def bulk():
    lineage();p.data_gate()
    for a in ARMS:clean(GRAPHS[a]);pin(GRAPHS[a],PINS[a],a)
def plan():return {'status':'PREFLIGHT_PASS_NO_SEARCH','script_sha256':script(),'vendor_sha256':sha(HERE/'vendor_calibration_v1.py'),'mr_script_sha256':sha(HERE/'r91_g6_matched_recall_12g_v1.py'),'manifest_sha256':sha(HERE/'SHA256SUMS.txt'),'mr_aggregate_sha256':MR_AGG,'graph_paths':{a:str(GRAPHS[a]) for a in ARMS},'graph_sha256':PINS,'data_sha256':{str(k):h for k,h in v.DATA_PINS.items()},'order':list(ARMS),'beams':list(BEAMS),'n_queries':100000,'gt_k':100,'cpu':'0','memory_max_bytes':v.MEMORY_MAX,'swap_max_bytes':0,'no_build':True,'limits':LIMITS}
def checkpre(expected):
    clean(OUT);pin(OUT/'preflight.json',expected,'PREFLIGHT');need(load(OUT/'preflight.json')==plan(),'PREFLIGHT_DRIFT')
def preflight():
    v.cgroup(True);v.environment_gate();clean(OUT);need(not OUT.exists(),'OUTPUT_EXISTS');bulk();OUT.mkdir(exist_ok=False);atom(OUT/'preflight.json',plan());print(TAG+'_PREFLIGHT_PASS_NO_SEARCH',sha(OUT/'preflight.json'),flush=True)
def command(a,d):return ['/usr/bin/time','-v','-o',str(d/'native.time'),'/usr/bin/taskset','-c','0',str(v.EVAL),str(GRAPHS[a]),str(v.BASE),str(v.QUERY),str(v.GT),','.join(map(str,BEAMS))]
def directory(a):return OUT/'runs'/a
def base_receipt(a,pre):return {'arm':a,'graph_sha256':PINS[a],'preflight_sha256':pre,'script_sha256':script(),'beams':list(BEAMS),'evaluator_sha256':v.DATA_PINS[v.EVAL]}
def verify(a,pre,rehash=True):
    d=directory(a);clean(d);f=d/'receipt.json';r=load(f);need(all(r[k]==val for k,val in base_receipt(a,pre).items()) and r['status']=='SEARCH_SLOT_PASS' and r['error'] is None,'RECEIPT_LINEAGE');need(p.good(r['resource']) and p.gnu_good(r['gnu_time']),'RESOURCE');need(set(r['files_sha256'])==set(FILES),'LOG_SET')
    for n,h in r['files_sha256'].items():clean(d/n);pin(d/n,h,'LOG_'+n)
    pr=load(d/'preregister.json');need(all(pr[k]==val for k,val in base_receipt(a,pre).items()) and pr['command']==command(a,d),'PREREGISTER_DRIFT');need((d/'native.stderr').stat().st_size==0 and v.timeparse(d/'native.time')==r['gnu_time'] and mr.parse((d/'native.stdout').read_text())==r['metrics'],'LOG_DRIFT')
    if rehash:pin(GRAPHS[a],PINS[a],a)
    return dict(r,receipt_sha256=sha(f))
def run(a,pre):
    scope=v.cgroup(True);v.environment_gate();checkpre(pre);bulk();d=directory(a);clean(d);need(not d.exists() and not (OUT/'summary.json').exists(),'OUTPUT_EXISTS')
    if a==ARMS[1]:verify(ARMS[0],pre)
    else:need(not directory(ARMS[1]).exists(),'ORDER_DRIFT')
    d.mkdir(parents=True,exist_ok=False);cmd=command(a,d);atom(d/'preregister.json',dict(base_receipt(a,pre),command=cmd,scope=str(scope[0]),timestamp=time.time()));print(TAG+'_START_'+a,flush=True)
    m=v.monitor(cmd,d/'native.stdout',d/'native.stderr',scope,max_seconds=10800);err=None;metrics=None;t=None
    try:
        need(p.good(m),'RESOURCE_OR_EXIT');need((d/'native.stderr').stat().st_size==0,'STDERR');t=v.timeparse(d/'native.time');need(p.gnu_good(t),'GNU_TIME');metrics=mr.parse((d/'native.stdout').read_text());pin(GRAPHS[a],PINS[a],a+'_AFTER');pin(v.EVAL,v.DATA_PINS[v.EVAL],'EVAL_AFTER')
        _,end=v.cgroup(True);orig=v.evparse(scope[1]['memory.events']);ev=v.evparse(end['memory.events']);m.update(events_delta={k:ev[k]-orig.get(k,0) for k in ev},cg_peak_bytes=int(end['memory.peak']),swap_after=int(end['memory.swap.current']));need(p.good(m),'POSTHASH_RESOURCE')
    except Exception as e:err=str(e)
    r=dict(base_receipt(a,pre),status='SEARCH_SLOT_PASS' if err is None else 'SEARCH_SLOT_HOLD_PRESERVE_OUTPUT',error=err,metrics=metrics,resource=m,gnu_time=t,files_sha256={n:sha(d/n) for n in FILES if v.regular(d/n)});atom(d/'receipt.json',r);print(TAG+'_'+r['status']+'_'+a,sha(d/'receipt.json'),flush=True);need(err is None,'SLOT_FAILED')
def summarize(slots,pre):
    comps=[]
    for t in (.99,.998):
        a,b=[mr.estimate(s['metrics'],t) for s in slots];row={'target':t,'STOCK':a,'FINAL_C64':b,'status':'PAIR_UNRESOLVED'}
        if all('estimated_qps' in z for z in (a,b)):row.update(status='PAIR_ESTIMATED_AT_TARGET',ratio_final_over_stock=b['estimated_qps']/a['estimated_qps'],delta_qps_pct=100*(b['estimated_qps']/a['estimated_qps']-1),log_qps_ratio_sensitivity=b.get('log_qps_sensitivity',b['estimated_qps'])/a.get('log_qps_sensitivity',a['estimated_qps']))
        comps.append(row)
    return {'status':'TWO_GRAPH_FIVE_BEAM_CLEAN_SEARCH_AUDIT_PASS','preflight_sha256':pre,'script_sha256':script(),'beams':list(BEAMS),'order':list(ARMS),'slots':slots,'comparisons':comps,'limits':LIMITS}
def audit(pre,readonly):
    v.cgroup(True);checkpre(pre);bulk();s=summarize([verify(a,pre) for a in ARMS],pre);f=OUT/'summary.json'
    if readonly:need(load(f)==s,'SUMMARY_DRIFT')
    else:atom(f,s)
    print(TAG+('_READONLY_AUDIT_PASS' if readonly else '_AUDIT_PASS'),sha(f),flush=True)
    for row in s['comparisons']:print(TAG+'_TARGET',json.dumps(row,sort_keys=True),flush=True)
def selftest():
    mr.selftest()
    t='R85_A1C_DYNAMIC_BEAMS count=5\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n'+''.join(f'R72_RECALL_ROW beam={b} recall={r} qps={q} avg_cmps=-1 avg_visited=500\n' for b,r,q in zip(BEAMS,[.989,.991,.9979,.9981,.9982],[900,800,340,330,320]))+'R72_RECALL_EVAL_PASS\n';m=mr.parse(t);s=summarize([{'metrics':m},{'metrics':m}],'fixture');need(all(r['ratio_final_over_stock']==1 for r in s['comparisons']),'RATIO');z=mr.parse(t.replace('recall=0.989','recall=0.9901'));need(summarize([{'metrics':z},{'metrics':m}],'fixture')['comparisons'][0]['status']=='PAIR_UNRESOLVED','NO_EXTRAP');print(TAG+'_SELFTEST_PASS_NO_NATIVE_SEARCH')
def main():
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['selftest','preflight','run','audit','readonly']);a.add_argument('--pre');a.add_argument('--arm',choices=ARMS);x=a.parse_args()
    if x.mode=='selftest':selftest();return
    if x.mode=='preflight':preflight();return
    need(x.pre and len(x.pre)==64,'PRE_SHA_REQUIRED')
    if x.mode=='run':need(x.arm in ARMS,'ARM_REQUIRED');run(x.arm,x.pre)
    else:audit(x.pre,x.mode=='readonly')
if __name__=='__main__':
    try:main()
    except Exception as e:print(TAG+'_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True);sys.exit(2)
