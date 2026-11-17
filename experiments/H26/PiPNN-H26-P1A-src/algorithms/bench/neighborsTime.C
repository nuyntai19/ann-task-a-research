// This code is part of the Problem Based Benchmark Suite (PBBS)
// Copyright (c) 2011 Guy Blelloch and the PBBS team
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights (to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to
// permit persons to whom the Software is furnished to do so, subject to
// the following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
// NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
// LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
// OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
// WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#include <iostream>
#include <algorithm>
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parse_command_line.h"
#include "time_loop.h"
#include "../utils/NSGDist.h"
#include "../utils/euclidian_point.h"
#include "../utils/point_range.h"
#include "../utils/mips_point.h"
#include "../utils/graph.h"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifdef ALG_HNSW
  #include <hnswlib/space_l2.h>
  #include <hnswlib/space_ip.h>
#endif

using namespace parlayANN;

// *************************************************************
//  TIMING
// *************************************************************

using uint = unsigned int;


template<typename Point, typename PointRange, typename indexType>
void timeNeighbors(PointRange &Query_Points, long k,
		   BuildParams &BP, char* outFile,
		   groundTruth<indexType> GT, char* res_file, char* exp_prefix, PointRange &Points, commandLine& P)
{
    time_loop(1, 0,
      [&] () {},
      [&] () {
        ANN<Point, PointRange, indexType>(k, BP, Query_Points, GT, res_file, exp_prefix, Points, P);
      },
      [&] () {});
}

int main(int argc, char* argv[]) {
    commandLine P(argc,argv,
    "[-a <alpha>] [-d <delta>] [-R <deg>]"
        "[-L <bm>] [-k <k> ]  [-gt_path <g>] [-query_path <qF>]"
        "[-graph_path <gF>] [-graph_outfile <oF>] [-res_path <rF>]" "[-num_passes <np>]"
        "[-memory_flag <algoOpt>] [-mst_deg <q>] [-num_clusters <nc>] [-cluster_size <cs>]"
        "[-base_path <b>] <inFile>");

  char* iFile = P.getOptionValue("-base_path");
  char* oFile = P.getOptionValue("-graph_outfile");
  char* gFile = P.getOptionValue("-graph_path");
  char* qFile = P.getOptionValue("-query_path");
  char* cFile = P.getOptionValue("-gt_path");
  char* rFile = P.getOptionValue("-res_path");
  char* exp_prefix = P.getOptionValue("-exp_prefix");
  long Q = P.getOptionIntValue("-Q", 0);
  long R = P.getOptionIntValue("-R", 0);
  if(R<0) P.badArgument();
  long L = P.getOptionIntValue("-L", 0);
  if(L<0) P.badArgument();
  long pivot_type = P.getOptionIntValue("-pivot_type", 0);
  long MST_deg = P.getOptionIntValue("-mst_deg", 2);
  if(MST_deg < 0) P.badArgument();
  long num_clusters = P.getOptionIntValue("-num_clusters", 1);
  if(num_clusters<0) P.badArgument();
  long cluster_size = P.getOptionIntValue("-cluster_size", 1024);
  if(cluster_size<0) P.badArgument();
  double radius  = P.getOptionDoubleValue("-radius", 0.0);
  double radius_2  = P.getOptionDoubleValue("-radius_2", radius);
  long k = P.getOptionIntValue("-k", 0);
  if (k > 1000 || k < 0) P.badArgument();
  double alpha = P.getOptionDoubleValue("-alpha", 1.1);
  int num_passes = P.getOptionIntValue("-num_passes", 1);
  int two_pass = P.getOptionIntValue("-two_pass", 0);
  if(two_pass > 1 | two_pass < 0) P.badArgument();
  if (two_pass == 1) num_passes = 2;
  double delta = P.getOptionDoubleValue("-delta", 0);
  if(delta<0) P.badArgument();
  int quantize = P.getOptionIntValue("-quantize_bits", 0);
  int fanout = P.getOptionIntValue("-fanout", 1);
  int quantize_build = P.getOptionIntValue("-quantize_mode", 0);
  bool verbose = P.getOption("-verbose");
  bool normalize = P.getOption("-normalize");
  double trim = P.getOptionDoubleValue("-trim", 0.0); // not used
  bool self = P.getOption("-self");
  int rerank_factor = P.getOptionIntValue("-rerank_factor", 100);
  bool range = P.getOption("-range");
  long prune_degree =
      P.getOptionLongValue("-prune_degree", 64);
  bool vary_degree = P.getOption("-vary_degree");
  int M = P.getOptionIntValue("-M", 16);
  int ef_construction = P.getOptionIntValue("-efc", 200);
  std::cout << "Vary degree = " << vary_degree << std::endl;
  long S = P.getOptionIntValue("-S", 0);
  long num_iter = P.getOptionIntValue("-num_iter", 0);

  // this integer represents the number of random edges to start with for
  // inserting in a single batch per round
  int single_batch = P.getOptionIntValue("-single_batch", 0);

  // std::string kAlgType = ANNInfo::kAlgType;
  BuildParams BP = BuildParams(kAlgType, R, L, alpha, num_passes, fanout, num_clusters, cluster_size, MST_deg, delta, pivot_type, verbose, quantize_build, radius, radius_2, self, range, single_batch, Q, trim, rerank_factor, prune_degree, vary_degree);
  BP.M = M;
  BP.ef_construction = ef_construction;
  BP.S = S;
  BP.num_iter = num_iter;
  long maxDeg = BP.max_degree();

  groundTruth<uint> GT = groundTruth<uint>(cFile);

#if defined(USE_DATATYPE_FLOAT_T)
  #if defined (USE_DISTANCE_EUCLIDEAN)
      PointRange<Euclidian_Point<float>> Points(iFile);
      PointRange<Euclidian_Point<float>> Query_Points(qFile);
      if (normalize) {
        std::cout << "normalizing data" << std::endl;
        for (int i=0; i < Points.size(); i++)
          Points[i].normalize();
        for (int i=0; i < Query_Points.size(); i++)
          Query_Points[i].normalize();
      }
      if (quantize == 8) {
        std::cout << "quantizing data to 1 byte" << std::endl;
        using QT = uint8_t;
        using QPoint = Euclidian_Point<QT>;
        using PR = PointRange<QPoint>;
        PR Points_(Points);
        PR Query_Points_(Query_Points, Points_.params);
        timeNeighbors<QPoint, PR, uint>(Query_Points_, k, BP, oFile, GT, rFile, exp_prefix, Points_, P);
      } else if (quantize == 16) {
        std::cout << "quantizing data to 2 bytes" << std::endl;
        using Point = Euclidian_Point<uint16_t>;
        using PR = PointRange<Point>;
        PR Points_(Points);
        PR Query_Points_(Query_Points, Points_.params);
        timeNeighbors<Point, PR, uint>(Query_Points_, k, BP, oFile, GT, rFile, exp_prefix, Points_, P);
      } else {
        using Point = Euclidian_Point<float>;
        using PR = PointRange<Point>;
        timeNeighbors<Point, PR, uint>(Query_Points, k, BP, oFile, GT, rFile, exp_prefix, Points, P);
      }
  #elif defined (USE_DISTANCE_MIPS)
      PointRange<Mips_Point<float>> Points(iFile);
      PointRange<Mips_Point<float>> Query_Points(qFile);
      if (normalize) {
        std::cout << "normalizing data" << std::endl;
        for (int i=0; i < Points.size(); i++)
          Points[i].normalize();
        for (int i=0; i < Query_Points.size(); i++)
          Query_Points[i].normalize();
      }
      if (quantize == 8) {
        std::cout << "quantizing data to 1 byte" << std::endl;
        using QT = int8_t;
        using Point = Quantized_Mips_Point<8>;
        using PR = PointRange<Point>;
        PR Points_(Points);
        PR Query_Points_(Query_Points, Points_.params);
        timeNeighbors<Point, PR, uint>(Query_Points_, k, BP, oFile, GT, rFile, exp_prefix, Points_, P);
      } else if (quantize == 16) {
        std::cout << "quantizing data to 2 bytes" << std::endl;
        using QT = int16_t;
        using Point = Quantized_Mips_Point<16>;
        using PR = PointRange<Point>;
        PR Points_(Points);
        PR Query_Points_(Query_Points, Points_.params);
        timeNeighbors<Point, PR, uint>(Query_Points_, k, BP, oFile, GT, rFile, exp_prefix, Points_, P);
      } else {
        using Point = Mips_Point<float>;
        using PR = PointRange<Point>;
        timeNeighbors<Point, PR, uint>(Query_Points, k, BP, oFile, GT, rFile, exp_prefix, Points, P);
      }
  #else
  #endif

#elif defined(USE_DATATYPE_INT8_T)
  #if defined (USE_DISTANCE_EUCLIDEAN)
        PointRange<Euclidian_Point<int8_t>> Points(iFile);
        PointRange<Euclidian_Point<int8_t>> Query_Points(qFile);
        timeNeighbors<Euclidian_Point<int8_t>, PointRange<Euclidian_Point<int8_t>>, uint>(Query_Points, k, BP,
          oFile, GT, rFile, exp_prefix, Points, P);
  #elif defined (USE_DISTANCE_MIPS)
        PointRange<Mips_Point<int8_t>> Points(iFile);
        PointRange<Mips_Point<int8_t>> Query_Points(qFile);
        timeNeighbors<Mips_Point<int8_t>, PointRange<Mips_Point<int8_t>>, uint>(Query_Points, k, BP,
          oFile, GT, rFile, exp_prefix, Points, P);
  #else
  #endif

#elif defined (USE_DATATYPE_UINT8_T)
  #if defined (USE_DISTANCE_EUCLIDEAN)
      PointRange<Euclidian_Point<uint8_t>> Points(iFile);
      PointRange<Euclidian_Point<uint8_t>> Query_Points(qFile);
      timeNeighbors<Euclidian_Point<uint8_t>, PointRange<Euclidian_Point<uint8_t>>, uint>(Query_Points, k, BP,
        oFile, GT, rFile, exp_prefix, Points, P);
  #elif defined (USE_DISTANCE_MIPS)
      PointRange<Mips_Point<uint8_t>> Points(iFile);
      PointRange<Mips_Point<uint8_t>> Query_Points(qFile);
      timeNeighbors<Mips_Point<uint8_t>, PointRange<Mips_Point<uint8_t>>, uint>(Query_Points, k, BP,
        oFile, GT, rFile, exp_prefix, Points, P);
  //  }
  #else
  #endif
#else

#endif



  return 0;
}

