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
#include <map>

using namespace parlayANN;

template<typename PointRange>
void check_distances(const char* gt_path, PointRange& B, PointRange& Q) {
    std::ifstream reader(gt_path, std::ios::binary);
    if (!reader.is_open()) {
        std::cerr << "Error opening groundtruth file: " << gt_path << std::endl;
        return;
    }

    uint32_t num_queries, k;
    reader.read(reinterpret_cast<char*>(&num_queries), sizeof(uint32_t));
    reader.read(reinterpret_cast<char*>(&k), sizeof(uint32_t));

    if (num_queries != Q.size()) {
        std::cerr << "Error: Number of queries in groundtruth file (" << num_queries 
                  << ") does not match number of query points (" << Q.size() << ")" << std::endl;
        return;
    }

    std::cout << "Groundtruth file contains " << num_queries << " queries with " << k << " neighbors each." << std::endl;

    std::vector<int32_t> ids(num_queries * k);
    std::vector<float> distances(num_queries * k);

    reader.read(reinterpret_cast<char*>(ids.data()), num_queries * k * sizeof(int32_t));
    reader.read(reinterpret_cast<char*>(distances.data()), num_queries * k * sizeof(float));
    reader.close();

    size_t identical_distance_pairs = 0;
    size_t identical_point_pairs = 0;

    for (uint32_t i = 0; i < num_queries; ++i) {
        std::map<float, std::vector<int>> distance_map;
        for (uint32_t j = 0; j < k; ++j) {
            distance_map[distances[i * k + j]].push_back(ids[i * k + j]);
        }

        for (auto const& [dist, neighbor_ids] : distance_map) {
            if (neighbor_ids.size() > 1) {
                for (size_t l = 0; l < neighbor_ids.size(); ++l) {
                    for (size_t m = l + 1; m < neighbor_ids.size(); ++m) {
                        identical_distance_pairs++;
                        auto p1 = B[neighbor_ids[l]];
                        auto p2 = B[neighbor_ids[m]];
                        bool points_are_identical = true;
                        if (p1 == p2) {
                            points_are_identical = true;
                        } else {
                            points_are_identical = false;
                        }
                        if (points_are_identical) {
                            identical_point_pairs++;
                        }
                    }
                }
            }
        }
    }

    std::cout << "Found " << identical_distance_pairs << " pairs of neighbors with identical distances." << std::endl;
    std::cout << "Found " << identical_point_pairs << " pairs of neighbors that were identical points." << std::endl;
}

int main(int argc, char* argv[]) {
    commandLine P(argc, argv, "-gt_path <groundtruth_file> -base_path <base_path> -query_path <query_path> -data_type <data_type> -dist_func <dist_func>");
    auto gt_path = P.getOptionValue("-gt_path");
    auto base_path = P.getOptionValue("-base_path");
    auto query_path = P.getOptionValue("-query_path");
    auto data_type = P.getOptionValue("-data_type");
    auto dist_func = P.getOptionValue("-dist_func");

    if (!gt_path || !base_path || !query_path || !data_type || !dist_func) {
        std::cout << "Usage: " << argv[0] << " -gt_path <groundtruth_file> -base_path <base_path> -query_path <query_path> -data_type <data_type> -dist_func <dist_func>" << std::endl;
        return 1;
    }

    if (std::string(dist_func) == "Euclidian") {
        if (std::string(data_type) == "uint8") {
            PointRange<Euclidian_Point<uint8_t>> B(base_path);
            PointRange<Euclidian_Point<uint8_t>> Q(query_path);
            check_distances(gt_path, B, Q);
        } else if (std::string(data_type) == "int8") {
            PointRange<Euclidian_Point<int8_t>> B(base_path);
            PointRange<Euclidian_Point<int8_t>> Q(query_path);
            check_distances(gt_path, B, Q);
        } else if (std::string(data_type) == "float") {
            PointRange<Euclidian_Point<float>> B(base_path);
            PointRange<Euclidian_Point<float>> Q(query_path);
            check_distances(gt_path, B, Q);
        } else {
            std::cout << "Unsupported data type for Euclidian distance" << std::endl;
        }
    } else if (std::string(dist_func) == "Mips") {
         if (std::string(data_type) == "float") {
            PointRange<Mips_Point<float>> B(base_path);
            PointRange<Mips_Point<float>> Q(query_path);
            check_distances(gt_path, B, Q);
        } else {
            std::cout << "Unsupported data type for MIPS" << std::endl;
        }
    } else {
        std::cout << "Unsupported distance function" << std::endl;
    }

    return 0;
}

