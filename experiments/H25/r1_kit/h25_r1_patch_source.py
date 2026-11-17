#!/usr/bin/env python3
"""Conservative, reversible instrumentation of EXISTING PiPNN checkout.
Fails unless exact anchors match revision 443a328; use an isolated source copy.
Fix v2: disambiguate repeated dist_mat declaration by checking eigen_knn context.
"""
from __future__ import annotations
import argparse,hashlib,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def repl(s,old,new):
    n=s.count(old)
    if n!=1:raise RuntimeError('Expected exactly one source anchor, found '+str(n)+': '+repr(old[:130]))
    return s.replace(old,new,1)

def plan(source):
    util=(source/'algorithms/PipNN/pipnn_utils.h').read_text()
    main=(source/'algorithms/PipNN/pipnn.h').read_text()
    if 'h25_r1_hook.h' in util or 'h25_r1::' in main:raise RuntimeError('Already instrumented; restore first')
    util=repl(util,'#include "hwy/highway.h"','#include "hwy/highway.h"\n#include "h25_r1_hook.h"')
    util=repl(util,'void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG) {',
        'void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG, size_t h25_leaf_id) {')
    # The dist_mat declaration appears twice in this PiPNN revision.
    # Pin the replacement to eigen_knn after eigen_build_distmat instead of
    # replacing an ambiguous single-line occurrence anywhere in the header.
    util=repl(util,
        '  auto N = active_indices.size();\n  eigen_build_distmat(active_indices, Points);\n  float* dist_mat = (float*)get_dist_mat();',
        '  auto N = active_indices.size();\n  eigen_build_distmat(active_indices, Points);\n  float* dist_mat = (float*)get_dist_mat();\n  const bool h25_target = h25_r1::target_leaf(static_cast<uint32_t>(h25_leaf_id));\n  if (h25_target && MST_DEG != 2) h25_r1::fail("MST_DEG must be 2 for this H18 capture");')
    util=repl(util,'    uint32_t global_i = active_indices[i];\n    for (size_t j = 0; j < limit; j++) {',
'''    uint32_t global_i = active_indices[i];
    if (h25_target) {
      if (limit != 2) h25_r1::fail("Local Top2 row must contain 2 candidates");
      auto h25_first = unpackDouble(Q[0]);
      auto h25_second = unpackDouble(Q[1]);
      h25_r1::check_row(static_cast<uint32_t>(h25_leaf_id), global_i,
                        active_indices[h25_first.second], active_indices[h25_second.second]);
    }
    for (size_t j = 0; j < limit; j++) {''')
    util=repl(util,'      directed_edges.emplace_back(global_i, global_neighbor, dist);',
'''      if (h25_target) {
        uint32_t new_neighbor = h25_r1::replacement(static_cast<uint32_t>(h25_leaf_id), global_i, global_neighbor);
        if (new_neighbor != global_neighbor) {
          size_t local_new = N;
          for (size_t candidate = 0; candidate < N; ++candidate)
            if (active_indices[candidate] == new_neighbor) { local_new = candidate; break; }
          if (local_new >= N || local_new == i) h25_r1::fail("Replacement is not within original leaf");
          // Native eigen_build_distmat already computed this pair (upper-triangular access).
          dist = (i < local_new) ? dist_mat[local_new*N + i] : dist_mat[i*N + local_new];
          global_neighbor = new_neighbor;
        }
      }
      directed_edges.emplace_back(global_i, global_neighbor, dist);''')
    main=repl(main,'if (buckets[i].size() > 1) RunLeaf(G, Points, buckets[i]);',
              'if (buckets[i].size() > 1) RunLeaf(G, Points, buckets[i], i);')
    main=repl(main,'               parlay::sequence<uint32_t> &active_indices) {\n    leaf_count++;',
              '               parlay::sequence<uint32_t> &active_indices, size_t h25_leaf_id) {\n    leaf_count++;')
    main=repl(main,'                     parlay::sequence<uint32_t> &active_indices) {\n    eigen_knn(G, active_indices, Points, MST_DEG);',
              '                     parlay::sequence<uint32_t> &active_indices, size_t h25_leaf_id) {\n    eigen_knn(G, active_indices, Points, MST_DEG, h25_leaf_id);')
    main=repl(main,'      std::cout << "# of comparisons during clustering: " << COMPARISONS\n                << std::endl;\n    }\n  }',
'''      std::cout << "# of comparisons during clustering: " << COMPARISONS
                << std::endl;
    }
    h25_r1::verify();  // FAIL CLOSED before final graph export.
  }''')
    return util,main

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--mode',choices=['check','apply','restore'],required=True)
    a=ap.parse_args();p=a.repo.resolve();folder=p/'algorithms/PipNN'
    files=[folder/'pipnn_utils.h',folder/'pipnn.h']
    backs=[folder/'pipnn_utils.h.h25r1_original',folder/'pipnn.h.h25r1_original']
    dest=folder/'h25_r1_hook.h'
    for f in files:
        if not f.is_file():raise RuntimeError('Missing '+str(f))
    if a.mode=='restore':
        if not all(b.is_file() for b in backs):raise RuntimeError('Restore impossible; original backups missing')
        for f,b in zip(files,backs):shutil.copy2(b,f)
        print('RESTORED original two headers from backups (not deleting backups)');return
    if any(b.exists() for b in backs):raise RuntimeError('Backup files already exist; restore or resolve manually first')
    if dest.exists():raise RuntimeError('h25_r1_hook.h already exists in source tree; refuse to overwrite')
    changed=plan(p)
    if not (ROOT/'h25_r1_hook.h').is_file():
        raise RuntimeError('Missing h25_r1_hook.h next to patch script (extracted kit incomplete)')
    print('ANCHOR CHECK PASS (source compatible with pinned PiPNN 443a328 anchors)')
    if a.mode=='check':print('DRY RUN ONLY. Neither source nor graph changed.');return
    for f,b in zip(files,backs):shutil.copy2(f,b)
    for f,s in zip(files,changed):f.write_text(s)
    shutil.copy2(ROOT/'h25_r1_hook.h',dest)
    print('PATCH_APPLIED. Two original headers backed up; new hook header installed. Rebuild target now.')
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL CLOSED:',e,file=sys.stderr);sys.exit(2)
