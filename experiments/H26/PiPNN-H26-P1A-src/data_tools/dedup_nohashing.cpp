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


template<typename PointRange>
void deduplicate_dataset(PointRange& B, const char* out_path, const char* dups_path) {
    using Point = typename PointRange::Point;
    using indexType = uint32_t;
    std::ofstream writer(out_path, std::ios::binary);
    if (!writer.is_open()) {
        std::cerr << "Error opening output file: " << out_path << std::endl;
        return;
    }

    // std::ofstream dups_writer;
    // if (dups_path && dups_path[0] != '\0') {
    //     dups_writer.open(dups_path, std::ios::binary);
    //     if (!dups_writer.is_open()) {
    //         std::cerr << "Warning: Could not open duplicates output file: " << dups_path << std::endl;
    //     }
    // }

    auto d_long = B.dimension();
    parlay::sequence<bool> to_keep(B.size(), true);
    auto ids = parlay::tabulate(B.size(), [&](indexType i) { return i; });

    for (auto i = 0; i < B.size(); ++i) {
        if (to_keep[i]) {
            parlay::parallel_for(i + 1, B.size(), [&](size_t j) {
                if (to_keep[j]) {
                    if (B[i] == B[j]) {
                        to_keep[j] = false;
                    }
                }
            });
        }
    if (i % 1000 == 0) std::cout << "computed: " << i << "/" << B.size() << "\r" << std::flush;
    }

    size_t new_size = parlay::reduce(to_keep, parlay::addm<size_t>());
    std::cout << "Original dataset size: " << B.size() << std::endl;
    std::cout << "New dataset size after deduplication: " << new_size << std::endl;
    

    uint32_t final_size = static_cast<uint32_t>(new_size);
    uint32_t final_dim = static_cast<uint32_t>(d_long);

    writer.write(reinterpret_cast<const char*>(&final_size), sizeof(uint32_t));
    writer.write(reinterpret_cast<const char*>(&final_dim), sizeof(uint32_t));

    // if (dups_writer.is_open()) {
    //     uint32_t num_buckets_u32 = static_cast<uint32_t>(num_buckets);
    //     // Binary format for duplicates file:
    //     // [uint32_t num_buckets]
    //     // For each bucket:
    //     //   [uint32_t num_items_in_bucket]
    //     //   [data for item 1]
    //     //   [data for item 2]
    //     //   ...
    //     dups_writer.write(reinterpret_cast<const char*>(&num_buckets_u32), sizeof(uint32_t));
    //     for (const auto& bucket : duplicate_buckets) {
    //         uint32_t bucket_size_u32 = static_cast<uint32_t>(bucket.size());
    //         dups_writer.write(reinterpret_cast<const char*>(&bucket_size_u32), sizeof(uint32_t));
    //         for (uint32_t point_index : bucket) {
    //             dups_writer.write(reinterpret_cast<const char*>(&point_index), sizeof(uint32_t));
    //         }
    //     }
    //     dups_writer.close();
    //     std::cout << "Duplicates written to: " << dups_path << std::endl;
    // }

    for (size_t i = 0; i < B.size(); ++i) {
        if (to_keep[i]) {
            auto dat = B.location(i);
            writer.write(reinterpret_cast<const char*>(dat), final_dim * sizeof(typename Point::T));
        }
    }
    writer.close();
    std::cout << "Deduplicated dataset written to: " << out_path << std::endl;
}

    


int main(int argc, char* argv[]) {
    commandLine P(argc, argv, "-base_path <base_path> -out_path <out_path> -dups_path <dups_path> -data_type <data_type> -dist_func <dist_func>");
    auto base_path = P.getOptionValue("-base_path");
    auto out_path = P.getOptionValue("-out_path");
    auto dups_path = P.getOptionValue("-dups_path");
    auto data_type = P.getOptionValue("-data_type");
    auto dist_func = P.getOptionValue("-dist_func");

    if (std::string(dist_func) == "Euclidian") {
        if (std::string(data_type) == "uint8") {
            PointRange<Euclidian_Point<uint8_t>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path);
        } else if (std::string(data_type) == "int8") {
            PointRange<Euclidian_Point<int8_t>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path);
        } else if (std::string(data_type) == "float") {
            PointRange<Euclidian_Point<float>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path);
        } else {
            std::cout << "Unsupported data type for Euclidian distance" << std::endl;
        }
    } else if (std::string(dist_func) == "Mips") {
         if (std::string(data_type) == "float") {
            PointRange<Mips_Point<float>> B(base_path);
            deduplicate_dataset(B, out_path, dups_path);
        } else {
            std::cout << "Unsupported data type for MIPS" << std::endl;
        }
    } else {
        std::cout << "Unsupported distance function" << std::endl;
    }

    return 0;
}