#include <cstdint>
#include <cstdlib>

#include <parlay/sequence.h>
#include <parlay/parallel.h>
#include <parlay/primitives.h>
#include <parlay/slice.h>

#include "custom_beam_search.h"

// Returns the number of nodes in each BFS level and the number of unreachable nodes
template <typename GraphType>
std::pair<parlay::sequence<size_t>, size_t> bfs(const GraphType &graph, const typename GraphType::indexType &source) {
    if (source >= graph.size()) return {parlay::sequence<size_t>(), graph.size()};
    parlay::sequence<size_t> levels;

    using indexType = typename GraphType::indexType;
    parlay::sequence<indexType> frontier(1, source);
    parlay::sequence<std::atomic<bool>> visited(graph.size());
    visited[source] = true;
    size_t total_visited = 1;

    // Unfortunately, direction optimization doesn't work because the graph is directed
    while (!frontier.empty()) {
        levels.push_back(frontier.size());
        auto candidates = parlay::flatten(
            parlay::map(frontier, [&] (indexType node) {
                return parlay::make_slice(
                    &graph[node][0],
                    &graph[node][graph[node].size()]
                );
            })
        );
        frontier = parlay::filter(candidates, [&] (indexType neighbor) {
            if (!visited[neighbor]) {
                return visited[neighbor].compare_exchange_strong(false, true);
            }
            return false;
        });
        total_visited += frontier.size();
    }

    size_t unreachable_nodes = graph.size() - total_visited;
    return {levels, unreachable_nodes};
}

template <typename GraphType>
double average_degree(const GraphType &graph) {
    size_t total_degree = parlay::reduce(
        parlay::delayed_tabulate(graph.size(), [&] (size_t i) {
            return graph[i].size();
        })
    );
    return static_cast<double>(total_degree) / graph.size();
}

template <typename GraphType>
parlay::sequence<size_t> degree_distribution(const GraphType &graph) {
    parlay::sequence<size_t> distribution(graph.max_degree() + 1, 0);
    size_t block_size = std::max(1000, graph.max_degree());
    size_t num_blocks = (graph.size() + block_size - 1) / block_size;

    auto partial_counts = parlay::tabulate(num_blocks, [&] (size_t block) {
        size_t start = block * block_size;
        size_t end = std::min(start + block_size, graph.size());
        parlay::sequence<size_t> local_counts(graph.max_degree() + 1, 0);
        for (size_t i = start; i < end; ++i) {
            if (i < graph.size()) {
                local_counts[graph[i].size()]++;
            }
        }
        return local_counts;
    });

    return parlay::reduce(partial_counts,
        [] (const parlay::sequence<size_t> &a, const parlay::sequence<size_t> &b) {
            return parlay::tabulate(std::max(a.size(), b.size()),
                [&] (size_t i) {
                    return (i < a.size() ? a[i] : 0) + (i < b.size() ? b[i] : 0);
                }
            );
        }
    );
}

template <typename GraphType>
parlay::sequence<typename GraphType::indexType> search_path(GraphType &G,
    typename GraphType::indexType s, typename GraphType::indexType t) {
    return parlay::sequence<typename GraphType::indexType>();
    // Placeholder for actual path search implementation
}