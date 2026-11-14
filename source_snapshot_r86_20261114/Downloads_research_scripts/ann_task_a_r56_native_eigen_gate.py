#!/usr/bin/env python3
"""R56: Isolated native C++/Eigen bfloat16 reproduction of PiPNN HashPrune comparisons.

NO PiPNN graph mutation, no SIFT1M BUILD or QUERY.  This fixture mirrors the
source comparisons but does NOT call the compiled LSHGraph class or prove
prevalence in a production build.
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

EXPECTED_BLOB_SHA1 = '7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f'
SOURCE_DEFAULT = Path('src/PiPNN/algorithms/utils/graph.h')
DEFAULT_OUT = Path('experiments/H56/r56_native_eigen_precision.json')
MARKERS = {
    'bf16_storage': r'Eigen::bfloat16\s+norm\s*;',
    'full_early_break': r'if\s*\(\s*deg\s*==\s*kMaxDegree\s*&&\s*dist\s*>=\s*max_val\s*\)\s*break\s*;',
    'relative_hash': r'H\.relative_hash\s*\(\s*i\s*,\s*pid\s*\)',
    'stored_distance_compare': r'if\s*\(\s*old\s*>\s*dist\s*\)',
    'stored_distance_convert': r'Eigen::bfloat16\s*\(\s*dist\s*\)',
}

CPP = r'''#include <Eigen/Core>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <vector>

// Only the decisive comparison and hash-collision paths from PiPNN graph.h.
// This is intentionally not a call to the original LSHGraph class.
struct In { int id; float dist; uint16_t hash; };
struct Stored { int id; Eigen::bfloat16 norm; uint16_t hash; };

static std::vector<int> replay(const std::vector<In>& incoming, size_t cap) {
  std::vector<Stored> slots;
  for (const auto& c : incoming) { // one candidate per original merge_neighbors call
    const float dist = c.dist;
    if (slots.size() == cap) {
      float max_val = -1.0f;
      for (const auto &s : slots) max_val = std::max(max_val, static_cast<float>(s.norm));
      if (dist >= max_val) continue; // actual source breaks a singleton range
    }
    auto pos = std::lower_bound(slots.begin(), slots.end(), c.hash,
        [](const Stored &s, uint16_t hash) { return s.hash < hash; });
    if (pos != slots.end() && pos->hash == c.hash) {
      const float old = static_cast<float>(pos->norm);
      if (old > dist) { // actual source comparison
        pos->id = c.id;
        pos->norm = Eigen::bfloat16(dist);
      }
      continue;
    }
    if (slots.size() < cap) {
      slots.insert(pos, Stored{c.id, Eigen::bfloat16(dist), c.hash});
    } else throw std::logic_error("fixture unexpectedly needs noncollision full replacement");
  }
  std::vector<int> out;
  for (const auto& s : slots) out.push_back(s.id);
  return out;
}
static int exact_float_reference(const std::vector<In>& incoming) {
  return std::min_element(incoming.begin(), incoming.end(), [](const In&a,const In&b) {
    return (a.dist == b.dist) ? a.id < b.id : a.dist < b.dist;
  })->id;
}
static void check(bool condition, const char* name) {
  if (!condition) { std::cerr << "R56_NATIVE_FAIL " << name << "\n"; throw std::runtime_error(name); }
}
int main() {
 try {
  const In A{101, 1.002f, 7}, B{202, 1.001f, 7};
  const float bf_a = static_cast<float>(Eigen::bfloat16(A.dist));
  const float bf_b = static_cast<float>(Eigen::bfloat16(B.dist));
  std::cout << std::setprecision(9);
  std::cout << "EIGEN_VERSION " << EIGEN_WORLD_VERSION << '.' << EIGEN_MAJOR_VERSION << '.' << EIGEN_MINOR_VERSION << "\n";
  std::cout << "FLOAT32 A=" << A.dist << " B=" << B.dist << " BF16 A=" << bf_a << " B=" << bf_b << "\n";
  check(A.dist > B.dist && bf_a == bf_b && bf_a == 1.0f, "rounding");
  check(exact_float_reference({A,B}) == 202, "float32_winner");
  for (auto cap : {1U, 2U}) {
    auto ab = replay({A, B}, cap), ba = replay({B, A}, cap);
    std::cout << "CAP" << cap << " AB=" << ab.at(0) << " BA=" << ba.at(0) << "\n";
    check(ab == std::vector<int>{101} && ba == std::vector<int>{202}, "order_sensitivity");
  }
  const In C{303, 1.02f, 7}, D{404, 1.0f, 7};
  check(replay({C,D}, 2) == std::vector<int>{404}, "far_control_ab");
  check(replay({D,C}, 2) == std::vector<int>{404}, "far_control_ba");
  std::cout << "R56_NATIVE_EIGEN_BF16_COMPARISON_REPRO_PASS\n";
  return 0;
 } catch (const std::exception& e) { std::cerr << "R56_NATIVE_FAIL " << e.what() << "\n"; return 2; }
}
'''


def git_blob_sha1(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def verify_local_source(path):
    if not path.is_file():
        raise ValueError(f'PiPNN source missing: {path}; pass --source with actual algorithms/utils/graph.h')
    raw = path.read_bytes()
    data = raw.decode('utf-8')
    missing = [name for name, pattern in MARKERS.items() if re.search(pattern, data) is None]
    if missing:
        raise ValueError(f'PiPNN source semantics differ; missing markers {missing}; refusing pinned claim')
    return {
        'path': str(path.resolve()),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'git_blob_sha1': git_blob_sha1(raw),
        'matches_pinned_original_blob': git_blob_sha1(raw) == EXPECTED_BLOB_SHA1,
        'source_checks': sorted(MARKERS),
    }


def eigen_directories(root, explicit):
    results = []
    if explicit:
        results.append(Path(explicit).expanduser())
    env = os.environ.get('EIGEN_INCLUDE', '')
    if env:
        results.append(Path(env).expanduser())
    results += [Path('/usr/include/eigen3'), Path('/usr/local/include/eigen3'),
                Path('/usr/include'), Path('/usr/local/include')]
    # Own PiPNN repo and other local dependencies; strictly bounded search.
    for base in (root/'src/PiPNN', root/'src/ParlayANN', root/'src', root/'build'):
        if base.is_dir():
            for marker in base.glob('**/Eigen/Core'):
                results.append(marker.parent.parent)
    results.append(Path('/opt/pyvenv/lib/python3.13/site-packages/casadi/include/eigen3'))
    seen = set()
    for p in results:
        s = str(p.resolve())
        if s not in seen and (p/'Eigen/Core').is_file():
            seen.add(s)
            yield p


def native_probe(root, eigen_include=None):
    compiler = shutil.which('g++') or shutil.which('c++')
    if not compiler:
        raise ValueError('C++ compiler not found (g++ or c++)')
    includes = list(eigen_directories(root, eigen_include))
    if not includes:
        raise ValueError('Eigen headers unavailable; run find src -path "*/Eigen/Core" or pass --eigen-include PATH')
    with tempfile.TemporaryDirectory(prefix='r56_native_') as tmp:
        source = Path(tmp)/'r56_fixture.cpp'
        binary = Path(tmp)/'r56_fixture'
        source.write_text(CPP, encoding='utf8')
        attempts = []
        for inc in includes:
            cmd = [compiler, '-std=c++17', '-O2', '-I'+str(inc), str(source), '-o', str(binary)]
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=90)
            attempts.append({'eigen_include':str(inc), 'exit':proc.returncode, 'stderr_tail':proc.stderr[-700:]})
            if proc.returncode == 0:
                break
        else:
            raise ValueError(f'All local Eigen compile attempts failed: {attempts}')
        run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=20)
        if run.returncode or 'R56_NATIVE_EIGEN_BF16_COMPARISON_REPRO_PASS' not in run.stdout:
            raise ValueError(f'C++ fixture failed exit={run.returncode}\nstdout={run.stdout}\nstderr={run.stderr}')
        version = subprocess.run([compiler, '--version'], text=True, capture_output=True, timeout=10)
        return {'compiler':compiler, 'compiler_version':version.stdout.splitlines()[0] if version.stdout else 'unknown',
                'eigen_include':str(inc), 'fixture_cpp_sha256': hashlib.sha256(CPP.encode('utf8')).hexdigest(),
                'native_stdout':run.stdout.strip().splitlines(),
                'test_scope': 'native Eigen::bfloat16 plus source-equivalent comparison code; NOT direct LSHGraph invocation',
                'compiled_with_optimization':'-O2'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['selftest', 'audit'])
    ap.add_argument('--root', default='.')
    ap.add_argument('--source', default=str(SOURCE_DEFAULT))
    ap.add_argument('--eigen-include', default=None)
    ap.add_argument('--output', default=str(DEFAULT_OUT))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    try:
        result = native_probe(root, args.eigen_include)
        if args.mode == 'selftest':
            print('R56_NATIVE_EIGEN_SELFTEST_PASS')
            for line in result['native_stdout']: print(line)
            return
        src = Path(args.source)
        if not src.is_absolute(): src = root/src
        prov = verify_local_source(src)
        report = {'audit':'R56_NATIVE_EIGEN_SOURCE_COMPARISON_PASS',
                  'source':prov,'native':result,
                  'interpretation_limits':[
                      'Uses isolated source-equivalent comparator code, not the original compiled LSHGraph class.',
                      'Does not measure any actual SIFT1M candidate collision frequency.',
                      'Does not establish graph correctness impact, recall differences, or algorithm novelty.',
                      'If source blob SHA differs from pinned reference, only relevant source markers are confirmed.',
                  ]}
        out = Path(args.output)
        if not out.is_absolute(): out = root/out
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('x', encoding='utf-8') as f:
            json.dump(report,f,ensure_ascii=False,indent=2)
            f.write('\n')
        print('R56_NATIVE_EIGEN_SOURCE_COMPARISON_PASS')
        print('R56_SOURCE_PINNED_BLOB_MATCH',prov['matches_pinned_original_blob'])
        for line in result['native_stdout']: print(line)
        print('R56_REPORT',out)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'R56_BLOCKED: {exc}', file=sys.stderr)
        raise SystemExit(2)

if __name__=='__main__':
    main()
