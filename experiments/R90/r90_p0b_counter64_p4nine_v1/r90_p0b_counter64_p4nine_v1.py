#!/usr/bin/env python3
"""R90 P0-B: Counter64 diagnostic on the nine FROZEN P4 MS-Turing1M graphs.

No graph BUILD, no source patch, no compiling, no modification to frozen inputs.
Requires existing G11 diagnostic binary from previously validated parity campaign.
Stages: selftest, preflight, run, audit. Only beams 368,880. Timing is DIAGNOSTIC
and MUST NOT be substituted for the OFF/P4R timing benchmark.
"""
from __future__ import annotations
import hashlib, json, os, re, statistics, subprocess, sys, argparse
from pathlib import Path

HOME=Path.home(); ROOT=HOME/'ann-task-a'
BASE=ROOT/'data/MSTuring_1M_v1/base.1M.fbin'
QUERY=ROOT/'data/MSTuring_1M_v1/query.public.100K.fbin'
GT=ROOT/'data/MSTuring_1M_v1/groundtruth.public.100K.ibin'
P4=ROOT/'experiments/R90/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'
P4M=ROOT/'experiments/R90/r90_p4m_mst1m_matched_recall_100kq_v1_1'
G11=ROOT/'experiments/R86/g11_counter64_diagnostic_v2_0'
ELF=G11/'msturing_1m_eval/r86_msturing1m_graph_recall_v4_diag_counter64'
G11_MANIFEST=G11/'diagnostic_manifest.json'
OUTPUT=ROOT/'experiments/R90/r90_p0b_counter64_p4nine_v1'
EVAL_ORIGINAL_SHA='bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144'
EVAL_DIAG_SHA='a98b8748b92787e6ccbf52556a8eef2c24bff4580c6275c9fa464dd82af4d3a4'
P4M_SUMMARY_SHA='8f7286a415fcd2465449110a0ef53b43402e6b6976e2adc20517cd15a8d8f3b2'
DATA_SHA={
 'base':'44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042',
 'query':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt':'fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344'}
SCRIPT_SHA=None
ARMS=('stock','h17','fast'); BEAMS=(368,880)
PAT=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([\deE.+-]+)\s+qps=([\deE.+-]+)\s+avg_cmps=([\deE.+-]+)\s+avg_visited=([\deE.+-]+)\s*$',re.M)
TAG='R90_P0B_COUNTER64_V1'

def hold(s): raise RuntimeError(TAG+'_HOLD_'+str(s))
def need(v,s):
 if not v:hold(s)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as fp:
  for buf in iter(lambda:fp.read(4*1024*1024),b''): h.update(buf)
 return h.hexdigest()
def read(path):
 need(Path(path).is_file() and not Path(path).is_symlink(),'FILE_MISSING_OR_SYMLINK_'+str(path))
 return json.loads(Path(path).read_text())
def pin(path,expected,label):
 need(Path(path).is_file() and not Path(path).is_symlink(),'MISSING_'+label)
 need(sha(path)==expected,'SHA_'+label)
def atomic_json(path,obj):
 path=Path(path);need(not path.exists() and not path.is_symlink(),'OUTPUT_EXISTS_'+path.name)
 temp=path.with_suffix(path.suffix+'.part'); need(not temp.exists() and not temp.is_symlink(),'TEMP_EXISTS_'+path.name)
 with temp.open('x') as f:
  json.dump(obj,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 temp.replace(path)
def parse(text):
 need('R72_RECALL_EVAL_PASS' in text and 'R72_RECALL_INPUT_PASS' in text,'EVALUATOR_MARKERS')
 rows={}
 for beam,recall,qps,cmps,visited in PAT.findall(text):
  b=int(beam);need(b in BEAMS and b not in rows,'BAD_BEAM')
  row={'beam':b,'recall_at10':float(recall),'qps_diagnostic_not_for_timing':float(qps),'avg_cmps_counter64':float(cmps),'avg_visited':float(visited)}
  need(0<=row['recall_at10']<=1 and 0<row['avg_cmps_counter64']<1e7 and 0<row['avg_visited']<10000,'BAD_METRIC')
  rows[str(b)]=row
 need(set(rows)==set(map(str,BEAMS)),'MISSING_BEAM')
 return rows

def source_state(full_hash=True):
 pin(ELF,EVAL_DIAG_SHA,'G11_DIAGNOSTIC_ELF')
 diag=read(G11_MANIFEST)
 need(diag['diagnostic_binary_sha256']==EVAL_DIAG_SHA and diag['original_v4_sha256']==EVAL_ORIGINAL_SHA,'G11_MANIFEST')
 pin(G11/'h70_effective_utils/stats.h',diag['diagnostic_stats_sha256'],'G11_DIAG_STATS')
 pin(G11/'msturing_1m_eval/r86_msturing1m_graph_recall_v4_diag_counter64.cc',diag['diagnostic_evaluator_sha256'],'G11_DIAG_SRC')
 pin(P4M/'full_matched_summary.json',P4M_SUMMARY_SHA,'P4M_FULL_SUMMARY')
 summary=read(P4M/'full_matched_summary.json')
 need(summary['status']=='BRACKETED_QUALITY_FLOORS_ON_TESTED_GRID','P4M_STATUS')
 source=read(P4M/'full_manifest.json')
 need(source['status']=='FULL_9_GRAPH_COMPLETE' and len(source['searches'])==9,'P4M_MANIFEST_STATUS')
 p4=read(P4/'build_manifest.json')
 need(len(p4['runs'])==9,'P4_RUNS')
 source_ids={(r['arm'],r['rep']):r for r in source['searches']}
 p4_ids={(r['arm'],r['rep']):r for r in p4['runs']}
 expected={(a,r) for a in ARMS for r in (1,2,3)}
 need(set(source_ids)==set(p4_ids)==expected,'NINE_GRAPH_KEYSET')
 if full_hash:
  for p,k in [(BASE,'base'),(QUERY,'query'),(GT,'gt')]:pin(p,DATA_SHA[k],'DATA_'+k)
 for key in sorted(expected):
  item=source_ids[key]; br=p4_ids[key]
  need(item['graph_sha']==br['graph_sha'] and item['graph']==br['graph'],'GRAPH_MANIFEST_'+str(key))
  need(item['nqueries']==100000 and item['threads']==1,'P4M_QUERY_PROTOCOL_'+str(key))
  if full_hash:pin(Path(item['graph']),item['graph_sha'],'P4_GRAPH_'+str(key))
  for beam,target in [(368,.99),(880,.998)]:
   rr=item['rows'][str(beam)];need(rr['recall_at10']>=target,'P4M_BRACKET_'+str(key))
 return {'p4m':source_ids,'p4':p4_ids}

def compare(rows,source,key):
 for beam in BEAMS:
  got=rows[str(beam)];orig=source[key]['rows'][str(beam)]
  need(abs(got['recall_at10']-orig['recall_at10'])<=5e-5,'RECALL_PARITY_'+str(key)+'_'+str(beam))
  need(abs(got['avg_visited']-orig['avg_visited'])<=1e-6,'VISITED_PARITY_'+str(key)+'_'+str(beam))
  need(got['avg_cmps_counter64']<1000000,'COUNTER64_PLAUSIBILITY_'+str(key))

def selftest():
 s='R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=100\n'
 s+='R72_RECALL_ROW beam=368 recall=0.99042 qps=1250 avg_cmps=16181 avg_visited=357\n'
 s+='R72_RECALL_ROW beam=880 recall=0.99808 qps=550 avg_cmps=30218 avg_visited=731\nR72_RECALL_EVAL_PASS\n'
 need(len(parse(s))==2,'SELFTEST_POSITIVE')
 for t in [s.replace('beam=880','beam=368'),s.replace('R72_RECALL_EVAL_PASS',''),s.replace('30218','4294954990')]:
  try:parse(t)
  except RuntimeError:pass
  else:hold('SELFTEST_NEGATIVE')
 print(TAG+'_SELFTEST_PASS_PARSER_COUNTER64_GUARDS')

def preflight():
 state=source_state(full_hash=True)
 need(not OUTPUT.exists() and not OUTPUT.is_symlink(),'OUTPUT_ALREADY_EXISTS')
 need(os.path.isfile('/usr/bin/taskset') or os.path.isfile('/bin/taskset'),'TASKSET_MISSING')
 print(TAG+'_PREFLIGHT_PASS_9_SHA_GRAPHS_ORIGINAL_P4M_G11_COUNTER64_ELF_2_BEAMS')
 return state

def run():
 need(not OUTPUT.exists() and not OUTPUT.is_symlink(),'OUT_EXISTS_RUN_MUST_START_CLEAN')
 state=preflight();OUTPUT.mkdir(parents=True,exist_ok=False)
 (OUTPUT/'logs').mkdir()
 jobs=[]
 # pilot on original stock rep1 validates parity before continuing across arms
 for arm,rep in [('stock',1)]+[(a,r) for r in (1,2,3) for a in ARMS if (a,r)!=('stock',1)]:
  key=(arm,rep);graph=Path(state['p4m'][key]['graph'])
  cmd=['taskset','-c','0',str(ELF),str(graph),str(BASE),str(QUERY),str(GT),'368,880']
  tag=f'{arm}_r{rep}'
  print(TAG+'_START',tag,'beams',list(BEAMS),flush=True)
  proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
    env={**os.environ,'PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},check=False)
  need(proc.returncode==0,'EVALUATOR_EXIT_'+tag+'_'+str(proc.returncode))
  rows=parse(proc.stdout);compare(rows,state['p4m'],key)
  stdout=OUTPUT/'logs'/f'{tag}.stdout';stderr=OUTPUT/'logs'/f'{tag}.stderr'
  with stdout.open('x') as f:f.write(proc.stdout)
  with stderr.open('x') as f:f.write(proc.stderr)
  entry={'arm':arm,'rep':rep,'graph_sha':state['p4m'][key]['graph_sha'],'stdout':str(stdout),'stdout_sha256':sha(stdout),
   'stderr':str(stderr),'stderr_sha256':sha(stderr),'command':cmd,'rows':rows,'status':'COUNTER64_RECALL_VISITED_PARITY_PASS'}
  jobs.append(entry)
  atomic_json(OUTPUT/f'{tag}.json',entry)
  print(TAG+'_PASS',tag,'cmps368',rows['368']['avg_cmps_counter64'],'cmps880',rows['880']['avg_cmps_counter64'],flush=True)
 atomic_json(OUTPUT/'full_results.json',{'protocol':'MS-Turing1M_P4_9GRAPH_COUNTER64_B368_B880_100KQ','diagnostic_elf_sha':EVAL_DIAG_SHA,
 'not_performance_timing':True,'status':'SEARCH_9_GRAPH_NATIVE_COMPLETE_AUDIT_REQUIRED','jobs':jobs})
 print(TAG+'_RUN_9_OF_9_COMPLETE_AUDIT_REQUIRED')

def audit():
 state=source_state(full_hash=True)
 result=read(OUTPUT/'full_results.json')
 need(result['status']=='SEARCH_9_GRAPH_NATIVE_COMPLETE_AUDIT_REQUIRED' and len(result['jobs'])==9,'RESULT_STATUS')
 unique=set()
 for job in result['jobs']:
  key=(job['arm'],job['rep']);need(key not in unique,'DUPLICATE');unique.add(key)
  need(job['graph_sha']==state['p4m'][key]['graph_sha'],'GRAPH_SHA_'+str(key))
  for k in ['stdout','stderr']:
   path=Path(job[k]); need(path.parent==OUTPUT/'logs' and path.is_file() and sha(path)==job[k+'_sha256'],'LOG_SHA_'+str(key))
  rows=parse(Path(job['stdout']).read_text());need(rows==job['rows'],'REPARSE_DRIFT_'+str(key));compare(rows,state['p4m'],key)
 need(unique=={(a,r) for a in ARMS for r in (1,2,3)},'KEYSET')
 measures=[]
 for arm in ARMS:
  for beam in BEAMS:
   vals=[j['rows'][str(beam)]['avg_cmps_counter64'] for j in result['jobs'] if j['arm']==arm]
   measures.append({'arm':arm,'beam':beam,'avg_cmps_per_graph':vals,'mean_avg_cmps':statistics.mean(vals),
    'source':'G11 valid 64-bit accumulator; diagnostic only'})
 obj={'status':'AUDIT_PASS_9_GRAPH_COUNTER64_RECALL_VISITED_PARITY','results_sha256':sha(OUTPUT/'full_results.json'),
 'no_build':True,'no_performance_timing':True,'measurements':measures,'diagnostic_elf_sha256':EVAL_DIAG_SHA}
 atomic_json(OUTPUT/'summary.json',obj)
 print(TAG+'_AUDIT_PASS_9_GRAPH_COUNTER64_100KQ_2BEAMS')
 print(TAG+'_REPORT',OUTPUT/'summary.json','sha256',sha(OUTPUT/'summary.json'))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['selftest','preflight','run','audit']);args=ap.parse_args()
 try:
  {'selftest':selftest,'preflight':preflight,'run':run,'audit':audit}[args.phase]()
 except Exception as e:
  print(TAG+'_ERROR',str(e),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
