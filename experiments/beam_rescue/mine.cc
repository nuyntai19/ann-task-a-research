#include <algorithm>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <random>
#include <set>
#include <stdexcept>
#include <unordered_set>
#include <vector>

#include "euclidian_point.h"
#include "point_range.h"
#include "trace/beamSearch.h"
#include "routing.h"

using Id = rescue::Id;
using Points = parlayANN::PointRange<parlayANN::Euclidian_Point<float>>;
using Graph = parlayANN::Graph<Id>;
using Clock = std::chrono::steady_clock;

struct Query {
  Id id;
  float kth_squared;
  std::array<Id,10> truth;
};

using Neighbor = std::pair<Id,float>;
struct Result {
  std::vector<Id> top;
  std::vector<Neighbor> visited;
  unsigned hits;
  std::size_t cmps;
};

static Result search(Graph& g, const Points& points, const Query& q, int beam,
                     rescue::Trace* trace = nullptr) {
  // Point aliases its base row, so native same_as excludes that row. Also
  // exclude it defensively from the answer and cover the entry point case.
  if (q.id == 0) throw std::runtime_error("Calibration may not use entry point");
  auto point = points[q.id];
  parlayANN::QueryParams params(10L, beam, 1.35, g.size(), g.max_degree());
  auto data = parlayANN::filtered_beam_search(g, point, points, point, points,
                                             parlay::sequence<Id>{0}, params, false, trace);
  Result r{{}, {data.first.second.begin(), data.first.second.end()}, 0, data.second};
  for (const auto& [id, dist] : data.first.first) {
    if (id == q.id) continue;
    if (r.top.size() == 10) break;
    r.top.push_back(id);
    r.hits += dist <= q.kth_squared;
  }
  if (r.top.size() != 10 || std::set<Id>(r.top.begin(), r.top.end()).size() != 10)
    throw std::runtime_error("Invalid calibration search result");
  return r;
}

struct Swap {
  Id u, slot, old_id, replacement;
  int hits = 0, visits_saved = 0, cmps_saved = 0;
};

static void apply(Graph& graph, const Swap& edit, bool undo = false) {
  auto row = graph[edit.u];
  std::vector<Id> ids;
  for (Id i = 0; i < row.size(); ++i) ids.push_back(row[i]);
  Id before = undo ? edit.replacement : edit.old_id;
  Id after = undo ? edit.old_id : edit.replacement;
  if (ids.at(edit.slot) != before || after == edit.u ||
      std::find(ids.begin(), ids.end(), after) != ids.end()) throw std::runtime_error("Invalid swap");
  ids[edit.slot] = after;
  row.update_neighbors(ids);
}

static std::vector<Id> two_hop(Graph& graph, Id u) {
  std::unordered_set<Id> seen{u};
  std::vector<Id> pool;
  auto row = graph[u];
  for (Id i = 0; i < row.size(); ++i) seen.insert(row[i]);
  for (Id i = 0; i < row.size(); ++i) {
    auto other = graph[row[i]];
    for (Id j = 0; j < other.size(); ++j)
      if (seen.insert(other[j]).second) pool.push_back(other[j]);
  }
  std::sort(pool.begin(), pool.end());
  return pool;
}

static Id redundant_slot(Graph& graph, const Points& points, Id u) {
  auto row = graph[u];
  std::vector<Neighbor> slots;
  for (Id i = 0; i < row.size(); ++i) slots.emplace_back(i, points[u].distance(points[row[i]]));
  std::sort(slots.begin(), slots.end(), [](auto a, auto b) {return a.second > b.second;});
  for (std::size_t i = 0; i + 2 < slots.size(); ++i) {
    auto slot = slots[i].first;
    for (Id j = 0; j < row.size(); ++j) {
      if (j == slot) continue;
      auto other = graph[row[j]];
      for (Id k = 0; k < other.size(); ++k)
        if (other[k] == row[slot]) return slot;
    }
  }
  return static_cast<Id>(row.size());
}

static std::vector<Swap> candidates(Graph& graph, const Points& points, const Query& q,
                                    const Result& low, const Result& high,
                                    const rescue::Trace& trace) {
  auto point = points[q.id];
  std::unordered_set<Id> expanded;
  for (const auto& e : low.visited) expanded.insert(e.first);
  std::vector<Neighbor> targets;
  for (const auto& e : high.visited) {
    if (!expanded.count(e.first) && e.first != q.id) targets.push_back(e);
    if (targets.size() == 48) break;
  }
  std::vector<std::pair<float,Swap>> found;
  for (const auto& s : trace.steps) {
    auto row = graph[s.source];
    if (row.size() < 4) continue;
    auto u = points[s.source];
    float best_neighbor = std::numeric_limits<float>::max(), longest = 0;
    for (Id j = 0; j < row.size(); ++j) {
      if (row[j] != q.id) best_neighbor = std::min(best_neighbor, point.distance(points[row[j]]));
      longest = std::max(longest, u.distance(points[row[j]]));
    }
    auto has_novel = [&](const Neighbor& e) {
      return e.second < std::min(best_neighbor, s.cutoff) &&
             u.distance(points[e.first]) <= 4 * longest; // squared distance
    };
    if (std::none_of(targets.begin(), targets.end(), has_novel)) continue;
    auto pool = two_hop(graph, s.source);
    for (auto e : targets) {
      if (!has_novel(e) || !std::binary_search(pool.begin(), pool.end(), e.first)) continue;
      auto slot = redundant_slot(graph, points, s.source);
      if (slot < row.size()) {
        // Require the same candidate pool to have an alternate for the random control.
        if (pool.size() > 2)
          found.push_back({e.second / std::max(1.0f, best_neighbor), {s.source,slot,row[slot],e.first}});
        break;
      }
    }
  }
  std::stable_sort(found.begin(), found.end(), [](auto a, auto b) {return a.first < b.first;});
  std::vector<Swap> top;
  for (auto& entry : found) {
    if (std::none_of(top.begin(), top.end(), [&](const Swap& s) {return s.u == entry.second.u;}))
      top.push_back(entry.second);
    if (top.size() == 6) break;
  }
  return top;
}

static std::size_t reachable(Graph& graph) {
  std::vector<unsigned char> seen(graph.size());
  std::vector<Id> queue{0};
  seen[0] = 1;
  for (std::size_t i = 0; i < queue.size(); ++i) {
    auto row = graph[queue[i]];
    for (Id j = 0; j < row.size(); ++j) {
      if (!seen[row[j]]) {
        seen[row[j]] = 1;
        queue.push_back(row[j]);
      }
    }
  }
  return queue.size();
}

using Score = std::array<long,3>;
static Score assess(Graph& graph, const Points& points, const std::vector<Query>& queries) {
  Score count{};
  for (const auto& q : queries) {
    auto r = search(graph, points, q, 80);
    count[0] += r.hits;
    count[1] -= r.visited.size();
    count[2] -= r.cmps;
  }
  return count;
}

static std::vector<Swap> random_edits(Graph& graph, const Points& points,
                                     const std::vector<Swap>& selected, unsigned seed) {
  std::mt19937 engine(seed);
  std::vector<Swap> result;
  for (auto e : selected) {
    auto pool = two_hop(graph, e.u);
    auto u = points[e.u];
    float length = u.distance(points[e.replacement]);
    auto diff = [&](Id v) {return std::abs(length - u.distance(points[v]));};
    pool.erase(std::remove(pool.begin(),pool.end(),e.replacement),pool.end());
    std::sort(pool.begin(), pool.end(), [&](Id a,Id b) {
      auto da = diff(a), db = diff(b);
      return da < db || (da == db && a < b);
    });
    auto candidates = std::min<std::size_t>(pool.size(), 8);
    if (!candidates) throw std::runtime_error("No random alternate");
    std::uniform_int_distribution<std::size_t> draw(0,candidates-1);
    result.push_back({e.u,e.slot,e.old_id,pool[draw(engine)]});
  }
  return result;
}

int main(int argc, char** argv) {
  try {
    if (argc != 7) throw std::runtime_error("usage: mine BASE GRAPH QUERIES.tsv OUT SEED audit|refine");
    Points points(argv[1]);
    Graph graph(argv[2]);
    std::ifstream input(argv[3]);
    std::filesystem::path out(argv[4]);
    unsigned seed = std::stoul(argv[5]);
    bool refine = std::string(argv[6]) == "refine";
    if (graph.size() != points.size() || !input ||
        (std::string(argv[6]) != "audit" && !refine)) throw std::runtime_error("Bad inputs");
    if (!std::filesystem::create_directory(out)) throw std::runtime_error("Output exists");
    std::ofstream audit(out/"audit.tsv");
    audit << "qid\tsplit\tbeam\thits\thigh_hits\thigh_only_hits\tvisited\tcmps\tcutoff\tmerge_drop\teviction\twitness_cutoff\twitness_merge_drop\twitness_eviction\n";
    std::ofstream witnesses(out/"witnesses.tsv");
    witnesses << "qid\tbeam\ttarget\tintermediate\tevent\n";
    std::ofstream edges(out/"candidate_replays.tsv");
    edges << "qid\tu\tslot\told\tnew\thit_delta\tvisits_saved\tcmps_saved\n";

    const auto begin = Clock::now();
    std::vector<Query> verify;
    std::map<std::pair<Id,Id>,Swap> positive;
    Query q{};
    int group;
    while (input >> group >> q.id >> q.kth_squared) {
      for (auto& id : q.truth) if (!(input >> id)) throw std::runtime_error("Incomplete GT");
      if (q.id >= graph.size() || (group!=0 && group!=1)) throw std::runtime_error("Bad query id");
      if (group == 1) verify.push_back(q);
      auto high = search(graph,points,q,128);
      for (int beam : {64,80,96,128}) {
        rescue::Trace trace;
        auto low = search(graph,points,q,beam,&trace);
        auto clean = search(graph,points,q,beam);
        if (low.top != clean.top || low.visited != clean.visited || low.cmps != clean.cmps ||
            trace.steps.size() != low.visited.size()) throw std::runtime_error("Trace parity");
        std::unordered_set<Id> missing;
        for (auto id : high.top)
          if (points[id].distance(points[q.id]) <= q.kth_squared &&
              std::find(low.top.begin(),low.top.end(),id) == low.top.end()) missing.insert(id);
        std::array<int,3> all{}, witness{};
        for (const auto& d : trace.decisions) {
          auto event = static_cast<unsigned>(d.event);
          ++all[event];
          auto row = graph[d.id];
          for (Id j=0; j<row.size(); ++j)
            if (missing.count(row[j])) {
              witnesses << q.id << '\t' << beam << '\t' << row[j] << '\t' << d.id << '\t'
                        << std::array<const char*,3>{"CUTOFF_REJECT","MERGE_DROP","KEPT_THEN_EVICTED"}[event]
                        << '\n';
              ++witness[event];
              break;
            }
        }
        audit << q.id << '\t' << group << '\t' << beam << '\t' << low.hits << '\t' << high.hits
              << '\t' << missing.size() << '\t' << low.visited.size() << '\t' << low.cmps;
        for (auto n : all) audit << '\t' << n;
        for (auto n : witness) audit << '\t' << n;
        audit << '\n';
        if (!refine || beam != 80 || group != 0 || missing.empty()) continue;
        for (auto e : candidates(graph,points,q,low,high,trace)) {
          apply(graph,e);
          auto improved = search(graph,points,q,beam);
          apply(graph,e,true);
          e.hits = int(improved.hits) - int(low.hits);
          e.visits_saved = int(low.visited.size()) - int(improved.visited.size());
          e.cmps_saved = int(low.cmps) - int(improved.cmps);
          edges << q.id << '\t' << e.u << '\t' << e.slot << '\t' << e.old_id << '\t' << e.replacement
                << '\t' << e.hits << '\t' << e.visits_saved << '\t' << e.cmps_saved << '\n';
          if (e.hits <= 0) continue;
          auto key = std::make_pair(e.u,e.replacement);
          auto [it,inserted] = positive.emplace(key,e);
          if (!inserted) {
            it->second.hits += e.hits;
            it->second.visits_saved += e.visits_saved;
            it->second.cmps_saved += e.cmps_saved;
          }
        }
      }
    }
    if (verify.empty()) throw std::runtime_error("Missing verify split");
    if (!refine) return 0;
    std::vector<Swap> ranked, selected, prefix;
    for (const auto& item : positive) ranked.push_back(item.second);
    std::stable_sort(ranked.begin(),ranked.end(),[](auto a,auto b) {
      return std::tie(a.hits,a.visits_saved,a.cmps_saved) > std::tie(b.hits,b.visits_saved,b.cmps_saved);
    });
    std::unordered_set<Id> sources;
    for (const auto& e : ranked) {
      if (sources.insert(e.u).second) prefix.push_back(e);
      if (prefix.size()==256) break;
    }
    auto baseline = assess(graph,points,verify);
    auto initial_reach = reachable(graph);
    Score best{std::numeric_limits<long>::min(),0,0};
    std::ofstream scores(out/"verify.tsv");
    scores << "swaps\thit_delta\tvisits_saved\tcmps_saved\treachable\n";
    scores << "0\t0\t0\t0\t" << initial_reach << '\n';
    std::set<std::size_t> sizes;
    for (auto cap : {16u,64u,256u}) if (!prefix.empty()) sizes.insert(std::min<std::size_t>(cap,prefix.size()));
    for (auto size : sizes) {
      std::vector<Swap> batch(prefix.begin(),prefix.begin()+size);
      for (const auto& e : batch) apply(graph,e);
      auto r = reachable(graph);
      auto score = assess(graph,points,verify);
      for (const auto& e : batch) apply(graph,e,true);
      for (std::size_t i=0;i<score.size();++i) score[i] -= baseline[i];
      scores << size << '\t' << score[0] << '\t' << score[1] << '\t' << score[2] << '\t' << r << '\n';
      if (r >= initial_reach && score > best) {
        best = score;
        selected = batch;
      }
    }
    std::ofstream edits(out/"patches.tsv");
    edits << "arm\tu\tslot\told\tnew\n";
    // Keep the strongest structurally valid batch for the evaluation even if
    // development gain is zero. The no-op graph is an explicit control.
    auto random = random_edits(graph,points,selected,seed + 71);
    auto seconds = [&]() {return std::chrono::duration<double>(Clock::now() - begin).count();};
    double mine_s = seconds();
    for (auto arm : {"rescue","random"}) {
      const auto& batch = std::string(arm) == "rescue" ? selected : random;
      for (const auto& e : batch) {
        apply(graph,e);
        edits << arm << '\t' << e.u << '\t' << e.slot << '\t' << e.old_id << '\t' << e.replacement << '\n';
      }
      if (std::string(arm) == "random" && reachable(graph) < initial_reach)
        throw std::runtime_error("Random control lost reachability");
      auto graph_path = (out/(std::string(arm)+".graph")).string();
      graph.save(graph_path.data());
      for (const auto& e : batch) apply(graph,e,true);
    }
    auto root = rescue::leaders(graph.size(),seed);
    std::ofstream leaders(out/"root_leaders.txt");
    for (auto id : root) leaders << id << '\n';
    std::cout << "REFINE_PASS edits=" << selected.size() << " mine_s=" << mine_s
              << " total_cleanup_and_export_s=" << seconds() << '\n';
  } catch (const std::exception& e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
