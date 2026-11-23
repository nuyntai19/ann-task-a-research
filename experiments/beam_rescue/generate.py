"""Create trace and timing headers from the exact search source used by Fixed/V2a."""
from pathlib import Path
import sys

native, out = map(Path, sys.argv[1:])
beam = (native / "beamSearch.h").read_text()


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected native source: {old!r}")
    return text.replace(old, new, 1)


trace_dir = out / "trace"
trace_dir.mkdir(parents=True, exist_ok=True)
trace = replace_one(beam, "bool use_filtering = false\n", "bool use_filtering = false, rescue::Trace* trace = nullptr\n")
trace = replace_one(trace, "    for (auto a : filtered) {",
                    "    if (trace) trace->steps.push_back({current.first, cutoff});\n    for (auto a : filtered) {")
trace = replace_one(trace, "      if (dist >= cutoff) continue;", """      if (dist >= cutoff) {
        if (trace) trace->decisions.push_back({a, rescue::Event::cutoff});
        continue;
      }""")
trace = replace_one(trace, "    candidates.clear();", "")
trace = replace_one(trace, "    // copy new_frontier back to the frontier", """    if (trace) {
      auto kept = [&](const id_dist& item) {
        return std::binary_search(new_frontier.begin(), new_frontier.begin() + new_frontier_size,
                                  item, less);
      };
      for (auto it = candidates.begin(); it != candidates_end; ++it)
        if (!kept(*it)) trace->decisions.push_back({it->first, rescue::Event::merge_drop});
      for (const auto& item : frontier)
        if (!kept(item) && !std::binary_search(visited.begin(), visited.end(), item, less))
          trace->decisions.push_back({item.first, rescue::Event::eviction});
    }
    candidates.clear();

    // copy new_frontier back to the frontier""")
(trace_dir / "beamSearch.h").write_text('#include "trace.h"\n' + trace)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "adaptive_fanout_followup"))
sys.dont_write_bytecode = True
from instrument_latency import instrument

eval_dir = out / "local_latency"
eval_dir.mkdir(parents=True, exist_ok=True)
timed = instrument(beam)
key = """      local_latency::QueryTimer query_timer(i);
      auto ngh_dist"""
p = timed.rindex(key)
timed = timed[:p] + timed[p:].replace(key, """      local_latency::QueryTimer query_timer(i);
      auto starts = starting_points;
      if (!rescue::routing_leaders.empty()) {
        starts[0] = rescue::entry(Query_Points[i], Base_Points);
        QueryStats.increment_dist(i, rescue::routing_leaders.size());
      }
      auto ngh_dist""", 1).replace("QueryStats, starting_points, QP);", "QueryStats, starts, QP);", 1)
# Keep the unrouted query path allocation identical to the original.
timed = timed.replace("      auto starts = starting_points;", """      parlay::sequence<indexType> routed;
      const auto* starts = &starting_points;""").replace(
    "        starts[0] = rescue::entry(Query_Points[i], Base_Points);",
    "        routed = {rescue::entry(Query_Points[i], Base_Points)};\n        starts = &routed;").replace(
    "QueryStats, starts, QP);", "QueryStats, *starts, QP);")
(eval_dir / "beamSearch.h").write_text('#include "routing.h"\n' + timed)
recall = (native / "check_nn_recall.h").read_text()
assert recall.count("numCorrect += 1;") == 2
recall = recall.replace("numCorrect += 1;", "numCorrect += 1; local_latency::query_hits[i] += 1;")
recall = replace_one(recall, "  query_time = t.next_time();", "  query_time = t.next_time();")
recall = replace_one(recall, "  t.next_time();\n  if (random)", "  rescue::configure_routing(Base_Points.size());\n  t.next_time();\n  if (random)")
(eval_dir / "check_nn_recall.h").write_text(recall)
