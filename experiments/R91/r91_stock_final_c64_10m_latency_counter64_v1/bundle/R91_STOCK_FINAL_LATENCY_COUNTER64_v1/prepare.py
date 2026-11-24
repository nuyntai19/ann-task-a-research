"""Pinned ExactGuard clone: instrument only per-query call and export after timing."""
import hashlib,json,shutil,subprocess,os
from pathlib import Path
import stock_final as sf
v=sf.v; need=sf.need; sha=sf.sha; pin=sf.pin; load=sf.load; atom=sf.atom
H=Path(__file__).resolve().parent
OUT=v.R91/'r91_stock_final_c64_10m_latency_counter64_v1'
OLD=v.EVAL.parent; SRC=OLD/(v.EVAL.name+'.cc'); CMD=OLD/'compile_command_pinned.json'
UTIL=v.ROOT/'experiments/H70/pipnn-clean-443a328/algorithms/utils'
G11=v.ROOT/'experiments/R86/g11_counter64_diagnostic_v2_0/h70_effective_utils'
BIN=OUT/'diagnostic_eval'; OVER=OUT/'utils'; NEW=OUT/'diagnostic_eval.cc'
PINS={SRC:'c851ec10cdc673eb2ef7237340c95a035656cad890f94b03df87b3595390baef',CMD:'4b73a68006ce52b3026b1b412eec95fe69cccbddb734a34d951cdc3ebbaf891b',OLD/'eval_build_receipt.json':'79373da654e102c9a115eb63bd1aca7937f1349d4a289c181bd9befd27b69f62',UTIL/'check_nn_recall.h':'d4de514eb98f058e3f9888d275b79d35f6a2e590dd98194cf7c461b5babc1e12',UTIL/'stats.h':'49f48e2b2d977607d25d07375a451bdcc263a329a45d81b7e935b83ad0298c9e',G11/'stats.h':'e9e0312893553d399329027387301fdd3f724bb99d5288c47d5dade8f5dd374a'}
def replace(s,a,b):
 need(s.count(a)==1,'PATCH_ANCHOR_'+a[:60]);return s.replace(a,b,1)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def inputs():
 for f,h in PINS.items():sf.clean(f);pin(f,h,'SOURCE_PIN')
 need(blob((UTIL/'beamSearch.h').read_bytes())=='3f377f3d1f4b844f3eb9f5a97fde04aeba2d10fc','H70_BEAM_BLOB')
 need(load(OLD/'eval_build_receipt.json')['compiled_elf_sha']==v.DATA_PINS[v.EVAL],'ELF_LINEAGE')
def patch(beam,check,src,header):
 beam=replace(beam,'#include <algorithm>','#include <algorithm>\n#include <chrono>\n#include <cstdint>\n#include <vector>')
 beam=replace(beam,'namespace parlayANN {','namespace parlayANN {\ninline std::vector<std::uint64_t> r91_latency_ns;')
 anchor='    parlay::sequence<indexType> starting_points = {starting_point};\n    parlay::parallel_for(0, Query_Points.size(), [&](size_t i) {\n      auto ngh_dist = beam_search_rerank'
 beam=replace(beam,anchor,'    parlay::sequence<indexType> starting_points = {starting_point};\n    r91_latency_ns.assign(Query_Points.size(), 0);\n    parlay::parallel_for(0, Query_Points.size(), [&](size_t i) {\n      if (Query_Points[i].id() != i) std::abort();\n      const auto r91_t0 = std::chrono::steady_clock::now();\n      auto ngh_dist = beam_search_rerank')
 anchor='      all_neighbors[i] = parlay::map(ngh_dist, [] (auto& p) {return p.first;});\n    });\n  }\n\n  return all_neighbors;\n}'
 beam=replace(beam,anchor,'      all_neighbors[i] = parlay::map(ngh_dist, [] (auto& p) {return p.first;});\n      r91_latency_ns[i] = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - r91_t0).count();\n    });\n  }\n\n  return all_neighbors;\n}')
 check=replace(check,'  query_time = t.next_time();','''  query_time = t.next_time();
  if (random || r91_latency_ns.size() != Query_Points.size()) std::abort();
  // Unquantized full precision path: traversal counter excludes k final distance recomputations.
  if (Base_Points.params.num_bytes() != Q_Base_Points.params.num_bytes() ||
      Q_Base_Points.params.num_bytes() != QQ_Base_Points.params.num_bytes()) std::abort();
  for (size_t i = 0; i < Query_Points.size(); ++i) {
    std::cout << "R91_DIAG_QUERY " << QP.beamSize << ' ' << i << ' '
              << r91_latency_ns[i] << ' ' << QueryStats.distances[i] << ' '
              << QueryStats.visited[i] << '\\n';
  }
''')
 src=replace(src,str(UTIL/'check_nn_recall.h'),str(header))
 return beam,check,src
def snapshot():
 return {str(f.relative_to(OUT)):sha(f) for f in sorted(OVER.rglob('*')) if f.is_file()} | {'diagnostic_eval.cc':sha(NEW),'diagnostic_eval':sha(BIN),'compile.argv.json':sha(OUT/'compile.argv.json')}
def prepare():
 inputs(); need(not OVER.exists() and not BIN.exists(),'PREP_OUTPUT_EXISTS')
 # The original utils directory is not modified. Full copy preserves quoted sibling includes.
 shutil.copytree(UTIL,OVER,symlinks=True)
 need(not any(f.is_symlink() for f in OVER.rglob('*')),'OVERLAY_SYMLINK')
 b,c,s=patch((UTIL/'beamSearch.h').read_text(),(UTIL/'check_nn_recall.h').read_text(),SRC.read_text(),OVER/'check_nn_recall.h')
 (OVER/'beamSearch.h').write_text(b);(OVER/'check_nn_recall.h').write_text(c);(OVER/'stats.h').write_bytes((G11/'stats.h').read_bytes());NEW.write_text(s)
 cmd=load(CMD)['argv'];need(cmd.count(str(SRC))==cmd.count(str(v.EVAL))==1,'COMPILE_ARGV');cmd=[str(NEW) if x==str(SRC) else str(BIN) if x==str(v.EVAL) else x for x in cmd]
 # Add overlay include before existing paths so all modified local headers are visible.
 cmd.insert(1,'-I'+str(OVER));atom(OUT/'compile.argv.json',cmd)
 with (OUT/'compile.stdout').open('x') as so,(OUT/'compile.stderr').open('x') as se:subprocess.run(cmd,stdout=so,stderr=se,check=True,timeout=300)
 q=subprocess.run([str(BIN)],capture_output=True,text=True,timeout=30);need(q.returncode==2 and 'Usage:' in q.stderr,'USAGE_TEST');inputs();return snapshot()
