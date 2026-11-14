#!/usr/bin/env python3
"""R57 read-only source-extracted LSHGraph direct method call on the *pinned* PiPNN graph.h.

Calls the original class and merge_neighbors method verbatim after extracting them
from the exact source blob. Only external Abseil mutex/span and Parlay parallel_for
are replaced by single-thread scaffolding. It is NOT the full linked PiPNN binary.
No source edits, no graph BUILD, no SIFT1M SEARCH or data changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

EXPECTED_SHA1 = '7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f'
SOURCE_DEFAULT = 'src/PiPNN/algorithms/utils/graph.h'
OUTPUT_DEFAULT = 'experiments/H57/r57_lshgraph_direct_class.json'
BEGIN = re.compile(r'template\s*<\s*typename\s+indexType\s*,\s*typename\s+distanceType\s*>\s*struct\s+LSHCandidate\s*\{')
END = re.compile(r'\}\s*//\s*end namespace')
MARKERS = [
    'struct LSHGraph', 'void merge_neighbors(', 'Eigen::bfloat16 norm;',
    'H.relative_hash(i, pid)', 'if (old > dist)',
    'if (deg == kMaxDegree && dist >= max_val) break;',
]

PRELUDE = r'''#include <Eigen/Core>
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <mutex>
#include <new>
#include <stdexcept>
#include <sys/mman.h>
#include <utility>
#include <vector>
#include <bitset>

// Only the SINGLE-THREADED dependency interfaces are stubbed.
// LSHGraph and merge_neighbors below come verbatim from the pinned graph.h.
namespace absl {
class Mutex { std::mutex m_; public: void Lock(){m_.lock();} void Unlock(){m_.unlock();} };
template<typename T> class Span {
  T* p_; size_t n_;
public: Span(T* p, size_t n):p_(p),n_(n){}
  T* begin() const {return p_;} T* end() const {return p_+n_;}
  size_t size() const {return n_;}
};
}
namespace parlay {
template<typename F> void parallel_for(size_t b, size_t e, F fn) {
  for (size_t i=b; i<e; ++i) fn(i);
}
}
namespace parlayANN {
'''

POSTLUDE = r'''} // namespace parlayANN
struct FixedHash {
  uint16_t relative_hash(size_t, uint32_t) { return 7; }
};
using Input = std::pair<uint32_t,float>;
using NativeGraph = parlayANN::LSHGraph<uint32_t,float,FixedHash>;

static std::vector<uint32_t> execute(const std::vector<Input>& input, size_t cap) {
  FixedHash h;
  NativeGraph g(1,cap,h,false);  // do NOT call the production allocator.
  g.locks = new absl::Mutex[1];
  g.tables = new NativeGraph::T[cap+1];
  g.degree(0) = 0;
  g.get_furthest(0) = Eigen::bfloat16(0);
  g.tables[0].hash = 0;
  for(const auto& c : input) {
    std::array<Input,1> single{{c}};
    g.merge_neighbors(0,single);   // DIRECT call to verbatim source method.
  }
  std::vector<uint32_t> ids;
  for(size_t j=0;j<g.degree(0);++j) ids.push_back(g.get_candidate(0,j).point_id);
  delete[] g.tables;
  delete[] g.locks;
  return ids;
}
static void require(bool ok,const char* cause) {
  if(!ok) throw std::runtime_error(cause);
}
int main() {
  try {
    const Input A{101,1.002f}, B{202,1.001f};
    const float a=A.second,b=B.second;
    const float ba=static_cast<float>(Eigen::bfloat16(a));
    const float bb=static_cast<float>(Eigen::bfloat16(b));
    std::cout << std::setprecision(9);
    std::cout << "R57_EIGEN_VERSION " << EIGEN_WORLD_VERSION << '.' << EIGEN_MAJOR_VERSION << '.' << EIGEN_MINOR_VERSION << '\n';
    std::cout << "R57_FLOAT32 A=" << a << " B=" << b << " BF16_A=" << ba << " BF16_B=" << bb << '\n';
    require(a>b && ba==bb && ba==1.0f,"expected_rounding_bin");
    for (size_t cap : {1U,2U}) {
      const auto ab=execute({A,B},cap), rev=execute({B,A},cap);
      std::cout << "R57_CAP" << cap << "_AB=" << (ab.empty()?0:ab.front()) << " BA=" << (rev.empty()?0:rev.front()) << '\n';
      require(ab==std::vector<uint32_t>{101} && rev==std::vector<uint32_t>{202},"arrival_order_native_class");
    }
    const Input C{303,1.02f}, D{404,1.0f};
    for (size_t cap : {1U,2U}) {
      require(execute({C,D},cap)==std::vector<uint32_t>{404},"control_forward");
      require(execute({D,C},cap)==std::vector<uint32_t>{404},"control_reverse");
    }
    std::cout << "R57_SOURCE_EXTRACTED_LSHGRAPH_DIRECT_CALL_PASS\n";
    return 0;
  } catch(const std::exception &e) {
    std::cerr << "R57_NATIVE_FAIL: " << e.what() << '\n';
    return 2;
  }
}
'''

def blob_sha(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def extract_pinned_class(raw):
    s=raw.decode('utf-8')
    b=BEGIN.search(s)
    if b is None: raise ValueError('LSHCandidate source start not found')
    e=END.search(s,b.end())
    if e is None: raise ValueError('End of namespace not found after LSHCandidate')
    block=s[b.start():e.start()]
    missing=[m for m in MARKERS if m not in block]
    if missing: raise ValueError('Missing pinned code markers: '+str(missing))
    if block.count('struct LSHGraph')!=1 or block.count('~LSHGraph()')!=1:
        raise ValueError('Ambiguous LSHGraph source class extraction')
    return block


def eigen_includes(root,preferred=None):
    candidates=[Path(preferred).expanduser()] if preferred else []
    if os.getenv('EIGEN_INCLUDE'): candidates.append(Path(os.getenv('EIGEN_INCLUDE')))
    candidates += [Path('/usr/include/eigen3'),Path('/usr/local/include/eigen3'),
                   Path('/opt/pyvenv/lib/python3.13/site-packages/casadi/include/eigen3')]
    # Follow the preexisting R56 resolver if that script exists (it scans local deps).
    try:
        from ann_task_a_r56_native_eigen_gate import eigen_directories
        candidates.extend(eigen_directories(root,None))
    except ImportError:
        pass
    seen=set()
    for c in candidates:
        key=str(c.resolve())
        if key not in seen and (c/'Eigen/Core').is_file():
            seen.add(key)
            yield c


def build_and_run(root,raw,preferred_include):
    cpp=PRELUDE+extract_pinned_class(raw)+POSTLUDE
    compiler=shutil.which('g++') or shutil.which('c++')
    if not compiler: raise ValueError('C++ compiler not found')
    includes=list(eigen_includes(root,preferred_include))
    if not includes: raise ValueError('Eigen/Core missing; specify --eigen-include')
    attempts=[]
    with tempfile.TemporaryDirectory(prefix='r57_lshgraph_') as td:
        src=Path(td)/'r57_direct.cpp'; binfile=Path(td)/'r57_direct'
        src.write_text(cpp)
        for inc in includes:
            cmd=[compiler,'-std=c++17','-O2','-pthread','-I'+str(inc),str(src),'-o',str(binfile)]
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
            attempts.append({'eigen_include':str(inc),'exit_code':p.returncode,'compiler_stderr_tail':p.stderr[-1200:]})
            if p.returncode==0: break
        else:
            raise ValueError('Source-extracted class compilation blocked: '+json.dumps(attempts,ensure_ascii=False))
        run=subprocess.run([str(binfile)],capture_output=True,text=True,timeout=30)
        if run.returncode!=0 or 'R57_SOURCE_EXTRACTED_LSHGRAPH_DIRECT_CALL_PASS' not in run.stdout:
            raise ValueError(f'Direct class runtime failed exit={run.returncode} stdout={run.stdout} stderr={run.stderr}')
        v=subprocess.run([compiler,'--version'],capture_output=True,text=True,timeout=10)
        return {'cpp_sha256':hashlib.sha256(cpp.encode()).hexdigest(),
                'source_extracted_class_sha256':hashlib.sha256(extract_pinned_class(raw).encode()).hexdigest(),
                'compiler':compiler,'compiler_version':v.stdout.splitlines()[0] if v.stdout else 'unknown',
                'eigen_include':str(inc),'native_stdout':run.stdout.strip().splitlines(),
                'actual_class_method_called':True,
                'scope':'Original LSHCandidate/LSHGraph class text compiled verbatim; single-thread stubs replace only Abseil/Parlay dependencies; constant-hash test fixture; NOT full linked PiPNN executable.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=['selftest','audit'])
    ap.add_argument('--root',default='.')
    ap.add_argument('--source',default=SOURCE_DEFAULT)
    ap.add_argument('--eigen-include',default=None)
    ap.add_argument('--output',default=OUTPUT_DEFAULT)
    args=ap.parse_args()
    root=Path(args.root).expanduser().resolve()
    source=Path(args.source).expanduser()
    if not source.is_absolute():source=root/source
    try:
        if not source.is_file():raise ValueError('Original source file missing: '+str(source))
        raw=source.read_bytes(); sha=blob_sha(raw)
        if sha!=EXPECTED_SHA1:
            raise ValueError('Source Git blob mismatch: '+sha+' expected '+EXPECTED_SHA1+'; refusing to label direct test as pinned')
        native=build_and_run(root,raw,args.eigen_include)
        if args.mode=='selftest':
            print('R57_PINNED_ORIGINAL_SOURCE_PASS',sha)
            for line in native['native_stdout']:print(line)
            print('R57_SELFTEST_PASS: original LSHGraph class compiled and invoked')
            return
        output=Path(args.output).expanduser()
        if not output.is_absolute():output=root/output
        if output.exists():raise ValueError('Output already exists; refusing overwrite: '+str(output))
        result={'audit':'R57_PINNED_SOURCE_EXTRACTED_LSHGRAPH_DIRECT_CALL_PASS',
                'original_source':str(source),'original_git_blob_sha1':sha,
                'original_source_sha256':hashlib.sha256(raw).hexdigest(),
                'native':native,
                'limits':[
                    'Compiles actual original class/method code extracted verbatim, not a rewritten comparator.',
                    'Abseil Mutex/Span and Parlay parallel_for are replaced by single-thread scaffolding.',
                    'Fixed relative hash=7 forces a synthetic hash collision.',
                    'Not the fully linked PiPNN library, not an observed production proposal stream.',
                    'No SIFT1M prevalence, graph-quality, Recall or BUILD-performance implication.',
                ]}
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x',encoding='utf-8') as f:
            json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        print('R57_PINNED_SOURCE_EXTRACTED_LSHGRAPH_DIRECT_CALL_PASS')
        print('R57_REPORT',output)
    except (ValueError,OSError,subprocess.TimeoutExpired,UnicodeDecodeError) as e:
        print('R57_BLOCKED:',e,file=sys.stderr)
        raise SystemExit(2)

if __name__=='__main__':
    main()
