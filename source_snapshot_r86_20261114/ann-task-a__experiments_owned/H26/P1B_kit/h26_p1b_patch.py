#!/usr/bin/env python3
"""Fail-closed H26-P1b leaf-size histogram instrumentation over a P1a worktree copy.
Adds aggregate counters AFTER timing boundaries, preserving the original rankUpdate timing.
"""
import argparse
from pathlib import Path
import sys

ANCHOR = '''template <typename PR, typename Seq>
auto eigen_build_distmat(Seq& seq, PR& all_points) {'''
TAIL = '''  const auto h26p1a_t5 = h26p1a::Clock::now();
  auto& p1a = h26p1a::counts();'''
HELPERS = r'''
// H26-P1b: distribution of leaf sizes and the costs of existing Eigen rankUpdate.
// Sums below are elapsed worker-time counters, NEVER BUILD wall time.
namespace h26p1b {
static constexpr size_t NBINS = 9;
static constexpr const char* labels[NBINS] = {
  "2-63", "64-127", "128-255", "256-383", "384-511",
  "512-767", "768-1023", "1024-1535", "1536+"
};
inline size_t bucket(size_t n) {
  if(n < 64) return 0;
  if(n < 128) return 1;
  if(n < 256) return 2;
  if(n < 384) return 3;
  if(n < 512) return 4;
  if(n < 768) return 5;
  if(n < 1024) return 6;
  if(n < 1536) return 7;
  return 8;
}
struct Bin {
  std::atomic<unsigned long long> calls{0};
  std::atomic<unsigned long long> rows{0};
  std::atomic<unsigned long long> pairs{0};
  std::atomic<unsigned long long> pair_dims{0};
  std::atomic<unsigned long long> rank_ns{0};
  std::atomic<unsigned long long> dist_ns{0};
};
struct Histogram {
  Bin bins[NBINS];
  void add(size_t n, size_t d, unsigned long long rank_ns,
           unsigned long long dist_ns) {
    auto &b = bins[bucket(n)];
    const auto u = (unsigned long long)n;
    const auto dims = (unsigned long long)d;
    const auto pairs = (u*(u+1ULL))/2ULL;  // upper/lower triangle, including diagonal
    b.calls.fetch_add(1ULL, std::memory_order_relaxed);
    b.rows.fetch_add(u, std::memory_order_relaxed);
    b.pairs.fetch_add(pairs, std::memory_order_relaxed);
    b.pair_dims.fetch_add(pairs*dims, std::memory_order_relaxed);
    b.rank_ns.fetch_add(rank_ns, std::memory_order_relaxed);
    b.dist_ns.fetch_add(dist_ns, std::memory_order_relaxed);
  }
  ~Histogram() {
    std::fprintf(stderr, "H26P1B,version,H26_P1B_v1\n");
    std::fprintf(stderr, "H26P1B,scope,worker_elapsed_sum_NOT_build_wall\n");
    std::fprintf(stderr, "H26P1B,description,pair_dims_is_triangular_work_proxy_NOT_exact_flops\n");
    for(size_t i=0;i<NBINS;++i) {
      const auto &b=bins[i];
      std::fprintf(stderr, "H26P1B,bin,%s,%llu,%llu,%llu,%llu,%llu,%llu\n",
        labels[i], b.calls.load(), b.rows.load(), b.pairs.load(),
        b.pair_dims.load(), b.rank_ns.load(), b.dist_ns.load());
    }
  }
};
inline Histogram & histogram() { static Histogram h; return h; }
}  // namespace h26p1b
'''

def one(src, old, new, reason):
    n=src.count(old)
    if n!=1: raise RuntimeError(f'{reason}: expected 1 anchor, found {n}')
    return src.replace(old,new,1)

def patch(s):
    if 'H26P1B,version' in s: raise RuntimeError('Already instrumented with P1b')
    if s.count('H26P1A,version,H26_P1A_v1') != 1: raise RuntimeError('Requires P1a v1 source')
    if s.count('H26_PROFILE,version,H26_P0_v1') != 1: raise RuntimeError('Requires P0 v1 source, not H25')
    s=one(s, ANCHOR, HELPERS+'\n'+ANCHOR,'eigen_build_distmat anchor')
    s=one(s,TAIL,'''  const auto h26p1a_t5 = h26p1a::Clock::now();
  // Histogram update is AFTER the measured P1a time boundaries.
  h26p1b::histogram().add(n, dimension,
     h26p1a::diff(h26p1a_t3, h26p1a_t4),
     h26p1a::diff(h26p1a_t0, h26p1a_t5));
  auto& p1a = h26p1a::counts();''','P1a epilogue')
    return s

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--file',type=Path,required=True); ap.add_argument('--apply',action='store_true')
    args=ap.parse_args(); old=args.file.read_text(); new=patch(old)
    print('H26P1B_PATCH_CHECK_PASS')
    if args.apply:
        args.file.write_text(new)
        print('H26P1B_PATCH_APPLIED',args.file)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('H26P1B_FAIL_CLOSED:',e,file=sys.stderr); sys.exit(2)
