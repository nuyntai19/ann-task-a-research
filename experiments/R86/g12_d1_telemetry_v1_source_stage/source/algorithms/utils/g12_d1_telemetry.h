// G12-D1: observation only. Never use this file from the original source tree.
// Enabled only when compiled with -DG12_D1_TELEMETRY=1.
#pragma once
#ifndef G12_D1_TELEMETRY_H_
#define G12_D1_TELEMETRY_H_
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <limits>
#include <algorithm>
#include <fcntl.h>
#include <unistd.h>

namespace parlayANN { namespace g12d1 {
// Logical counters, not hardware instructions or memory bytes.
struct Row {
  std::uint64_t query_id=0, beam=0, k=0;
  std::uint64_t hash_seen_calls=0, hash_seen_hits=0, hash_overwrites=0;
  std::uint64_t same_as_reject=0, adjacency_entries=0;
  std::uint64_t low_quality_reject=0, exact_dist_calls=0;
  std::uint64_t cutoff_reject=0, accepted_candidate=0;
  std::uint64_t deferred_small_batches=0, deferred_zero_batches=0;
  std::uint64_t pending_max=0, merge_calls=0, merge_inputs=0;
  std::uint64_t candidate_duplicates_removed=0;
  std::uint64_t union_before_trim=0, beam_trim_dropped=0;
  std::uint64_t cut_trim_dropped=0, evicted_unexpanded=0;
  std::uint64_t expanded=0, dk_improved=0, dk_observed=0;
  double dk_first=0.0, dk_last=0.0;
  std::uint64_t output_distance_calls=0;
  std::uint64_t traversal_counter=0, visited_counter=0;
  std::uint64_t returned_ids_hash=0, returned_count=0;
  std::uint64_t starting_point_dist_calls=0, low_quality_dist_calls=0;
  std::uint64_t threshold_dist_calls=0, frontier_less_calls=0;
};
inline thread_local Row* current = nullptr;
inline thread_local bool suppress_less_count = false;
inline std::vector<Row> rows;
inline bool tracing = false;
inline long query_beam = 0;
inline long query_k = 0;
inline std::string directory;

inline bool requested() {
  const char* s=std::getenv("G12_D1_CSV_DIR");
  return s && *s;
}
inline void begin(std::size_t n,long beam,long k) {
  directory.clear(); rows.clear(); tracing=false; current=nullptr;
  const char* s=std::getenv("G12_D1_CSV_DIR");
  if(!s || !*s) return;
  directory=s; query_beam=beam; query_k=k;
  rows.resize(n);
  for(std::size_t i=0;i<n;++i){rows[i].query_id=i;rows[i].beam=beam;rows[i].k=k;}
  tracing=true;
}
inline void attach(std::size_t i) { current=(tracing && i<rows.size())?&rows[i]:nullptr; }
inline void detach() { current=nullptr; }
template<class A,class B>
inline bool same_as(const A& a,const B& b) {
  bool answer=a.same_as(b);
  if(answer && current) ++current->same_as_reject;
  return answer;
}
inline void observe_dk(double d){
  if(!current) return;
  if(!current->dk_observed){current->dk_first=d;current->dk_last=d;current->dk_observed=1;return;}
  if(d<current->dk_last)++current->dk_improved;
  current->dk_last=d; ++current->dk_observed;
}
inline std::uint64_t fnv_update(std::uint64_t h,std::uint64_t id) {
  for(int j=0;j<8;++j){h^=(id>>(8*j)) & 0xff; h*=1099511628211ULL;}
  return h;
}
template <class IDSequence>
inline void results(std::size_t i,const IDSequence& ids,std::uint64_t traversal,std::uint64_t visited) {
  if(!tracing || i>=rows.size())return;
  Row& r=rows[i];
  r.traversal_counter=traversal; r.visited_counter=visited;
  r.returned_count=ids.size();
  std::uint64_t h=14695981039346656037ULL;
  for(auto id:ids)h=fnv_update(h,static_cast<std::uint64_t>(id));
  r.returned_ids_hash=h;
}
inline bool shadow_requested(){const char* s=std::getenv("G12_D1_SHADOW_PARITY");return tracing && s && std::strcmp(s,"1")==0;}
inline void report_shadow_ok(std::size_t n){std::fprintf(stderr,"G12_D1_SHADOW_FULL_IDS_COUNTER_PARITY_PASS queries=%zu (same isolated binary, telemetry on/off; NOT original evaluator parity)\n",n);}
inline void write_after_timer(){
  if(!tracing || directory.empty())return;
  const std::string fn=directory+"/g12_d1_b"+std::to_string(query_beam)+"_k"+std::to_string(query_k)+"_q"+std::to_string(rows.size())+".csv";
  int fd=::open(fn.c_str(),O_WRONLY|O_CREAT|O_EXCL,0644);
  if(fd<0){std::perror("G12_D1_OUTPUT_CREATE_EXCLUSIVE_FAIL");std::abort();}
  FILE* f=::fdopen(fd,"w"); if(!f){::close(fd);std::abort();}
  std::fprintf(f,"query_id,beam,k,hash_seen_calls,hash_seen_hits,hash_overwrites,same_as_reject,adjacency_entries,low_quality_reject,exact_dist_calls,cutoff_reject,accepted_candidate,deferred_small_batches,deferred_zero_batches,pending_max,merge_calls,merge_inputs,candidate_duplicates_removed,union_before_trim,beam_trim_dropped,cut_trim_dropped,evicted_unexpanded,expanded,dk_improved,dk_observed,dk_first,dk_last,output_distance_calls,traversal_counter,visited_counter,returned_ids_hash,returned_count,starting_point_dist_calls,low_quality_dist_calls,threshold_dist_calls,frontier_less_calls\n");
  for(const auto& r:rows) {
    std::fprintf(f,"%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%.17g,%.17g,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu\n",
      (unsigned long long)r.query_id,(unsigned long long)r.beam,(unsigned long long)r.k,
      (unsigned long long)r.hash_seen_calls,(unsigned long long)r.hash_seen_hits,(unsigned long long)r.hash_overwrites,
      (unsigned long long)r.same_as_reject,(unsigned long long)r.adjacency_entries,(unsigned long long)r.low_quality_reject,
      (unsigned long long)r.exact_dist_calls,(unsigned long long)r.cutoff_reject,(unsigned long long)r.accepted_candidate,
      (unsigned long long)r.deferred_small_batches,(unsigned long long)r.deferred_zero_batches,(unsigned long long)r.pending_max,
      (unsigned long long)r.merge_calls,(unsigned long long)r.merge_inputs,(unsigned long long)r.candidate_duplicates_removed,
      (unsigned long long)r.union_before_trim,(unsigned long long)r.beam_trim_dropped,(unsigned long long)r.cut_trim_dropped,
      (unsigned long long)r.evicted_unexpanded,(unsigned long long)r.expanded,(unsigned long long)r.dk_improved,
      (unsigned long long)r.dk_observed,r.dk_first,r.dk_last,(unsigned long long)r.output_distance_calls,
      (unsigned long long)r.traversal_counter,(unsigned long long)r.visited_counter,
      (unsigned long long)r.returned_ids_hash,(unsigned long long)r.returned_count,
      (unsigned long long)r.starting_point_dist_calls,(unsigned long long)r.low_quality_dist_calls,
      (unsigned long long)r.threshold_dist_calls,(unsigned long long)r.frontier_less_calls);
  }
  if(std::fclose(f)!=0){std::perror("G12_D1_OUTPUT_CLOSE_FAIL");std::abort();}
  std::fprintf(stderr,"G12_D1_TELEMETRY_CSV_WRITTEN path=%s rows=%zu\n",fn.c_str(),rows.size());
}
}} // namespace parlayANN::g12d1
#endif
