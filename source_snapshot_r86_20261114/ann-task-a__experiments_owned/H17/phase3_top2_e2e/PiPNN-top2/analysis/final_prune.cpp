#include <iostream>
#include <fstream>
#include <vector>
#include <utility>
#include <unordered_map>
#include <atomic>

#include <parlay/sequence.h>
#include <parlay/parallel.h>
#include <parlay/primitives.h>
#include <parlay/random.h>

#include "utils/types.h"
#include "utils/graph.h"
#include "utils/euclidian_point.h"
#include "utils/point_range.h"
#include "utils/stats.h"
#include "vamana/index.h"

#include "custom_beam_search.h"

using index_t = uint32_t;
using value_t = float;
using point_t = parlayANN::Euclidian_Point<value_t>;
using point_range_t = parlayANN::PointRange<point_t>;

// Load a graph, run RobustPrune on each vertex, then save the graph to a file
int main(int argc, char* argv[]) {
    char g_file[] = "/ssd2/richard/anndata/deep/graphs/vamana.graph";
    char p_file[] = "/ssd2/richard/anndata/deep/base.10M.fbin";
    char o_file[] = "/ssd2/richard/anndata/deep/graphs/vamana_final_prune.graph";

    std::cout << "Loading graph from " << g_file << std::endl;
    parlayANN::Graph<index_t> graph(g_file);
    std::cout << "Loading base points from " << p_file << std::endl;
    point_range_t points(p_file);
    if (graph.size() != points.size()) {
        std::cerr << "Graph and point range sizes do not match. Aborting..." << std::endl;
        return 1;
    }

    // Initialize vamana index
    std::cout << "Initializing Vamana index..." << std::flush;
    auto BP = parlayANN::BuildParams(
        graph.max_degree(), // max degree
        graph.max_degree() * 2, // L
        1.05, // alpha
        2, // num passes
        false // verbose
    );
    auto I = parlayANN::knn_index<point_range_t, point_range_t, index_t>(BP);
    std::cout << " done." << std::endl;

    // Run RobustPrune on the graph
    std::cout << "Running RobustPrune..." << std::flush;
    parlay::parallel_for(0, graph.size(), [&](size_t i) {
        parlay::sequence<std::pair<index_t, float>> candidates;
        auto new_neighbors = I.robustPrune(i, candidates, graph, points, BP.alpha, true, false);
        // Update the graph with the new neighbors
        graph[i].update_neighbors(new_neighbors.first);
    });
    std::cout << " done." << std::endl;

    // Save the pruned graph to a file
    graph.save(o_file);
    std::cout << "Pruned graph saved to " << o_file << std::endl;

    return 0;
}