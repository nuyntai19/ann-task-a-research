#!/usr/bin/env python3
"""Test fail-closed patching and compilable standalone scan2 comparator."""
import pathlib, subprocess, tempfile
from h26_instrument import ANCHOR, PREP, SORT, SELECT_END, MERGE_END, H26_HELPERS, transform

fixture='''#pragma once
#include <vector>
#include <algorithm>
namespace parlayANN {
'''+ANCHOR+'''\n'''+PREP+'''\n  for (size_t i = 0; i < N; ++i) {
    size_t whatever=0;
'''+SORT+'''\n  }\n\n  // the problem with this approach is that we only merge one neighbor at a time.
  for (const auto& edge : directed_edges) {
'''+MERGE_END+'''\n}
'''
patched=transform(fixture)
assert patched.count('H26_PROFILE,version')==1
assert 'h26exp::scan2(Q)' in patched
try:transform(patched)
except ValueError:pass
else:raise AssertionError('idempotence guard failed')
try:transform('#pragma once\n')
except ValueError:pass
else:raise AssertionError('unexpected patch on unrelated source')

# Compile and execute the exact scan2 implementation included in the header patch.
start=H26_HELPERS.index('inline void scan2(')
end=H26_HELPERS.index('\n}',start)+2
scan=H26_HELPERS[start:end]
cpp='''#include <vector>
#include <algorithm>
#include <random>
#include <cstdio>
#include <cstddef>
#include <cassert>
'''+scan+'''
int main(){std::mt19937_64 rng(54321);
for(int len=2;len<512;len++) for(int trial=0;trial<100;trial++) {
std::vector<double> values(len);
for(auto &x:values) x=(double)(rng()%1000000)/100.;
auto gold=values;
std::partial_sort(gold.begin(),gold.begin()+2,gold.end());
scan2(values);
if(values[0]!=gold[0] || values[1]!=gold[1])return 3;
}
std::puts("H26_SCAN2_STANDALONE_PASS"); }
'''
with tempfile.TemporaryDirectory() as temp:
    root=pathlib.Path(temp);src=root/'scan2.cpp';out=root/'scan2'
    src.write_text(cpp)
    subprocess.run(['g++','-std=c++17','-O2',str(src),'-o',str(out)],check=True)
    subprocess.run([str(out)],check=True)
print('H26_PATCH_FAIL_CLOSED_SELFTEST_PASS')
