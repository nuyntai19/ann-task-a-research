#!/usr/bin/env python3
"""H32-R47-R4 v2: offline native R45 vs R47 per-query Top-k ID parity.

R45: SEARCH|qid|beamSize|k|repeat|dist_cmps|beam_ids|visited_ids
R47: 5 identical chronological event blocks per pinned query from R47-R2.

Reconstruct R47 final beam membership using MERGE_KEEP/BEAM_EVICT events,
then sort with exact squared-L2 for integer-coordinate float SIFT vectors
and compare its full beam order, Top-k order, visited set and comparisons
against 5 native R45 repeats. Fails closed if any invariant is unmet.

No write to input datasets, graph, binaries, or source. Never claims a
causal construction defect or benchmark improvement.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
import mmap
from pathlib import Path
import struct
import sys

PIN_GRAPH_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'


def hash_file(path):
    h = sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Fbin:
    def __init__(self, path):
        self.path = path
        self.fp = path.open('rb')
        header = self.fp.read(8)
        if len(header) != 8:
            raise ValueError(f'{path}: truncated fbin header')
        self.n, self.dim = struct.unpack('<II', header)
        if not 0 < self.n <= 50_000_000 or not 0 < self.dim <= 4096:
            raise ValueError(f'{path}: implausible n/dim {self.n}, {self.dim}')
        expected = 8 + 4 * self.n * self.dim
        if path.stat().st_size != expected:
            raise ValueError(f'{path}: size mismatch {path.stat().st_size} != {expected}')
        self.mm = mmap.mmap(self.fp.fileno(), 0, access=mmap.ACCESS_READ)
        self.cache = {}

    def vector(self, i):
        if not 0 <= i < self.n:
            raise ValueError(f'Invalid fbin ID {i} (n={self.n})')
        if i not in self.cache:
            coords = struct.unpack_from(f'<{self.dim}f', self.mm, 8 + i * self.dim * 4)
            # This pinned SIFT protocol should consist of integer-valued floats.
            # Without that guarantee, Python float64 and C++ float32 might order ties differently.
            if any(not (-1.0e8 <= x <= 1.0e8) or not x.is_integer() for x in coords):
                raise ValueError(f'{self.path}: non-integer/invalid float at vector {i}; refuse exact-score parity')
            self.cache[i] = tuple(int(x) for x in coords)
        return self.cache[i]

    def close(self):
        self.mm.close()
        self.fp.close()


def read_r45_search(path, qid, beam_size=100, k=10, repeats=5):
    """Read 5 SEARCH records; field[4] is NOT assumed to be a repeat index.

    In the user's native R45 traces, the 5th pipe-delimited field can remain
    0 across all five independently generated SEARCH rows. Index repeat rows
    by their observed position, and require all five scientific payloads to
    agree. Also accept explicit 0..4 numbering if present.
    """
    if not path.is_file():
        raise ValueError(f'Missing R45 trace {path}')
    recs = []
    slots = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if not line.startswith('SEARCH|'):
            continue
        fields = line.split('|')
        if len(fields) < 8:
            raise ValueError(f'{path}:{lineno}: SEARCH has {len(fields)} fields; expected >=8')
        try:
            rq, rqbeam, rk, slot, cmps = map(int, fields[1:6])
        except ValueError as e:
            raise ValueError(f'{path}:{lineno}: bad SEARCH header: {e}')
        if (rq, rqbeam, rk) != (qid, beam_size, k):
            raise ValueError(f'{path}:{lineno}: Q/k/query mismatch: {(rq,rqbeam,rk)}')

        def ids(raw):
            return tuple(int(v) for v in raw.split(',') if v.strip())

        beam = ids(fields[6])
        visited = ids(fields[7])
        if not beam or len(set(beam)) != len(beam):
            raise ValueError(f'{path}:{lineno}: invalid beam IDs')
        if not visited or len(set(visited)) != len(visited):
            raise ValueError(f'{path}:{lineno}: invalid visited IDs')
        slots.append(slot)
        recs.append({'beam': beam, 'visited': visited, 'comparisons': cmps})
    if len(recs) != repeats:
        raise ValueError(f'{path}: expected {repeats} SEARCH records, found {len(recs)}')
    # Do not silently re-interpret the 5th field as a repeat index; traces
    # with all zeros were observed on Ubuntu. Reject unexpected mixed modes.
    if not (len(set(slots)) == 1 or slots == list(range(repeats))):
        raise ValueError(f'{path}: inconsistent SEARCH header field[4]: {slots}')
    first = recs[0]
    for j in range(repeats):
        if recs[j] != first:
            raise ValueError(f'{path}: R45 5 native SEARCH records disagree at row={j}')
    return first


def reconstruct_r47(events, qid, beam_size=100):
    starts = [e for e in events if e['type'] == 'EXPAND']
    if not starts or starts[0].get('step') != 0:
        raise ValueError(f'q={qid}: no step-zero expansion from starting point')
    start = starts[0]
    beam = {int(start['node']): float(start['distance'])}
    retained_distances = {int(start['node']): float(start['distance'])}
    n_keep = n_drop = n_evict = 0
    for event in events:
        typ = event['type']
        if typ == 'MERGE_KEEP':
            v = int(event['node'])
            d = float(event['distance'])
            if v in beam:
                raise ValueError(f'q={qid}: duplicate MERGE_KEEP for already-present node {v}')
            beam[v] = d
            retained_distances[v] = d
            n_keep += 1
        elif typ == 'MERGE_DROP':
            n_drop += 1
        elif typ == 'BEAM_EVICT':
            v = int(event['node'])
            if v not in beam:
                raise ValueError(f'q={qid}: BEAM_EVICT of absent beam node {v}')
            del beam[v]
            n_evict += 1
    begin = next((e for e in events if e['type'] == 'BEGIN'), None)
    end = next((e for e in events if e['type'] == 'END'), None)
    if begin is None or end is None or int(begin['beam']) != beam_size:
        raise ValueError(f'q={qid}: missing/incorrect BEGIN/END')
    if len(beam) != beam_size:
        raise ValueError(f'q={qid}: reconstructed final beam size {len(beam)}, expected {beam_size}')
    if len(starts) != int(end['expanded']):
        raise ValueError(f'q={qid}: inconsistent expansion count')
    if len(starts) != len({int(e['node']) for e in starts}):
        raise ValueError(f'q={qid}: duplicate expanded nodes')
    return {
        'beam_distances_printed': beam,
        'visited_ids': frozenset(int(e['node']) for e in starts),
        'comparisons': int(end['full_dist_cmps']),
        'events': {'merge_keep': n_keep, 'merge_drop': n_drop, 'evicted_old_beam': n_evict}
    }


def exact_integer_l2(qvector, bvector):
    if len(qvector) != len(bvector):
        raise ValueError('Dimensions differ')
    d = sum((x - y) * (x - y) for x, y in zip(qvector, bvector))
    if d >= 2**24:
        raise ValueError('L2 squared >= 2^24: float32 reduction may not exactly match; refuse parity')
    return d


def audit(args):
    from ann_task_a_r47_r3_witness_audit import read_events
    m = json.loads(args.manifest.read_text())
    r45 = json.loads(args.r45_report.read_text())
    r46 = json.loads(args.r46.read_text())
    qids = sorted(set(int(q) for q in m['native_fail_query_ids']))
    if len(qids) != 17:
        raise ValueError(f'R47 manifest expected 17 queries; found {len(qids)}')
    if r45.get('parity') != 'PASS_RECALL_VISITED_COMPARISONS':
        raise ValueError(f'R45 parity not PASS: {r45.get("parity")}')
    if r46['counts']['queries_native_miss'] != len(qids):
        raise ValueError('R46 native failing query count mismatch')
    if m['protocol']['graph_sha256'] != PIN_GRAPH_SHA or r46['protocol']['graph_sha256'] != PIN_GRAPH_SHA:
        raise ValueError('R46/R47 graph SHA pin mismatch')
    r45_sample_hash = r45['query_sample']['sample_sha256']
    if r45_sample_hash != m['protocol']['R45_query_sample_sha256']:
        raise ValueError('R45/R47 sample SHA mismatch')
    if args.graph is not None and hash_file(args.graph) != PIN_GRAPH_SHA:
        raise ValueError('Actual R26a graph SHA mismatch')
    if r46['protocol']['Q'] != 100 or r46['protocol']['k'] != 10:
        raise ValueError('Expected pinned Q=100, k=10')
    native_missing = {int(q['query_id']): int(q['visited_count']) for q in r46['missed_query_details'] if q['native_deficit'] > 0}
    if set(native_missing) != set(qids):
        raise ValueError('Manifest vs R46 query IDs differ')
    r47_events = read_events(args.events, set(qids), expected_repeats=5)
    base = Fbin(args.base)
    queries = Fbin(args.queries)
    outputs = []
    try:
        if base.n != 1_000_000 or queries.n != 10_000 or base.dim != 128 or queries.dim != 128:
            raise ValueError(f'Unexpected SIFT1M shape: base={base.n}x{base.dim}, query={queries.n}x{queries.dim}')
        for qid in qids:
            native = read_r45_search(args.r45_traces / f'q_{qid}.trace', qid)
            r47 = reconstruct_r47(r47_events[qid], qid)
            if len(native['beam']) != 100:
                raise ValueError(f'q={qid}: native R45 beam size {len(native["beam"])}')
            if len(native['visited']) != native_missing[qid]:
                raise ValueError(f'q={qid}: R45 visited_count differs from R46')
            if set(native['visited']) != r47['visited_ids']:
                raise ValueError(f'q={qid}: R45/R47 visited IDs mismatch; only native={list(set(native["visited"])-r47["visited_ids"])[:6]}; only R47={list(r47["visited_ids"]-set(native["visited"]))[:6]}')
            if native['comparisons'] != r47['comparisons']:
                raise ValueError(f'q={qid}: R45/R47 comparisons {native["comparisons"]}!={r47["comparisons"]}')
            r47_beam = set(r47['beam_distances_printed'])
            if set(native['beam']) != r47_beam:
                raise ValueError(f'q={qid}: beam ID membership mismatch; native-only={list(set(native["beam"])-r47_beam)[:8]}, R47-only={list(r47_beam-set(native["beam"]))[:8]}')
            qv = queries.vector(qid)
            scored = []
            for idx in r47_beam:
                exact_score = exact_integer_l2(qv, base.vector(idx))
                logged_score = r47['beam_distances_printed'][idx]
                if abs(float(exact_score) - logged_score) > max(0.51, abs(exact_score) * 1.0e-5):
                    raise ValueError(f'q={qid}: node={idx} logged distance {logged_score} differs from pinned fbin L2={exact_score}')
                scored.append((exact_score, idx))
            reconstructed_order = tuple(idx for score, idx in sorted(scored))
            if reconstructed_order != native['beam']:
                for rank,(r,n) in enumerate(zip(reconstructed_order, native['beam']), 1):
                    if r != n:
                        raise ValueError(f'q={qid}: ordered beam differs at rank={rank}: R47={r} R45={n}; STOP, no Top-k parity claim')
            outputs.append({'query_id': qid, 'top10_parity': True, 'beam100_parity': True,
                            'visited_id_set_parity': True, 'comparisons_parity': True,
                            'top10': list(native['beam'][:10]), 'visited_count': len(native['visited']),
                            'comparisons': native['comparisons'], 'events_first_repeat': r47['events']})
    finally:
        base.close()
        queries.close()

    result = {'audit': 'R47_R4_NATIVE_TOPK_ID_PARITY_PASS',
              'graph_sha256': PIN_GRAPH_SHA, 'r45_query_sample_sha256': r45_sample_hash,
              'Q': 100, 'k': 10, 'queries': len(outputs), 'repeats': 5,
              'checks': ['top10_order_exact', 'full_beam100_order_exact', 'visited_id_set', 'full_distance_comparisons', 'R45_repeats_identical', 'R47_repeats_identical'],
              'method': 'R47 MERGE_KEEP/BEAM_EVICT replay + exact integer-coordinate L2 ranking, cross-checked with R45 SEARCH beam and visited IDs',
              'caution': 'Supports search-result parity only; does not demonstrate a graph-construction causal mechanism or a recall improvement.',
              'per_query': outputs}
    # Writes only a report into H47; never overwrites science inputs.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError(f'Output already exists; refusing to overwrite: {args.output}')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('R47_R4_NATIVE_TOPK_ID_PARITY_PASS')
    print('R45_SEARCH_RECORDS', f'{len(outputs)} queries x 5 repeats')
    print('R47_EVENT_RECORDS', f'{len(outputs)} queries x 5 repeats')
    print('FULL_BEAM100_ORDER_PARITY', f'{len(outputs)}/{len(outputs)}')
    print('TOP10_ORDER_PARITY', f'{len(outputs)}/{len(outputs)}')
    print('VISITED_ID_SET_PARITY', f'{len(outputs)}/{len(outputs)}')
    print('COMPARISONS_PARITY', f'{len(outputs)}/{len(outputs)}')
    print('OUTPUT', args.output)


def selftest():
    from tempfile import TemporaryDirectory
    assert exact_integer_l2((1,2), (4,6)) == 25
    e = [
        {'type':'BEGIN','beam':2},
        {'type':'EXPAND','node':0,'distance':25.0,'step':0},
        {'type':'MERGE_KEEP','node':1,'distance':16.0},
        {'type':'MERGE_KEEP','node':2,'distance':9.0},
        {'type':'BEAM_EVICT','node':0,'distance':25.0},
        {'type':'END','expanded':1,'full_dist_cmps':3},
    ]
    r = reconstruct_r47(e, 11, 2)
    assert set(r['beam_distances_printed']) == {1,2}
    assert r['visited_ids'] == {0}
    assert tuple(i for d,i in sorted((d,i) for i,d in r['beam_distances_printed'].items())) == (2,1)
    with TemporaryDirectory() as td:
        p = Path(td) / 'q_11.trace'
        p.write_text('\n'.join(f'SEARCH|11|100|10|{j}|1332|2,1,|0,1,\nEVAL|11' for j in range(5)))
        r45 = read_r45_search(p, 11)
        assert r45['beam'] == (2,1)
        assert r45['visited'] == (0,1)
        assert r45['comparisons'] == 1332
        # Native R45 can write all 5 SEARCH rows with a constant field[4]=0.
        constant_slot = '\n'.join('SEARCH|11|100|10|0|1332|2,1,|0,1,\nEVAL|11'
                                 for j in range(5))
        p.write_text(constant_slot)
        assert read_r45_search(p, 11)['comparisons'] == 1332
        # Enumerated field[4] remains compatible.
        p.write_text('\n'.join(f'SEARCH|11|100|10|{j}|1332|2,1,|0,1,\nEVAL|11'
                                for j in range(5)))
        assert read_r45_search(p, 11)['beam'] == (2, 1)
        # Even with constant header field, unequal search results must fail.
        p.write_text(constant_slot.replace('SEARCH|11|100|10|0|1332',
                                           'SEARCH|11|100|10|0|1333', 1))
        try:
            read_r45_search(p, 11)
            raise AssertionError('Expected R45 SEARCH payload mismatch')
        except ValueError as ex:
            assert 'disagree' in str(ex)
        # Missing a SEARCH row must also fail.
        p.write_text('\n'.join('SEARCH|11|100|10|0|1332|2,1,|0,1,\nEVAL|11'
                                for j in range(4)))
        try:
            read_r45_search(p, 11)
            raise AssertionError('Expected R45 SEARCH count mismatch')
        except ValueError as ex:
            assert 'expected 5 SEARCH records' in str(ex)
    print('R47_R4_V2_SELFTEST_PASS: constant/enumerated SEARCH field, mismatch/row count, replay, L2')


def main():
    root = Path('experiments/H47')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['selftest','audit'])
    ap.add_argument('--manifest', type=Path, default=root/'r47_target_manifest.json')
    ap.add_argument('--r45-report', type=Path, default=Path('experiments/H45/native_q100_256/R45_native_query_trace.json'))
    ap.add_argument('--r45-traces', type=Path, default=Path('experiments/H45/native_q100_256/traces'))
    ap.add_argument('--r46', type=Path, default=Path('experiments/H46/r46_native_miss_reclassified.json'))
    ap.add_argument('--events', type=Path, default=root/'r47_events.stderr')
    ap.add_argument('--base', type=Path, default=Path('data/sift1m.fbin'))
    ap.add_argument('--queries', type=Path, default=Path('data/sift1m_queries.fbin'))
    ap.add_argument('--graph', type=Path, default=Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph'))
    ap.add_argument('--output', type=Path, default=root/'r47_r4_topk_parity.json')
    args = ap.parse_args()
    if args.action == 'selftest':
        selftest()
        return
    try:
        audit(args)
    except (ValueError, KeyError, IndexError, OSError, AssertionError) as e:
        print('R47_R4_PARITY_FAIL:', e, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
