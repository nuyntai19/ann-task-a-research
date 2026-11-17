#!/usr/bin/env python3
"""Fail-closed P1a distance-stage timing augmentation of H26-P0 transformed PiPNN.
Only call on a fresh H26-P1A worktree, never on H26-P0 itself.
"""
import argparse
import pathlib
import sys

START = '''template <typename PR, typename Seq>
auto eigen_build_distmat(Seq& seq, PR& all_points) {'''
M1 = '''  size_t dimension = all_points.get_dims();
  float* dist_mat = (float*)get_dist_mat();
  float* point_mat = (float*)get_point_mat();'''
M2 = '''  Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> P(point_mat, n, dimension);'''
M3 = '''  D.setZero();
  D.selfadjointView<Eigen::Lower>().rankUpdate(P);'''
M4 = '''  }
}

thread_local uint8_t* tile_point_mat'''

HELPERS = r'''
// H26-P1a diagnostic only. These are SUMS of worker elapsed time, NOT wall time.
namespace h26p1a {
using Clock = std::chrono::steady_clock;
inline unsigned long long diff(Clock::time_point t0, Clock::time_point t1) {
  return (unsigned long long)std::chrono::duration_cast<std::chrono::nanoseconds>(t1-t0).count();
}
struct Counts {
  std::atomic<unsigned long long> buffers_ns{0};
  std::atomic<unsigned long long> copy_ns{0};
  std::atomic<unsigned long long> norm_zero_ns{0};
  std::atomic<unsigned long long> rankupdate_ns{0};
  std::atomic<unsigned long long> finalize_ns{0};
  std::atomic<unsigned long long> calls{0};
  ~Counts() {
    std::fprintf(stderr,"H26P1A,version,H26_P1A_v1\n");
    std::fprintf(stderr,"H26P1A,scope,worker_elapsed_sum_NOT_build_wall\n");
    std::fprintf(stderr,"H26P1A,buffers_worker_ns,%llu\n",buffers_ns.load());
    std::fprintf(stderr,"H26P1A,copy_worker_ns,%llu\n",copy_ns.load());
    std::fprintf(stderr,"H26P1A,norm_zero_worker_ns,%llu\n",norm_zero_ns.load());
    std::fprintf(stderr,"H26P1A,rankupdate_worker_ns,%llu\n",rankupdate_ns.load());
    std::fprintf(stderr,"H26P1A,finalize_worker_ns,%llu\n",finalize_ns.load());
    std::fprintf(stderr,"H26P1A,calls,%llu\n",calls.load());
  }
};
inline Counts& counts() {static Counts c; return c;}
}
'''

def replace_once(code, old, new, desc):
    times = code.count(old)
    if times != 1:
        raise RuntimeError(f'{desc}: expected one matching anchor; got {times}')
    return code.replace(old, new, 1)

def patch(s):
    if 'H26P1A,version' in s: raise RuntimeError('Already patched P1a')
    if s.count('H26_PROFILE,version,H26_P0_v1') != 1:
        raise RuntimeError('Require H26-P0 v1 instrumented source, no H25 hooks')
    # The namespace must appear before eigen_build_distmat, since P0 helpers are below.
    s = replace_once(s,START,HELPERS+'\n'+START+'\n  const auto h26p1a_t0 = h26p1a::Clock::now();','function start')
    s = replace_once(s,M1,M1+'\n  const auto h26p1a_t1 = h26p1a::Clock::now();','buffers')
    s = replace_once(s,M2,'  const auto h26p1a_t2 = h26p1a::Clock::now();\n'+M2,'copy')
    s = replace_once(s,M3,'''  D.setZero();
  const auto h26p1a_t3 = h26p1a::Clock::now();
  D.selfadjointView<Eigen::Lower>().rankUpdate(P);
  const auto h26p1a_t4 = h26p1a::Clock::now();''','rankupdate')
    s = replace_once(s,M4,'''  }
  const auto h26p1a_t5 = h26p1a::Clock::now();
  auto& p1a = h26p1a::counts();
  p1a.buffers_ns.fetch_add(h26p1a::diff(h26p1a_t0,h26p1a_t1),std::memory_order_relaxed);
  p1a.copy_ns.fetch_add(h26p1a::diff(h26p1a_t1,h26p1a_t2),std::memory_order_relaxed);
  p1a.norm_zero_ns.fetch_add(h26p1a::diff(h26p1a_t2,h26p1a_t3),std::memory_order_relaxed);
  p1a.rankupdate_ns.fetch_add(h26p1a::diff(h26p1a_t3,h26p1a_t4),std::memory_order_relaxed);
  p1a.finalize_ns.fetch_add(h26p1a::diff(h26p1a_t4,h26p1a_t5),std::memory_order_relaxed);
  p1a.calls.fetch_add(1,std::memory_order_relaxed);
}

thread_local uint8_t* tile_point_mat''','function tail')
    return s

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--file',type=pathlib.Path,required=True); ap.add_argument('--apply',action='store_true')
    a=ap.parse_args(); src=a.file
    if not src.exists(): raise RuntimeError(f'No file: {src}')
    old=src.read_text(encoding='utf-8')
    new=patch(old)
    print('H26P1A_PATCH_CHECK_PASS')
    if a.apply:
        src.write_text(new,encoding='utf-8')
        print('H26P1A_PATCH_APPLIED',src)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('H26P1A_FAIL_CLOSED:',exc,file=sys.stderr)
        sys.exit(2)
