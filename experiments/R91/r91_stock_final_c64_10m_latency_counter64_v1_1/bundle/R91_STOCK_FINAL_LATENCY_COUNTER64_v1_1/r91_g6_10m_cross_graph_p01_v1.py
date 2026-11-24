#!/usr/bin/env python3
"""Search-only pilot on two of 12 frozen fixed-seed repeated BUILD graphs."""
import argparse, hashlib, json, math, os, re, sys, time
from pathlib import Path
import vendor_calibration_v1 as v
TAG='R91_G6_10M_CROSS_GRAPH_P01_V1'
v.TAG=TAG
BEAMS=(544,576,1728,1792)
v.BEAMS=BEAMS
ARMS=('C512','C64')
ORDER=[['C512','C64'],['C64','C512'],['C64','C512'],['C512','C64'],['C512','C64'],['C64','C512']]
PAIRS=tuple(f'p{i:02}' for i in range(1,7))
HERE=Path(__file__).resolve().parent
ROOT=v.R91/'r91_g6_mst10m_repeat_build_6pairs_v1'
OUT=v.R91/'r91_g6_mst10m_cross_graph_12g_p01_v1'
AGG_SHA='f7c5a1612f6495a326f913cc952dac9ea022194db21286d7bf388f45b280e152'
EXT_SHA='2d20ea7bb341067d162d7dbba1cf29fb8bc9606f4e7246e768a1c5629ea5ead2'
P01_PRE='1999377c94cd71a5f1bc2cb5a11c6589645985cb033ef1b264b45d10ab1b0c93'
ELF_SHA='53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690'
CAL_SHA='92a5f9d0b4637e00b8d6c1672308a49e08dc4c83c6133641fd581aaaa60162c8'
CAL_PRE='abd26a5df6200d64b9e78f63a64bb168fe9453af738d7229d9db973708880a91'
VENDOR_SHA='29ae3db642f757bcc53e4a0ac9890469bbf4a121e9016a24d9e858df0533de7e'
PINS_SHA='42e3d915b914fde8fdd548443cf6f87d4dcbae78e5d0335916a5f192d63c2c59'
need=v.require; sha=v.sha; pin=v.pin; load=v.jload; atom=v.atom

def cleanpath(p):
    need(not any(x.is_symlink() for x in [p,*p.parents]),'SYMLINK_PATH_'+p.name)

def pins():
    pin(HERE/'vendor_calibration_v1.py',VENDOR_SHA,'VENDOR')
    pin(HERE/'source_pins.json',PINS_SHA,'PINS')
    return load(HERE/'source_pins.json')

def graph(pid,arm):return ROOT/'pairs'/pid/'arms'/arm/'graph.bin'
def source(verify_graphs=False):
    pp=pins();cleanpath(ROOT);need(ROOT.is_dir(),'BUILD_ROOT_MISSING')
    pin(ROOT/'repeat_6pair_summary.json',AGG_SHA,'AGGREGATE')
    pin(ROOT/'extension_p02_p06_preflight_v1.json',EXT_SHA,'EXT_PREFLIGHT')
    pin(ROOT/'preflight.json',P01_PRE,'BUILD_PREFLIGHT')
    agg=load(ROOT/'repeat_6pair_summary.json')
    need(agg['status']=='SIX_PAIRED_FIXED_SEED_BUILDS_AUDIT_PASS_NO_SEARCH' and agg['order']==ORDER and agg['source_elf_sha256']==ELF_SHA and agg['preflight_sha256']==EXT_SHA,'AGGREGATE_LINEAGE')
    need(set(agg['pairs'])==set(PAIRS) and agg['p01_audit_sha256']==pp['p01']['audit'],'PAIR_SET')
    for i,pid in enumerate(PAIRS):
        d=ROOT/'pairs'/pid; cleanpath(d)
        ap=d/('pilot_pair_audit.json' if pid=='p01' else 'pair_audit.json')
        pin(ap,pp[pid]['audit'],'PAIR_'+pid); a=load(ap); p=agg['pairs'][pid]
        need(p['audit_sha256']==pp[pid]['audit'] and a['order']==p['order']==ORDER[i] and a['source_receipt_sha256']==pp[pid]['receipts'],'PAIR_LINEAGE_'+pid)
        need(a['C64_minus_C512']['wall_s']==p['delta'],'PAIR_DELTA_'+pid)
        for arm in ARMS:
            m=p[arm]; g=graph(pid,arm);cleanpath(g)
            need(m==a[arm] and m['graph_full_all_vertices_audit'] and m['stage1_baseline_match']=='STAGE1_COUNTERS_MATCH_V13_REFERENCE','PAIR_METRICS_'+pid+arm)
            rp=g.parent/'receipt.json';pin(rp,pp[pid]['receipts'][arm],'BUILD_RECEIPT_'+pid+arm);r=load(rp)
            expected='PILOT_BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS' if pid=='p01' else 'BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS'
            need(r['status']==expected and r['error'] is None and r['arm']==arm and r['source_elf_sha256']==ELF_SHA and r['graph']['sha256']==m['graph_sha256']==pp[pid]['graphs'][arm],'BUILD_RECEIPT_LINK_'+pid+arm)
            need(r['graph']['full_all_vertices_audit'] and r['graph']['nodes']==10000000,'BUILD_GRAPH_AUDIT_'+pid+arm)
            need(v.regular(g),'GRAPH_MISSING_'+pid+arm)
            if verify_graphs:pin(g,pp[pid]['graphs'][arm],'GRAPH_'+pid+arm)
    v.source_integrity(False)
    cal=v.R91/'r91_g6_mst10m_matched_recall_calib_v1'
    pin(cal/'preflight.json',CAL_PRE,'CAL_PRE');pin(cal/'matched_recall_calibration_summary.json',CAL_SHA,'CAL_SUMMARY')
    return pp

def data_gate():
    for p,h in v.DATA_PINS.items():cleanpath(p);pin(p,h,'DATA_'+p.name)
    need(os.access(v.EVAL,os.X_OK),'EVAL_NOT_EXECUTABLE')

def parse(s):
    # Keep proven native parser, add exact numeric marker boundaries.
    lines=s.splitlines(); b=[x for x in lines if x.startswith('R85_A1C_DYNAMIC_BEAMS ')]
    need(len(b)==1 and re.search(r'\bcount=4(?:\s|$)',b[0]) is not None,'EXACT_BEAM_MARKER')
    inp=[x for x in lines if x.startswith('R72_RECALL_INPUT_PASS ')]
    need(len(inp)==1 and all(re.search(r'\b'+x+r'(?:\s|$)',inp[0]) for x in ('graph_nodes=10000000','queries=100000','gt_k=100')),'EXACT_INPUT_MARKER')
    need(len([x for x in lines if x.startswith('R72_RECALL_ROW ')])==4,'EXACT_ROW_COUNT')
    return v.parse_stdout(s)

def script_sha():return sha(Path(__file__))
def plan(pp):
    return {'status':'PREFLIGHT_PASS_NO_SEARCH','script_sha256':script_sha(),'vendor_sha256':VENDOR_SHA,'source_pins_sha256':PINS_SHA,'aggregate_sha256':AGG_SHA,'calibration_sha256':CAL_SHA,'all_12_graph_sha256':{k:pp[k]['graphs'] for k in PAIRS},'pilot_pair':'p01','beams':list(BEAMS),'n_queries':100000,'gt_k':100,'memory_max_bytes':v.MEMORY_MAX,'swap_max_bytes':0,'cpu':'0','pilot_order':list(ARMS),'data_sha256':{str(p):h for p,h in v.DATA_PINS.items()},'quality_floors':{'544':.99,'576':.99,'1728':.998,'1792':.998},'quality_miss_policy':'REPORT_NOT_INFRASTRUCTURE_HOLD','no_build':True}
def preflight():
    cleanpath(OUT);need(not OUT.exists(),'OUTPUT_EXISTS');v.environment_gate();pp=source(True);data_gate();OUT.mkdir(exist_ok=False);atom(OUT/'preflight.json',plan(pp));print(TAG+'_PREFLIGHT_PASS_NO_SEARCH',sha(OUT/'preflight.json'),flush=True)
def checkpre(pp):
    cleanpath(OUT);need(load(OUT/'preflight.json')==plan(pp),'PREFLIGHT_DRIFT');return sha(OUT/'preflight.json')
def command(arm,d):return ['/usr/bin/time','-v','-o',str(d/'native.time'),'/usr/bin/taskset','-c','0',str(v.EVAL),str(graph('p01',arm)),str(v.BASE),str(v.QUERY),str(v.GT),','.join(map(str,BEAMS))]
def slotdir(arm):return OUT/'runs'/arm

def good(m):
    return v.resources_good(m) and {'max','oom','oom_kill','oom_group_kill','high'}.issubset(m['events_delta']) and all(x==0 for x in m['events_delta'].values())

def gnu_good(g):return g['exit_status']=='0' and g['swaps']==0 and g['max_rss_kib']>0 and g['major_faults']>=0 and g['file_system_inputs']>=0

def run(arm):
    scope=v.cgroup(True);v.environment_gate();pp=source();pre=checkpre(pp);data_gate();d=slotdir(arm);cleanpath(d)
    need(not d.exists(),'OUTPUT_EXISTS_'+arm)
    need(not (OUT/'pilot_search_summary.json').exists(),'SUMMARY_EXISTS')
    if arm=='C64':verify_slot('C512',pp,pre,True)
    else:need(not slotdir('C64').exists(),'ORDER_DRIFT')
    g=graph('p01',arm);h=pp['p01']['graphs'][arm];pin(g,h,'GRAPH_BEFORE_'+arm)
    d.mkdir(parents=True,exist_ok=False);tm,so,se=[d/n for n in ('native.time','native.stdout','native.stderr')]
    cmd=command(arm,d)
    atom(d/'preregister.json',{'arm':arm,'pair':'p01','command':cmd,'preflight_sha256':pre,'graph_sha256':h,'aggregate_sha256':AGG_SHA,'script_sha256':script_sha(),'scope':str(scope[0]),'timestamp':time.time()})
    print(TAG+'_START_'+arm,flush=True)
    m=v.monitor(cmd,so,se,scope,max_seconds=10800);err=None;metrics=None;t=None
    try:
        need(good(m),'RESOURCE_OR_EXIT');need(se.stat().st_size==0,'STDERR_NONEMPTY');t=v.timeparse(tm);need(gnu_good(t),'GNU_TIME');metrics=parse(so.read_text());pin(g,h,'GRAPH_AFTER_'+arm);pin(v.EVAL,v.DATA_PINS[v.EVAL],'EVAL_AFTER')
        _,end=v.cgroup(True);orig=v.evparse(scope[1]['memory.events']);ev=v.evparse(end['memory.events']);m['events_delta']={k:ev[k]-orig.get(k,0) for k in ev};m['cg_peak_bytes']=int(end['memory.peak']);m['swap_after']=int(end['memory.swap.current']);need(good(m),'POSTHASH_RESOURCE')
    except Exception as ex:err=str(ex)
    receipt={'status':'SEARCH_SLOT_PASS' if err is None else 'SEARCH_SLOT_HOLD_PRESERVE_OUTPUT','arm':arm,'pair':'p01','error':err,'graph_sha256':h,'aggregate_sha256':AGG_SHA,'preflight_sha256':pre,'script_sha256':script_sha(),'beams':list(BEAMS),'metrics':metrics,'resource':m,'gnu_time':t,'files_sha256':{p.name:sha(p) for p in (tm,so,se,d/'preregister.json') if v.regular(p)}}
    atom(d/'receipt.json',receipt);print(TAG+'_'+receipt['status']+'_'+arm,sha(d/'receipt.json'),flush=True);need(err is None,'SLOT_FAILED_'+arm)

def verify_slot(arm,pp,pre,rehash):
    d=slotdir(arm);cleanpath(d);r=load(d/'receipt.json');h=pp['p01']['graphs'][arm]
    need(r['status']=='SEARCH_SLOT_PASS' and r['error'] is None and r['arm']==arm and r['pair']=='p01' and r['preflight_sha256']==pre and r['script_sha256']==script_sha() and r['aggregate_sha256']==AGG_SHA and r['graph_sha256']==h and r['beams']==list(BEAMS),'RECEIPT_LINEAGE_'+arm)
    need(good(r['resource']) and gnu_good(r['gnu_time']),'RECEIPT_RESOURCE_'+arm)
    need(set(r['files_sha256'])=={'native.time','native.stdout','native.stderr','preregister.json'},'LOG_SET')
    for n,hsh in r['files_sha256'].items():pin(d/n,hsh,'LOG_'+arm+n)
    pr=load(d/'preregister.json');need(pr['command']==command(arm,d) and pr['preflight_sha256']==pre and pr['arm']==arm and pr['graph_sha256']==h and pr['script_sha256']==script_sha() and pr['aggregate_sha256']==AGG_SHA,'PREREGISTER_DRIFT')
    need((d/'native.stderr').stat().st_size==0 and v.timeparse(d/'native.time')==r['gnu_time'] and parse((d/'native.stdout').read_text())==r['metrics'],'LOG_READBACK')
    if rehash:pin(graph('p01',arm),h,'GRAPH_AUDIT_'+arm)
    return {'arm':arm,'graph_sha256':h,'receipt_sha256':sha(d/'receipt.json'),'metrics':r['metrics'],'resource':r['resource'],'gnu_time':r['gnu_time']}

def summarize(slots,pre):
    x,y=[z['metrics'] for z in slots];rows=[]
    for a,b in zip(x,y):
        beam=a['beam'];need(beam==b['beam'],'GRID_MISMATCH');floor=.99 if beam<1000 else .998
        rows.append({'beam':beam,'target_recall':floor,'C512_floor_pass':a['recall_at10']>=floor,'C64_floor_pass':b['recall_at10']>=floor,'delta_recall_C64_minus_C512':b['recall_at10']-a['recall_at10'],'delta_qps_pct':100*(b['qps']/a['qps']-1),'delta_avg_visited':b['avg_visited']-a['avg_visited']})
    return {'status':'P01_NATIVE_TWO_GRAPH_FOUR_BEAM_AUDIT_PASS','aggregate_sha256':AGG_SHA,'preflight_sha256':pre,'script_sha256':script_sha(),'pilot_pair':'p01','slots':slots,'beams':list(BEAMS),'rows':rows,'quality_all_floors_pass':all(z[a+'_floor_pass'] for z in rows for a in ARMS),'remaining_graphs_not_run':10,'limits':['Same beam is not exact matched Recall','Quality floor misses are valid measurements, not infrastructure failure','No p95/p99, no formal noninferiority, no multi-seed claim','One native invocation per graph; timing descriptive']}
def audit(readonly=False):
    pp=source();pre=checkpre(pp);data_gate();slots=[verify_slot(a,pp,pre,True) for a in ARMS];s=summarize(slots,pre);f=OUT/'pilot_search_summary.json'
    if readonly:need(load(f)==s,'SUMMARY_DRIFT')
    else:atom(f,s)
    print(TAG+('_READONLY_AUDIT_PASS' if readonly else '_PILOT_AUDIT_PASS'),sha(f),flush=True)
    for r in s['rows']:print(TAG+'_ROW',json.dumps(r,sort_keys=True),flush=True)

def selftest():
    pp=pins();need(len(pp)==6 and len({h for p in pp.values() for h in p['graphs'].values()})==12,'PIN_COUNT')
    txt='R85_A1C_DYNAMIC_BEAMS count=4\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n'+''.join(f'R72_RECALL_ROW beam={b} recall={r} qps=300 avg_cmps=-1 avg_visited=500\n' for b,r in zip(BEAMS,[.989,.991,.9979,.9981]))+'R72_RECALL_EVAL_PASS\n'
    m=parse(txt);need(len(m)==4,'PARSE')
    for bad in [txt.replace('count=4','count=40'),txt.replace('queries=100000','queries=1000000'),txt.replace('beam=1792','beam=1793'),txt.replace('qps=300','qps=nan'),txt.replace('R72_RECALL_EVAL_PASS','NO_END')]:
        try:parse(bad)
        except RuntimeError:pass
        else:need(False,'BAD_PARSER_ACCEPTED')
    s=summarize([{'metrics':m},{'metrics':m}],'fixture');need(not s['quality_all_floors_pass'] and s['rows'][0]['C64_floor_pass']==False and s['rows'][3]['C64_floor_pass']==True,'FLOOR_REPORT')
    clean={'status':'COMPLETED','exit_code':0,'sampled_peak_swap':0,'swap_after':0,'cg_peak_bytes':8*1024**3,'min_available_kib':4*1024**2,'min_disk_gib':100,'events_delta':{k:0 for k in ('max','oom','oom_kill','oom_group_kill','high')}}
    need(good(clean),'RESOURCE_GOOD');need(not good({**clean,'swap_after':1}) and not good({**clean,'events_delta':{}}),'RESOURCE_MUTATION')
    print(TAG+'_SELFTEST_PASS_12_GRAPH_PINS_4_BEAMS_PARSER_RESOURCE_QUALITY_REPORT',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['selftest','scopecheck','preflight','run-arm','audit','readonly']);p.add_argument('--arm',choices=ARMS);a=p.parse_args()
    try:
        if a.mode=='selftest':selftest()
        elif a.mode=='scopecheck':print(TAG+'_SCOPE_PROBE_PASS_24GIB_ZERO_SWAP',v.cgroup(True)[0],flush=True)
        elif a.mode=='preflight':preflight()
        elif a.mode=='run-arm':need(a.arm in ARMS,'ARM_REQUIRED');run(a.arm)
        else:audit(a.mode=='readonly')
    except Exception as e:print(TAG+'_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True);sys.exit(2)
if __name__=='__main__':main()
