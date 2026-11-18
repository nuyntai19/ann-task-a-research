#include <cassert>
#include <iostream>
#include "adaptive_fanout.h"
int main() {
  const float a[] = {100,121,144};
  assert(af::choose_count(a,3,.1,1)==2);  // epsilon uses L2, not squared-L2.
  assert(af::choose_count(a,3,.05,1)==1);
  assert(af::choose_count(a,3,0,2)==2);
  const float ties[] = {100,100,100};
  assert(af::choose_count(ties,3,0,1)==3);
  const float zero[] = {0,0,1};
  assert(af::choose_count(zero,3,.1,1)==2);
  assert(af::choose_count(a,1,0,2)==1);
  std::size_t previous=1;
  for (double eps : {0., .01, .05, .1, .2, 1.}) {
    const auto n=af::choose_count(a,3,eps,1);
    assert(n>=previous && n>=1 && n<=3);previous=n;
  }
  std::cout << "ADAPTIVE_POLICY_TEST_PASS\n";
}
