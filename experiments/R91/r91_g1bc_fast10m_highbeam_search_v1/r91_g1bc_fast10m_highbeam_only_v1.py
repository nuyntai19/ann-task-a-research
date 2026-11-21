#!/usr/bin/env python3
"""R91 G1B-C v1: FROZEN G1 Fast v2 graph 10M, SEARCH ONLY at beams 1792/2048.

Fresh isolated versioned paths. Never builds/edits ANN graphs, R90/R86 sources,
previous G1B receipts, or originals. Guarded preflight -> run -> audit.
"""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
ROOT = HOME/'ann-task-a'
R91 = ROOT/'experiments/R91'
NAME = 'R91_G1BC_FAST10M_HIGHBEAM_SEARCH_ONLY_V1'
BEAMS = (1792, 2048)
CAP = 24 * 1024**3
PREF = R91/'r91_g1bc_fast10m_highbeam_preflight_v1'
OUT = R91/'r91_g1bc_fast10m_highbeam_search_v1'
OLD = R91/'r91_g1b_v2_mst10m_fast_fixedbeam_search_v1_1'/'quality_screen_summary.json'
V2PRE = R91/'r91_g1b_v2_mst10m_fast_preflight_v1_1'/'r91_g1b_v2_preflight.json'
COMPILE = R91/'r91_g1b_v2_native_eval_mst10m_exactguard_v1_1'/'eval_build_receipt.json'
EVALDIR = COMPILE.parent
G1 = R91/'r91_g1_one_fastv2_flat_c160_mst10m_24g_v1'/'r91_g1_single10m_result.json'
GRAPH = G1.parent/'graphs'/'MSTuring10M_fast_off_C160_K1024_N2.graph'
DATA = ROOT/'data/MSTuring_10M_v1'
BASE = DATA/'base.10M.fbin'
QUERY = DATA/'query.public.100K.fbin'
GT = DATA/'groundtruth.public.100K.ibin'
SHAS = {
 'old': '960295996dc176dc6d1bb5074ff0543e96f43cba06907b5142c44be8949a44eb',
 'pre': 'ec040c05b3984c81cab38aeae85145d19391833a27ad4a0eb1f186d3f77b2b7c',
 'receipt': '79373da654e102c9a115eb63bd1aca7937f1349d4a289c181bd9befd27b69f62',
 'g1': 'bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835',
 'graph': '4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429',
 'elf': '394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9',
 'base': 'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700',
 'query': '48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt': '77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2',
}
FILES = {'old':OLD,'pre':V2PRE,'receipt':COMPILE,'g1':G1,'graph':GRAPH,
         'base':BASE,'query':QUERY,'gt':GT}
ROW = re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([^ ]+) qps=([^ ]+) avg_cmps=([^ ]+) avg_visited=([^ ]+)\s*$')
INPUT_PASS = 'R72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100'

def hold(s):
    raise RuntimeError(NAME+'_HOLD_'+s)

def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024), b''):h.update(b)
    return h.hexdigest()

def safe_file(p:Path)->None:
    if p.is_symlink() or not p.is_file():hold('MISSING_OR_SYMLINK_'+p.name)

def jsonfile(p:Path):
    safe_file(p)
    with p.open('r',encoding='utf-8') as f:return json.load(f)

def find_elf()->Path:
    if not EVALDIR.is_dir() or EVALDIR.is_symlink():hold('EVALDIR_NOT_PRESENT')
    hits=[]
    for p in EVALDIR.rglob('*'):
        if (p.is_file() and not p.is_symlink() and os.access(p,os.X_OK)
                and p.stat().st_size<100*1024*1024 and sha(p)==SHAS['elf']):
            hits.append(p)
    if len(hits)!=1:hold('EXPECTED_ONE_PINNED_ELF_FOUND_'+str(len(hits)))
    return hits[0]

def check_headers():
    import struct
    for p,n,d,s in ((BASE,10000000,100,4000000008), (QUERY,100000,100,40000008),
                    (GT,100000,100,80000008)):
        with p.open('rb') as f:hdr=f.read(8)
        if len(hdr)!=8:hold('BAD_HEADER_'+p.name)
        x,y=struct.unpack('<II',hdr)
        if (x,y)!=(n,d) or p.stat().st_size!=s:hold('WRONG_HEADER_OR_LENGTH_'+p.name)
    if GRAPH.stat().st_size!=2202769196:hold('GRAPH_BYTES_CHANGED')

def read_references(full_sha=True):
    for k,p in FILES.items():
        safe_file(p)
        if full_sha and sha(p)!=SHAS[k]:hold('SHA_MISMATCH_'+k)
    check_headers()
    a=jsonfile(OLD); b=jsonfile(V2PRE); c=jsonfile(COMPILE); d=jsonfile(G1)
    if a.get('status')!='R91_G1B_V2_10M_SEARCH_NATIVE_FIXEDBEAM_PASS' or a.get('evaluator_exit_code')!=0:hold('OLD_NOT_PASS')
    if a.get('source_graph_sha256')!=SHAS['graph'] or a.get('eval_binary_sha256')!=SHAS['elf']:hold('OLD_IDENTITY')
    if a.get('metrics',{}).get('1536',{}).get('meets_recall_0_998') is not False:hold('OLD_0998_ALREADY_PASS_DIFFERENT_PLAN')
    if b.get('status')!='R91_G1B_V2_PINNED_10M_NEW_ELF_PREFLIGHT_PASS_NO_SEARCH':hold('PREF_STATUS')
    if b.get('eval_bin_sha256')!=SHAS['elf'] or b.get('validated',{}).get('graph',{}).get('sha256')!=SHAS['graph']:hold('PREF_IDENTITY')
    if c.get('status')!='R91_G1B_V2_EVAL_COMPILE_PASS' or c.get('compiled_elf_sha')!=SHAS['elf'] or c.get('compile_exit')!=0:hold('ELF_COMPILE')
    if d.get('status')!='NATIVE_1_OF_1_10M_BUILD_AND_FULL_GRAPH_STRUCTURE_PASS_NO_SWAP' or d.get('graph_quality',{}).get('sha256')!=SHAS['graph']:hold('G1_IDENTITY')
    elf=find_elf()
    return elf

def cgroup_stats():
    p=Path('/proc/self/cgroup')
    rows=p.read_text().splitlines()
    unified=[line.split('::',1)[1] for line in rows if line.startswith('0::')]
    if len(unified)!=1:hold('NO_UNIFIED_CGROUP')
    cg=Path('/sys/fs/cgroup')/unified[0].lstrip('/')
    return cg

def verify_scope():
    cg=cgroup_stats()
    mem=(cg/'memory.max').read_text().strip()
    swap=(cg/'memory.swap.max').read_text().strip()
    if mem!=str(CAP) or swap!='0':hold('HARD_CGROUP_GUARD_NOT_ACTIVE')
    return cg

def events(cg):
    r={}
    for l in (cg/'memory.events').read_text().splitlines():
        k,v=l.split();r[k]=int(v)
    return r

def capture_scope_test():
    if shutil.which('systemd-run') is None:hold('SYSTEMD_RUN_MISSING')
    cmd=['systemd-run','--user','--scope','--collect','-p','MemoryAccounting=yes',
         '-p',f'MemoryMax={CAP}','-p','MemorySwapMax=0',sys.executable,
         str(Path(__file__).resolve()),'scope-check']
    x=subprocess.run(cmd,capture_output=True,text=True)
    if x.returncode!=0 or NAME+'_CGROUP_HARD24G_NOSWAP_PASS' not in x.stdout:
        hold('SCOPE_TEST_FAILED_rc'+str(x.returncode)+'_'+(x.stdout+x.stderr)[-500:])

def preflight():
    if PREF.exists() or PREF.is_symlink() or OUT.exists() or OUT.is_symlink():hold('OUTPUT_EXISTS_NO_OVERWRITE')
    elf=read_references(True)
    if shutil.disk_usage(R91).free < 8*1024**3:hold('FREE_DISK_LT8G')
    capture_scope_test()
    PREF.mkdir(parents=False,exist_ok=False)
    x={'status':NAME+'_PREFLIGHT_PASS_NO_SEARCH_NO_BUILD','beam_grid':list(BEAMS),
       'graph_sha256':SHAS['graph'],'new_eval_elf_sha256':SHAS['elf'],
       'eval_path':str(elf),'all_source_shas':SHAS,'hardcap_bytes':CAP,'swapmax_bytes':0,
       'nqueries':100000,'timestamp':time.time(),'no_ann_build':True}
    (PREF/'preflight.json').write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
    print(NAME+'_PREFLIGHT_PASS_NO_BUILD',sha(PREF/'preflight.json'))

def parse(stdout:str):
    if INPUT_PASS not in stdout or 'R72_RECALL_EVAL_PASS' not in stdout:
        hold('NATIVE_OUTPUT_MARKERS')
    r={}
    for line in stdout.splitlines():
        m=ROW.fullmatch(line.strip())
        if m:
            b=int(m.group(1)); recall=float(m.group(2));qps=float(m.group(3));v=float(m.group(5))
            if b not in BEAMS or b in r or not all(math.isfinite(z) for z in (recall,qps,v)):
                hold('INVALID_NATIVE_ROW')
            if not 0<=recall<=1 or not qps>0 or not v>=0:hold('INVALID_METRICS')
            r[b]={'recall_at10':recall,'qps':qps,'avg_visited':v,
                  'latency_inverse_qps_us_NOT_P95':1000000/qps,
                  'meets_0_99':recall>=.99,'meets_0_998':recall>=.998,
                  'avg_cmps_legacy_untrusted':None}
    if set(r)!=set(BEAMS):hold('NOT_EXACTLY_TWO_ROWS')
    return r

def in_scope():
    if OUT.is_symlink() or not OUT.is_dir() or not (OUT/'RUN_REQUEST').is_file():hold('RUN_REQUEST_MISSING')
    cg=verify_scope()
    # Recheck SHA-pinned evaluator and graph right before native execution.
    elf=read_references(full_sha=True)
    log=OUT/'logs';log.mkdir(exist_ok=False)
    before=events(cg); swap_before=int((cg/'memory.swap.current').read_text());
    cmd=['/usr/bin/time','-v','-o',str(log/'native_highbeam.time'),
         'taskset','-c','0',str(elf),str(GRAPH),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
    with (log/'native_highbeam.stdout').open('xb') as so,(log/'native_highbeam.stderr').open('xb') as se:
        process=subprocess.run(cmd,stdout=so,stderr=se,env={**os.environ,'PARLAY_NUM_THREADS':'1'})
    after=events(cg)
    swap_after=int((cg/'memory.swap.current').read_text())
    peak=int((cg/'memory.peak').read_text())
    outbytes=(log/'native_highbeam.stdout').read_bytes()
    try:
        parsed=parse(outbytes.decode('utf-8','replace')) if process.returncode==0 else {}
        error=None
    except Exception as exc:
        parsed={};error=str(exc)
    delta={k:after.get(k,0)-before.get(k,0) for k in set(before)|set(after)}
    good=(process.returncode==0 and not error and delta.get('oom',0)==0 and
          delta.get('oom_kill',0)==0 and swap_after==0 and swap_before==0)
    x={'status':NAME+'_NATIVE_SEARCH_PASS' if good else NAME+'_HOLD_PRESERVE_LOGS',
       'error':error, 'native_exit_code':process.returncode, 'metrics':parsed,
       'graph_sha256':SHAS['graph'],'elf_sha256':SHAS['elf'],'no_ann_build':True,
       'nqueries':100000,'beam_grid':BEAMS,'cpu_core':0,
       'cgroup_peak_bytes':peak,'cgroup_events_delta':delta,'cgroup_swap_before':swap_before,
       'cgroup_swap_after':swap_after,'stdout_sha256':sha(log/'native_highbeam.stdout'),
       'stderr_sha256':sha(log/'native_highbeam.stderr'),
       'time_sha256':sha(log/'native_highbeam.time'),
       'preflight_sha256':sha(PREF/'preflight.json'),'timestamp':time.time()}
    (OUT/'quality_screen_summary.json').write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
    print(NAME+'_RESULT',x['status'],'exit',process.returncode,'summary_sha256',sha(OUT/'quality_screen_summary.json'))
    if not good:hold('NATIVE_HOLD_PRESERVE_LOGS')

def run():
    if OUT.exists() or OUT.is_symlink():hold('OLD_RUN_EXISTS_NO_OVERWRITE')
    pref=jsonfile(PREF/'preflight.json')
    if pref.get('status')!=NAME+'_PREFLIGHT_PASS_NO_SEARCH_NO_BUILD' or pref.get('beam_grid')!=list(BEAMS) or pref.get('graph_sha256')!=SHAS['graph']:hold('PRECHECK_RECEIPT')
    read_references(full_sha=True)
    if shutil.disk_usage(R91).free<8*1024**3:hold('FREE_DISK_LT8G')
    OUT.mkdir(exist_ok=False)
    (OUT/'RUN_REQUEST').write_text(NAME+' beams='+','.join(map(str,BEAMS))+'\n')
    cmd=['systemd-run','--user','--scope','--collect','-p','MemoryAccounting=yes',
         '-p',f'MemoryMax={CAP}','-p','MemorySwapMax=0',sys.executable,
         str(Path(__file__).resolve()),'inscope']
    x=subprocess.run(cmd)
    if x.returncode:hold('SCOPE_OR_NATIVE_FAILURE_PRESERVE_ORIGINAL_OUTPUT_rc'+str(x.returncode))
    print(NAME+'_SEARCH_SCOPE_EXIT0__CALL_AUDIT')

def audit():
    s=jsonfile(OUT/'quality_screen_summary.json')
    if s.get('status')!=NAME+'_NATIVE_SEARCH_PASS':hold('NOT_PASS')
    l=OUT/'logs'
    for p,k in [('native_highbeam.stdout','stdout_sha256'),('native_highbeam.stderr','stderr_sha256'),('native_highbeam.time','time_sha256')]:
        if sha(l/p)!=s[k]:hold('LOG_HASH_CHANGED_'+p)
    if s['preflight_sha256']!=sha(PREF/'preflight.json'):hold('PREF_CHANGED')
    p=parse((l/'native_highbeam.stdout').read_text(errors='replace'))
    if p!={int(k):v for k,v in s['metrics'].items()}:hold('SUMMARY_METRICS_MISMATCH')
    if sha(GRAPH)!=SHAS['graph'] or s['graph_sha256']!=SHAS['graph']:hold('GRAPH_CHANGED')
    print(NAME+'_FINAL_READONLY_AUDIT_PASS',sha(OUT/'quality_screen_summary.json'))
    for b in BEAMS:print('BEAM',b,'RECALL',p[b]['recall_at10'],'QPS',p[b]['qps'],'REACH0998',p[b]['meets_0_998'])

def selftest():
    synthetic=(INPUT_PASS+'\n'+
      'R72_RECALL_ROW beam=1792 recall=0.99800001 qps=300.00000000 avg_cmps=0 avg_visited=950\n'+
      'R72_RECALL_ROW beam=2048 recall=0.99850000 qps=270.00000000 avg_cmps=0 avg_visited=1020\n'+
      'R72_RECALL_EVAL_PASS\n')
    assert parse(synthetic)[1792]['meets_0_998']
    assert not parse(synthetic.replace('0.99800001','0.99799999'))[1792]['meets_0_998']
    try:parse(synthetic.replace('beam=2048','beam=1792'))
    except RuntimeError:pass
    else:raise AssertionError('duplicated beams accepted')
    print(NAME+'_SELFTEST_PASS_NATIVE_OUTPUT_AND_STRICT_RECALL_FLOOR')

if __name__=='__main__':
    try:
        if len(sys.argv)!=2 or sys.argv[1] not in ('selftest','scope-check','preflight','run','inscope','audit'):
            hold('USAGE_selftest_preflight_run_audit')
        x=sys.argv[1]
        if x=='selftest':selftest()
        elif x=='scope-check':verify_scope();print(NAME+'_CGROUP_HARD24G_NOSWAP_PASS')
        elif x=='preflight':preflight()
        elif x=='run':run()
        elif x=='inscope':in_scope()
        else:audit()
    except Exception as e:
        print('R91_G1BC_ERROR',repr(e),file=sys.stderr)
        sys.exit(2)
