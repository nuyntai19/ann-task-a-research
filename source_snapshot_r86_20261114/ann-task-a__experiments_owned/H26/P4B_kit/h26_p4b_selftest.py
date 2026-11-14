#!/usr/bin/env python3
"""P4b patch safety + sampled C++ recorder + analyzer synthetic gate."""
import csv, os, pathlib, subprocess, sys, tempfile
from h26_p4b_patch import P4B_HELPER, patch_graph, patch_cluster, patch_cmake
from h26_p4b_analyze import analyze

def main():
    g='''#include <atomic>\nnamespace parlayANN {\ntemplate<typename indexType_, typename distanceType_, typename sketchHash>\nstruct LSHGraph {\ntemplate<typename rangeType>\nvoid merge_neighbors(const size_t i, const rangeType& r) {\n  locks[i].Lock();\n  // intentionally synthetic only\n  sentinel->point_id = static_cast<indexType>(deg);\n  locks[i].Unlock();\n}\n\n//   template<typename rangeType>\n};\n}\n'''
    gp=patch_graph(g)
    assert 'h26p4b::recorder().sample()' in gp and 'h26p4b::recorder().record' in gp
    try:patch_graph(gp);raise AssertionError('double patch should fail')
    except RuntimeError:pass
    c='''    std::cout << "Building leaves:" << std::endl;\n     parlay::parallel_for(0, buckets.size(), [&](size_t i) {'''
    assert 'h26p4b::prepare' in patch_cluster(c)
    assert 'parlaylib_BINARY_DIR' in patch_cmake('add_subdirectory(${parlaylib_SOURCE_DIR} EXCLUDE_FROM_ALL)')
    print('H26P4B_PATCH_FAIL_CLOSED_SELFTEST_PASS')
    with tempfile.TemporaryDirectory(prefix='h26p4b_test_') as temp:
        td=pathlib.Path(temp)
        code='''#include <atomic>\n#include <chrono>\n#include <cstdlib>\n#include <cstring>\n#include <cstdio>\n#include <cstdint>\n#include <thread>\n#include <functional>\n#include <vector>\n#include <mutex>\n#include <iostream>\nnamespace parlayANN {\n'''+P4B_HELPER+'''
}\nint main(){
 using namespace parlayANN;
 h26p4b::prepare(85529);
 std::mutex mu[4];std::vector<std::thread> tt;
 for(int t=0;t<4;t++)tt.emplace_back([&,t](){
  for(int k=0;k<180000;k++) {
   int u=(k+t)%4;
   bool sample=h26p4b::recorder().sample();
   h26p4b::Tick a{},b{},c{};
   if(sample)a=h26p4b::Clock::now();
   mu[u].lock();
   if(sample)b=h26p4b::Clock::now();
   volatile int x=0; for(int j=0;j<15;j++) x+=j;
   if(sample)c=h26p4b::Clock::now();
   mu[u].unlock();
   if(sample)h26p4b::recorder().record(u,a,b,c);
  }
 });
 for(auto &t:tt)t.join();
}
'''
        cpp=td/'x.cpp';bin=td/'x';out=td/'lock.csv'
        cpp.write_text(code)
        subprocess.run(['g++','-O2','-std=c++17','-pthread',str(cpp),'-o',str(bin)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        env={**os.environ,'H26P4B_LOCK_ENABLE':'1','H26P4B_SAMPLE_MOD':'512','H26P4B_LOCK_TRACE_FILE':str(out)}
        run=subprocess.run([str(bin)],env=env,capture_output=True,text=True,check=True)
        assert 'H26P4B_LOCK,enabled,1' in run.stderr
        assert 'H26P4B_LOCK,version,H26P4B_v1' in run.stderr
        with out.open(newline='') as f:
            rows=list(csv.DictReader(f))
        assert 700<=len(rows)<=2500, len(rows)
        assert all(0<=int(r['vertex'])<4 and int(r['hold_ns'])>=0 for r in rows)
        print('H26P4B_CPP_MULTITHREAD_RECORDER_PASS',len(rows),'sampled locks')
        # Minimal synthetic seven-arm logs with GNU time to exercise schema and analysis, not real timings.
        def log(label):
            on=label.endswith('_on')
            p0=label.endswith('_p0')
            mode= '' if p0 else f'H26P4B_LOCK,enabled,{int(on)}\\n'
            if on:mode+='H26P4B_LOCK,samples,14000\\nH26P4B_LOCK,sample_mod,8192\\n'
            s=f'''H26_PROFILE,leaf_count,85529
H26_PROFILE,rows,29995085
H26_PROFILE,proposals,59990170
H26_PROFILE,dist_worker_ns,62000000000
H26_PROFILE,select_worker_ns,40000000000
H26_PROFILE,merge_worker_ns,14000000000
Parlay time: build leaf time: 29.000
Parlay time: buckets time: 9.000
Parlay time: Final prune time: 3.600
User time (seconds): 117.00
System time (seconds): 5.20
Percent of CPU this job got: 280%
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:44.00
Voluntary context switches: 1200
Involuntary context switches: 670
Maximum resident set size (kbytes): 1900000
'''+mode.replace('\\n','\n')
            (td/(label+'.log')).write_text(s)
            if on:
                with (td/(label+'.csv')).open('w',newline='') as fp:
                    w=csv.writer(fp);w.writerow(['wait_ns','hold_ns','vertex','worker'])
                    for j in range(14000):w.writerow([150+(j%40),300+(j%60),j%1000000,j%4])
        for label in ['r1_p0','r1_off','r1_on','r1_1t_on','r2_on','r2_off','r2_p0']:log(label)
        analyze(td)
        assert (td/'h26_p4b_summary.txt').is_file()
        print('H26P4B_ANALYZER_SELFTEST_PASS')
if __name__=='__main__':
    try:main()
    except Exception as e:print('H26P4B_SELFTEST_FAIL:',e,file=sys.stderr);raise
