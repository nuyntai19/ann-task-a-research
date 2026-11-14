#!/usr/bin/env python3
"""Instrument PiPNN's build with distance counters (idempotent source patch).

PiPNN evaluates distances in three places:
  1. leader assignment during clustering  -- already counted (COMPARISONS)
  2. leaf exact kNN: Eigen rank-update GEMM over each leaf, N(N-1)/2 pairs
  3. alpha-prune in ExportToGraph: scalar Points[a].distance(Points[b])
Adds LEAF_PAIRS / LEAF_POINTS (2) and PRUNE_DISTANCES (3) and prints
  BUILD_DISTANCES_PIPNN clustering=<c> leaf=<l> prune=<p> total=<t>
so PiPNN's build cost is comparable, in distance evaluations, with Vamana's
BUILD_DISTANCES and fg's count.

    python3 pipnn_build_distance_counter.py <PiPNN repo root>
"""
import sys, os
root = sys.argv[1]
def patch(path, edits):
    s = open(path).read()
    if 'GRAFT-COUNTER' in s:
        print('already patched:', path); return
    for old, new in edits:
        assert old in s, (path, old[:60])
        s = s.replace(old, new, 1)
    open(path, 'w').write(s); print('patched:', path)

P = os.path.join(root, 'algorithms/PipNN/pipnn.h')
patch(P, [
 ("  std::atomic<size_t> COMPARISONS = 0;",
  "  std::atomic<size_t> COMPARISONS = 0;\n"
  "  std::atomic<size_t> LEAF_PAIRS = 0;   // GRAFT-COUNTER: leaf GEMM pairs N(N-1)/2\n"
  "  std::atomic<size_t> LEAF_POINTS = 0;  // GRAFT-COUNTER: sum of leaf sizes"),
 ("    leaf_count++;\n    EigenKNN(G, Points, active_indices);",
  "    leaf_count++;\n"
  "    { size_t N = active_indices.size();\n"
  "      LEAF_PAIRS.fetch_add(N * (N - 1) / 2, std::memory_order_relaxed);\n"
  "      LEAF_POINTS.fetch_add(N, std::memory_order_relaxed); }\n"
  "    EigenKNN(G, Points, active_indices);"),
 ("    std::cout << \"Average distance traversed: \" << (dist_traversed.load() / Points.size()) << std::endl;",
  "    std::cout << \"Average distance traversed: \" << (dist_traversed.load() / Points.size()) << std::endl;\n"
  "    { size_t c = C.COMPARISONS.load(), l = C.LEAF_PAIRS.load(), p = prune_dist.load();\n"
  "      std::cout << \"LEAF_POINTS \" << C.LEAF_POINTS.load() << \" leaves \" << leaf_count.load() << std::endl;\n"
  "      std::cout << \"BUILD_DISTANCES_PIPNN clustering=\" << c << \" leaf=\" << l\n"
  "                << \" prune=\" << p << \" total=\" << (c + l + p) << std::endl; }"),
])

U = os.path.join(root, 'algorithms/PipNN/pipnn_utils.h')
patch(U, [
 ("std::atomic<size_t> dist_traversed(0);",
  "std::atomic<size_t> dist_traversed(0);\n"
  "std::atomic<size_t> prune_dist(0);  // GRAFT-COUNTER: scalar distances in the alpha-prune"),
 ("    float inverse_alpha = 1.0 / alpha;\n    size_t candidate_idx = 0;",
  "    float inverse_alpha = 1.0 / alpha;\n    size_t candidate_idx = 0;\n    size_t nd_local = 0;"),
 ("        const auto dist_starprime = Points[p_star].distance(Points[p_prime]);",
  "        ++nd_local;\n        const auto dist_starprime = Points[p_star].distance(Points[p_prime]);"),
 ("    dist_traversed.fetch_add(candidate_idx, std::memory_order_relaxed);",
  "    dist_traversed.fetch_add(candidate_idx, std::memory_order_relaxed);\n"
  "    prune_dist.fetch_add(nd_local, std::memory_order_relaxed);"),
])
