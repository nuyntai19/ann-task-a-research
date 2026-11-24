#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "euclidian_point.h"
#include "point_range.h"
#include "beamSearch.h"

using Id = uint32_t;
using Points = parlayANN::PointRange<parlayANN::Euclidian_Point<float>>;
using Graph = parlayANN::Graph<Id>;
using Clock = std::chrono::steady_clock;
constexpr Id no_id = std::numeric_limits<Id>::max();

struct SeedChoice {
  Id first, second;
  unsigned route_cmps;
  float entry_sq;
};

class Router {
  std::vector<Id> leaders;
  std::vector<std::vector<Id>> local;
  double ratio_sq = 0;

 public:
  Router(const char* path, std::size_t n) {
    std::ifstream in(path);
    std::string kind;
    int count = 0;
    if (!(in >> kind >> count) || count < 0 || count > 100)
      throw std::runtime_error("Invalid route file");
    auto read = [&]() {
      Id id;
      if (!(in >> id) || id >= n) throw std::runtime_error("Invalid leader");
      return id;
    };
    if (kind == "flat") {
      double ratio;
      if (!(in >> ratio) || !std::isfinite(ratio) || ratio < 0)
        throw std::runtime_error("Invalid entry threshold");
      ratio_sq = ratio * ratio; // params are ratios in ordinary L2
      for (int i = 0; i < count; ++i) leaders.push_back(read());
    } else if (kind == "hier") {
      int per;
      if (!(in >> per) || count < 2 || per < 2 || per > 32)
        throw std::runtime_error("Invalid hierarchy");
      local.resize(count);
      for (int i = 0; i < count; ++i) {
        leaders.push_back(read());
        for (int j = 0; j < per; ++j) local[i].push_back(read());
      }
    } else {
      throw std::runtime_error("Unknown router");
    }
    if (std::set<Id>(leaders.begin(),leaders.end()).size()!=leaders.size())
      throw std::runtime_error("Duplicate flat/global leader");
  }

  template<class Point>
  SeedChoice choose(Point q, const Points& base, Id self) const {
    if (leaders.empty()) return {0,no_id,0,0.0f};
    auto best = [](auto a, auto b) { return a.second < b.second; };
    using Candidate = std::pair<Id,float>;
    const float inf = std::numeric_limits<float>::infinity();
    Candidate first{no_id,inf}, second{no_id,inf};
    unsigned count = 0;
    for (Id id : leaders) {
      auto d = q.distance(base[id]);
      ++count;
      if (id == self) continue;
      Candidate item{id,d};
      if (best(item,first)) { second=first; first=item; }
      else if (best(item,second)) second=item;
    }
    if (first.first == no_id) throw std::runtime_error("No eligible entry");
    if (!local.empty()) {
      auto bin = static_cast<std::size_t>(std::find(leaders.begin(),leaders.end(),first.first)-leaders.begin());
      Candidate inner{no_id,inf};
      for (auto id : local[bin]) {
        auto d = q.distance(base[id]);
        ++count;
        if (id != self && best(Candidate{id,d},inner)) inner={id,d};
      }
      if (inner.first != no_id) first=inner;
      return {first.first,no_id,count,first.second};
    }
    bool two = ratio_sq > 0 && second.first != no_id &&
               second.second <= ratio_sq * first.second;
    return {first.first,two ? second.first : no_id,count,first.second};
  }
};

struct Row {
  unsigned visits, cmps, hits;
  bool dual;
  Id entry;
  float entry_sq;
  double us;
  std::array<Id,10> top;
};

int main(int argc, char** argv) {
  try {
    if (argc != 9) throw std::runtime_error("usage: evaluate BASE GRAPH QUERY|@IDS GT ROUTE BEAMS SUMMARY DETAIL|-");
    Points base(argv[1]);
    Graph graph(argv[2]);
    std::string query_spec(argv[3]);
    std::unique_ptr<Points> queries;
    std::vector<Id> ids;
    if (query_spec.at(0) == '@') {
      std::ifstream in(query_spec.substr(1));
      Id id;
      while (in >> id) {
        if (!id || id >= base.size()) throw std::runtime_error("Invalid self query id");
        ids.push_back(id);
      }
      if (ids.empty()) throw std::runtime_error("Empty self query file");
    } else queries = std::make_unique<Points>(argv[3]);
    bool from_base = !queries;
    const std::size_t count = from_base ? ids.size() : queries->size();
    parlayANN::groundTruth<Id> gt(argv[4]);
    if (!count || gt.size()!=count || gt.dimension()<10 ||
        graph.size()!=base.size() || (queries && queries->dimension()!=base.dimension()))
      throw std::runtime_error("Shape mismatch");
    Router router(argv[5],base.size());
    std::vector<long> beams;
    std::istringstream bs(argv[6]);
    std::string token;
    while (std::getline(bs,token,',')) {
      long b = std::stol(token);
      if (b < 10 || b > 10000) throw std::runtime_error("Invalid beam");
      beams.push_back(b);
    }
    if (beams.empty() || std::filesystem::exists(argv[7]) ||
        (std::string(argv[8])!="-" && std::filesystem::exists(argv[8])))
      throw std::runtime_error("Output exists or no beams");
    std::ofstream summary(argv[7]);
    if (!summary) throw std::runtime_error("Cannot open summary");
    summary << "beam,recall,qps,mean_us,p95_us,p99_us,visited,distance,route_cmps,two_fraction,entry_l2\n";
    std::ofstream detail;
    if (std::string(argv[8])!="-") {
      detail.open(argv[8]);
      if (!detail) throw std::runtime_error("Cannot open details");
      detail << "beam,qid,entry,visited,distance,hits\n";
    }
    std::vector<Row> rows(count);
    std::vector<float> cutoff(count);
    for (std::size_t i = 0; i < count; ++i) {
      auto q = from_base ? base[ids[i]] : (*queries)[i];
      auto last = gt.coordinates(i,9);
      if (last >= base.size() || (from_base && last == ids[i]))
        throw std::runtime_error("Bad GT");
      cutoff[i] = q.distance(base[last]);
    }
    for (std::size_t bi=0;bi<beams.size();++bi) {
      auto beam = beams[bi];
      parlayANN::QueryParams qp(10L,beam,1.35,graph.size(),graph.max_degree());
      auto start = Clock::now();
      parlay::parallel_for(0,count,[&](std::size_t i) {
        auto begin=Clock::now();
        Id self = from_base ? ids[i] : no_id;
        auto q = from_base ? base[self] : (*queries)[i];
        auto entry = router.choose(q,base,self);
        parlay::sequence<Id> starts{entry.first};
        if (entry.second != no_id) starts.push_back(entry.second);
        auto [result,cmps]=parlayANN::filtered_beam_search(graph,q,base,q,base,starts,qp,false);
        // Native kernel excludes the aliased base row (same_as) for the proxy dataset.
        if (result.first.size()<10) throw std::runtime_error("Too few results");
        std::array<Id,10> top;
        for (std::size_t j=0;j<top.size();++j) top[j]=result.first[j].first;
        double us=std::chrono::duration<double,std::micro>(Clock::now()-begin).count();
        rows[i] = {static_cast<unsigned>(result.second.size()),
                   static_cast<unsigned>(cmps)+entry.route_cmps,0,entry.second!=no_id,
                   entry.first,entry.entry_sq,us,top};
      });
      auto elapsed = std::chrono::duration<double>(Clock::now()-start).count();
      if (bi==0) continue; // first beam is a warmup
      double hit=0, visits=0, cmps=0, route_cmps=0, dual=0, entry_l2=0, total=0;
      std::vector<double> times;
      times.reserve(count);
      for (std::size_t i=0;i<count;++i) {
        auto& r=rows[i];
        Id self=from_base ? ids[i] : no_id;
        auto q=from_base ? base[self] : (*queries)[i];
        for (Id id:r.top) {
          if (id==self) throw std::runtime_error("Self result leaked");
          r.hits += q.distance(base[id]) <= cutoff[i];
        }
        hit+=r.hits;
        visits+=r.visits;
        cmps+=r.cmps;
        dual+=r.dual;
        total+=r.us;
        if (std::isfinite(r.entry_sq)) entry_l2+=std::sqrt(r.entry_sq);
        times.push_back(r.us);
        if (detail.is_open()) detail << beam << ',' << i << ',' << r.entry << ',' << r.visits
                           << ',' << r.cmps << ',' << r.hits << '\n';
      }
      // A route configuration has a fixed comparison budget, even for excluded query IDs.
      auto first_query=from_base ? base[ids[0]] : (*queries)[0];
      route_cmps=router.choose(first_query,base,from_base ? ids[0] : no_id).route_cmps;
      std::sort(times.begin(),times.end());
      summary << std::setprecision(12) << beam << ',' << hit/(10*count) << ',' << count/elapsed
              << ',' << total/count << ',' << times[(count-1)*95/100] << ',' << times[(count-1)*99/100]
              << ',' << visits/count << ',' << cmps/count << ',' << route_cmps
              << ',' << dual/count << ',' << entry_l2/count << '\n';
    }
    std::cout << "ROUTE_EVAL_PASS queries=" << count << " beams=" << beams.size()-1 << '\n';
  } catch (const std::exception& e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
