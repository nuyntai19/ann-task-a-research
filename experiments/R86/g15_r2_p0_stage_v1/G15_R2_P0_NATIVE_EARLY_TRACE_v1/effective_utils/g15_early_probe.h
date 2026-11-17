#pragma once
// G15-R2 P0: read-only recording of EARLY Search-state, no GT access.
#include <array>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
namespace parlayANN {
constexpr int G15N = 4;
constexpr int g15_steps[G15N] = {16,64,128,256};
struct G15Moment {
  int reached=0;
  unsigned long long comps=0;
  int frontier_n=0;
  int pending_n=0;
  double best=-1.0;
  double kth=-1.0;
  double furthest=-1.0;
  unsigned long long top10_hash=0;
};
struct G15EarlyTrace {
  G15Moment moments[G15N];
  unsigned long long final_comps=0;
  unsigned long long final_visited=0;
  unsigned int final_ids[10]{};
  int done=0;
};
static thread_local G15EarlyTrace g15_last_trace;
static std::vector<G15EarlyTrace> g15_trace_rows;
static bool g15_trace_enabled=false;
static void g15_trace_begin(size_t n) {
  if(g15_trace_enabled)throw std::runtime_error("G15_TRACE_REENTRY");
  g15_trace_rows.clear();
  g15_trace_rows.resize(n);
  g15_trace_enabled=true;
}
template<class NeighborSeq, class StatsT>
static void g15_trace_save(size_t i,const NeighborSeq& neighbors,const StatsT& s) {
  if(!g15_trace_enabled)return;
  if(i>=g15_trace_rows.size() || neighbors.size()<10)throw std::runtime_error("G15_TRACE_ROW_OOB_OR_SHORT");
  G15EarlyTrace r=g15_last_trace;
  r.final_comps=static_cast<unsigned long long>(s.distances[i]);
  r.final_visited=static_cast<unsigned long long>(s.visited[i]);
  for(int j=0;j<10;j++) r.final_ids[j]=static_cast<unsigned int>(neighbors[j].first);
  r.done=1;
  g15_trace_rows[i]=r;
}
static void g15_trace_dump(const char* filename) {
  if(!g15_trace_enabled) throw std::runtime_error("G15_TRACE_NOT_ENABLED");
  if(filename==nullptr || !*filename)throw std::runtime_error("G15_TRACE_OUTPUT_ENV_UNSET");
  std::ofstream f(filename, std::ios::out|std::ios::trunc);
  if(!f)throw std::runtime_error("G15_TRACE_OUTPUT_CANNOT_CREATE");
  f<<"query_id,final_comps,final_visited";
  for(int i=0;i<G15N;i++){
    const int m=g15_steps[i];
    f<<",hit"<<m<<",cmps"<<m<<",frontier"<<m<<",pending"<<m
     <<",best"<<m<<",kth"<<m<<",furthest"<<m<<",hash10"<<m;
  }
  for(int j=0;j<10;j++)f<<",nn"<<j;
  f<<"\n"<<std::setprecision(10);
  for(size_t q=0;q<g15_trace_rows.size();q++){
    const auto& r=g15_trace_rows[q];
    if(r.done!=1)throw std::runtime_error("G15_TRACE_QUERY_MISSING");
    f<<q<<","<<r.final_comps<<","<<r.final_visited;
    for(auto& m:r.moments){
      f<<","<<m.reached<<","<<m.comps<<","<<m.frontier_n<<","<<m.pending_n<<","<<m.best<<","<<m.kth<<","<<m.furthest<<","<<m.top10_hash;
    }
    for(int j=0;j<10;j++)f<<","<<r.final_ids[j];
    f<<"\n";
  }
  f.flush();
  if(!f)throw std::runtime_error("G15_TRACE_WRITE_ERROR");
  g15_trace_rows.clear();
  g15_trace_enabled=false;
}
} // namespace parlayANN
