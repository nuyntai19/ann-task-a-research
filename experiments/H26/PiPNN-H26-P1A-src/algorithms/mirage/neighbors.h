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
#include <faiss/IndexMIRAGE.h>

namespace parlayANN {

static std::string kAlgType = "Mirage";

struct MirageRunResult {
    float recall;
    float QPS;

    int k;
    int ef;

    size_t num_queries;
};

template <typename PointRange, typename SearchIndex, typename indexType>
MirageRunResult check_mirage_recall(SearchIndex &I,
        float *query_data,
        groundTruth<indexType> &GT,
        size_t ef,
        size_t k,
        bool verbose = false) {
    if (k > I.ntotal) {
        std::cout << "Error: k (" << k << ") is larger than index size ("
                  << I.ntotal << ")" << std::endl;
        abort();
    }

    MirageRunResult result;
    result.ef = ef;
    result.k = k;
    result.num_queries = GT.size();

    I.hierarchy.hnsw.efSearch = ef;
    auto neighbors = parlay::sequence<faiss::idx_t>::uninitialized(GT.size() * k);
    auto distances = parlay::sequence<float>::uninitialized(GT.size() * k);

    parlay::internal::timer t;
    t.next_time();
    I.search(GT.size(), query_data, k, distances.data(), neighbors.data());
    float query_time = t.next_time();
    result.QPS = (float)GT.size() / query_time;

    size_t num_correct = 0;
    for (size_t i = 0; i < GT.size(); i++) {
        std::set<indexType> reported_nbhs;
        for (size_t j = 0; j < k; j++) {
            reported_nbhs.insert(neighbors[i * k + j]);
        }
        for (size_t l = 0; l < k; l++) {
            if (reported_nbhs.find((GT.coordinates(i,l))) !=
                reported_nbhs.end()) {
                num_correct += 1;
            }
        }
    }
    result.recall = (float)num_correct / (k * GT.size());

    if (verbose)
        std::cout << "Mirage recall@" << k << ": " << result.recall
                  << ", ef: " << result.ef
                  << ", QPS: " << result.QPS
                  << std::endl;
    return result;
}

template <typename Point, typename PointRange, typename indexType>
void ANN(long k, BuildParams &BP, PointRange &Query_Points,
         groundTruth<indexType> GT, char *res_file, char *exp_prefix,
         PointRange &Points, commandLine &P) {
    faiss::MetricType metric;
    #if defined(USE_DISTANCE_EUCLIDEAN)
        metric = faiss::METRIC_L2;
    #elif defined(USE_DISTANCE_MIPS)
        metric = faiss::METRIC_INNER_PRODUCT;
    #else
        static_assert(false, "Unknown distance type");
    #endif

    float *data;
    #if defined(USE_DATATYPE_FLOAT_T)
        data = (float*)Points.data();
    #elif defined(USE_DATATYPE_INT8_T) || defined(USE_DATATYPE_UINT8_T)
        std::cout << "Converting data to float for Faiss Mirage index" << std::endl;
        auto database = parlay::sequence<float>::uninitialized(Points.size() * Points.dimension());
        parlay::parallel_for(0, Points.size(), [&] (size_t i) {
            for (size_t j = 0; j < Points.dimension(); j++) {
                database[i * Points.dimension() + j] = static_cast<float>(Points[i][j]);
            }
        });
        data = database.data();
    #else
        static_assert(false, "Unknown data type");
    #endif

    std::cout << "Building Mirage index with M = " << BP.M << ", S = " << BP.S
              << ", R = " << BP.R << ", iter = " << BP.num_iter << std::endl;
    
    parlay::internal::timer t("ANN");
    t.next_time();

    using findex = faiss::IndexMirage;
    findex I(Points.dimension(), BP.M, metric);
    I.mirage.S = BP.S;
    I.mirage.R = BP.R;
    I.mirage.iter = BP.num_iter;
    I.verbose = BP.verbose;
    
    I.add(Points.size(), data);
    std::cout << "Mirage index built in " << t.next_time() << " seconds." << std::endl;

    if (Query_Points.size() != GT.size()) {
        std::cout << "Error: number of query points (" << Query_Points.size()
                  << ") does not match groundtruth size (" << GT.size() << ")"
                  << std::endl;
        abort();
    }

    float *query_data;
    #if defined(USE_DATATYPE_FLOAT_T)
        query_data = (float*)Query_Points.data();
    #elif defined(USE_DATATYPE_INT8_T) || defined(USE_DATATYPE_UINT8_T)
        std::cout << "Converting query data to float for Faiss Mirage index" << std::endl;
        auto queries = parlay::sequence<float>::uninitialized(Query_Points.size() * Query_Points.dimension());
        parlay::parallel_for(0, Query_Points.size(), [&] (size_t i) {
            for (size_t j = 0; j < Query_Points.dimension(); j++) {
                queries[i * Query_Points.dimension() + j] = static_cast<float>(Query_Points[i][j]);
            }
        });
        query_data = queries.data();
    #else
        static_assert(false, "Unknown data type");
    #endif
    
    std::vector<size_t> ef_values = {10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 45, 50, 55, 60, 65, 70, 80, 90,
        100, 120, 140, 160, 180, 200, 225, 250, 275, 300, 375, 500, 750, 1000};
    std::vector<MirageRunResult> results;
    for (auto ef : ef_values) {
        results.push_back(check_mirage_recall<PointRange, findex, indexType>(I, query_data, GT, ef, k, BP.verbose));
    }

    parlay::sequence<float> buckets = {0, .1, .2, .3,  .4,  .5,  .6, .7, .75,  .8, .85,
        .9, .93, .95, .97, .98, .99, .995, .999, .9995, .9999, .99995, .99999};
    parlay::sequence<MirageRunResult> best_runs(buckets.size());
    for (auto &result : results) {
        size_t i = 0;
        for (; i < buckets.size() - 1; i++) {
            if (result.recall < buckets[i + 1]) break;
        }
        if (best_runs[i].recall < result.recall ||
            best_runs[i].recall == 0) {
            best_runs[i] = result;
        }
    }

    for (size_t i = 0; i < best_runs.size(); i++) {
        if (best_runs[i].num_queries == 0) continue;
        std::cout << "Mirage best run for recall >= " << buckets[i]
                  << ": recall " << best_runs[i].recall
                  << ", ef " << best_runs[i].ef
                  << ", QPS " << best_runs[i].QPS
                  << std::endl;
    }

    if (res_file != nullptr) {
        std::ofstream csv_writer(res_file, std::ios::app);
        if (!csv_writer.is_open()) {
            std::cout << "Error: cannot open result file " << res_file << std::endl;
            abort();
        }
        for (size_t i = 0; i < best_runs.size(); i++) {
            auto &result = best_runs[i];
            if (result.num_queries > 0) {
                csv_writer << (exp_prefix != nullptr ? exp_prefix : "") << ","
                        << result.num_queries << ","
                        << buckets[i] << ","
                        << result.recall << ","
                        << result.QPS << ","
                        << "0,0,0,0,"
                        << result.k << ","
                        << result.ef << ","
                        << "0,0" << std::endl;
            }
        }
        csv_writer << std::endl << std::endl;
        csv_writer.close();
    }
}

}  // namespace parlayANN