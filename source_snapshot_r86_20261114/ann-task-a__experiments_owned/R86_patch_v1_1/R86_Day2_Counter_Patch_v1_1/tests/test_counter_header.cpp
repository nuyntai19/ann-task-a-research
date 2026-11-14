#include "r86_counters.hpp"
#include <vector>
#include <cstdint>
int main() {
  r86::require_output_paths();
  r86::begin_pass(1);
  r86::add(r86::Metric::W_P,80,0);
  r86::add(r86::Metric::W_A,20,0);
  r86::note_depth(0);
  r86::add(r86::Metric::collision_same_id,0);
  r86::add(r86::Metric::leaf_count);
  r86::add(r86::Metric::leaf_size_sum,3);
  r86::add(r86::Metric::W_L,9);
  r86::add(r86::Metric::W_pairs,3);
  r86::emit_leaf_sizes(std::vector<std::vector<int>>{{1,2,3},{10}});
  r86::set_active_pass(0);
  r86::declare_metric(r86::Metric::prune_distance_calls);
  r86::add(r86::Metric::prune_distance_calls,2);
  r86::dump_jsonl_from_env();
}
