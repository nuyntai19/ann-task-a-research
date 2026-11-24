#!/usr/bin/env python3
"""Search-only extension, reuses immutable native P01 code and vendor calibration."""
import argparse, json, math, os, statistics, sys, time
from pathlib import Path
import r91_g6_10m_cross_graph_p01_v1 as p
v=p.v
TAG='R91_G6_10M_CROSS_GRAPH_P02_P06_V1'
BEAMS=p.BEAMS; ARMS=p.ARMS; ORDER=p.ORDER; PAIRS=p.PAIRS; NEW=PAIRS[1:]
ROOT=p.ROOT; OUT=v.R91/'r91_g6_mst10m_cross_graph_12g_p02_p06_v1'
AGG_SHA=p.AGG_SHA
PILOT_PRE='89d4dc926a6347c5d9bde7ef43f1d563c18135aa0b7c4fa109f365bed543903a'
PILOT_SUM='048b1682402fbb3bde136cf7f51b29bf85e63c4d1eae60f856dde236276c8acd'
PILOT_SCRIPT='61f7b860a9d806a45a628dd4288913bc842dd8b47bea98b9dfe673ae04ba0411'
PILOT_RECEIPTS={'C512':'b3245acd9469af682ef2ee2fb219bb3e2de2dcfbe8ce9bed3d31fea297364f26','C64':'fa0a34e23b58be36a199c49132e637fb23b186f30385bb541a16ede482146d67'}
need=p.need; sha=p.sha; pin=p.pin; load=p.load; atom=p.atom; cleanpath=p.cleanpath
source=p.source; data_gate=p.data_gate; parse=p.parse; graph=p.graph; good=p.good; gnu_good=p.gnu_good

def script_sha():return sha(Path(__file__))
def slotdir(pid,arm):return OUT/'pairs'/pid/'runs'/arm
def pairfile(pid):return OUT/'pairs'/pid/'pair_search_summary.json'
def command(pid,arm,d):return ['/usr/bin/time','-v','-o',str(d/'native.time'),'/usr/bin/taskset','-c','0',str(v.EVAL),str(graph(pid,arm)),str(v.BASE),str(v.QUERY),str(v.GT),','.join(map(str,BEAMS))]
def pilot_pins():
    pin(Path(p.__file__),PILOT_SCRIPT,'PILOT_SCRIPT');cleanpath(p.OUT)
    pin(p.OUT/'preflight.json',PILOT_PRE,'PILOT_PREFLIGHT');pin(p.OUT/'pilot_search_summary.json',PILOT_SUM,'PILOT_SUMMARY')
    for arm,h in PILOT_RECEIPTS.items():pin(p.slotdir(arm)/'receipt.json',h,'PILOT_SEARCH_RECEIPT_'+arm)
    s=load(p.OUT/'pilot_search_summary.json')
    need(s['status']=='P01_NATIVE_TWO_GRAPH_FOUR_BEAM_AUDIT_PASS' and s['preflight_sha256']==PILOT_PRE and s['aggregate_sha256']==AGG_SHA,'PILOT_LINEAGE')
    return s

def plan(pp):
    return {'status':'PREFLIGHT_PASS_NO_SEARCH','script_sha256':script_sha(),'pilot_script_sha256':PILOT_SCRIPT,'pilot_preflight_sha256':PILOT_PRE,'pilot_summary_sha256':PILOT_SUM,'pilot_receipt_sha256':PILOT_RECEIPTS,'vendor_sha256':p.VENDOR_SHA,'source_pins_sha256':p.PINS_SHA,'aggregate_sha256':AGG_SHA,'all_12_graph_sha256':{k:pp[k]['graphs'] for k in PAIRS},'order':ORDER,'pairs_to_run':list(NEW),'beams':list(BEAMS),'n_queries':100000,'gt_k':100,'memory_max_bytes':v.MEMORY_MAX,'swap_max_bytes':0,'cpu':'0','data_sha256':{str(k):h for k,h in v.DATA_PINS.items()},'quality_floors':{'544':.99,'576':.99,'1728':.998,'1792':.998},'quality_miss_policy':'REPORT_NOT_INFRASTRUCTURE_HOLD','no_build':True}
def preflight():
    v.cgroup(True);cleanpath(OUT);need(not OUT.exists(),'OUTPUT_EXISTS');v.environment_gate();pp=source(True);data_gate();pilot_pins();p.audit(True);OUT.mkdir(exist_ok=False);atom(OUT/'preflight.json',plan(pp));print(TAG+'_PREFLIGHT_PASS_NO_SEARCH',sha(OUT/'preflight.json'),flush=True)
def checkpre(pp):
    cleanpath(OUT);pilot_pins();need(load(OUT/'preflight.json')==plan(pp),'PREFLIGHT_DRIFT');return sha(OUT/'preflight.json')

def pair_summary(pid,slots,pre):
    need([x['arm'] for x in slots]==list(ARMS),'CANONICAL_ARM_ORDER')
    r=p.summarize(slots,pre)
    return {'status':'TWO_GRAPH_FOUR_BEAM_AUDIT_PASS','pair':pid,'order':ORDER[PAIRS.index(pid)],'aggregate_sha256':AGG_SHA,'preflight_sha256':pre,'pilot_summary_sha256':PILOT_SUM,'script_sha256':script_sha(),'slots':slots,'beams':list(BEAMS),'rows':r['rows'],'quality_all_floors_pass':r['quality_all_floors_pass'],'limits':r['limits']}
def verify_pair(pid,pp,pre,rehash=False):
    f=pairfile(pid);cleanpath(f)
    s=pair_summary(pid,[verify_slot(pid,arm,pp,pre,rehash) for arm in ARMS],pre)
    need(load(f)==s,'PAIR_SUMMARY_DRIFT_'+pid)
    return s

def prior_chain(pid,pp,pre):
    need(pid in NEW,'INVALID_PAIR');need(not (OUT/'cross_graph_12g_summary.json').exists() and not (OUT/'cross_graph_12g_summary.json').is_symlink(),'AGGREGATE_EXISTS')
    for prev in NEW[:NEW.index(pid)]:verify_pair(prev,pp,pre,False)
    for later in NEW[NEW.index(pid)+1:]:
        d=OUT/'pairs'/later;need(not d.exists() and not d.is_symlink(),'LATER_PAIR_EXISTS_'+later)

def audit(pid,readonly=False):
    v.cgroup(True);pp=source();pre=checkpre(pp);data_gate();prior_chain(pid,pp,pre) if not readonly else None
    s=pair_summary(pid,[verify_slot(pid,a,pp,pre,True) for a in ARMS],pre);f=pairfile(pid)
    if readonly:need(load(f)==s,'PAIR_SUMMARY_DRIFT_'+pid)
    else:atom(f,s)
    print(TAG+('_READONLY_PAIR_AUDIT_PASS_' if readonly else '_PAIR_AUDIT_PASS_')+pid,sha(f),flush=True)
    for row in s['rows']:print(TAG+'_ROW_'+pid,json.dumps(row,sort_keys=True),flush=True)

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
    atom(d/'preregister.json',{'arm':arm,'pair':pid,'command':cmd,'preflight_sha256':pre,'graph_sha256':h,'aggregate_sha256':AGG_SHA,'script_sha256':script_sha(),'scope':str(scope[0]),'timestamp':time.time()})
    print(TAG+'_START_'+pid+'_'+arm,flush=True)
    m=v.monitor(cmd,so,se,scope,max_seconds=10800);err=None;metrics=None;t=None
    try:
        need(good(m),'RESOURCE_OR_EXIT');need(se.stat().st_size==0,'STDERR_NONEMPTY');t=v.timeparse(tm);need(gnu_good(t),'GNU_TIME');metrics=parse(so.read_text());pin(g,h,'GRAPH_AFTER_'+arm);pin(v.EVAL,v.DATA_PINS[v.EVAL],'EVAL_AFTER')
        _,end=v.cgroup(True);orig=v.evparse(scope[1]['memory.events']);ev=v.evparse(end['memory.events']);m['events_delta']={k:ev[k]-orig.get(k,0) for k in ev};m['cg_peak_bytes']=int(end['memory.peak']);m['swap_after']=int(end['memory.swap.current']);need(good(m),'POSTHASH_RESOURCE')
    except Exception as ex:err=str(ex)
    receipt={'status':'SEARCH_SLOT_PASS' if err is None else 'SEARCH_SLOT_HOLD_PRESERVE_OUTPUT','arm':arm,'pair':pid,'error':err,'graph_sha256':h,'aggregate_sha256':AGG_SHA,'preflight_sha256':pre,'script_sha256':script_sha(),'beams':list(BEAMS),'metrics':metrics,'resource':m,'gnu_time':t,'files_sha256':{p.name:sha(p) for p in (tm,so,se,d/'preregister.json') if v.regular(p)}}
    atom(d/'receipt.json',receipt);print(TAG+'_'+receipt['status']+'_'+pid+'_'+arm,sha(d/'receipt.json'),flush=True);need(err is None,'SLOT_FAILED_'+arm)

def verify_slot(pid,arm,pp,pre,rehash):
    d=slotdir(pid,arm);cleanpath(d);r=load(d/'receipt.json');h=pp[pid]['graphs'][arm]
    need(r['status']=='SEARCH_SLOT_PASS' and r['error'] is None and r['arm']==arm and r['pair']==pid and r['preflight_sha256']==pre and r['script_sha256']==script_sha() and r['aggregate_sha256']==AGG_SHA and r['graph_sha256']==h and r['beams']==list(BEAMS),'RECEIPT_LINEAGE_'+arm)
    need(good(r['resource']) and gnu_good(r['gnu_time']),'RECEIPT_RESOURCE_'+arm)
    need(set(r['files_sha256'])=={'native.time','native.stdout','native.stderr','preregister.json'},'LOG_SET')
    for n,hsh in r['files_sha256'].items():pin(d/n,hsh,'LOG_'+arm+n)
    pr=load(d/'preregister.json');need(pr['command']==command(pid,arm,d) and pr['preflight_sha256']==pre and pr['arm']==arm and pr['pair']==pid and pr['graph_sha256']==h and pr['script_sha256']==script_sha() and pr['aggregate_sha256']==AGG_SHA,'PREREGISTER_DRIFT')
    need((d/'native.stderr').stat().st_size==0 and v.timeparse(d/'native.time')==r['gnu_time'] and parse((d/'native.stdout').read_text())==r['metrics'],'LOG_READBACK')
    if rehash:pin(graph(pid,arm),h,'GRAPH_AUDIT_'+arm)
    return {'arm':arm,'graph_sha256':h,'receipt_sha256':sha(d/'receipt.json'),'metrics':r['metrics'],'resource':r['resource'],'gnu_time':r['gnu_time']}


def stats(summaries):
    need(list(summaries)==list(PAIRS),'AGG_PAIR_ORDER');result=[]
    for i,beam in enumerate(BEAMS):
        floor=.99 if beam<1000 else .998; aa={a:[] for a in ARMS}; dd=[];qq=[];vv=[]
        for pid,s in summaries.items():
            need([z['arm'] for z in s['slots']]==list(ARMS),'AGG_ARM_ORDER')
            x,y=[z['metrics'][i] for z in s['slots']];need(x['beam']==y['beam']==beam,'AGG_GRID')
            aa['C512'].append(x);aa['C64'].append(y);dd.append(y['recall_at10']-x['recall_at10']);qq.append(y['qps']/x['qps']);vv.append(y['avg_visited']-x['avg_visited'])
        desc={}
        for arm,rows in aa.items():
            rs=[r['recall_at10'] for r in rows];qs=[r['qps'] for r in rows]
            desc[arm]={'floor_pass_count':sum(r>=floor for r in rs),'recall_min':min(rs),'recall_max':max(rs),'recall_median':statistics.median(rs),'recall_sample_sd':statistics.stdev(rs),'qps_median':statistics.median(qs),'qps_min':min(qs),'qps_max':max(qs)}
        result.append({'beam':beam,'target_recall':floor,'arms':desc,'paired_delta_recall_min':min(dd),'paired_delta_recall_max':max(dd),'paired_delta_recall_median':statistics.median(dd),'paired_qps_geomean_C64_over_C512':math.exp(statistics.mean(map(math.log,qq))),'C64_qps_higher_pairs':sum(q>1 for q in qq),'C64_recall_higher_pairs':sum(d>0 for d in dd),'paired_delta_avg_visited_median':statistics.median(vv)})
    return result

def aggregate(readonly=False):
    v.cgroup(True);pp=source();pre=checkpre(pp);data_gate();p.audit(True);summaries={'p01':pilot_pins()}
    for pid in NEW:summaries[pid]=verify_pair(pid,pp,pre,True)
    r={'status':'TWELVE_GRAPH_FOUR_BEAM_NATIVE_AUDIT_PASS','n_graphs':12,'n_beam_points':48,'order':ORDER,'beams':list(BEAMS),'aggregate_build_sha256':AGG_SHA,'pilot_summary_sha256':PILOT_SUM,'extension_preflight_sha256':pre,'script_sha256':script_sha(),'pair_summary_sha256':{'p01':PILOT_SUM,**{pid:sha(pairfile(pid)) for pid in NEW}},'pairs':summaries,'beam_stats':stats(summaries),'limits':['One invocation per graph; descriptive QPS only','Fixed seed555 repeated BUILD graphs, not independent seeds','Same beam is not exact matched Recall','Quality misses retained; no formal noninferiority or p95/p99']}
    f=OUT/'cross_graph_12g_summary.json'
    if readonly:need(load(f)==r,'AGGREGATE_DRIFT')
    else:atom(f,r)
    print(TAG+'_TWELVE_GRAPH_AGGREGATE_PASS',sha(f),flush=True)
    for row in r['beam_stats']:print(TAG+'_BEAM_STATS',json.dumps(row,sort_keys=True),flush=True)

def selftest():
    pin(Path(p.__file__),PILOT_SCRIPT,'PILOT_SCRIPT');p.selftest();need(ORDER==[['C512','C64'],['C64','C512'],['C64','C512'],['C512','C64'],['C512','C64'],['C64','C512']],'ORDER')
    ss={}
    for pid in PAIRS:
        slots=[]
        for arm in ARMS:
            slots.append({'arm':arm,'metrics':[{'beam':b,'recall_at10':(.989 if b<1000 else .997) if arm=='C512' else (.991 if b<1000 else .999),'qps':300 if arm=='C512' else 303,'avg_visited':500 if arm=='C512' else 495} for b in BEAMS]})
        ss[pid]=pair_summary(pid,slots,'fixture')
    for row in stats(ss):need(row['arms']['C512']['floor_pass_count']==0 and row['arms']['C64']['floor_pass_count']==6 and row['C64_qps_higher_pairs']==6 and math.isclose(row['paired_qps_geomean_C64_over_C512'],1.01),'SYNTHETIC_STATS')
    need(not ss['p02']['quality_all_floors_pass'],'FLOOR_MISS_RETAINED')
    print(TAG+'_SELFTEST_PASS_SYNTHETIC_ONLY_NO_NATIVE_SEARCH',flush=True)

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
