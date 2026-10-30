#include <iostream>
#include <fstream>
#include <cstdint>
#include <cstring>
#include <algorithm>
#include <set>
#include <utility>
#include <vector>

#include "../bench/parse_command_line.h"
#include "../utils/types.h"
#include <parlay/parallel.h>
#include <parlay/primitives.h>
#include <parlay/internal/get_time.h>
#include <hnswlib/hnswlib.h>

namespace parlayANN {

static std::string kAlgType = "HNSWLib";

struct HNSWRunResult {
    float recall;
    float QPS;

    float avg_dist_cmps;
    float avg_visited;

    int k;
    int ef;

    size_t num_queries;
};

template <typename PointRange, typename SearchIndex, typename indexType>
HNSWRunResult check_hnsw_recall(SearchIndex &I,
        PointRange &Query_Points,
        groundTruth<indexType> &GT,
        size_t ef,
        size_t k,
        bool verbose = false) {
    if (k > I.getMaxElements()) {
        std::cout << "Error: k (" << k << ") is larger than index size ("
                  << I.getMaxElements() << ")" << std::endl;
        abort();
    }
    if (Query_Points.size() != GT.size()) {
        std::cout << "Error: number of query points (" << Query_Points.size()
                  << ") does not match ground truth size (" << GT.size()
                  << ")" << std::endl;
        abort();
    }

    HNSWRunResult result;
    result.ef = ef;
    result.k = k;
    result.num_queries = Query_Points.size();

    I.setEf(ef);

    // Run without metrics collection to get query time
    parlay::internal::timer t;
    t.next_time();
    auto nghs = parlay::tabulate(Query_Points.size(), [&] (size_t i) {
        return I.searchKnn((void*) Query_Points[i].data(), k);
    });
    float query_time = t.next_time();
    result.QPS = (float)Query_Points.size() / query_time;

    // Compute recall
    size_t num_correct = 0;
    for (size_t i = 0; i < Query_Points.size(); i++) {
        std::set<indexType> reported_nbhs;
        if (nghs[i].size() != k) {
            std::cout << "bad number of neighbors reported: "
                      << nghs[i].size() << std::endl;
            abort();
        }
        while (!nghs[i].empty()) {
            reported_nbhs.insert(nghs[i].top().second);
            nghs[i].pop();
        }
        if (reported_nbhs.size() != k) {
            std::cout << "duplicate entries in reported neighbors" << std::endl;
            abort();
        }
        for (size_t l = 0; l < k; l++) {
            if (reported_nbhs.find((GT.coordinates(i,l))) !=
                reported_nbhs.end()) {
                num_correct += 1;
            }
        }
    }
    result.recall = (float)num_correct / (k * Query_Points.size());
    
    // Run again to get distance computations and hops
    I.metric_distance_computations.store(0);
    I.metric_hops.store(0);
    parlay::parallel_for(0, Query_Points.size(), [&] (size_t i) {
        I.searchKnnWithMetrics((void*) Query_Points[i].data(), k);
    });
    result.avg_dist_cmps = (float)I.metric_distance_computations.load() / Query_Points.size();
    result.avg_visited = (float)I.metric_hops.load() / Query_Points.size();

    if (verbose)
        std::cout << "HNSWLib recall@" << k << ": " << result.recall
                  << ", ef: " << result.ef
                  << ", QPS: " << result.QPS
                  << ", avg dist comps: " << result.avg_dist_cmps
                  << ", avg visited: " << result.avg_visited
                  << std::endl;
    return result;
}

template <typename Point, typename PointRange, typename indexType>
void ANN(long k, BuildParams &BP, PointRange &Query_Points,
         groundTruth<indexType> GT, char *res_file, char *exp_prefix,
         PointRange &Points, commandLine &P) {
    #if defined(USE_DATATYPE_FLOAT_T)
        using distType = float;
        #if defined(USE_DISTANCE_EUCLIDEAN)
            using SpaceType = hnswlib::L2Space;
        #elif defined(USE_DISTANCE_MIPS)
            using SpaceType = hnswlib::InnerProductSpace;
        #else
            static_assert(false, "Unknown distance type");
        #endif
    #elif defined(USE_DATATYPE_INT8_T)
        using distType = int;
        #if defined(USE_DISTANCE_EUCLIDEAN)
            using SpaceType = hnswlib::L2SpaceI8;
        #else
            static_assert(false, "Small int data type only supports Euclidean distance");
        #endif
    #elif defined(USE_DATATYPE_UINT8_T)
        using distType = int;
        #if defined(USE_DISTANCE_EUCLIDEAN)
            using SpaceType = hnswlib::L2SpaceU8;
        #else
            static_assert(false, "Small int data type only supports Euclidean distance");
        #endif
    #else
        static_assert(false, "Unknown data type");
    #endif

    std::cout << "Building HNSWLib index with M = " << BP.M << ", efc = " << BP.ef_construction << std::endl;

    parlay::internal::timer t;
    t.next_time();

    using findex = hnswlib::HierarchicalNSW<distType>;
    SpaceType space(Points.dimension());
    findex I(&space, Points.size(), BP.M, BP.ef_construction, 100ull, false);

    parlay::parallel_for(0, Points.size(), [&] (long i) {
        I.addPoint((void*) Points[i].data(), (size_t) i);
    });

    std::cout << "HNSWLib index built in " << t.next_time() << " seconds" << std::endl;
    std::cout << "Performing HNSWLib recall tests..." << std::endl;

    std::vector<size_t> ef_values = {10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 45, 50, 55, 60, 65, 70, 80, 90,
        100, 120, 140, 160, 180, 200, 225, 250, 275, 300, 375, 500, 750, 1000};
    std::vector<HNSWRunResult> results;
    for (auto ef : ef_values) {
        results.push_back(check_hnsw_recall<PointRange, findex, indexType>(I, Query_Points, GT, ef, k, BP.verbose));
    }

    // Find best runs for each recall bucket
    parlay::sequence<float> buckets = {0, .1, .2, .3,  .4,  .5,  .6, .7, .75,  .8, .85,
      .9, .93, .95, .97, .98, .99, .995, .999, .9995, .9999, .99995, .99999};
    parlay::sequence<HNSWRunResult> best_runs(buckets.size());
    for (auto &result : results) {
        size_t i = 0;
        for (; i < buckets.size() - 1; i++) {
            if (result.recall < buckets[i + 1]) break;
        }
        if (best_runs[i].num_queries == 0 || best_runs[i].QPS < result.QPS) {
            best_runs[i] = result;
        }
    }

    for (size_t i = 0; i < best_runs.size(); i++) {
        auto &result = best_runs[i];
        if (result.num_queries > 0) {
            std::cout << "HNSWLib best run for recall >= " << buckets[i]
                      << ": ef: " << result.ef
                      << ", k: " << result.k
                      << ", recall: " << result.recall
                      << ", QPS: " << result.QPS
                      << ", avg dist comps: " << result.avg_dist_cmps
                      << ", avg visited: " << result.avg_visited
                      << std::endl;
        }
    }

    if (res_file != NULL) {
        std::ofstream csv_writer(res_file, std::ios::app);
        if (!csv_writer.is_open()) {
            std::cout << "Error: cannot open result file " << res_file << std::endl;
            abort();
        }
        for (size_t i = 0; i < best_runs.size(); i++) {
            auto &result = best_runs[i];
            if (result.num_queries > 0) {
                csv_writer << (exp_prefix != NULL ? exp_prefix : "") << ","
                        << result.num_queries << ","
                        << buckets[i] << ","
                        << result.recall << ","
                        << result.QPS << ","
                        << result.avg_dist_cmps << ","
                        << result.avg_dist_cmps << ","
                        << result.avg_visited << ","
                        << result.avg_visited << ","
                        << result.k << ","
                        << result.ef << ","
                        << 0 << ","
                        << 0 << std::endl;
            }
        }
        csv_writer << std::endl << std::endl;
        csv_writer.close();
    }
}

} // namespace parlayANN