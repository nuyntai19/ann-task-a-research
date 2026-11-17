#include <iostream>
#include <cstring>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <atomic>

#include <unordered_set>

#include <parlay/sequence.h>
#include <parlay/primitives.h>
#include <parlay/parallel.h>

#include "custom_beam_search.h"

std::vector<parlay::sequence<uint32_t>> bfs(parlayANN::Graph<uint32_t>& graph, uint32_t start_node) {
    std::vector<parlay::sequence<uint32_t>> levels;
    std::unordered_set<uint32_t> visited;
    std::unordered_set<uint32_t> fringe;
    visited.insert(start_node);
    fringe.insert(start_node);

    while (fringe.size() > 0) {
        parlay::sequence<uint32_t> current_level(fringe.begin(), fringe.end());
        levels.push_back(current_level);
        std::unordered_set<uint32_t> new_fringe;
        for (uint32_t node : fringe) {
            for (uint32_t neighbor : graph[node]) {
                if (visited.count(neighbor) == 0) {
                    visited.insert(neighbor);
                    new_fringe.insert(neighbor);
                }
            }
        }
        fringe = new_fringe;
    }
    return levels;
}

std::vector<parlay::sequence<uint32_t>> bfs_parallel(parlayANN::Graph<uint32_t>& graph, uint32_t start_node) {
    std::vector<parlay::sequence<uint32_t>> levels;
    std::vector<std::atomic<bool>> visited(graph.size());
    for (size_t i = 0; i < graph.size(); i++) {
        visited[i].store(false);
    }
    visited[start_node].store(true);
    parlay::sequence<uint32_t> fringe(1, start_node);

    while (fringe.size() > 0) {
        levels.push_back(fringe);
        parlay::sequence<uint32_t> new_fringe = parlay::filter(
            parlay::flatten(
                parlay::map(fringe, [&] (uint32_t node) {
                    return parlay::make_slice(
                        graph[node].begin(),
                        graph[node].end()
                    );
                })
            ),
            [&] (uint32_t neighbor) {
                bool expected = false;
                return visited[neighbor].compare_exchange_strong(expected, true);
            }
        );
        fringe = std::move(new_fringe);
    }

    return levels;
}

int main(int argc, char **argv) {
    std::string path = "/ssd2/richard/anndata/space/pipnn_100m.graph";
    if (argc > 1) {
        path = argv[1];
    }
    
    parlayANN::Graph<uint32_t> graph(path.data());

    uint32_t start_node = 0;
    if (argc > 2) {
        start_node = static_cast<uint32_t>(std::stoi(argv[2]));
    }

    auto levels = bfs_parallel(graph, start_node);
    for (size_t i = 0; i < levels.size(); i++) {
        std::cout << "Level " << i << ": " << levels[i].size() << " nodes" << std::endl;
    }
    size_t total_visited = 0;
    for (const auto& level : levels) {
        total_visited += level.size();
    }
    std::cout << "Unreachable nodes: " << graph.size() - total_visited << std::endl;

    return 0;
}