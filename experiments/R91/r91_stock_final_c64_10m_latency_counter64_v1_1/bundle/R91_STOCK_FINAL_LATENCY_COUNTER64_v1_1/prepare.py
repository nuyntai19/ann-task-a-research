"""Pinned ExactGuard clone: instrument only per-query call and export after timing."""
import hashlib,json,shutil,subprocess,os
from pathlib import Path
import stock_final as sf
v=sf.v; need=sf.need; sha=sf.sha; pin=sf.pin; load=sf.load; atom=sf.atom
H=Path(__file__).resolve().parent
OUT=v.R91/'r91_stock_final_c64_10m_latency_counter64_v1_1'
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
# v1.1: remap only the four retired include roots and the static archive paths.
V1=v.R91/'r91_stock_final_c64_10m_latency_counter64_v1'
V1_PINS={
 'compile.stderr':'ccd6a2dcad44721d076151f0bc7b1dd494ad05cdcd56793927a5519298f9cfdc',
 'compile.stdout':'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'compile.argv.json':'6a337d1fbf2fd1858223f501375f74e3ec702239fac3fb09aebbb44ac0ec0df4',
 'diagnostic_eval.cc':'b4b5d6ccde954000b9bd4c8bd8482a7823dea738e33f0f0f4afedd5defcc1c9b',
 'utils/beamSearch.h':'3e67bdf251eaab7cefea88bc52fe28000ba8b8a4292aed1bd37e75b9a029850c',
 'utils/check_nn_recall.h':'ccd1b76b73c483d7bbc8b77d00f2dd1376558d60327a922f7be1effd299f5de3',
 'utils/stats.h':'e9e0312893553d399329027387301fdd3f724bb99d5288c47d5dade8f5dd374a',
}
OLD_DEPS=v.ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps'
SRC_DEPS=v.ROOT/'src/PiPNN/build/_deps'
G6_BUILD=v.R91/'r91_g6_d2_leader_cap_v1/build'
LIB_DEPS=G6_BUILD/'_deps'
CACHE=G6_BUILD/'CMakeCache.txt'
ROOTS={'parlaylib':(SRC_DEPS/'parlaylib-src','51017699dcc4'),
       'eigen':(SRC_DEPS/'eigen-src','3147391d946b'),
       'abseil':(SRC_DEPS/'abseil-cpp-src','bc257a88f7c1'),
       'highway':(v.ROOT/'vendor_pinned/highway-6bc2d477','6bc2d477')}
INCLUDES={str(OLD_DEPS/'parlaylib-src/include'):str(ROOTS['parlaylib'][0]/'include'),
          str(OLD_DEPS/'eigen-src'):str(ROOTS['eigen'][0]),
          str(OLD_DEPS/'abseil-cpp-src'):str(ROOTS['abseil'][0]),
          str(OLD_DEPS/'highway-src'):str(ROOTS['highway'][0])}
HEADERS=[ROOTS['parlaylib'][0]/'include/parlay/parallel.h',ROOTS['parlaylib'][0]/'include/parlay/primitives.h',
         ROOTS['eigen'][0]/'Eigen/Dense',ROOTS['abseil'][0]/'absl/container/flat_hash_set.h',ROOTS['highway'][0]/'hwy/highway.h']
def remap(cmd):
    result=[]; inc=[]; libs=[]; prefix=str(OLD_DEPS)+'/'
    for a in cmd:
        if a.startswith('-I') and a[2:] in INCLUDES:
            inc.append(a[2:]);result.append('-I'+INCLUDES[a[2:]])
        elif a.startswith(prefix) and a.endswith('.a'):
            b=str(LIB_DEPS/a[len(prefix):]);libs.append(b);result.append(b)
        else:
            need(str(OLD_DEPS) not in a,'UNKNOWN_RETIRED_ARG '+a);result.append(a)
    need(len(inc)==4 and set(inc)==set(INCLUDES),'REMAP_INCLUDE_COUNT')
    need(len(libs)==44 and all(a.startswith(str(LIB_DEPS)+'/') for a in libs),'REMAP_LIBRARY_COUNT')
    return result,libs

def original_hold():
    for f,h in V1_PINS.items():pin(V1/f,h,'V1_HOLD_'+f)
    for f in ('diagnostic_eval','preflight.json','runs','summary.json'):
        need(not (V1/f).exists() and not (V1/f).is_symlink(),'V1_HOLD_STATE_DRIFT '+f)

def git_identity(root,prefix):
    # A vendored source export may lack its own Git metadata. Never mistake the
    # enclosing project repository for the dependency's commit.
    def run(*args):
        return subprocess.run(['git','--no-optional-locks','-C',str(root),*args],capture_output=True,text=True,timeout=30)
    top=run('rev-parse','--show-toplevel')
    if top.returncode or Path(top.stdout.strip()).resolve()!=root.resolve():
        return {'expected_prefix':prefix,'head':None,'status':'NO_INDEPENDENT_GIT_METADATA'}
    head=run('rev-parse','HEAD');need(head.returncode==0 and head.stdout.strip().startswith(prefix),'DEPENDENCY_REVISION '+str(root))
    status=run('status','--porcelain','--untracked-files=no');need(status.returncode==0 and not status.stdout.strip(),'DEPENDENCY_TRACKED_CHANGES '+str(root))
    return {'expected_prefix':prefix,'head':head.stdout.strip(),'status':'GIT_PREFIX_MATCH_TRACKED_CLEAN'}

def dependency_snapshot(cmd):
    # All path resolutions come from the selected G6 build cache, not from a search/fallback.
    mapped,libs=remap(cmd)
    cache={}
    for line in CACHE.read_text().splitlines():
        if line.startswith('FETCHCONTENT_SOURCE_DIR_') and '=' in line:
            k,val=line.split('=',1);cache[k.split(':',1)[0]]=val
    paths={str(Path(z).resolve()) for z in cache.values() if z and Path(z).is_absolute()}
    for name,(root,rev) in ROOTS.items():
        need(root.is_dir() and str(root.resolve()) in paths,'G6_CACHE_SOURCE_MISMATCH '+name)
    for a in mapped:
        if a.startswith('-I'):need(Path(a[2:]).is_dir(),'INCLUDE_MISSING '+a)
    # Preserve order and repetitions in the argv. Hash unique archives once.
    archive_hashes={f:sha(Path(f)) for f in dict.fromkeys(libs)}
    for f in archive_hashes:
        with open(f,'rb') as stream:need(stream.read(8)==b'!<arch>\n','NOT_STATIC_ARCHIVE '+f)
    return {'scheme':'R91_G6_OPTION_A','cache_path':str(CACHE),'cache_sha256':sha(CACHE),
            'fetchcontent_source_dirs':cache,'include_remap':INCLUDES,
            'dependency_git':{k:git_identity(*z) for k,z in ROOTS.items()},
            'header_sha256':{str(f):sha(f) for f in HEADERS},
            'archive_entries':len(libs),'archive_unique_count':len(archive_hashes),
            'archive_order':libs,'archive_sha256':archive_hashes,
            'compiler_sha256':sha(Path(cmd[0]).resolve()),
            'provenance_limit':'G6 cache and host hashes recorded; original R86 libraries removed; no claim of identical old ELF or identical dependency bytes.'}

def remap_selftest():
    libs=[str(OLD_DEPS/'highway-build/libhwy.a')]*44
    original=['/usr/bin/c++',*['-I'+x for x in INCLUDES],'-O3',*libs,'-lrt']
    result,order=remap(original)
    need(result[0]==original[0] and result[5]=='-O3' and result[-1]=='-lrt' and len(order)==44,'REMAP_FIXTURE')
    need(all(x==str(LIB_DEPS/'highway-build/libhwy.a') for x in order),'REMAP_ORDER')
    for bad in (original[:-2]+['-lrt'],original+['-I'+str(OLD_DEPS/'unknown')],original[:1]+original[2:]):
        try:remap(bad)
        except RuntimeError:continue
        raise RuntimeError('REMAP_BAD_FIXTURE_ACCEPTED')
    print('R91_LATENCY_V1_1_REMAP_SELFTEST_PASS',flush=True)

def snapshot():
 original_hold(); receipt=OUT/'dependency_receipt.json';need(load(receipt)==dependency_snapshot(load(CMD)['argv']),'DEPENDENCY_DRIFT')
 return {str(f.relative_to(OUT)):sha(f) for f in sorted(OVER.rglob('*')) if f.is_file()} | {'diagnostic_eval.cc':sha(NEW),'diagnostic_eval':sha(BIN),'compile.argv.json':sha(OUT/'compile.argv.json'),'dependency_receipt.json':sha(receipt),'compile.stdout':sha(OUT/'compile.stdout'),'compile.stderr':sha(OUT/'compile.stderr')}
def prepare():
 inputs(); original_hold(); deps=dependency_snapshot(load(CMD)['argv']); need(not OVER.exists() and not BIN.exists(),'PREP_OUTPUT_EXISTS')
 # The original utils directory is not modified. Full copy preserves quoted sibling includes.
 shutil.copytree(UTIL,OVER,symlinks=True)
 need(not any(f.is_symlink() for f in OVER.rglob('*')),'OVERLAY_SYMLINK')
 b,c,s=patch((UTIL/'beamSearch.h').read_text(),(UTIL/'check_nn_recall.h').read_text(),SRC.read_text(),OVER/'check_nn_recall.h')
 (OVER/'beamSearch.h').write_text(b);(OVER/'check_nn_recall.h').write_text(c);(OVER/'stats.h').write_bytes((G11/'stats.h').read_bytes());NEW.write_text(s)
 for f in ('beamSearch.h','check_nn_recall.h','stats.h'):pin(OVER/f,V1_PINS['utils/'+f],'UNCHANGED_INSTRUMENTATION_'+f)
 need(s.replace(str(OVER/'check_nn_recall.h'),str(V1/'utils/check_nn_recall.h'))==(V1/'diagnostic_eval.cc').read_text(),'UNCHANGED_DIAGNOSTIC_SOURCE')
 cmd=load(CMD)['argv'];need(cmd.count(str(SRC))==cmd.count(str(v.EVAL))==1,'COMPILE_ARGV');cmd=[str(NEW) if x==str(SRC) else str(BIN) if x==str(v.EVAL) else x for x in cmd]
 # Add overlay include before existing paths so all modified local headers are visible.
 cmd,libs=remap(cmd);cmd.insert(1,'-I'+str(OVER));atom(OUT/'compile.argv.json',cmd);atom(OUT/'dependency_receipt.json',deps)
 print('R91_LATENCY_V1_1_DEPENDENCY_REMAP_PASS_4_INCLUDES_44_ARCHIVE_ENTRIES',flush=True)
 with (OUT/'compile.stdout').open('x') as so,(OUT/'compile.stderr').open('x') as se:rc=subprocess.run(cmd,stdout=so,stderr=se,timeout=300).returncode
 if rc:
  print((OUT/'compile.stderr').read_text(errors='replace')[-12000:],flush=True)
  raise RuntimeError('DIAGNOSTIC_COMPILE_EXIT_'+str(rc))
 q=subprocess.run([str(BIN)],capture_output=True,text=True,timeout=30);need(q.returncode==2 and 'Usage:' in q.stderr,'USAGE_TEST');inputs();return snapshot()
