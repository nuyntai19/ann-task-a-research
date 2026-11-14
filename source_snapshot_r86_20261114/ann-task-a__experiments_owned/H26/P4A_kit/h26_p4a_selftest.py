#!/usr/bin/env python3
"""Fail-closed patch + concurrent C++ recorder smoke test + analyzer fixture."""
import csv, importlib.util, os, pathlib, shutil, subprocess, sys, tempfile
from h26_p4a_patch import P4_HELPER,instrument_p0,instrument_cluster,instrument_cmake

def check(cond,msg):
    if not cond:raise AssertionError(msg)

def raises(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected fail-closed ValueError')

def patch_test():
    src=('''#pragma once\n#include <cstdint>\n// H26_PROFILE,version,H26_P0_v1 H26_SELECTOR\n'''
         '''template<typename GraphH, typename PR>\nvoid eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG) {\n'''
         '''  h26_c.proposals.fetch_add(directed_edges.size(),std::memory_order_relaxed);\n}\n''')
    mod=instrument_p0(src)
    check('h26p4::record_leaf(N,h26_t0,h26_t1,h26_t2,h26_t3);' in mod,'missing trace call')
    raises(lambda:instrument_p0(mod))
    raises(lambda:instrument_p0(src.replace('h26_c.proposals.fetch_add','h26_c.proposals.fake')))
    before='    std::cout << "Building leaves:" << std::endl;\n     parlay::parallel_for(0, buckets.size(), [&](size_t i) {'
    check('h26p4::prepare' in instrument_cluster(before),'missing preallocation')
    raises(lambda:instrument_cluster('incompatible'))
    check('${parlaylib_BINARY_DIR}' in instrument_cmake('add_subdirectory(${parlaylib_SOURCE_DIR} EXCLUDE_FROM_ALL)'),'cmake repair')
    print('H26P4A_PATCH_FAIL_CLOSED_SELFTEST_PASS')

def recorder_test():
    if not shutil.which('g++'):
        print('H26P4A_CPP_SKIPPED_NO_GXX');return
    with tempfile.TemporaryDirectory(prefix='h26p4a_smoke_') as tmp:
        td=pathlib.Path(tmp)
        cpp='''#include <chrono>\n#include <atomic>\n#include <vector>\n#include <cstdio>\n#include <cstdlib>\n#include <cstring>\n#include <cstdint>\n#include <thread>\n#include <algorithm>\nnamespace h26exp { using Clock=std::chrono::steady_clock; inline unsigned long long ns(Clock::time_point a,Clock::time_point b){return std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();}}\n'''+P4_HELPER+'''
int main(){
 h26p4::prepare(80);
 std::vector<std::thread> ts;
 for(int j=0;j<4;++j)ts.emplace_back([j](){
   for(int i=0;i<20;++i){auto t0=h26p4::Clock::now();
     auto t1=h26p4::Clock::now();auto t2=h26p4::Clock::now();auto t3=h26p4::Clock::now();
     h26p4::record_leaf(3,t0,t1,t2,t3);
   }
 });
 for(auto& t:ts)t.join();
}
'''
        src=td/'test.cpp';src.write_text(cpp)
        exe=td/'testbin'
        subprocess.run(['g++','-std=c++17','-pthread','-O2',str(src),'-o',str(exe)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        csvp=td/'trace.csv'
        env=dict(os.environ,H26P4_TRACE='1',H26P4_TRACE_FILE=str(csvp))
        p=subprocess.run([str(exe)],env=env,capture_output=True,text=True,check=True)
        check('H26P4_TRACE,events,80' in p.stderr,'missing 80 events log')
        with csvp.open(newline='') as f:
            rows=list(csv.DictReader(f))
        check(len(rows)==80,'tracer events incorrect')
        check(set(int(r['leaf_size']) for r in rows)=={3},'incorrect sizes')
        print('H26P4A_CPP_THREADED_RECORDER_PASS')

def analyzer_fixture():
    from h26_p4a_analyze import parse_csv,percentile,gini
    with tempfile.TemporaryDirectory(prefix='h26p4a_analyzer_') as t:
        p=pathlib.Path(t)/'run.csv'
        with p.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['start_ns','end_ns','dist_ns','select_ns','merge_ns','leaf_size','worker_token'])
            w.writerow([1000000000,1000004000,2000,1000,1000,2,0]);w.writerow([1000002000,1000005000,1000,1000,1000,3,1]);w.writerow([1000004000,1000006000,1000,500,500,4,0])
        log={'leaf_count':3,'rows':9,'dist_worker_ns':4000,'select_worker_ns':2500,'merge_worker_ns':2500}
        # Note: expected dist for fixture rows 2000+1000+1000=4000; select=1000+1000+500=2500; merge idem.
        s=parse_csv(p,log)
        check(s['maximum_concurrent_leaf_calls']==2,'peak concurrency wrong')
        check(abs(s['leaf_envelope_span_s']-0.000006)<1e-12,'span wrong')
        check(s['worker_thread_tokens_observed']==2,'worker thread count wrong')
        check(percentile([1,2,3],50)==2,'median wrong')
        check(gini([3,3])==0,'gini zero wrong')
        print('H26P4A_ANALYZER_SELFTEST_PASS')

def main():
    patch_test();recorder_test();analyzer_fixture()
if __name__=='__main__':
    try:main()
    except Exception as e:print('H26P4A_SELFTEST_FAIL:',e,file=sys.stderr);sys.exit(2)
