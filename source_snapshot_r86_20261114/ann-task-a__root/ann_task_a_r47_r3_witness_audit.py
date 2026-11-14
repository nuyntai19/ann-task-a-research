#!/usr/bin/env python3
"""H32-R47-R3: read-only, pinned native beam-decision / two-hop witness audit.

Reads R46 JSON, R47-R0 manifest, R47 event stderr and R26a graph.
Never edits or rebuilds graph; does not interpret search outcomes as construction defects.
Only Python standard library is needed.
"""
import argparse
from array import array
from collections import Counter, defaultdict
import hashlib
import json
import mmap
from pathlib import Path
import re
import struct
import sys

PIN_GRAPH_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
BEGIN = re.compile(r'^R47_BEGIN q=(\d+)\b')
END = re.compile(r'^R47_END q=(\d+)\b')
EVENT = re.compile(r'^R47_([A-Z_]+) q=(\d+)\b')
FIELD = re.compile(r'\b([a-z_]+)=([^\s]+)')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(4 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


class Graph:
    """Pinned ParlayANN uint32 graph: uint32 n,max_degree; n degrees; directed IDs."""
    def __init__(self, path, expected_sha=PIN_GRAPH_SHA):
        self.path = path
        actual = sha256(path)
        if actual != expected_sha or actual != PIN_GRAPH_SHA:
            raise ValueError(f'Graph SHA mismatch: {actual}')
        self.fp = path.open('rb')
        self.n, self.max_degree = struct.unpack('<II', self.fp.read(8))
        if not 0 < self.n < 100_000_000 or not 0 < self.max_degree < 100000:
            raise ValueError('Implausible graph header')
        self.degree = array('I')
        self.degree.fromfile(self.fp, self.n)
        if sys.byteorder != 'little':
            self.degree.byteswap()
        self.offsets = array('Q', [0])
        total = 0
        for v in self.degree:
            if v > self.max_degree:
                raise ValueError('Invalid degree > max_degree')
            total += v
            self.offsets.append(total)
        self.edges = total
        if expected_sha == 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef' and (self.n, self.max_degree, total) != (1_000_000, 32, 22_797_630):
            raise ValueError('Graph dimensions/edge count differ from pinned R26a')
        self.edge_start = 8 + self.n * 4
        expected_size = self.edge_start + total * 4
        if expected_size != path.stat().st_size:
            raise ValueError(f'Unexpected graph file size {path.stat().st_size} != {expected_size}')
        self.mm = mmap.mmap(self.fp.fileno(), length=0, access=mmap.ACCESS_READ)
        self.cache = {}

    def out(self, u):
        u = int(u)
        if u < 0 or u >= self.n:
            raise ValueError(f'Invalid vertex {u}')
        if u not in self.cache:
            d = self.degree[u]
            self.cache[u] = (struct.unpack_from(f'<{d}I', self.mm,
                              self.edge_start + 4 * self.offsets[u]) if d else ())
        return self.cache[u]

    def close(self):
        self.mm.close()
        self.fp.close()


def read_events(path, expected_qids, expected_repeats=5):
    """Trace is emitted as one block per query. Check five identical event sequences."""
    first = {}
    digests = defaultdict(list)
    block = None
    block_hash = None
    pending = None
    with path.open('r', encoding='utf-8', errors='replace') as fp:
        for lineno, line in enumerate(fp, 1):
            line = line.rstrip('\n')
            bm = BEGIN.match(line)
            if bm:
                if pending is not None:
                    raise ValueError(f'Nested R47_BEGIN near line {lineno}')
                q = int(bm.group(1))
                if q not in expected_qids:
                    raise ValueError(f'Unexpected query {q}')
                pending = q
                block = []
                block_hash = hashlib.sha256()
            elif pending is None:
                if line.startswith('R47_'):
                    raise ValueError(f'Event outside query block: {lineno}: {line[:120]}')
                continue
            if pending is not None:
                if not line.startswith('R47_'):
                    raise ValueError(f'Unexpected line inside R47 block {lineno}: {line[:120]}')
                em = EVENT.match(line)
                if em is None or int(em.group(2)) != pending:
                    raise ValueError(f'Query event mismatch at line {lineno}: {line[:120]}')
                block_hash.update(line.encode('utf-8') + b'\n')
                if pending not in first:
                    vals = {}
                    for k, v in FIELD.findall(line):
                        try:
                            vals[k] = float(v) if k in ('distance', 'cutoff') else int(v)
                        except ValueError:
                            vals[k] = v
                    block.append({'type': em.group(1), **vals})
                end = END.match(line)
                if end:
                    q = pending
                    if int(end.group(1)) != q:
                        raise ValueError('End mismatch')
                    digests[q].append(block_hash.hexdigest())
                    if q not in first:
                        first[q] = block
                    block, block_hash, pending = None, None, None
    if pending is not None:
        raise ValueError('Last query block did not end')
    if set(first) != expected_qids:
        raise ValueError(f'Query IDs mismatch: missing {sorted(expected_qids-set(first))}')
    for q in expected_qids:
        if len(digests[q]) != expected_repeats:
            raise ValueError(f'Query {q} trace repeats = {len(digests[q])}, expected {expected_repeats}')
        if len(set(digests[q])) != 1:
            raise ValueError(f'Query {q} trace events differ across repeats')
    return first


def event_summary(events):
    per_node = defaultdict(list)
    expanded = []
    begin = None
    end = None
    for idx, e in enumerate(events):
        name = e['type']
        if name == 'BEGIN':
            begin = e
        elif name == 'END':
            end = e
        elif name == 'EXPAND':
            expanded.append(e['node'])
        if 'node' in e:
            per_node[e['node']].append((idx, e))
    return per_node, expanded, begin, end


def classify(events):
    kinds = {e['type'] for _, e in events}
    if 'EXPAND' in kinds:
        return 'EXPANDED_CONTRADICTION'
    if 'MERGE_KEEP' in kinds and 'BEAM_EVICT' in kinds:
        return 'KEPT_THEN_EVICTED'
    if 'MERGE_DROP' in kinds:
        return 'MERGE_DROP'
    if 'CUTOFF_REJECT' in kinds:
        return 'CUTOFF_REJECT'
    if 'MERGE_KEEP' in kinds:
        return 'MERGE_KEEP_NOT_EXPANDED'
    if 'STAGE' in kinds:
        return 'STAGED_NO_MERGE_DECISION'
    if 'SCORE' in kinds:
        return 'SCORED_NO_DECISION'
    if 'DISCOVER' in kinds:
        return 'DISCOVERED_NO_SCORE'
    if 'SEEN_SKIP' in kinds:
        return 'SEEN_SKIP_ONLY'
    if 'SAME_SKIP' in kinds:
        return 'SAME_QUERY_SKIP'
    return 'NO_TRACE_EVENT'


def audit(r46_path, manifest_path, events_path, graph_path):
    r46 = json.loads(r46_path.read_text())
    m = json.loads(manifest_path.read_text())
    if not isinstance(m.get('native_fail_query_ids'), list):
        raise ValueError('Missing R47 manifest query IDs')
    qids = set(map(int, m['native_fail_query_ids']))
    if len(qids) != 17 or len(m['twohop_targets']) != 18 or len(m['non_twohop_targets']) != 2:
        raise ValueError('R47-R0 manifest counts do not match pinned R46')
    if r46['counts']['queries_native_miss'] != 17 or r46['counts']['native_deficit'] != 20:
        raise ValueError('R46 counts mismatch')
    if m['protocol'].get('graph_sha256') != PIN_GRAPH_SHA or r46['protocol'].get('graph_sha256') != PIN_GRAPH_SHA:
        raise ValueError('Pinned graph hash mismatch in manifest or R46')
    detail_map = {int(q['query_id']): q for q in r46['missed_query_details'] if q['native_deficit'] > 0}
    if set(detail_map) != qids:
        raise ValueError('R46 failing query IDs mismatch')
    # Collect only first of the five identical native event blocks per query.
    traces = read_events(events_path, qids)
    graph = Graph(graph_path)
    result = []
    errors = []
    total_witnesses = 0
    all_categories = Counter()
    try:
        for q in sorted(qids):
            by_node, expanded, begin, end = event_summary(traces[q])
            if len(expanded) != detail_map[q]['visited_count'] or int(end.get('expanded', -1)) != len(expanded):
                raise ValueError(f'Expanded count for q={q} differs from R46')
            if not begin or not end:
                raise ValueError(f'Missing BEGIN/END q={q}')
            if int(begin.get('beam', -1)) != 100 or int(begin.get('degree_limit', -1)) != graph.max_degree:
                raise ValueError(f'Unexpected beam or degree_limit q={q}')
            expanded_set = set(expanded)
            if len(expanded_set) != len(expanded):
                raise ValueError(f'Duplicate expanded node in q={q}')
            for miss in detail_map[q]['misses']:
                t = int(miss['GT'])
                if miss['category'] != 'not_adjacent_to_expanded':
                    raise ValueError(f'Unexpected miss category q={q}: {miss["category"]}')
                witnesses = defaultdict(set)
                for u in expanded:
                    if t in graph.out(u):
                        errors.append(f'q={q}: direct edge from expanded {u} to GT {t}, violates R46')
                    for v in graph.out(u):
                        if t in graph.out(v):
                            witnesses[int(v)].add(int(u))
                gt_expected = bool(miss['graph_twohop_from_expanded'])
                if bool(witnesses) != gt_expected:
                    raise ValueError(f'Graph twohop disagrees with R46: q={q} gt={t} calculated={bool(witnesses)} expected={gt_expected}')
                rows = []
                for v, us in sorted(witnesses.items()):
                    node_ev = by_node.get(v, [])
                    category = classify(node_ev)
                    all_categories[category] += 1
                    # For each witness parent, this directed edge should be exercised by the expansion.
                    parent_seen = sorted({e['from'] for _, e in node_ev
                                          if e['type'] in {'DISCOVER','SEEN_SKIP','SAME_SKIP'}
                                          and 'from' in e and e['from'] in us})
                    if not parent_seen:
                        errors.append(f'q={q}: witness v={v}, gt={t} has no logged source-parent event')
                    rows.append({
                        'v': v, 'expanded_parents': sorted(us),
                        'logged_expanded_parents': parent_seen,
                        'status': category,
                        'event_types': [e['type'] for _, e in node_ev],
                        'score_records': [{k: e[k] for k in ('distance','cutoff') if k in e}
                                          for _, e in node_ev if e['type'] == 'SCORE'],
                    })
                total_witnesses += len(rows)
                result.append({
                    'query_id': q, 'gt_id': t, 'gt_rank': miss.get('strict_gt_rank'),
                    'twohop': bool(rows), 'witness_count': len(rows),
                    'status_counts': dict(Counter(row['status'] for row in rows)),
                    'witnesses': rows,
                })
    finally:
        graph.close()
    if len(result) != 20 or sum(bool(row['twohop']) for row in result) != 18:
        raise ValueError('Unexpected R47 witness counts')
    if errors:
        raise ValueError('Trace/graph inconsistencies (first 8): ' + '; '.join(errors[:8]))
    return {
        'status': 'R47_R3_OFFLINE_WITNESS_AUDIT_PASS',
        'scope': 'R46 17 native-failing queries; 20 strict GT IDs; one fully repeated native event block per query',
        'graph_sha256': PIN_GRAPH_SHA,
        'trace_repetitions_identical': 5,
        'queries': len(qids),
        'targets': len(result),
        'twohop_targets': sum(bool(r['twohop']) for r in result),
        'non_twohop_targets': sum(not r['twohop'] for r in result),
        'distinct_witness_occurrences_across_targets': total_witnesses,
        'witness_status_counts': dict(all_categories),
        'results': result,
        'caution': 'A two-hop witness does not imply the native search would have reached the target; R47 has not yet shown per-query Top-k ID parity.'
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--r46', type=Path, default=Path('experiments/H46/r46_native_miss_reclassified.json'))
    ap.add_argument('--manifest', type=Path, default=Path('experiments/H47/r47_target_manifest.json'))
    ap.add_argument('--events', type=Path, default=Path('experiments/H47/r47_events.stderr'))
    ap.add_argument('--graph', type=Path, default=Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph'))
    ap.add_argument('--output', type=Path, default=Path('experiments/H47/r47_r3_witness_report.json'))
    args = ap.parse_args()
    result = audit(args.r46, args.manifest, args.events, args.graph)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(result['status'])
    print('QUERY_COUNT', result['queries'])
    print('TARGET_COUNT', result['targets'])
    print('TWOHOP', result['twohop_targets'], 'NON_TWOHOP', result['non_twohop_targets'])
    print('WITNESS_OCCURRENCES', result['distinct_witness_occurrences_across_targets'])
    print('WITNESS_STATUSES', json.dumps(result['witness_status_counts'], ensure_ascii=False, sort_keys=True))
    for row in result['results']:
        print(f"q={row['query_id']} GT={row['gt_id']} rank={row['gt_rank']} "
              f"twohop={row['twohop']} witnesses={row['witness_count']} "
              f"statuses={json.dumps(row['status_counts'], sort_keys=True)}")
        for x in row['witnesses'][:3]:
            print(f"    v={x['v']} parents={x['expanded_parents'][:3]} "
                  f"status={x['status']} score={x['score_records'][:1]}")
    print('OUTPUT', args.output)
    print('LIMITATION: This is an observational diagnosis, not proof of causal topology failure or Top-k parity.')

if __name__ == '__main__':
    main()
