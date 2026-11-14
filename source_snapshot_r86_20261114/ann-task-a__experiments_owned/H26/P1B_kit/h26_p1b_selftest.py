#!/usr/bin/env python3
"""Test P1b patch fail-closed and analyzer on known synthetic diagnostic logs."""
import sys, tempfile
from pathlib import Path
from h26_p1b_patch import patch
from h26_p1b_analyze import parse

sample='''H26_PROFILE,version,H26_P0_v1
H26P1A,version,H26_P1A_v1
namespace h26p1a {}
template <typename PR, typename Seq>
auto eigen_build_distmat(Seq& seq, PR& all_points) {
  const auto h26p1a_t5 = h26p1a::Clock::now();
  auto& p1a = h26p1a::counts();
}
'''
p=patch(sample)
assert p.count('H26P1B,version,H26_P1B_v1')==1
assert p.count('h26p1b::histogram().add(')==1
for t in [sample+'H26P1B,version',p]:
    try:patch(t)
    except RuntimeError: pass
    else:raise AssertionError('Should reject duplicate or stale patch')
print('H26P1B_PATCH_FAIL_CLOSED_SELFTEST_PASS')

with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'p1b_r1_top2.log'
    lines=['H26P1B,version,H26_P1B_v1','H26P1A,version,H26_P1A_v1',
      'H26P1A,calls,85529','H26P1A,buffers_worker_ns,0',
      'H26P1A,copy_worker_ns,0','H26P1A,norm_zero_worker_ns,0',
      'H26P1A,rankupdate_worker_ns,120','H26P1A,finalize_worker_ns,0',
      'H26_PROFILE,selector,top2','H26_PROFILE,leaf_count,85529',
      'H26_PROFILE,rows,29995085']
    bins=['2-63','64-127','128-255','256-383','384-511','512-767','768-1023','1024-1535','1536+']
    for i,name in enumerate(bins):
        rows=[0,0,0,29995085,0,0,0,0,0][i]
        leaf=[0,0,0,85529,0,0,0,0,0][i]
        rank=120 if i==3 else 0
        lines.append(f'H26P1B,bin,{name},{leaf},{rows},1,10,{rank},{rank}')
    p.write_text('\n'.join(lines)+'\n')
    r=parse(p)
    assert r['leaves']==85529 and r['rank_worker_ns']==120
    print('H26P1B_ANALYZER_SELFTEST_PASS')
