#!/usr/bin/env python3
"""Five-beam same-invocation matched-Recall estimates; no extrapolation, no BUILD."""
import argparse,json,math,statistics,sys,time,re
from pathlib import Path
import r91_g6_10m_cross_graph_p02_p06_v1 as old
p=old.p; v=p.v
TAG='R91_G6_MATCHED_RECALL_12G_V1'
BEAMS=(512,544,1664,1728,1792)
ARMS=p.ARMS; PAIRS=p.PAIRS; ORDER=p.ORDER; NEW=PAIRS
ROOT=p.ROOT; OUT=v.R91/'r91_g6_mst10m_matched_recall_12g_v1'
AGG_SHA=p.AGG_SHA
CROSS_SHA='e8710595c6e04dd7e302a43dbccb6cdcdec6e22bfff41740ce08c0202678d676'
OLD_PRE='510cf70ca6e2b7c93ee8c31e5288ad7ce6aa00a0c737e07218f5c4fb1d2b4172'
OLD_SCRIPT='911b6bd192bfc64df2d2ee133da3379c61c7b5cf52c803e3766e702187510d23'
need=p.need; sha=p.sha; pin=p.pin; load=p.load; atom=p.atom; cleanpath=p.cleanpath
source=p.source; data_gate=p.data_gate; graph=p.graph; good=p.good; gnu_good=p.gnu_good
LIMITS=['Linear interpolation of measured QPS versus Recall within adjacent sampled beams only; not exact native matched Recall','One invocation per graph; descriptive QPS, fixed seed555, shared 100K queries','No extrapolation; missing brackets retained; no p95/p99 or formal noninferiority']
def script_sha():return sha(Path(__file__))
def parse(s):
    lines=s.splitlines()
    b=[x for x in lines if x.startswith('R85_A1C_DYNAMIC_BEAMS ')]
    need(len(b)==1 and re.search(r'\bcount=5(?:\s|$)',b[0]) is not None,'EXACT_BEAM_COUNT')
    inp=[x for x in lines if x.startswith('R72_RECALL_INPUT_PASS ')]
    need(len(inp)==1 and all(re.search(r'\b'+x+r'(?:\s|$)',inp[0]) for x in ('graph_nodes=10000000','queries=100000','gt_k=100')),'EXACT_INPUT_MARKER')
    need(len([x for x in lines if x.startswith('R72_RECALL_ROW ')])==5,'EXACT_ROW_COUNT')
    original=v.BEAMS
    try:
        v.BEAMS=BEAMS
        return v.parse_stdout(s)
    finally:v.BEAMS=original

def prior_evidence(pp):
    pin(Path(old.__file__),OLD_SCRIPT,'OLD_SCRIPT'); pin(Path(p.__file__),old.PILOT_SCRIPT,'P01_SCRIPT')
    pin(old.OUT/'preflight.json',OLD_PRE,'CROSS_PREFLIGHT'); pin(old.OUT/'cross_graph_12g_summary.json',CROSS_SHA,'CROSS_AGG')
    a=load(old.OUT/'cross_graph_12g_summary.json')
    need(a['status']=='TWELVE_GRAPH_FOUR_BEAM_NATIVE_AUDIT_PASS' and a['n_graphs']==12 and a['n_beam_points']==48 and a['aggregate_build_sha256']==AGG_SHA and a['order']==ORDER,'CROSS_LINEAGE')
    for pid in PAIRS:
        f=p.OUT/'pilot_search_summary.json' if pid=='p01' else old.pairfile(pid)
        pin(f,a['pair_summary_sha256'][pid],'OLD_PAIR_'+pid);need(load(f)==a['pairs'][pid],'OLD_PAIR_CONTENT')
        for slot in a['pairs'][pid]['slots']:
            arm=slot['arm']; d=p.slotdir(arm) if pid=='p01' else old.slotdir(pid,arm)
            pin(d/'receipt.json',slot['receipt_sha256'],'OLD_RECEIPT_'+pid+arm)
            need(slot['graph_sha256']==pp[pid]['graphs'][arm],'OLD_GRAPH_LINK')
    old.pilot_pins()
    return a

def plan(pp):
    return {'status':'PREFLIGHT_PASS_NO_SEARCH','script_sha256':script_sha(),'old_script_sha256':OLD_SCRIPT,'source_pins_sha256':p.PINS_SHA,'vendor_sha256':p.VENDOR_SHA,'aggregate_sha256':AGG_SHA,'cross_graph_sha256':CROSS_SHA,'cross_preflight_sha256':OLD_PRE,'all_12_graph_sha256':{k:pp[k]['graphs'] for k in PAIRS},'order':ORDER,'beams':list(BEAMS),'windows':{'0.99':[512,544],'0.998':[1664,1728,1792]},'n_queries':100000,'gt_k':100,'memory_max_bytes':v.MEMORY_MAX,'swap_max_bytes':0,'cpu':'0','data_sha256':{str(k):h for k,h in v.DATA_PINS.items()},'no_build':True,'limits':LIMITS}
def preflight():
    v.cgroup(True);cleanpath(OUT);need(not OUT.exists(),'OUTPUT_EXISTS');v.environment_gate();pp=source(True);data_gate();prior_evidence(pp);OUT.mkdir(exist_ok=False);atom(OUT/'preflight.json',plan(pp));print(TAG+'_PREFLIGHT_PASS_NO_SEARCH',sha(OUT/'preflight.json'),flush=True)
def checkpre(pp):
    cleanpath(OUT);prior_evidence(pp);need(load(OUT/'preflight.json')==plan(pp),'PREFLIGHT_DRIFT');return sha(OUT/'preflight.json')
def slotdir(pid,arm):return OUT/'pairs'/pid/'runs'/arm
def pairfile(pid):return OUT/'pairs'/pid/'pair_search_summary.json'
def command(pid,arm,d):return ['/usr/bin/time','-v','-o',str(d/'native.time'),'/usr/bin/taskset','-c','0',str(v.EVAL),str(graph(pid,arm)),str(v.BASE),str(v.QUERY),str(v.GT),','.join(map(str,BEAMS))]
def verify_pair(pid,pp,pre,rehash=False):
    f=pairfile(pid);cleanpath(f)
    s=pair_summary(pid,[verify_slot(pid,arm,pp,pre,rehash) for arm in ARMS],pre)
    need(load(f)==s,'PAIR_SUMMARY_DRIFT_'+pid)
    return s

def prior_chain(pid,pp,pre):
    need(pid in NEW,'INVALID_PAIR');need(not (OUT/'matched_recall_12g_summary.json').exists() and not (OUT/'matched_recall_12g_summary.json').is_symlink(),'AGGREGATE_EXISTS')
    for prev in NEW[:NEW.index(pid)]:verify_pair(prev,pp,pre,False)
    for later in NEW[NEW.index(pid)+1:]:
        d=OUT/'pairs'/later;need(not d.exists() and not d.is_symlink(),'LATER_PAIR_EXISTS_'+later)

def audit(pid,readonly=False):
    v.cgroup(True);pp=source();pre=checkpre(pp);data_gate();prior_chain(pid,pp,pre) if not readonly else None
    s=pair_summary(pid,[verify_slot(pid,a,pp,pre,True) for a in ARMS],pre);f=pairfile(pid)
    if readonly:need(load(f)==s,'PAIR_SUMMARY_DRIFT_'+pid)
    else:atom(f,s)
    print(TAG+('_READONLY_PAIR_AUDIT_PASS_' if readonly else '_PAIR_AUDIT_PASS_')+pid,sha(f),flush=True)
    for row in s['comparisons']:print(TAG+'_ROW_'+pid,json.dumps(row,sort_keys=True),flush=True)

def run(pid,arm):
    scope=v.cgroup(True);v.environment_gate();pp=source();pre=checkpre(pp);data_gate();prior_chain(pid,pp,pre);d=slotdir(pid,arm);cleanpath(d)
    need(not d.exists(),'OUTPUT_EXISTS_'+arm)
    need(not pairfile(pid).exists() and not pairfile(pid).is_symlink(),'SUMMARY_EXISTS')
    first,second=ORDER[PAIRS.index(pid)]
    if arm==second:verify_slot(pid,first,pp,pre,True)
    else:need(not slotdir(pid,second).exists() and not slotdir(pid,second).is_symlink(),'ORDER_DRIFT')
    g=graph(pid,arm);h=pp[pid]['graphs'][arm];pin(g,h,'GRAPH_BEFORE_'+arm)
    d.mkdir(parents=True,exist_ok=False);tm,so,se=[d/n for n in ('native.time','native.stdout','native.stderr')]
    cmd=command(pid,arm,d)
    atom(d/'preregister.json',{'arm':arm,'pair':pid,'command':cmd,'preflight_sha256':pre,'graph_sha256':h,'aggregate_sha256':AGG_SHA,'cross_graph_sha256':CROSS_SHA,'script_sha256':script_sha(),'scope':str(scope[0]),'timestamp':time.time()})
    print(TAG+'_START_'+pid+'_'+arm,flush=True)
    m=v.monitor(cmd,so,se,scope,max_seconds=10800);err=None;metrics=None;t=None
    try:
        need(good(m),'RESOURCE_OR_EXIT');need(se.stat().st_size==0,'STDERR_NONEMPTY');t=v.timeparse(tm);need(gnu_good(t),'GNU_TIME');metrics=parse(so.read_text());pin(g,h,'GRAPH_AFTER_'+arm);pin(v.EVAL,v.DATA_PINS[v.EVAL],'EVAL_AFTER')
        _,end=v.cgroup(True);orig=v.evparse(scope[1]['memory.events']);ev=v.evparse(end['memory.events']);m['events_delta']={k:ev[k]-orig.get(k,0) for k in ev};m['cg_peak_bytes']=int(end['memory.peak']);m['swap_after']=int(end['memory.swap.current']);need(good(m),'POSTHASH_RESOURCE')
    except Exception as ex:err=str(ex)
    receipt={'status':'SEARCH_SLOT_PASS' if err is None else 'SEARCH_SLOT_HOLD_PRESERVE_OUTPUT','arm':arm,'pair':pid,'error':err,'graph_sha256':h,'aggregate_sha256':AGG_SHA,'cross_graph_sha256':CROSS_SHA,'preflight_sha256':pre,'script_sha256':script_sha(),'beams':list(BEAMS),'metrics':metrics,'resource':m,'gnu_time':t,'files_sha256':{p.name:sha(p) for p in (tm,so,se,d/'preregister.json') if v.regular(p)}}
    atom(d/'receipt.json',receipt);print(TAG+'_'+receipt['status']+'_'+pid+'_'+arm,sha(d/'receipt.json'),flush=True);need(err is None,'SLOT_FAILED_'+arm)

def verify_slot(pid,arm,pp,pre,rehash):
    d=slotdir(pid,arm);cleanpath(d);r=load(d/'receipt.json');h=pp[pid]['graphs'][arm]
    need(r['status']=='SEARCH_SLOT_PASS' and r['error'] is None and r['arm']==arm and r['pair']==pid and r['preflight_sha256']==pre and r['script_sha256']==script_sha() and r['aggregate_sha256']==AGG_SHA and r['cross_graph_sha256']==CROSS_SHA and r['graph_sha256']==h and r['beams']==list(BEAMS),'RECEIPT_LINEAGE_'+arm)
    need(good(r['resource']) and gnu_good(r['gnu_time']),'RECEIPT_RESOURCE_'+arm)
    need(set(r['files_sha256'])=={'native.time','native.stdout','native.stderr','preregister.json'},'LOG_SET')
    for n,hsh in r['files_sha256'].items():pin(d/n,hsh,'LOG_'+arm+n)
    pr=load(d/'preregister.json');need(pr['command']==command(pid,arm,d) and pr['preflight_sha256']==pre and pr['arm']==arm and pr['pair']==pid and pr['graph_sha256']==h and pr['script_sha256']==script_sha() and pr['aggregate_sha256']==AGG_SHA and pr['cross_graph_sha256']==CROSS_SHA,'PREREGISTER_DRIFT')
    need((d/'native.stderr').stat().st_size==0 and v.timeparse(d/'native.time')==r['gnu_time'] and parse((d/'native.stdout').read_text())==r['metrics'],'LOG_READBACK')
    if rehash:pin(graph(pid,arm),h,'GRAPH_AUDIT_'+arm)
    return {'arm':arm,'graph_sha256':h,'receipt_sha256':sha(d/'receipt.json'),'metrics':r['metrics'],'resource':r['resource'],'gnu_time':r['gnu_time']}



def estimate(metrics,target):
    window=(512,544) if target==.99 else (1664,1728,1792)
    rows=[r for r in metrics if r['beam'] in window]
    need([r['beam'] for r in rows]==list(window),'WINDOW_GRID')
    result={'target':target,'window':list(window),'measured':rows}
    if any(b['recall_at10']<a['recall_at10'] for a,b in zip(rows,rows[1:])):
        return dict(result,status='NONMONOTONE_NO_ESTIMATE')
    exact=[r for r in rows if r['recall_at10']==target]
    if exact:
        a=exact[0];return dict(result,status='EXACT_SAMPLED_RECALL',estimated_qps=a['qps'],estimated_beam=a['beam'],lower=a,upper=a,fraction=0.)
    for a,b in zip(rows,rows[1:]):
        if a['recall_at10']<target<b['recall_at10']:
            f=(target-a['recall_at10'])/(b['recall_at10']-a['recall_at10'])
            return dict(result,status='LINEAR_INTERPOLATION_ESTIMATE_ONLY',lower=a,upper=b,fraction=f,estimated_qps=a['qps']+f*(b['qps']-a['qps']),estimated_beam=a['beam']+f*(b['beam']-a['beam']),log_qps_sensitivity=math.exp(math.log(a['qps'])+f*(math.log(b['qps'])-math.log(a['qps']))))
    return dict(result,status='UNBRACKETED')

def pair_summary(pid,slots,pre):
    need([z['arm'] for z in slots]==list(ARMS),'CANONICAL_ARM_ORDER')
    prior=load(old.OUT/'cross_graph_12g_summary.json')['pairs'][pid]
    anchors=[]
    for z in slots:
        oldm={r['beam']:r for r in next(a for a in prior['slots'] if a['arm']==z['arm'])['metrics']}
        for r in z['metrics']:
            if r['beam'] in oldm:
                a=oldm[r['beam']];anchors.append({'arm':z['arm'],'beam':r['beam'],'recall_delta':r['recall_at10']-a['recall_at10'],'visited_delta':r['avg_visited']-a['avg_visited'],'qps_ratio':r['qps']/a['qps']})
    comps=[]
    for target in (.99,.998):
        a,b=[estimate(z['metrics'],target) for z in slots]
        row={'target':target,'C512':a,'C64':b,'status':'PAIR_UNRESOLVED'}
        if all('estimated_qps' in z for z in (a,b)):
            row.update(status='PAIR_ESTIMATED_AT_TARGET',ratio_C64_over_C512=b['estimated_qps']/a['estimated_qps'],delta_qps_pct=100*(b['estimated_qps']/a['estimated_qps']-1),log_qps_ratio_sensitivity=b.get('log_qps_sensitivity',b['estimated_qps'])/a.get('log_qps_sensitivity',a['estimated_qps']))
        comps.append(row)
    return {'status':'TWO_GRAPH_FIVE_BEAM_NATIVE_AUDIT_PASS','pair':pid,'order':ORDER[PAIRS.index(pid)],'aggregate_sha256':AGG_SHA,'cross_graph_sha256':CROSS_SHA,'preflight_sha256':pre,'script_sha256':script_sha(),'slots':slots,'beams':list(BEAMS),'comparisons':comps,'anchor_comparison_prior_screen':anchors,'limits':LIMITS}

def aggregate(readonly=False):
    v.cgroup(True);pp=source();pre=checkpre(pp);data_gate()
    pairs={pid:verify_pair(pid,pp,pre,True) for pid in PAIRS};stats=[]
    for i,t in enumerate((.99,.998)):
        rows=[s['comparisons'][i] for s in pairs.values()];ratios=[r['ratio_C64_over_C512'] for r in rows if 'ratio_C64_over_C512' in r]
        stats.append({'target':t,'n_pairs':6,'n_resolved':len(ratios),'unresolved_pairs':[pid for pid,s in pairs.items() if s['comparisons'][i]['status']=='PAIR_UNRESOLVED'],'C64_faster_resolved':sum(r>1 for r in ratios),'geomean_ratio_resolved':math.exp(statistics.mean(map(math.log,ratios))) if ratios else None,'full_six_pair_geomean_ratio':math.exp(statistics.mean(map(math.log,ratios))) if len(ratios)==6 else None})
    r={'status':'TWELVE_GRAPH_FIVE_BEAM_NATIVE_AUDIT_PASS','n_graphs':12,'n_beam_points':60,'beams':list(BEAMS),'order':ORDER,'aggregate_build_sha256':AGG_SHA,'cross_graph_sha256':CROSS_SHA,'preflight_sha256':pre,'script_sha256':script_sha(),'pairs':pairs,'pair_summary_sha256':{pid:sha(pairfile(pid)) for pid in PAIRS},'target_stats':stats,'limits':LIMITS}
    f=OUT/'matched_recall_12g_summary.json'
    if readonly:need(load(f)==r,'AGGREGATE_DRIFT')
    else:atom(f,r)
    print(TAG+'_AGGREGATE_PASS',sha(f),flush=True)
    for row in stats:print(TAG+'_TARGET_STATS',json.dumps(row,sort_keys=True),flush=True)

def selftest():
    p.selftest();pin(Path(old.__file__),OLD_SCRIPT,'OLD_SCRIPT')
    def fixture(rs):return 'R85_A1C_DYNAMIC_BEAMS count=5\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n'+''.join(f'R72_RECALL_ROW beam={b} recall={r} qps={q} avg_cmps=-1 avg_visited=500\n' for b,r,q in zip(BEAMS,rs,[900,800,340,330,320]))+'R72_RECALL_EVAL_PASS\n'
    txt=fixture([.989,.991,.9979,.9981,.9982]);m=parse(txt)
    need(math.isclose(estimate(m,.99)['estimated_qps'],850),'INTERP_LOW');need(math.isclose(estimate(m,.998)['estimated_qps'],335),'INTERP_HIGH')
    need(estimate(parse(fixture([.9901,.991,.9979,.99799,.9981])),.99)['status']=='UNBRACKETED','NO_EXTRAP')
    need(estimate(parse(fixture([.989,.991,.9979,.99799,.9981])),.998)['lower']['beam']==1728,'UPPER_BRACKET')
    need(estimate(parse(fixture([.989,.99,.9979,.998,.9981])),.99)['status']=='EXACT_SAMPLED_RECALL','EXACT')
    need(estimate(parse(fixture([.989,.991,.9979,.9981,.998])),.998)['status']=='NONMONOTONE_NO_ESTIMATE','NONMONOTONE')
    for bad in (txt.replace('count=5','count=50'),txt.replace('queries=100000','queries=1000000'),txt.replace('qps=900','qps=nan'),txt.replace('beam=512','beam=511'),txt.replace('R72_RECALL_EVAL_PASS','NO_END')):
        try:parse(bad)
        except RuntimeError:pass
        else:need(False,'BAD_PARSER_ACCEPTED')
    print(TAG+'_SELFTEST_PASS_SYNTHETIC_ONLY_NO_SEARCH',flush=True)
def main():
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['selftest','scopecheck','preflight','run-arm','audit','readonly','aggregate','aggregate-readonly']);a.add_argument('--pair',choices=NEW);a.add_argument('--arm',choices=ARMS);x=a.parse_args()
    try:
        if x.mode=='selftest':selftest()
        elif x.mode=='scopecheck':print(TAG+'_SCOPE_PROBE_PASS_24GIB_ZERO_SWAP',v.cgroup(True)[0],flush=True)
        elif x.mode=='preflight':preflight()
        elif x.mode=='run-arm':need(x.pair in NEW and x.arm in ARMS,'PAIR_ARM_REQUIRED');run(x.pair,x.arm)
        elif x.mode in ('audit','readonly'):need(x.pair in NEW,'PAIR_REQUIRED');audit(x.pair,x.mode=='readonly')
        else:aggregate(x.mode=='aggregate-readonly')
    except Exception as e:print(TAG+'_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True);sys.exit(2)
if __name__=='__main__':main()
