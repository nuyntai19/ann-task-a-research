#!/usr/bin/env python3
"""Fail-closed sampled selection subphase instrumentation of H26-P0 (pinned PiPNN).
Pure transformation; no source writes unless --apply in CLI.
"""
import argparse
from pathlib import Path
import sys

FUNC = '''template<typename GraphH, typename PR>
void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG) {'''
QSET = '''  std::vector<double> Q;
  Q.reserve(N);

  for (size_t i = 0; i < N; ++i) {
    Q.clear();'''
SCAN = '''    size_t limit = std::min(MST_DEG, Q.size());
    if (h26exp::use_top2() && limit == 2) {'''
EMIT = '''    uint32_t global_i = active_indices[i];'''
END = '''      directed_edges.emplace_back(global_i, global_neighbor, dist);
    }
  }
  const auto h26_t2 = h26exp::Clock::now();'''

HELPER = r'''
// H26-P3a: sampled leaf-level selection breakdown; DIAGNOSTIC ONLY.
// Timers are active only on a deterministic ~1/M fraction of leaves.
namespace h26p3a {
using Clock=std::chrono::steady_clock;
inline unsigned long long diff(Clock::time_point a, Clock::time_point b) {
  return (unsigned long long)std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();
}
inline unsigned long long sample_mod() {
  static const unsigned long long mod=[](){
    const char* p=std::getenv("H26P3A_SAMPLE_MOD");
    if(!p || !*p) return 64ULL;
    char* end=nullptr;
    unsigned long long val=std::strtoull(p,&end,10);
    if(!end || *end || (val!=16 && val!=32 && val!=64 && val!=128)) {
      std::fprintf(stderr,"H26P3A_FAIL_CLOSED: sample mod must be 16, 32, 64 or 128\n");
      std::abort();
    }
    return val;
  }();
  return mod;
}
inline bool sample_leaf(const parlay::sequence<uint32_t>& idx) {
  if(idx.empty()) return false;
  // Stable hash of first few members + N, sampling leaves rather than rows.
  uint64_t z=14695981039346656037ULL ^ (uint64_t)idx.size();
  for(size_t i=0;i<idx.size() && i<8;i++) {
    z^=(uint64_t)idx[i]; z*=1099511628211ULL;
  }
  z^=(z>>33); z*=0xff51afd7ed558ccdULL;
  z^=(z>>33);
  return (z % sample_mod())==0;
}
struct Counters {
  std::atomic<unsigned long long> sampled_leaves{0},sampled_rows{0},sampled_candidates{0};
  std::atomic<unsigned long long> pack_ns{0},selector_ns{0},emit_ns{0},outer_select_ns{0};
  void add(unsigned long long leaves,unsigned long long rows,unsigned long long candidates,
           unsigned long long p,unsigned long long s,unsigned long long e,unsigned long long o) {
    sampled_leaves.fetch_add(leaves,std::memory_order_relaxed);
    sampled_rows.fetch_add(rows,std::memory_order_relaxed);
    sampled_candidates.fetch_add(candidates,std::memory_order_relaxed);
    pack_ns.fetch_add(p,std::memory_order_relaxed);
    selector_ns.fetch_add(s,std::memory_order_relaxed);
    emit_ns.fetch_add(e,std::memory_order_relaxed);
    outer_select_ns.fetch_add(o,std::memory_order_relaxed);
  }
  ~Counters() {
    std::fprintf(stderr,"H26P3A,version,H26_P3A_v1\n");
    std::fprintf(stderr,"H26P3A,scope,sampled_worker_elapsed_NOT_build_wall\n");
    std::fprintf(stderr,"H26P3A,sample_mod,%llu\n",sample_mod());
    std::fprintf(stderr,"H26P3A,sampled_leaves,%llu\n",sampled_leaves.load());
    std::fprintf(stderr,"H26P3A,sampled_rows,%llu\n",sampled_rows.load());
    std::fprintf(stderr,"H26P3A,sampled_candidates,%llu\n",sampled_candidates.load());
    std::fprintf(stderr,"H26P3A,pack_ns,%llu\n",pack_ns.load());
    std::fprintf(stderr,"H26P3A,selector_ns,%llu\n",selector_ns.load());
    std::fprintf(stderr,"H26P3A,emit_ns,%llu\n",emit_ns.load());
    std::fprintf(stderr,"H26P3A,outer_select_ns,%llu\n",outer_select_ns.load());
  }
};
inline Counters& counts(){static Counters c;return c;}
} // namespace h26p3a
'''

def once(code,old,new,label):
    n=code.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected exactly one anchor, found {n}')
    return code.replace(old,new,1)

def patch(s):
    if s.count('H26_PROFILE,version,H26_P0_v1')!=1:
        raise RuntimeError('Requires exact H26-P0 v1 instrumentation')
    if 'H26P3A,version,H26_P3A_v1' in s or 'H26P1A,version,H26_P1A_v1' in s:
        raise RuntimeError('Source already instrumented with another phase')
    s=once(s,FUNC,HELPER+'\n'+FUNC,'function signature')
    s=once(s,QSET,'''  std::vector<double> Q;
  Q.reserve(N);
  const bool h26p3a_sample = h26p3a::sample_leaf(active_indices);
  unsigned long long h26p3a_pack=0, h26p3a_sel=0, h26p3a_emit=0;

  for (size_t i = 0; i < N; ++i) {
    h26p3a::Clock::time_point h26p3a_t0, h26p3a_t1, h26p3a_t2;
    if(h26p3a_sample) h26p3a_t0=h26p3a::Clock::now();
    Q.clear();''','Q packing start')
    s=once(s,SCAN,'''    if(h26p3a_sample) {
      h26p3a_t1=h26p3a::Clock::now();
      h26p3a_pack+=h26p3a::diff(h26p3a_t0,h26p3a_t1);
    }
    size_t limit = std::min(MST_DEG, Q.size());
    if (h26exp::use_top2() && limit == 2) {''','selector start')
    s=once(s,EMIT,'''    if(h26p3a_sample) {
      h26p3a_t2=h26p3a::Clock::now();
      h26p3a_sel+=h26p3a::diff(h26p3a_t1,h26p3a_t2);
    }
    uint32_t global_i = active_indices[i];''','emit start')
    s=once(s,END,'''      directed_edges.emplace_back(global_i, global_neighbor, dist);
    }
    if(h26p3a_sample) h26p3a_emit+=h26p3a::diff(h26p3a_t2,h26p3a::Clock::now());
  }
  const auto h26_t2 = h26exp::Clock::now();
  if(h26p3a_sample) {
    h26p3a::counts().add(1ULL,(unsigned long long)N,(unsigned long long)N*(N-1ULL),
        h26p3a_pack,h26p3a_sel,h26p3a_emit,h26exp::ns(h26_t1,h26_t2));
  }''','selection end')
    return s

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--file',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    a=ap.parse_args()
    old=a.file.read_text(encoding='utf8')
    updated=patch(old)
    print('H26P3A_PATCH_CHECK_PASS')
    if a.apply:
        a.file.write_text(updated,encoding='utf8')
        print('H26P3A_PATCH_APPLIED',a.file)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('H26P3A_FAIL_CLOSED:',exc,file=sys.stderr)
        sys.exit(2)
