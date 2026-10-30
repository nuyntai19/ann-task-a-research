#include <iostream>
#include <vector>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <cmath>
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parlay/io.h"
#include "../algorithms/bench/parse_command_line.h"
#include "utils/euclidian_point.h"
#include "utils/mips_point.h"
#include "utils/point_range.h"
#include "utils/hash.h"
#include <map>
using namespace parlayANN;

// Helper to compare two points for exact equality
template<typename Point>
bool are_points_equal(const Point& p1, const Point& p2) {
    return p1 == p2;
}

template<typename PointRange>
void deduplicate_dataset(PointRange& B, const char* out_path, const char* dups_path, const char* true_dups_out_path) {
    using Point = typename PointRange::Point;
    using indexType = uint32_t;
    std::ofstream writer(out_path, std::ios::binary);
    if (!writer.is_open()) {
        std::cerr << "Error opening output file: " << out_path << std::endl;
        return;
    }

    std::ofstream dups_writer;
    if (dups_path && dups_path[0] != '\0') {
        dups_writer.open(dups_path, std::ios::binary);
        if (!dups_writer.is_open()) {
            std::cerr << "Warning: Could not open duplicates output file: " << dups_path << std::endl;
        }
    }

    auto d_long = B.dimension();
    auto n  = B.size();
    SimHash<Point, PointRange, uint32_t> simhash(64, d_long);
    parlay::sequence<bool> to_keep(B.size(), true);
    auto ids = parlay::tabulate(B.size(), [&](indexType i) { return i; });
    parlay::sequence<std::pair<size_t, uint32_t>> hash_values = simhash.generate_hash_values(B, ids);
    parlay::sort_inplace(hash_values, [](const std::pair<size_t, uint32_t>& a, const std::pair<size_t, uint32_t>& b) {
        return a.first < b.first;
    });

    size_t min_run = -1;
    size_t max_run = 0;
    size_t total_run_items = 0;
    size_t num_buckets = 0;
    std::vector<std::vector<uint32_t>> duplicate_buckets;

    size_t i = 0;
    while (i < hash_values.size()) {
        size_t j = i;
        while (j + 1 < hash_values.size() && hash_values[j + 1].first == hash_values[i].first) {
            j++;
        }
        size_t run_size = j - i + 1;
        if (run_size > 1) {
            num_buckets++;
            total_run_items += run_size;
            if (min_run == (size_t)-1 || run_size < min_run) {
                min_run = run_size;
            }
            if (run_size > max_run) {
                max_run = run_size;
            }
            
            std::vector<uint32_t> current_bucket;
            current_bucket.reserve(run_size);
            for (size_t k = i; k <= j; k++) {
                if (k > i) { // Keep the first item, mark others as duplicates
                    to_keep[hash_values[k].second] = false;
                }
                current_bucket.push_back(hash_values[k].second);
            }
            duplicate_buckets.push_back(current_bucket);
        }
        i = j + 1;
    }

    size_t new_size = parlay::reduce(to_keep, parlay::addm<size_t>());
    std::cout << "Original dataset size: " << B.size() << std::endl;
    std::cout << "New dataset size after deduplication: " << new_size << std::endl;
    
    std::cout << "Duplicate statistics:" << std::endl;
    if (num_buckets > 0) {
        double avg_run = static_cast<double>(total_run_items) / num_buckets;
        std::cout << "  Number of duplicate buckets: " << num_buckets << std::endl;
        std::cout << "  Min run of duplicates: " << min_run << std::endl;
        std::cout << "  Average run of duplicates: " << avg_run << std::endl;
        std::cout << "  Longest run of duplicates: " << max_run << std::endl;
    } else {
        std::cout << "  No duplicates found." << std::endl;
    }

    uint32_t final_size = static_cast<uint32_t>(new_size);
    uint32_t final_dim = static_cast<uint32_t>(d_long);

    // writer.write(reinterpret_cast<const char*>(&final_size), sizeof(uint32_t));
    // writer.write(reinterpret_cast<const char*>(&final_dim), sizeof(uint32_t));

    if (dups_writer.is_open()) {
        uint32_t num_buckets_u32 = static_cast<uint32_t>(num_buckets);
        // Binary format for duplicates file:
        // [uint32_t num_buckets]
        // For each bucket:
        //   [uint32_t num_items_in_bucket]
        //   [data for item 1]
        //   [data for item 2]
        //   ...
        dups_writer.write(reinterpret_cast<const char*>(&num_buckets_u32), sizeof(uint32_t));
        for (const auto& bucket : duplicate_buckets) {
            uint32_t bucket_size_u32 = static_cast<uint32_t>(bucket.size());
            dups_writer.write(reinterpret_cast<const char*>(&bucket_size_u32), sizeof(uint32_t));
            for (uint32_t point_index : bucket) {
                dups_writer.write(reinterpret_cast<const char*>(&point_index), sizeof(uint32_t));
            }
        }
        dups_writer.close();
        std::cout << "Duplicates written to: " << dups_path << std::endl;
    }

    // for (size_t i = 0; i < B.size(); ++i) {
    //     if (to_keep[i]) {
    //         auto dat = B.location(i);
    //         writer.write(reinterpret_cast<const char*>(dat), final_dim * sizeof(typename Point::T));
    //     }
    // }
    writer.close();
    std::cout << "Deduplicated dataset written to: " << out_path << std::endl;
    // --- Optional: Write out dataset with true duplicates omitted ---
    if (true_dups_out_path && *true_dups_out_path) {
        std::cout << "\n--- Analyzing duplicate buckets ---" << std::endl;
        int exact_dup_buckets = 0;
        size_t total_points_in_exact_buckets = 0;
        size_t total_points_that_are_exact_dups = 0;
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
        }

        std::cout << "5a. Number of buckets with all exact duplicates: " << exact_dup_buckets << " / " << num_buckets << std::endl;
        std::cout << "5b. Total number of points in exact duplicate buckets: " << total_points_in_exact_buckets << std::endl;
        std::cout << "5c. Total points that are exact duplicates (even in mixed buckets): " << total_points_that_are_exact_dups << std::endl;

        std::cout << "\n--- Writing dataset with true duplicates omitted to " << true_dups_out_path << " ---" << std::endl;

        //parlay::sequence<bool> to_keep = parlay::tabulate(n, [&](size_t i) { return !to_omit[i]; });
        size_t new_size = parlay::reduce(
            parlay::tabulate(n, [&](size_t i) -> size_t { return !static_cast<bool>(to_omit[i]); }),
            parlay::addm<size_t>());
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
                if (!static_cast<bool>(to_omit[i])) {
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
    commandLine P(argc, argv, "-base_path <base_path> -out_path <out_path> -dups_path <dups_path> -data_type <data_type> -dist_func <dist_func>");
    auto base_path = P.getOptionValue("-base_path");
    auto out_path = P.getOptionValue("-out_path");
    auto dups_path = P.getOptionValue("-dups_path");
    auto data_type = P.getOptionValue("-data_type");
    auto dist_func = P.getOptionValue("-dist_func");
    auto true_dups_out_path = P.getOptionValue("-true_dups_out_path");

    if (std::string(dist_func) == "Euclidian") {
        if (std::string(data_type) == "uint8") {
            PointRange<Euclidian_Point<uint8_t>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path, true_dups_out_path);
        } else if (std::string(data_type) == "int8") {
            PointRange<Euclidian_Point<int8_t>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path, true_dups_out_path);
        } else if (std::string(data_type) == "float") {
            PointRange<Euclidian_Point<float>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path, true_dups_out_path);
        } else {
            std::cout << "Unsupported data type for Euclidian distance" << std::endl;
        }
    } else if (std::string(dist_func) == "Mips") {
         if (std::string(data_type) == "float") {
            PointRange<Mips_Point<float>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path, true_dups_out_path);
        } else {
            std::cout << "Unsupported data type for MIPS" << std::endl;
        }
    } else {
        std::cout << "Unsupported distance function" << std::endl;
    }

    return 0;
}
