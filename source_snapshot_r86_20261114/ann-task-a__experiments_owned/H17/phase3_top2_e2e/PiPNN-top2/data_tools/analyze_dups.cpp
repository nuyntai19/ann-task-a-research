#include <iostream>
#include <vector>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <cmath>
#include <random>
#include <numeric>

#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parlay/io.h"
#include "../algorithms/bench/parse_command_line.h"
#include "utils/euclidian_point.h"
#include "utils/mips_point.h"
#include "utils/point_range.h"

using namespace parlayANN;

// Helper to compare two points for exact equality
template<typename Point>
bool are_points_equal(const Point& p1, const Point& p2) {
    return p1 == p2;
}


template<typename PointRange>
void analyze_duplicates(PointRange& B, const char* dups_path, const char* true_dups_out_path) {
    using Point = typename PointRange::Point;
    size_t n = B.size();
    size_t d = B.dimension();

    // Load the duplicates file which contains indices
    std::ifstream dups_reader(dups_path, std::ios::binary);
    if (!dups_reader.is_open()) {
        std::cerr << "Error opening duplicates file: " << dups_path << std::endl;
        return;
    }

    uint32_t num_buckets;
    dups_reader.read(reinterpret_cast<char*>(&num_buckets), sizeof(uint32_t));
    std::cout << "loading " << num_buckets << " duplicate buckets from " << dups_path << std::endl;
    std::vector<std::vector<uint32_t>> duplicate_buckets(num_buckets);
    std::vector<uint32_t> all_duplicates_indices;

    for (uint32_t i = 0; i < num_buckets; ++i) {
        uint32_t bucket_size;
        dups_reader.read(reinterpret_cast<char*>(&bucket_size), sizeof(uint32_t));
        duplicate_buckets[i].reserve(bucket_size);
        // for (uint32_t j = 0; j < bucket_size; ++j) {
        //     uint32_t point_index;
        //     dups_reader.read(reinterpret_cast<char*>(&point_index), sizeof(uint32_t));
        //     duplicate_buckets[i].push_back(point_index);
        //     all_duplicates_indices.push_back(point_index);
        // }
        //load the rest of the dups in one go
        std::vector<uint32_t> bucket_indices(bucket_size);
        dups_reader.read(reinterpret_cast<char*>(bucket_indices.data()), bucket_size * sizeof(uint32_t));
        duplicate_buckets[i] = std::move(bucket_indices);
        all_duplicates_indices.insert(all_duplicates_indices.end(), duplicate_buckets[i].begin(), duplicate_buckets[i].end());
        //progress bar
        if (i % 1000 == 0) {
            std::cout << "  Loaded " << i << " / " << num_buckets << " buckets\r" << std::flush;
        }
    }
    dups_reader.close();
    std::cout << "Loaded " << num_buckets << " duplicate buckets, totaling " << all_duplicates_indices.size() << " points." << std::endl;


    // --- Statistics Calculations ---
    const int sample_size = std::min(1000, (int)n);
    std::mt19937 rng(12345); // Seed for reproducibility
    
    // --- Stat 1 & 2: Random point analysis ---
    std::cout << "\n--- Analyzing random points from base dataset ---" << std::endl;
    parlay::sequence<int> random_indices(n);
    std::iota(random_indices.begin(), random_indices.end(), 0);
    std::shuffle(random_indices.begin(), random_indices.end(), rng);

    double total_random_dist = 0;
    long pairs = 0;
    for(int i = 0; i < sample_size; ++i) {
        for (int j = i + 1; j < sample_size; ++j) {
            total_random_dist += B[random_indices[i]].distance(B[random_indices[j]]);
            pairs++;
        }
    }
    if (pairs > 0) {
       std::cout << "1. Average distance between " << sample_size << " random points: " << total_random_dist / pairs << std::endl;
    }
    
    double total_nn_dist_100 = 0;
    double total_nn_dist_10 = 0;
    const int k100 = 100;
    const int k10 = 10;
    for(int i = 0; i < sample_size; ++i) {
        Point query = B[random_indices[i]];
        parlay::sequence<float> distances = parlay::tabulate(n, [&](size_t j){
            return query.distance(B[j]);
        });
        parlay::sort_inplace(distances);
        double current_nn_dist_100 = 0;
        double current_nn_dist_10 = 0;
        for(int j = 1; j <= k100 && j < n; ++j) { // Start at 1 to exclude self
            if (j <= k10) current_nn_dist_10 += distances[j];
            current_nn_dist_100 += distances[j];
        }
        total_nn_dist_100 += (current_nn_dist_100 / k100);
        total_nn_dist_10 += (current_nn_dist_10 / k10);
    }
    if (sample_size > 0) {
        std::cout << "2a. Average distance to " << k100 << "-NN for random points: " << total_nn_dist_100 / sample_size << std::endl;
        std::cout << "2b. Average distance to " << k10 << "-NN for random points: " << total_nn_dist_10 / sample_size << std::endl;
    }

    // --- Stat 3 & 4: Duplicate point analysis (inclusive of other dups) ---
    std::cout << "\n--- Analyzing duplicate points (inclusive of other dups) ---" << std::endl;
    if (!all_duplicates_indices.empty()){
        double total_dup_random_dist = 0;
        long dup_pairs = 0;
        for(int i = 0; i < sample_size && i < all_duplicates_indices.size(); ++i) {
             for (int j = 0; j < sample_size; ++j) {
                total_dup_random_dist += B[all_duplicates_indices[i]].distance(B[random_indices[j]]);
                dup_pairs++;
            }
        }
        if (dup_pairs > 0) {
            std::cout << "3. Average distance between dups and random non-dup points: " << total_dup_random_dist / dup_pairs << std::endl;
        }

        double total_dup_nn_dist_100 = 0;
        double total_dup_nn_dist_10 = 0;
        for(int i = 0; i < sample_size && i < all_duplicates_indices.size(); ++i) {
            Point query = B[all_duplicates_indices[i]];
            parlay::sequence<float> distances = parlay::tabulate(n, [&](size_t j){
                return query.distance(B[j]);
            });
            parlay::sort_inplace(distances);
            double current_nn_dist_100 = 0;
            double current_nn_dist_10 = 0;
            for(int j = 0; j <= k100 && j < n; ++j) { // Include self if it's a neighbor
                if (j <= k10) current_nn_dist_10 += distances[j];
                current_nn_dist_100 += distances[j];
            }
            total_dup_nn_dist_100 += (current_nn_dist_100 / k100);
            total_dup_nn_dist_10 += (current_nn_dist_10 / k10);
        }
        if (sample_size > 0 && !all_duplicates_indices.empty()) {
            int count = std::min(sample_size, (int)all_duplicates_indices.size());
            std::cout << "4a. Average distance to " << k100 << "-NN for duplicate points: " << total_dup_nn_dist_100 / count << std::endl;
            std::cout << "4b. Average distance to " << k10 << "-NN for duplicate points: " << total_dup_nn_dist_10 / count << std::endl;
        }
    }

    // --- New Stat: Duplicate point analysis (exclusive of other dups) ---
    std::cout << "\n--- Analyzing duplicate points (exclusive of other dups) ---" << std::endl;
    parlay::sequence<bool> is_duplicate(n, false);
    parlay::parallel_for(0, all_duplicates_indices.size(), [&](size_t i) {
        is_duplicate[all_duplicates_indices[i]] = true;
    });

    double total_dup_nn_dist_exclusive_100 = 0;
    double total_dup_nn_dist_exclusive_10 = 0;

    for (int i = 0; i < sample_size && i < all_duplicates_indices.size(); ++i) {
        Point query = B[all_duplicates_indices[i]];
        auto non_dup_distances = parlay::pack(parlay::delayed_seq<float>(n, [&](size_t j) {
            return query.distance(B[j]);
        }), parlay::delayed_seq<bool>(n, [&](size_t j) {
            return !is_duplicate[j];
        }));

        parlay::sort_inplace(non_dup_distances);
        
        double current_nn_dist_100 = 0;
        double current_nn_dist_10 = 0;

        if (!non_dup_distances.empty()) {
            for (int j = 0; j < k100 && j < non_dup_distances.size(); ++j) {
                if (j < k10) current_nn_dist_10 += non_dup_distances[j];
                current_nn_dist_100 += non_dup_distances[j];
            }
            total_dup_nn_dist_exclusive_100 += (current_nn_dist_100 / std::min(k100, (int)non_dup_distances.size()));
            total_dup_nn_dist_exclusive_10 += (current_nn_dist_10 / std::min(k10, (int)non_dup_distances.size()));
        }
    }

    if (sample_size > 0 && !all_duplicates_indices.empty()) {
        int count = std::min(sample_size, (int)all_duplicates_indices.size());
        std::cout << "4c. Average distance to " << k100 << "-NN (excluding other dups): " << total_dup_nn_dist_exclusive_100 / count << std::endl;
        std::cout << "4d. Average distance to " << k10 << "-NN (excluding other dups): " << total_dup_nn_dist_exclusive_10 / count << std::endl;
    }

    // --- Stat 5 & 6: Bucket analysis ---
    std::cout << "\n--- Analyzing duplicate buckets ---" << std::endl;
    int exact_dup_buckets = 0;
    size_t total_points_in_exact_buckets = 0;
    size_t total_points_that_are_exact_dups = 0;
    double total_intrabucket_dist = 0;
    parlay::sequence<bool> to_omit(n, false);

    for (const auto& bucket : duplicate_buckets) {
        if (bucket.size() <= 1) continue;

        bool is_exact = true;
        for (size_t i = 1; i < bucket.size(); ++i) {
            if (!are_points_equal(B[bucket[0]], B[bucket[i]])) {
                is_exact = false;
                break;
            }
        }
        if (is_exact) {
            exact_dup_buckets++;
            total_points_in_exact_buckets += bucket.size();
        }

        // Corrected stat: Partition bucket into subgroups of identical points
        // and count all points that belong to a subgroup of size > 1.
        parlay::sequence<bool> assigned_to_group(bucket.size(), false);
        for (size_t i = 0; i < bucket.size(); i++) {
            if (!assigned_to_group[i]) {
                std::vector<size_t> current_group_indices;
                current_group_indices.push_back(i);
                assigned_to_group[i] = true; // Mark point i as processed

                for (size_t j = i + 1; j < bucket.size(); j++) {
                    if (!assigned_to_group[j] && are_points_equal(B[bucket[i]], B[bucket[j]])) {
                        current_group_indices.push_back(j);
                        assigned_to_group[j] = true; // Mark point j as processed
                    }
                }
                
                // If a group of identical points is found, mark all but one for removal.
                if (current_group_indices.size() > 1) {
                    total_points_that_are_exact_dups += current_group_indices.size();
                    // Keep the first one (at index 0), mark the rest for removal.
                    for (size_t k = 1; k < current_group_indices.size(); ++k) {
                        to_omit[bucket[current_group_indices[k]]] = true;
                    }
                }
            }
        }

        double bucket_dist = 0;
        long bucket_pairs = 0;
        for (size_t i = 0; i < bucket.size(); ++i) {
            for (size_t j = i + 1; j < bucket.size(); ++j) {
                bucket_dist += B[bucket[i]].distance(B[bucket[j]]);
                bucket_pairs++;
            }
        }
        if (bucket_pairs > 0) {
            total_intrabucket_dist += (bucket_dist / bucket_pairs);
        }
    }

    std::cout << "5a. Number of buckets with all exact duplicates: " << exact_dup_buckets << " / " << num_buckets << std::endl;
    std::cout << "5b. Total number of points in exact duplicate buckets: " << total_points_in_exact_buckets << std::endl;
    std::cout << "5c. Total points that are exact duplicates (even in mixed buckets): " << total_points_that_are_exact_dups << std::endl;
    if (num_buckets > 0) {
        std::cout << "6. Average distance between points within a dup bucket: " << total_intrabucket_dist / num_buckets << std::endl;
    }

    // --- Optional: Write out dataset with true duplicates omitted ---
    if (true_dups_out_path && *true_dups_out_path) {
        std::cout << "\n--- Writing dataset with true duplicates omitted to " << true_dups_out_path << " ---" << std::endl;

        parlay::sequence<bool> to_keep = parlay::tabulate(n, [&](size_t i) { return !to_omit[i]; });
        size_t new_size = parlay::reduce(to_keep, parlay::addm<size_t>());

        std::ofstream writer(true_dups_out_path, std::ios::binary);
        if (!writer.is_open()) {
            std::cerr << "Error opening output file for true duplicates: " << true_dups_out_path << std::endl;
        } else {
            auto d = B.dimension();
            uint32_t new_size_u32 = static_cast<uint32_t>(new_size);
            uint32_t d_u32 = static_cast<uint32_t>(d);

            writer.write(reinterpret_cast<const char*>(&new_size_u32), sizeof(uint32_t));
            writer.write(reinterpret_cast<const char*>(&d_u32), sizeof(uint32_t));
            
            size_t point_size_bytes = d * sizeof(typename Point::T);
            for (size_t i = 0; i < n; ++i) {
                if (to_keep[i]) {
                    writer.write(reinterpret_cast<const char*>(B.location(i)), point_size_bytes);
                }
            }
            
            writer.close();
            std::cout << "Original dataset size: " << n << std::endl;
            std::cout << "Number of true duplicates omitted: " << (n - new_size) << std::endl;
            std::cout << "New dataset size: " << new_size << std::endl;
            std::cout << "Deduplicated dataset written." << std::endl;
        }
    }
}


int main(int argc, char* argv[]) {
    commandLine P(argc, argv, "-base_path <base_path> -dups_path <dups_path> -data_type <data_type> -dist_func <dist_func> [-true_dups_out_path <out_path>]");
    auto base_path = P.getOptionValue("-base_path");
    auto dups_path = P.getOptionValue("-dups_path");
    auto data_type = P.getOptionValue("-data_type");
    auto dist_func = P.getOptionValue("-dist_func");
    auto true_dups_out_path = P.getOptionValue("-true_dups_out_path");

    if (!base_path || !dups_path || !data_type || !dist_func) {
        std::cout << "All arguments: -base_path, -dups_path, -data_type, -dist_func are required." << std::endl;
        return 1;
    }
    
    if (std::string(dist_func) == "Euclidian") {
        if (std::string(data_type) == "uint8") {
            PointRange<Euclidian_Point<uint8_t>> B(base_path);
            analyze_duplicates(B, dups_path, true_dups_out_path);
        } else if (std::string(data_type) == "int8") {
            PointRange<Euclidian_Point<int8_t>> B(base_path);
            analyze_duplicates(B, dups_path, true_dups_out_path);
        } else if (std::string(data_type) == "float") {
            PointRange<Euclidian_Point<float>> B(base_path);
            analyze_duplicates(B, dups_path, true_dups_out_path);
        } else {
            std::cout << "Unsupported data type for Euclidian distance" << std::endl;
        }
    } else if (std::string(dist_func) == "Mips") {
         if (std::string(data_type) == "float") {
            PointRange<Mips_Point<float>> B(base_path);
            analyze_duplicates(B, dups_path, true_dups_out_path);
        } else {
            std::cout << "Unsupported data type for MIPS" << std::endl;
        }
    } else {
        std::cout << "Unsupported distance function" << std::endl;
    }

    return 0;
}