#include <iostream>
#include <fstream>
#include <vector>
#include <utility>
#include <unordered_map>
#include <atomic>
#include <algorithm>
#include <numeric>
#include <random>

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

// Load a graph and count the indegree of each vertex.
// Then, replace all but the first 16 neighbors of each vertex with random vertices.
// Select the random vertices with probability proportional to their indegree.
// Finally, save the modified graph to a file.
int main(int argc, char* argv[]) {
    char g_file[] = "/ssd2/richard/anndata/deep/graphs/vamana.graph";
    char p_file[] = "/ssd2/richard/anndata/deep/base.10M.fbin";
    char o_file[] = "/ssd2/richard/anndata/deep/graphs/vamana_high_indegree.graph";

    std::cout << "Loading graph from " << g_file << std::endl;
    parlayANN::Graph<index_t> graph(g_file);
    std::cout << "Loading base points from " << p_file << std::endl;
    point_range_t points(p_file);
    if (graph.size() != points.size()) {
        std::cerr << "Graph and point range sizes do not match. Aborting..." << std::endl;
        return 1;
    }

    // Count indegrees
    std::cout << "Counting indegrees..." << std::flush;
    std::vector<std::atomic<size_t>> indegrees(graph.size());
    parlay::parallel_for(0, graph.size(), [&](size_t i) {
        auto neighbors = graph[i];
        for (size_t j = 0; j < neighbors.size(); ++j) {
            indegrees[neighbors[j]]++;
        }
    });
    std::vector<size_t> cdf(indegrees.size());
    cdf[0] = indegrees[0].load();
    for (size_t i = 1; i < indegrees.size(); ++i) {
        cdf[i] = cdf[i - 1] + indegrees[i].load();
    }
    std::cout << " done." << std::endl;

    // Replace neighbors with random vertices based on indegree
    std::cout << "Replacing neighbors with random vertices..." << std::flush;
    parlay::random_generator gen;
    std::uniform_int_distribution<size_t> dis(0, cdf.back() - 1);
    parlay::parallel_for(0, graph.size(), [&](size_t i) {
        auto r = gen[i];
        parlay::sequence<index_t> new_neighbors;
        for (size_t j = 0; j < 16 && j < graph[i].size(); j++) {
            new_neighbors.push_back(graph[i][j]);
        }
        for (size_t j = 16; j < graph[i].size(); ++j) {
            // Select a random vertex based on indegree
            size_t rand_val = dis(r);
            auto it = std::lower_bound(cdf.begin(), cdf.end(), rand_val);
            size_t index = std::distance(cdf.begin(), it);
            new_neighbors.push_back(index);
        }
        graph[i].update_neighbors(new_neighbors);
    });
    std::cout << " done." << std::endl;

    // Save the modified graph
    std::cout << "Saving modified graph to " << o_file << std::endl;
    graph.save(o_file);

    return 0;
}