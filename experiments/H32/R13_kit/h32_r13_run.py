#!/usr/bin/env python3
"""H32-R13: isolated compile + read-only graph-search diagnostic.
This executes NEW ANN SEARCH (Q100), but NO index BUILD or graph modifications.
It does not claim same-binary parity; it checks the aggregate source-style Recall
against H31 and fails closed before classifying missed IDs.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys
from datetime import datetime
from pathlib import Path

HEAD='a48c6a34e5f959190992aa531cc18454cfcc3dd3'
GRAPH_SPECS={
 'VAMANA': ('results/vamana_sift1m.graph','84b2935cb9f25e9ad53044099901c8c1e6cb4de059975882e8d91bca66aa5259',0.983140),
 'STOCK': ('experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_stock.graph','ce1cd7c5ae97b79972df2b30235a0844b88a6c8a983ce731ca3afca494d7095d',0.990870),
 'TOP2': ('experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_top2.graph','73646a2b5655e16939ca804c598818460152803c20f6932e6e9286acd334c5c6',0.990870),
}
class AuditError(Exception):pass
def require(x,msg):
 if not x:raise AuditError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def run(cmd,**kw):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,**kw)
 if p.returncode:raise AuditError('COMMAND_FAIL '+repr(cmd)+'\n'+p.stdout[-5000:])
 return p.stdout
def find_parlay_include(repo):
 candidates=[repo/'parlaylib/include',repo/'external/parlaylib/include',repo/'parlaylib',repo/'include',repo.parent/'parlaylib/include',repo.parent/'parlaylib',repo/'parlay/include']
 for c in candidates:
  if (c/'parlay/parallel.h').is_file():return c
 # Search locally for a header; does not download anything.
 for f in repo.rglob('parallel.h'):
  if f.parent.name=='parlay':return f.parent.parent
 raise AuditError('PARLAY_INCLUDE_NOT_FOUND: locate parlay/parallel.h in local ParlayANN dependencies')
def selftest():
 assert len(GRAPH_SPECS)==3
 assert len({v[1] for v in GRAPH_SPECS.values()})==3
 assert all(len(v[1])==64 for v in GRAPH_SPECS.values())
 assert abs(1-10/100000-.9999)<1e-12
 print('H32R13_PYTHON_SELFTEST_PASS (NO NATIVE COMPILE / NO SIFT1M CHECKED)')
def audit(root, toolkit, compile_only=False):
 root=root.expanduser().resolve(); repo=root/'src/ParlayANN'
 require(repo.is_dir() and (repo/'.git').is_dir(),'PINNED_PARLAYANN_SOURCE_NOT_FOUND')
 require(run(['git','-C',str(repo),'rev-parse','HEAD']).strip()==HEAD,'REPOSITORY_HEAD_CHANGED')
 needed=['algorithms/utils/beamSearch.h','algorithms/utils/check_nn_recall.h','algorithms/utils/euclidian_point.h','algorithms/utils/types.h','algorithms/vamana/neighbors.h']
 dirty=run(['git','-C',str(repo),'diff','--name-only','HEAD','--',*needed]);require(not dirty.strip(),'SOURCE_MODIFIED: '+dirty)
 code=(repo/'algorithms/utils/check_nn_recall.h').read_text()
 vamana=(repo/'algorithms/vamana/neighbors.h').read_text()
 require('results_with_ties' in code and '== last_dist' in code,'NATIVE_TIE_POLICY_NOT_CONFIRMED')
 require(re.search(r'res_file,\s*k,\s*false,\s*start_point',vamana),'ENTRY_NONRANDOM_NOT_CONFIRMED')
 require('start_point = 0' in vamana,'ENTRY0_NOT_CONFIRMED')
 base=root/'data/sift1m.fbin'; query=root/'data/sift1m_queries.fbin'; gt=root/'data/sift1m_gt.ibin'
 for p,n in [(base,512000008),(query,5120008),(gt,8000008)]:
  require(p.is_file() and p.stat().st_size==n,'DATA_SIZE_MISMATCH: '+str(p))
 for role,(rp,digest,_) in GRAPH_SPECS.items():
  graph=root/rp;require(graph.is_file() and sha(graph)==digest,'GRAPH_PIN_MISMATCH: '+role)
 compiler=shutil.which('g++') or shutil.which('clang++');require(compiler,'CXX_COMPILER_NOT_FOUND')
 inc=find_parlay_include(repo)
 dest=root/'experiments/H32'/('H32_R13_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
 require(dest.parent.is_dir(),'MISSING_EXPERIMENTS_H32')
 dest.mkdir()
 binary=dest/'h32_r13_native_capture'; cpp=toolkit/'h32_r13_native_capture.cpp'
 require(cpp.is_file(),'MISSING_DIAGNOSTIC_CPP')
 cmd=[compiler,'-std=c++17','-O3','-pthread','-I'+str(repo),'-I'+str(inc),str(cpp),'-o',str(binary)]
 (dest/'compile_command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 try:
  out=run(cmd)
 except AuditError as e:
  (dest/'compile_failure.txt').write_text(str(e)+'\n')
  raise AuditError(str(e)+'\nCOMPILE_LOG='+str(dest/'compile_failure.txt'))
 require(binary.is_file(),'MISSING_COMPILED_EXECUTABLE')
 binary_sha=sha(binary)
 if compile_only:
  print('H32R13_COMPILE_ONLY_PASS='+str(binary));return
 r11=sorted((root/'experiments/H32').glob('H32_R11_2*'),reverse=True)
 require(bool(r11) and (r11[0]/'h32_r11_gt_query_matrix.csv').is_file(),'R11_GT_MATRIX_NOT_FOUND')
 reachability={}
 with (r11[0]/'h32_r11_gt_query_matrix.csv').open(newline='') as f:
  for row in csv.DictReader(f):
   reachability[(row['role'],int(row['query_index']))]=set(map(int,filter(None,row['unreachable_gt_ids'].split(';'))))
 require(len(reachability)==30000,'INCOMPLETE_R11_REACHABILITY_MATRIX')
 summary=['H32-R13 | ISOLATED SOURCE-BASED NATIVE Q100 PREDICTION CAPTURE',f'ROOT={root}',f'SOURCE_GIT_HEAD={HEAD}',f'DIAGNOSTIC_BINARY_SHA256={binary_sha}', 'NO GRAPH BUILD OR INPUT MODIFICATION; NEW QUERY SEARCH PERFORMED', 'H31_BINARY_EQUIVALENCE=NOT_PROVEN; AGGREGATE_RECALL_GATE_REQUIRED', '']
 reports={};all_pass=True
 for role,(rp,digest,historical) in GRAPH_SPECS.items():
  outfile=dest/f'{role.lower()}_q100_predictions.csv'
  native=run([str(binary),str(base),str(query),str(root/rp),str(gt),str(outfile)],env={**os.environ,'PARLAY_NUM_THREADS':'1'})
  (dest/f'{role.lower()}_native_stdout.txt').write_text(native)
  m=re.search(r'H32R13_SOURCE_TIE_AWARE_RECALL=([0-9.]+)',native)
  require(m,'NATIVE_RECALL_NOT_PRINTED: '+role)
  observed=float(m.group(1)); parity=abs(observed-historical)<=0.00002
  if not parity:all_pass=False
  missed_strict=missed_reach=missed_unreach=0;strict_total=tie_total=0;affected=[]
  with outfile.open(newline='') as f:
   rows=list(csv.DictReader(f))
  require(len(rows)==10000,'WRONG_QUERY_COUNT: '+role)
  with gt.open('rb') as f:
   import mmap,struct
   with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
    require(struct.unpack_from('<II',mm,0)==(10000,100),'GT_HEADER_INVALID')
    for qi,row in enumerate(rows):
     require(int(row['query_index'])==qi,'QUERY_ORDER_MISMATCH')
     got={int(row[f'id{j}']) for j in range(10)}
     require(len(got)==10,'DUPLICATE_PREDICTION_IDS')
     gt10=set(struct.unpack_from('<10I',mm,8+qi*400))
     misses=gt10-got
     unreachable=reachability[(role,qi)]
     missed_strict+=len(misses);missed_unreach+=len(misses & unreachable);missed_reach+=len(misses-unreachable)
     strict_total+=int(row['strict_hits']);tie_total+=int(row['tie_aware_hits'])
     if misses and len(affected)<10:
      affected.append({'query':qi,'misses_total':len(misses),'misses_reachable':len(misses-unreachable),'misses_unreachable':len(misses & unreachable)})
  require(abs(tie_total/100000-observed)<1e-9,'NATIVE_TIE_SCORE_INTERNAL_MISMATCH')
  rep={'graph_sha256':digest,'observed_tie_aware_recall':observed,'H31_historical_tie_aware_recall':historical,'aggregate_recall_parity_pass':parity,'new_search_binary_sha256':binary_sha,'strict_gt10_missed':missed_strict,'strict_missed_reachable_from_entry0':missed_reach,'strict_missed_unreachable_from_entry0':missed_unreach,'strict_recall':strict_total/100000,'samples':affected}
  reports[role]=rep
  summary.extend([f'[{role}] AGGREGATE_RECALL_PARITY={"PASS" if parity else "FAIL"} native={observed:.6f} historical={historical:.6f}',f'  STRICT_GT10_MISSED={missed_strict} REACHABLE_MISSED={missed_reach} UNREACHABLE_MISSED={missed_unreach}',f'  PREDICTION_CSV={outfile}',''])
 status='PASS_SOURCE_BASED_PREDICTION_CAPTURE_WITH_AGGREGATE_GATE' if all_pass else 'HOLD_DIAGNOSTIC_AGGREGATE_RECALL_PARITY_FAILED'
 summary.insert(1,'OVERALL='+status)
 summary.extend(['NOTE: This is a NEW standalone executable reusing qsearchAll and the source tie rule, not the original H31 binary.','NOTE: Reachable misses are descriptive only; they do not establish which search decision caused them.','NOTE: Structural comparison is not equal-graph-budget, and GT exactness is not independently recomputed.','NO H33 / NO NOVELTY CLAIM',f'H32R13_DONE={dest}'])
 (dest/'h32_r13_summary.txt').write_text('\n'.join(summary)+'\n')
 (dest/'h32_r13_report.json').write_text(json.dumps({'status':status,'roles':reports,'graph_budget_equal':False,'native_binary_exact_parity':False},indent=2,ensure_ascii=False)+'\n')
 print('\n'.join(summary))
 if not all_pass:raise AuditError('RECALL_PARITY_GATE_FAILED: Results kept for audit, not accepted as replicated H31 outcomes')
def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['selftest','compile','audit'],required=True);p.add_argument('--root',default='~/ann-task-a');a=p.parse_args()
 try:
  selftest() if a.mode=='selftest' else audit(Path(a.root),Path(__file__).resolve().parent,a.mode=='compile')
 except (AuditError,ValueError,KeyError,OSError,subprocess.SubprocessError) as ex:
  print('H32R13_FAIL_CLOSED:',ex,file=sys.stderr);sys.exit(2)
if __name__=='__main__':main()
