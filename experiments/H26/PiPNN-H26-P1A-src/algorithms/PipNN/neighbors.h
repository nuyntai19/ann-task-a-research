// This code is part of the Problem Based Benchmark Suite (PBBS)
// Copyright (c) 2011 Guy Blelloch and the PBBS team
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights (to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to
// permit persons to whom the Software is furnished to do so, subject to
// the following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
// NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
// LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
// OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
// WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#include <algorithm>
#include <cmath>

#include "../bench/parse_command_line.h"
#include "../utils/NSGDist.h"
#include "../utils/beamSearch.h"
#include "../utils/check_nn_recall.h"
#include "../utils/graph.h"
#include "../utils/parse_results.h"
#include "../utils/stats.h"
#include "../utils/types.h"
#include "pipnn.h"
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parlay/random.h"

namespace parlayANN {

static std::string kAlgType = "NavHCNNG";

template <typename Point, typename PointRange, typename indexType>
void ANN(long k, BuildParams &BP, PointRange &Query_Points,
         groundTruth<indexType> GT, char *res_file, char *exp_prefix,
         PointRange &Points, commandLine &P) {
  parlay::internal::timer t("ANN");
  using findex = pipnn_index<Point, PointRange, indexType>;
  char* gFile = P.getOptionValue("-graph_path");
  if (gFile) {
    // Just load the graph and search it.  Leaving this as a stub for
    // now.
    return;
  }

  // Graph building stuff.
  bool presearch = P.getOption("-presearch");
  bool prune = std::string(P.getOptionValue("-prune", "1")) != "0";
  bool prune_all = std::string(P.getOptionValue("-prune_all", "1")) != "0";
  long top_level_leaders = P.getOptionLongValue("-top_level_leaders", 1000);
  double alpha = P.getOptionDoubleValue("-alpha", 1.1);
  long prune_degree = P.getOptionLongValue("-prune_degree", 64);
  int fanout_per_level = P.getOptionIntValue("-fanout_per_level", 0);
  double fraction_leaders = P.getOptionDoubleValue("-fraction_leaders", 0.005);
  std::string fanout_scheme = P.getOptionValue("-fanout_scheme", "10,3,1");
  int Hsize = P.getOptionIntValue("-hash_bits", 12);
  long table_size = P.getOptionLongValue("-table_size", 2.5*prune_degree);
  bool no_reservoir = P.getOption("-no_reservoir");
  size_t fixed_num_leaders = P.getOptionLongValue("-fixed_leaders", 0);
  double idx_time;
  Graph<unsigned int> G;

  findex I;
  // Note, we need to allocate G internally.
  I.build_index(G, P, Points, BP.num_clusters, BP.cluster_size, BP.MST_deg,
                prune, prune_all, alpha,
                prune_degree,
                top_level_leaders, BP.fanout, fanout_per_level,
                fraction_leaders, fanout_scheme, Hsize, table_size,
                no_reservoir, fixed_num_leaders);
  idx_time = t.next_time();

  char* oFile = P.getOptionValue("-graph_outfile");
  if (oFile != nullptr) {
    std::cout << "Writing graph to " << oFile << std::endl;
    G.save(oFile);
  }

  // Below is query stuff.
  std::string name = "PiPNN";
  std::string params = "Trees = " + std::to_string(BP.num_clusters);
  auto [avg_deg, max_deg] = graph_stats_(G);
  Graph_ G_(name, params, G.size(), avg_deg, max_deg, idx_time);
  G_.print();

  if (Query_Points.size() != 0) {
    search_and_parse(G_, G, Points, Query_Points, GT, res_file, exp_prefix, k,
        BP.verbose, P.getOption("-vary_degree"), presearch);
  }
}

};  // namespace parlayANN
