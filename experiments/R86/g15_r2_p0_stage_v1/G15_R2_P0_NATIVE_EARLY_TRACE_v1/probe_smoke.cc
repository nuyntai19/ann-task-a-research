#include "effective_utils/g15_early_probe.h"
#include <array>
#include <string>
#include <vector>
struct FakeS {std::vector<unsigned> distances,visited;};
int main(int argc,char** argv) {
 if(argc != 2)return 2;
 using namespace parlayANN;
 g15_trace_begin(2);
 FakeS s{{7,9},{2,3}};
 for(size_t i=0;i<2;i++){
   g15_last_trace=G15EarlyTrace{};
   g15_last_trace.moments[0].reached=1;
   g15_last_trace.moments[0].comps=3;
   std::vector<std::pair<unsigned,float>> nn;
   for(unsigned j=0;j<10;j++)nn.emplace_back(j+i*10,static_cast<float>(j));
   g15_trace_save(i,nn,s);
 }
 g15_trace_dump(argv[1]);
 return 0;
}
