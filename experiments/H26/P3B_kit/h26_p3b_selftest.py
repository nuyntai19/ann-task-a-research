#!/usr/bin/env python3
"""Fail-closed patch guard, C++ streaming Top2 semantics, analyzer fixture.
Not a substitute for full native PiPNN compile, sampled Highway validation, or graph quality.
"""
from pathlib import Path
import tempfile, subprocess
from h26_p3b_patch import patch, FUNC, Q_REGION, SELECT_CONDITION, FALLBACK, SELECT_END, HELPER
from h26_p3b_analyze import parse, analyze

def main():
    fixture='\n'.join(['H26_PROFILE,version,H26_P0_v1',FUNC,Q_REGION,SELECT_CONDITION,FALLBACK,SELECT_END])
    source=patch(fixture)
    for marker in ('H26P3B,version,H26_P3B_v1','h26p3b::insert','h26p3b_do_fused','h26p3b::stats()'):
        assert marker in source, marker
    # Regression: the real pinned PiPNN uses a spaces-only blank line.
    fallback_with_spaces = FALLBACK.replace('    }\n\n    uint32_t global_i',
                                             '    }\n    \n    uint32_t global_i')
    assert fallback_with_spaces != FALLBACK
    real_whitespace_fixture = fixture.replace(FALLBACK, fallback_with_spaces)
    spaced_source = patch(real_whitespace_fixture)
    assert 'h26p3b_do_fused' in spaced_source
    print('H26P3B_WHITESPACE_ANCHOR_REGRESSION_PASS')
    for broken in (fixture.replace(Q_REGION,'broken'), source, fixture.replace(FALLBACK,'broken'),
                   real_whitespace_fixture.replace(fallback_with_spaces, 'broken')):
        try: patch(broken)
        except RuntimeError:pass
        else:raise AssertionError('Patch should fail closed')
    print('H26P3B_PATCH_FAIL_CLOSED_SELFTEST_PASS')
    # Compile the EXACT helper and compare packed-double streaming minima with
    # materialized minima under varying distances, encounters and ties.
    cpp=r'''
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <atomic>
#include <cstdint>
#include <algorithm>
#include <random>
#include <cmath>
#include <limits>
'''+HELPER+r'''
static double pack(float v,unsigned short id) {
 union {double d; unsigned long long u;} a;
 a.d=static_cast<double>(v);
 a.u=(a.u & ~(2047ULL)) | (static_cast<unsigned long long>(id)&2047ULL);
 return a.d;
}
int main(){
 std::mt19937 rng(42);
 std::uniform_real_distribution<float> dis(0,2000);
 for(unsigned int t=0;t<50000;t++) {
   const unsigned int n=3+(rng()%1024),skip=rng()%n;
   std::vector<double> ref; ref.reserve(n-1);
   size_t seen=0; double a=0,b=0;
   for(unsigned int j=0;j<n;j++){
     if(j==skip)continue;
     float v= (t%3==0)?(float)(rng()%17):dis(rng);
     double packed=pack(v,(unsigned short)j);
     ref.push_back(packed);
     h26p3b::insert(packed,seen,a,b);
   }
   std::partial_sort(ref.begin(),ref.begin()+2,ref.end());
   if(seen!=n-1 || a!=ref[0] || b!=ref[1])return 7;
 }
 puts("H26P3B_CPP_STREAMING_TOP2_PASS");
}
'''
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp)
        (tmp/'t.cpp').write_text(cpp)
        subprocess.run(['g++','-std=c++17','-O2','-pthread',str(tmp/'t.cpp'),'-o',str(tmp/'t')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        cp=subprocess.run([str(tmp/'t')],check=True,capture_output=True,text=True)
        assert 'H26P3B_CPP_STREAMING_TOP2_PASS' in cp.stdout
        print(cp.stdout.strip())
        for i in [1,2]:
          for policy in ['top2','fused']:
            wall=40+(0 if policy=='fused' else 3)+i/10
            select=18 if policy=='fused' else 39
            stats=['H26_PROFILE,version,H26_P0_v1',f'H26_PROFILE,selector,{policy}',
                'H26_PROFILE,dist_worker_ns,62000000000',f'H26_PROFILE,select_worker_ns,{select}000000000',
                'H26_PROFILE,merge_worker_ns,14000000000','H26_PROFILE,leaf_count,85529',
                'H26_PROFILE,rows,29995085','H26_PROFILE,proposals,59990170','H26_PROFILE,top2_checks,0',
                'Parlay time: buckets time: 9.1','Parlay time: build leaf time: 28.2',
                'Parlay time: Final prune time: 3.6',f'Elapsed (wall clock) time (h:mm:ss or m:ss): 0:{wall:.2f}']
            if policy=='fused':
                stats+=['H26P3B,version,H26_P3B_v1','H26P3B,fused_rows,29995085','H26P3B,fused_leaves,85529']
            (tmp/f'r{i}_{policy}.log').write_text('\n'.join(stats)+'\n')
        assert parse(tmp/'r1_fused.log')['p3b_fused_rows']=='29995085'
        analyze(tmp)
        assert (tmp/'h26_p3b_summary.json').exists()
        print('H26P3B_ANALYZER_SELFTEST_PASS')

if __name__=='__main__':main()
