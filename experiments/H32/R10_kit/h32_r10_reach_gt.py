#!/usr/bin/env python3
"""H32-R10 | READ-ONLY structural GT@10 vs entry-0 directed reachability.

No ANN build, ANN search, repair, input mutations, or data uploads.
Requires Python 3.9+ on a little-endian machine. H31 pinned artifacts only.
"""
from __future__ import annotations
import argparse
from array import array
from collections import Counter, deque
from datetime import datetime
import hashlib
import json
import math
import mmap
from pathlib import Path
import struct
import sys
import tempfile

EXPECTED_N = 1_000_000
EXPECTED_QUERIES = 10_000
EXPECTED_GT_K = 100
EXPECTED_D = 128
GRAPH_SPECS = {
    'VAMANA': {
        'relative_path': 'results/vamana_sift1m.graph',
        'sha256': '84b2935cb9f25e9ad53044099901c8c1e6cb4de059975882e8d91bca66aa5259',
        'edge_count': 27_643_346, 'bytes': 114_573_392, 'reachable_h31': 999_795,
        'recall_q100_h31': 0.983140,
    },
    'STOCK': {
        'relative_path': 'experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_stock.graph',
        'sha256': 'ce1cd7c5ae97b79972df2b30235a0844b88a6c8a983ce731ca3afca494d7095d',
        'edge_count': 22_793_556, 'bytes': 95_174_232, 'reachable_h31': 999_999,
        'recall_q100_h31': 0.990870,
    },
    'TOP2': {
        'relative_path': 'experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_top2.graph',
        'sha256': '73646a2b5655e16939ca804c598818460152803c20f6932e6e9286acd334c5c6',
        'edge_count': 22_794_064, 'bytes': 95_176_264, 'reachable_h31': 999_999,
        'recall_q100_h31': 0.990870,
    },
}

class AuditError(RuntimeError):
    pass


def assert_ok(cond, message):
    if not cond:
        raise AuditError(message)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def analyze_graph(path: Path, expected: dict | None, required_n: int, entry: int = 0):
    assert_ok(path.is_file(), f'GRAPH_MISSING: {path}')
    size = path.stat().st_size
    assert_ok(size >= 8, f'GRAPH_TOO_SMALL: {path}')
    if expected:
        assert_ok(size == expected['bytes'], f'GRAPH_BYTES_MISMATCH: {path.name}: {size} != {expected["bytes"]}')
        digest = file_sha256(path)
        assert_ok(digest == expected['sha256'], f'GRAPH_SHA_MISMATCH: {path.name}: {digest}')
    else:
        digest = file_sha256(path)
    with path.open('rb') as f:
        n, max_degree = struct.unpack('<II', f.read(8))
        assert_ok(n == required_n, f'GRAPH_N_MISMATCH: {path.name}: {n} != {required_n}')
        assert_ok(0 <= entry < n, f'BAD_ENTRY: {entry}')
        assert_ok(0 < max_degree <= n, f'BAD_MAX_DEGREE: {max_degree}')
        degree_bytes = f.read(4 * n)
        assert_ok(len(degree_bytes) == 4 * n, 'TRUNCATED_DEGREES')
        degrees = array('I')
        degrees.frombytes(degree_bytes)
        if sys.byteorder != 'little':
            degrees.byteswap()
        assert_ok(max(degrees) <= max_degree, 'DEGREE_EXCEEDS_MAX')
        edge_count = sum(degrees)
        assert_ok(size == 8 + 4 * n + 4 * edge_count, 'GRAPH_SCHEMA_OR_EDGE_SIZE_MISMATCH')
        if expected:
            assert_ok(edge_count == expected['edge_count'], 'GRAPH_EDGE_COUNT_MISMATCH')
        starts = array('Q', [0])
        for degree in degrees:
            starts.append(starts[-1] + degree)
        assert_ok(starts[-1] == edge_count, 'BAD_CSR_OFFSETS')
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            edges = memoryview(mapped)[8 + 4 * n:].cast('I')
            try:
                assert_ok(len(edges) == edge_count, 'EDGE_LENGTH_MISMATCH')
                assert_ok(max(edges, default=0) < n, 'NEIGHBOR_OUT_OF_RANGE')
                reachable_mask = bytearray(n)
                reachable_mask[entry] = 1
                queue = deque([entry])
                reached = 1
                while queue:
                    u = queue.popleft()
                    for j in range(starts[u], starts[u + 1]):
                        v = edges[j]
                        if not reachable_mask[v]:
                            reachable_mask[v] = 1
                            reached += 1
                            queue.append(v)
            finally:
                edges.release()
    if expected:
        assert_ok(reached == expected['reachable_h31'],
                  f'H31_REACHABILITY_DISAGREEMENT: {path.name}: {reached} != {expected["reachable_h31"]}')
    return reachable_mask, {
        'path': str(path), 'sha256': digest, 'bytes': size,
        'nodes': n, 'max_degree': max_degree, 'edges': edge_count,
        'entry': entry, 'reachable': reached, 'unreachable': n-reached,
        'unreachable_rate': (n - reached) / n,
    }


def check_fbin(path: Path, n: int, d: int):
    assert_ok(path.is_file(), f'DATA_MISSING: {path}')
    size = path.stat().st_size
    assert_ok(size == 8 + 4*n*d, f'FBIN_LENGTH_MISMATCH: {path.name}: {size}')
    with path.open('rb') as f:
        got = struct.unpack('<II', f.read(8))
    assert_ok(got == (n,d), f'FBIN_HEADER_MISMATCH: {path.name}: {got}')
    return {'path': str(path), 'n': n, 'd': d, 'bytes': size, 'header_size_verified_only': True}


def analyze_gt(gt_path: Path, masks: dict[str, bytearray], base_n: int, nq: int, k_gt: int, k: int):
    assert_ok(gt_path.is_file(), f'GT_MISSING: {gt_path}')
    size = gt_path.stat().st_size
    assert_ok(size == 8 + 8*nq*k_gt, f'GT_LENGTH_MISMATCH: {size}')
    with gt_path.open('rb') as f:
        header = struct.unpack('<II', f.read(8))
        assert_ok(header == (nq,k_gt), f'GT_HEADER_MISMATCH: {header}')
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            ids = memoryview(mapped)[8:8+4*nq*k_gt].cast('I')
            dist = memoryview(mapped)[8+4*nq*k_gt:].cast('f')
            try:
                assert_ok(len(ids) == nq*k_gt and len(dist) == nq*k_gt, 'GT_LAYOUT_MISMATCH')
                assert_ok(max(ids, default=0) < base_n, 'GT_ID_OUT_OF_RANGE')
                assert_ok(all(math.isfinite(v) and v >= 0 for v in dist), 'GT_INVALID_DISTANCE')
                rows_with_hits = {role:0 for role in masks}
                total_hits = {role:0 for role in masks}
                hist = {role:Counter() for role in masks}
                node_occurrences = {role:Counter() for role in masks}
                sample_queries = {role:[] for role in masks}
                for q in range(nq):
                    row = tuple(ids[q*k_gt:q*k_gt+k])
                    assert_ok(len(set(row)) == k, f'GT_DUPLICATE_ID_IN_TOP{k}: q={q}')
                    for role, mask in masks.items():
                        matches = [int(v) for v in row if not mask[v]]
                        count = len(matches)
                        total_hits[role] += count
                        hist[role][count] += 1
                        if count:
                            rows_with_hits[role] += 1
                            node_occurrences[role].update(matches)
                            if len(sample_queries[role]) < 20:
                                sample_queries[role].append({'query_index':q, 'unreachable_gt_ids': matches})
                results = {}
                for role in masks:
                    m = total_hits[role]
                    results[role] = {
                        'unreachable_gt_positions_M': m,
                        'queries_with_unreachable_gt': rows_with_hits[role],
                        'query_hit_histogram': dict(sorted(hist[role].items())),
                        'distinct_unreachable_gt_vertices': len(node_occurrences[role]),
                        'top_unreachable_vertices': node_occurrences[role].most_common(20),
                        'sample_queries': sample_queries[role],
                        'structural_miss_floor_fraction': m/(nq*k),
                        'reachability_recall_ceiling': 1-m/(nq*k),
                    }
                return results
            finally:
                ids.release()
                dist.release()


def audit(root: Path):
    root = root.expanduser().resolve()
    assert_ok(sys.byteorder == 'little', 'LITTLE_ENDIAN_REQUIRED')
    assert_ok(root.is_dir(), f'ROOT_MISSING: {root}')
    inventory = root / 'experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json'
    assert_ok(inventory.is_file(), f'PINNED_H31_INVENTORY_MISSING: {inventory}')
    try:
        json.loads(inventory.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise AuditError(f'INVENTORY_INVALID: {exc}') from exc
    data_dir = root / 'data'
    base_meta = check_fbin(data_dir/'sift1m.fbin', EXPECTED_N, EXPECTED_D)
    query_meta = check_fbin(data_dir/'sift1m_queries.fbin', EXPECTED_QUERIES, EXPECTED_D)
    masks = {}
    graph_meta = {}
    for role, spec in GRAPH_SPECS.items():
        mask, gmeta = analyze_graph(root/spec['relative_path'], spec, EXPECTED_N)
        masks[role] = mask
        graph_meta[role] = gmeta
        print(f'GRAPH_{role}=PASS_SHA_SCHEMA_REACHABLE, unreachable={gmeta["unreachable"]}', flush=True)
    gt_path = data_dir/'sift1m_gt.ibin'
    result = analyze_gt(gt_path,masks,EXPECTED_N,EXPECTED_QUERIES,EXPECTED_GT_K,10)
    out_parent = root/'experiments/H32'
    assert_ok(out_parent.is_dir(), f'OUTPUT_PARENT_MISSING: {out_parent}')
    now = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    dest = out_parent/f'H32_R10_{now}'
    dest.mkdir(mode=0o755)
    report = {
      'status':'PASS_REAL_READONLY_GT_REACHABILITY', 'method':'directed_BFS_entry_0_vs_GT_top10',
      'notes':['No ANN BUILD, SEARCH, or graph edits.','GT validated structurally, not independently recomputed exact NN.',
               'Upper bound assumes search walks only directed edges from entry 0 with no teleport/fallback.',
               'No equal-graph-budget or causal repair claim.'],
      'provenance':{'inventory':str(inventory),'base':base_meta,'queries':query_meta,
                    'GT':{'path':str(gt_path),'queries':EXPECTED_QUERIES,'GT_k':EXPECTED_GT_K,'layout':'uint32 IDs block then float32 distance block'}},
      'graphs':{},
    }
    lines = ['H32-R10 | READ-ONLY GT@10 × DIRECTED ENTRY REACHABILITY','OVERALL=PASS_REAL_READONLY_GT_REACHABILITY',
             f'ROOT={root}', f'INVENTORY={inventory}', 'N_QUERY=10000; TOP_K=10; GT_LAYOUT=IDS_BLOCK_THEN_DISTANCES_BLOCK',
             'NO BUILD / NO ANN SEARCH / NO GRAPH MODIFICATION',
             'GT exactness NOT independently recomputed. No matched graph budget or novelty claim.','']
    for role in GRAPH_SPECS:
        graph = graph_meta[role]
        r = result[role]
        historical_recall = GRAPH_SPECS[role]['recall_q100_h31']
        observed_missed_slots = round((1-historical_recall)*EXPECTED_QUERIES*10)
        structural_share = (r['unreachable_gt_positions_M']/observed_missed_slots) if observed_missed_slots else None
        report['graphs'][role] = dict(graph=graph,GT=r,h31_q100_recall_historical=historical_recall,
                                      h31_q100_missed_slots_historical=observed_missed_slots,
                                      structural_M_over_historical_missed_slots=structural_share)
        lines += [f'[{role}] SHA256={graph["sha256"]}',
                  f'  NODES={graph["nodes"]} EDGES={graph["edges"]} GRAPH_BYTES={graph["bytes"]}',
                  f'  ENTRY0_REACHABLE={graph["reachable"]} ENTRY0_UNREACHABLE={graph["unreachable"]}',
                  f'  GT_UNREACHABLE_POSITIONS_M={r["unreachable_gt_positions_M"]}',
                  f'  GT_QUERIES_AFFECTED={r["queries_with_unreachable_gt"]}',
                  f'  DISTINCT_UNREACHABLE_GT_NODES={r["distinct_unreachable_gt_vertices"]}',
                  f'  STRUCTURAL_MISS_FLOOR={r["structural_miss_floor_fraction"]:.8f}',
                  f'  THEORETICAL_RECALL_CEILING={r["reachability_recall_ceiling"]:.8f}',
                  f'  H31_Q100_RECALL_HISTORICAL={historical_recall:.6f}',
                  f'  M_OVER_HISTORICAL_Q100_MISSED_SLOTS={structural_share:.8f}' if structural_share is not None else '  M_OVER_HISTORICAL_Q100_MISSED_SLOTS=NOT_DEFINED',
                  f'  QUERY_HISTOGRAM={r["query_hit_histogram"]}', '']
        if r['unreachable_gt_positions_M'] > observed_missed_slots:
            lines.append(f'  WARNING_H31_RECALL_CONSISTENCY: M={r["unreachable_gt_positions_M"]} > approximate observed Q100 missed slots={observed_missed_slots}; check metric/GT/protocol')
    vamana_m = result['VAMANA']['unreachable_gt_positions_M']
    if vamana_m == 0:
        decision = 'STOP_ORPHAN_REPAIR_FOR_MEAN_RECALL_GT_ON_CURRENT_HELDOUT_QUERIES; NO H33 CLAIM'
    else:
        decision = 'STRUCTURAL_MISS_FLOOR_NONZERO; PRIOR_ART_AND_MATCHED_BUDGET_REVIEW_BEFORE_ANY_REPAIR; NO H33 CLAIM'
    lines += [f'RESEARCH_DECISION={decision}',f'H32R10_DONE={dest}']
    report['research_decision'] = decision
    (dest/'h32_r10_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (dest/'h32_r10_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('\n'.join(lines),flush=True)


def selftest():
    # Synthetic directed graph: 0->1->2->3; detached 4<->5 is a closed SCC.
    # All nodes of detached SCC have indegree >=1, yet are unreachable from 0.
    with tempfile.TemporaryDirectory(prefix='h32r10_synthetic_') as d:
        folder = Path(d)
        graph_path = folder/'g.graph'
        adjacency = [[1],[2],[3],[],[5],[4]]
        degrees=[len(a) for a in adjacency]
        with graph_path.open('wb') as f:
            f.write(struct.pack('<II',6,1))
            f.write(struct.pack('<6I',*degrees))
            for a in adjacency:
                for v in a:f.write(struct.pack('<I',v))
        mask, meta = analyze_graph(graph_path,None,6)
        assert_ok(meta['reachable']==4 and meta['unreachable']==2,'SELFTEST_BFS_BAD')
        gt_path = folder/'gt.ibin'
        gt_ids = [4,3,0,2,5,1]
        with gt_path.open('wb') as f:
            f.write(struct.pack('<II',3,2))
            f.write(struct.pack('<6I',*gt_ids))
            f.write(struct.pack('<6f',*([0.1,0.2]*3)))
        r=analyze_gt(gt_path,{'SYN':mask},6,3,2,2)['SYN']
        assert_ok(r['unreachable_gt_positions_M']==2 and r['queries_with_unreachable_gt']==2,
                  f'SELFTEST_GT_M_BAD: {r}')
        broken=folder/'bad.graph'
        broken.write_bytes(graph_path.read_bytes()[:-4])
        try:
            analyze_graph(broken,None,6)
        except AuditError:
            pass
        else:
            raise AuditError('SELFTEST_FAIL_CLOSED_SCHEMA_FAILED')
    print('H32R10_READONLY_SYNTHETIC_SELFTEST_PASS (NO REAL SIFT1M DATA CHECKED)')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['selftest','audit'],required=True)
    parser.add_argument('--root',default='~/ann-task-a')
    a=parser.parse_args()
    try:
        selftest() if a.mode=='selftest' else audit(Path(a.root))
    except (AuditError,OSError,ValueError,struct.error) as exc:
        print(f'H32R10_FAIL_CLOSED: {exc}',file=sys.stderr)
        sys.exit(2)

if __name__=='__main__':
    main()
