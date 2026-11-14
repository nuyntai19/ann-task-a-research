#!/usr/bin/env python3
"""String-anchor selftest, does not prove PiPNN compilation. Fail-closed before build."""
from h26_p1a_patch import patch
from h26_p1a_analyze import parse
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

def main():
    s='''#pragma once\n'''+'''#include <chrono>\n'''+'''template <typename PR, typename Seq>
auto eigen_build_distmat(Seq& seq, PR& all_points) {
  size_t n = seq.size();
  size_t dimension = all_points.get_dims();
  float* dist_mat = (float*)get_dist_mat();
  float* point_mat = (float*)get_point_mat();
  Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> P(point_mat, n, dimension);
  D.setZero();
  D.selfadjointView<Eigen::Lower>().rankUpdate(P);
  if (Point::is_metric()) {foo();}
  else {bar();}
  }
}

thread_local uint8_t* tile_point_mat'''+'''\nnamespace h26exp { // H26_PROFILE,version,H26_P0_v1
}
'''
    # This synthetic snippet exercises anchor matching, not full C++ compilation.
    transformed=patch(s)
    assert transformed.count('H26P1A,version,H26_P1A_v1')==1
    assert transformed.count('h26p1a_t5')>=1
    print('H26P1A_ANCHOR_TRANSFORM_PASS')
    try:
        patch(transformed)
        raise AssertionError('Double patch unexpectedly accepted')
    except RuntimeError:
        print('H26P1A_DOUBLE_PATCH_FAIL_CLOSED_PASS')
    try:
        patch(s.replace('D.setZero();','D.randomize();'))
        raise AssertionError('Malformed patch unexpectedly accepted')
    except RuntimeError:
        print('H26P1A_BAD_ANCHOR_FAIL_CLOSED_PASS')
    # First package-level parser fixtures
    with TemporaryDirectory() as d:
        p=Path(d)/'test.log'
        p.write_text('H26P1A,version,H26_P1A_v1\nH26P1A,buffers_worker_ns,1\nH26P1A,copy_worker_ns,2\nH26P1A,norm_zero_worker_ns,3\nH26P1A,rankupdate_worker_ns,4\nH26P1A,finalize_worker_ns,5\nH26P1A,calls,85529\nH26_PROFILE,selector,top2\nH26_PROFILE,dist_worker_ns,7\nH26_PROFILE,select_worker_ns,8\nH26_PROFILE,merge_worker_ns,9\nH26_PROFILE,leaf_count,85529\nElapsed (wall clock) time (h:mm:ss or m:ss): 0:42.00\n')
        r=parse(p)
        assert r['calls']==85529 and r['process_wall_s_no_graph_output']==42.0
        print('H26P1A_ANALYZER_SMOKE_PASS')
if __name__=='__main__':
    try:main()
    except Exception as exc:print('H26P1A_SELFTEST_FAILED',exc,file=sys.stderr);sys.exit(1)
