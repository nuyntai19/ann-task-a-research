#!/usr/bin/env python3
"""Fail-closed H26 P0 -> P3b fused packed Top2 transformation, scoped to eigen_knn."""
from pathlib import Path
import argparse, sys, re

FUNC='''template<typename GraphH, typename PR>
void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG) {'''
Q_REGION='''  std::vector<double> Q;
  Q.reserve(N);

  for (size_t i = 0; i < N; ++i) {
    Q.clear();
    for (indexType j = 0; j < N; ++j) {
      if (i == j) continue;
      float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
      double packed = packFloatAndInt(dist_ij, j);
      Q.push_back(packed);
    }
    size_t limit = std::min(MST_DEG, Q.size());'''
SELECT_CONDITION='''    if (h26exp::use_top2() && limit == 2) {'''
FALLBACK='''    } else {
      VQPartialSort(Q.data(), Q.data() + Q.size(), limit);
    }

    uint32_t global_i = active_indices[i];
    for (size_t j = 0; j < limit; j++) {
      auto unpacked = unpackDouble(Q[j]);'''
SELECT_END='''  }
  const auto h26_t2 = h26exp::Clock::now();

  // the problem with this approach is that we only merge one neighbor at a time.'''

HELPER=r'''
// H26-P3b: streaming packed Top2 while assembling a row, no full Q materialization.
// Implementation-only hypothesis: NOT claimed as a new ANN algorithm.
namespace h26p3b {
inline bool fused() {
  static const bool b=[](){
    const char* p=std::getenv("H26_SELECTOR");
    return p && std::strcmp(p,"fused")==0;
  }();
  return b;
}
inline bool check() {
  static const bool b=[](){
    const char* p=std::getenv("H26P3B_CHECK");
    return p && std::strcmp(p,"1")==0;
  }();
  return b;
}
// Same strict comparisons and encounter order as h26exp::scan2(std::vector<double>&).
inline void insert(double x, size_t& seen, double& a, double& b) {
  if(seen == 0) a=x;
  else if(seen == 1) {b=x; if(b<a) {const double t=a; a=b; b=t;}}
  else if(x<a) {b=a; a=x;}
  else if(x<b) b=x;
  ++seen;
}
struct Stats {
  std::atomic<unsigned long long> fused_leaves{0}, fused_rows{0};
  ~Stats(){
    std::fprintf(stderr,"H26P3B,version,H26_P3B_v1\n");
    std::fprintf(stderr,"H26P3B,fused_leaves,%llu\n",fused_leaves.load());
    std::fprintf(stderr,"H26P3B,fused_rows,%llu\n",fused_rows.load());
  }
};
inline Stats& stats(){static Stats obj;return obj;}
} // namespace h26p3b
'''

def once(code, old, new, label):
    count=code.count(old)
    if count!=1:
        raise RuntimeError(f'{label}: expected one exact anchor, got {count}')
    return code.replace(old,new,1)

def once_blank_insensitive(code, old, new, label):
    """Allow horizontal whitespace on one known blank line; keep fail-closed matching.

    GitHub's pinned PiPNN source has a whitespace-only blank line between
    the VQPartialSort branch and `uint32_t global_i`. H26-P0 preserves it.
    """
    parts = old.split('\n\n')
    if len(parts) != 2:
        raise RuntimeError(f'{label}: internal anchor must have exactly one blank line')
    pattern = re.compile(re.escape(parts[0]) + r'\n[ \t]*\n' + re.escape(parts[1]))
    matches = list(pattern.finditer(code))
    if len(matches) != 1:
        raise RuntimeError(f'{label}: expected one whitespace-tolerant anchor, got {len(matches)}')
    m = matches[0]
    return code[:m.start()] + new + code[m.end():]


def patch(text):
    if text.count('H26_PROFILE,version,H26_P0_v1')!=1:
        raise RuntimeError('Requires H26 P0 instrumentation in pipnn_utils.h')
    if 'H26P3B,version' in text or 'H26P3A,version' in text or 'H26P1A,version' in text:
        raise RuntimeError('Existing phase-specific instrumentation; refuse stacking')
    text=once(text,FUNC,HELPER+'\n'+FUNC,'function')
    text=once(text,Q_REGION,'''  // Stock/Top2 retain the original packed-Q materialization.
  // Fused mode carries just two packed candidates through each row.
  std::vector<double> Q;
  const bool h26p3b_do_fused = h26p3b::fused() && MST_DEG == 2 && N >= 3;
  if (!h26p3b_do_fused) Q.reserve(N);

  for (size_t i = 0; i < N; ++i) {
    Q.clear();
    double h26p3b_a=0.0, h26p3b_b=0.0;
    size_t h26p3b_seen=0;
    if (h26p3b_do_fused) {
      for (indexType j = 0; j < N; ++j) {
        if (i == j) continue;
        float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
        double packed = packFloatAndInt(dist_ij, j);
        h26p3b::insert(packed,h26p3b_seen,h26p3b_a,h26p3b_b);
      }
    } else {
      for (indexType j = 0; j < N; ++j) {
        if (i == j) continue;
        float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
        double packed = packFloatAndInt(dist_ij, j);
        Q.push_back(packed);
      }
    }
    size_t limit = std::min(MST_DEG, h26p3b_do_fused ? h26p3b_seen : Q.size());
    if(h26p3b_do_fused && h26p3b::check() && ((active_indices[i] & 1023u)==0u)) {
      // Sampled, untimed equivalence check against the original Highway selector.
      std::vector<double> ref;
      ref.reserve(N-1);
      for(indexType jj=0;jj<N;++jj) {
        if(jj==i) continue;
        const float d=(i<jj) ? dist_mat[jj*N+i] : dist_mat[i*N+jj];
        ref.push_back(packFloatAndInt(d,jj));
      }
      VQPartialSort(ref.data(), ref.data()+ref.size(), limit);
      if(ref[0]!=h26p3b_a || ref[1]!=h26p3b_b) {
        std::fprintf(stderr,"H26P3B_FAIL_CLOSED: fused/Highway Top2 mismatch source=%u\\n",active_indices[i]);
        std::abort();
      }
      h26exp::counters().top2_checks.fetch_add(1,std::memory_order_relaxed);
    }''','Q assembly')
    text=once(text,SELECT_CONDITION,'''    if (!h26p3b_do_fused && h26exp::use_top2() && limit == 2) {''','top2 condition')
    text=once_blank_insensitive(text,FALLBACK,'''    } else if (!h26p3b_do_fused) {
      VQPartialSort(Q.data(), Q.data() + Q.size(), limit);
    }

    uint32_t global_i = active_indices[i];
    for (size_t j = 0; j < limit; j++) {
      auto unpacked = unpackDouble(h26p3b_do_fused ? (j==0 ? h26p3b_a : h26p3b_b) : Q[j]);''','sort fallback and emit')
    text=once(text,SELECT_END,'''  }
  const auto h26_t2 = h26exp::Clock::now();
  if(h26p3b_do_fused) {
    auto& s=h26p3b::stats();
    s.fused_leaves.fetch_add(1,std::memory_order_relaxed);
    s.fused_rows.fetch_add(N,std::memory_order_relaxed);
  }

  // the problem with this approach is that we only merge one neighbor at a time.''','selection boundary')
    return text

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--file',type=Path,required=True)
    a.add_argument('--apply',action='store_true')
    args=a.parse_args()
    s=args.file.read_text(encoding='utf8')
    updated=patch(s)
    print('H26P3B_PATCH_CHECK_PASS')
    if args.apply:
        args.file.write_text(updated,encoding='utf8')
        print('H26P3B_PATCH_APPLIED',args.file)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('H26P3B_FAIL_CLOSED:',exc,file=sys.stderr)
        sys.exit(2)
