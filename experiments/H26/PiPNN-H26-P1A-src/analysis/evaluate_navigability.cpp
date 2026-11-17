#include <iostream>
#include <fstream>
#include <vector>
#include <atomic>

#include <parlay/sequence.h>
#include <parlay/parallel.h>
#include <parlay/primitives.h>
#include <parlay/random.h>

#include "custom_beam_search.h"

template <typename index_t, typename point_t>
void evaluate_navigability(
    char *g_file, // graph file
    char *p_file, // base points file
    char *o_file, // output file
    size_t bucket_width = 10, // width of each bucket in the histogram
    size_t max_beam_width = 1000, // maximum beam width to consider
    size_t num_samples = 100000 // number of random samples to take
) {
    using point_range_t = parlayANN::PointRange<point_t>;

    std::cout << "Loading graph from " << g_file << std::endl;
    parlayANN::Graph<index_t> graph(g_file);
    std::cout << "Loading base points from " << p_file << std::endl;
    point_range_t points(p_file);
    if (graph.size() != points.size()) {
        std::cerr << "Graph and point range sizes do not match. Aborting..." << std::endl;
        return;
    }

    std::vector<std::atomic<size_t>> buckets(max_beam_width / bucket_width);
    parlay::random_generator gen;
    std::uniform_int_distribution<index_t> dis(0, points.size() - 1);

    // num_samples = 1; // For debugging
    parlay::parallel_for(0, num_samples, [&] (size_t i) {
        auto r = gen[i];
        index_t source_point = dis(r);
        // index_t source_point = 0;
        index_t target_point = dis(r);
        parlay::sequence<index_t> starting_points(1, source_point);
        // std::cout << "Starting point: " << source_point << ", Target point: " << target_point << std::endl;

        auto QP = parlayANN::QueryParams(
            10, // k
            64, // beam size
            1.35, // cut
            graph.size(), // limit
            graph.max_degree() // degree limit
        );

        // Binary search for the minimum beam width that finds the target point
        size_t low_beam_width = 1;
        size_t high_beam_width = max_beam_width;
        while (low_beam_width < high_beam_width) {
            size_t mid_beam_width = (low_beam_width + high_beam_width) / 2;
            // mid_beam_width = 1000; // For debugging
            QP.beamSize = mid_beam_width;

            bool found = false;
            auto result = custom_beam_search(
                graph, points[target_point], points,
                points[target_point], points,
                starting_points, QP,
                [&] (index_t i) {}, // point_func
                [] (index_t, index_t) {}, // edge_func
                false, // use_filtering
                true // allow_finding_self
            );

            if (result.first.second[0].first == target_point) {
                // If the target point is found, we can try a smaller beam width
                high_beam_width = mid_beam_width;
            }
            else {
                // If the target point is not found, we need a larger beam width
                low_beam_width = mid_beam_width + 1;
            }

            // std::cout << "Frontier: ";
            // for (const auto& [id, dist] : result.first.first) {
            //     std::cout << "(" << id << ", " << dist << ") ";
            // }
            // std::cout << std::endl;

            // std::cout << "Visited: ";
            // for (const auto& [id, dist] : result.first.second) {
            //     std::cout << "(" << id << ", " << dist << ") ";
            // }
            // std::cout << std::endl;
            // break; // For debugging
        }

        // Increment the appropriate bucket
        size_t bucket_index = (low_beam_width - 1) / bucket_width;
        if (bucket_index < buckets.size()) {
            buckets[bucket_index]++;
        }
    });

    // Write the histogram to a CSV file
    std::ofstream out(o_file);
    if (!out.is_open()) {
        std::cerr << "Failed to open output file " << o_file << std::endl;
        return;
    }
    for (size_t i = 0; i < buckets.size(); i++) {
        out << (i * bucket_width) << "," << buckets[i] << std::endl;
    }
    out.close();
    std::cout << "Beam width histogram written to " << o_file << std::endl;
}

// This script evaluates the minimum beam width required to satisfy search for random pairs
// It outputs a histogram of these beam widths in a CSV file
int main(int argc, char* argv[]) {
    char g_file[] = "/ssd2/richard/anndata/bigann/vamana_onepass.graph"; // Placeholder until I know the graph file
    char p_file[] = "/ssd2/richard/anndata/bigann/base.1B.u8bin.crop_nb_10000000"; // Placeholder until I know the base file
    char o_file[] = "../../output/beam_width_hist.csv";

    using index_t = uint32_t;
    using point_t = parlayANN::Euclidian_Point<uint8_t>;

    evaluate_navigability<index_t, point_t>(
        g_file, p_file, o_file,
        10, // bucket width
        1000, // max beam width
        100000 // number of samples
    );

    return 0;
}