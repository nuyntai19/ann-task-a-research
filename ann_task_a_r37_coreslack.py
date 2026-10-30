#!/usr/bin/env python3
"""H32-R37 CORE-Slack R0: read-only structural / reverse-proposal audit.

IMPORTANT: Produces structural DIAGNOSTICS, not a modified ANN graph, Recall
measurement, original HashPrune angular hash or a novel algorithm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import tempfile
from pathlib import Path

import numpy as np

POOL_PIN = '7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8'
GRAPH_PIN = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
SOURCE = 'https://github.com/ParAlg/PiPNN/blob/443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd/algorithms/utils/graph.h'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class Graph:
    """ParlayANN/PiPNN uint32 n,maxdeg; n uint32 degrees; sum(degrees) uint32 edges.

    This is NOT an interleaved [degree,edges] layout. Graph file is read-only.
    """
    def __init__(self, path):
        self.path = Path(path)
        if self.path.stat().st_size < 8:
            raise ValueError('Truncated graph')
        with self.path.open('rb') as f:
            self.n, self.maxdeg = struct.unpack('<II', f.read(8))
        if self.n == 0 or not (1 <= self.maxdeg <= 4096):
            raise ValueError('Invalid ParlayANN n/maxdeg header')
        self.degrees = np.memmap(self.path, mode='r', dtype='<u4', offset=8, shape=(self.n,))
        if int(self.degrees.max()) > self.maxdeg:
            raise ValueError('Degree exceeds max_degree')
        self.offsets = np.empty(self.n + 1, dtype=np.int64)
        self.offsets[0] = 0
        np.cumsum(self.degrees, dtype=np.int64, out=self.offsets[1:])
        self.arcs = int(self.offsets[-1])
        expected = 8 + self.n * 4 + self.arcs * 4
        actual = self.path.stat().st_size
        if actual != expected:
            raise ValueError(f'Graph format length mismatch: file={actual} expected={expected}')
        self.edges = np.memmap(self.path, dtype='<u4', mode='r',
                               offset=8 + self.n * 4, shape=(self.arcs,))

    def neighbors(self, u):
        return np.asarray(self.edges[self.offsets[u]:self.offsets[u + 1]], dtype=np.int64)

    def indegrees(self, chunk=2_000_000):
        result = np.zeros(self.n, dtype=np.int64)
        for start in range(0, self.arcs, chunk):
            destinations = np.asarray(self.edges[start:start + chunk], dtype=np.int64)
            if destinations.size and int(destinations.max()) >= self.n:
                raise ValueError('Out-of-range destination in graph')
            result += np.bincount(destinations, minlength=self.n).astype(np.int64)
        return result

    def incoming_for_sample(self, sample_ids, chunk=2_000_000):
        """Scan all arcs for incoming edges to sampled vertices; memory O(Echunk+sample)."""
        select = np.zeros(self.n, dtype=bool)
        select[sample_ids] = True
        inbound = {int(u): [] for u in sample_ids}
        for start in range(0, self.arcs, chunk):
            arr = np.asarray(self.edges[start:start + chunk])
            mask = select[arr]
            hit = np.flatnonzero(mask)
            if not len(hit):
                continue
            absolute_edge_positions = hit + start
            sources = np.searchsorted(self.offsets[1:], absolute_edge_positions, side='right')
            targets = arr[hit]
            for source, target in zip(sources, targets):
                inbound[int(target)].append(int(source))
        return inbound


class Pool:
    """int32 source-indexed fixed C array; -1 = padding."""
    def __init__(self, path, n, capacity):
        self.path = Path(path)
        if capacity < 1 or self.path.stat().st_size != 4 * n * capacity:
            raise ValueError('Candidate pool size does not match n*capacity*4')
        self.a = np.memmap(self.path, dtype='<i4', mode='r', shape=(n, capacity))
        self.capacity = capacity

    def candidates(self, u, n):
        raw = np.asarray(self.a[u], dtype=np.int64)
        if np.any((raw < -1) | (raw >= n)):
            raise ValueError(f'Invalid candidate ID in row {u}')
        if int(u) in raw:
            raise ValueError(f'Self candidate in row {u}')
        valid = raw[raw >= 0]
        if len(np.unique(valid)) != len(valid):
            raise ValueError(f'Duplicate candidate ID in row {u}')
        return valid


class Fbin:
    def __init__(self, path, n):
        self.path = Path(path)
        with open(path, 'rb') as f:
            head = f.read(8)
        if len(head) != 8:
            raise ValueError('Missing fbin header')
        nread, d = struct.unpack('<ii', head)
        if nread != n or d <= 0 or self.path.stat().st_size != 8 + nread * d * 4:
            raise ValueError('Invalid fbin header/length')
        self.d = d
        self.rows = np.memmap(self.path, mode='r', dtype='<f4', offset=8, shape=(n, d))


def angles_and_distances(src, ids, out_ids, X, cos_gate, distance_ratio):
    """Offline exact Float32 vector geometry PROXY, NOT PiPNN angular hash."""
    if not len(ids):
        return np.zeros(0, dtype=bool), np.zeros(0, dtype=bool), []
    center = np.asarray(X[src], dtype=np.float64)
    candvec = np.asarray(X[ids], dtype=np.float64) - center
    cdist = np.linalg.norm(candvec, axis=1)
    if len(out_ids):
        edgvec = np.asarray(X[out_ids], dtype=np.float64) - center
        edist = np.linalg.norm(edgvec, axis=1)
        scale = float(np.median(edist))
        cnorm = np.maximum(cdist, 1e-20)
        enorm = np.maximum(edist, 1e-20)
        sim = (candvec / cnorm[:, None]) @ (edgvec / enorm[:, None]).T
        sim = np.clip(sim, -1.0, 1.0)
        maxsim = np.max(sim, axis=1)
        angular_novel = maxsim < cos_gate
    else:
        scale = 0.0
        maxsim = np.full(len(ids), float('nan'))
        angular_novel = np.ones(len(ids), dtype=bool)
    # If no outgoing edge has positive scale, do NOT assert distance-feasibility.
    dist_feasible = (cdist <= scale * distance_ratio) if scale > 0 else np.zeros(len(ids), dtype=bool)
    examples = [(int(v), float(d), None if math.isnan(c) else float(c))
                for v, d, c in zip(ids[:3], cdist[:3], maxsim[:3])]
    return angular_novel, dist_feasible, examples


def selected_stats(source, graph, pool, vectors, indegree, inbound, cone_deg, distance_ratio):
    out = graph.neighbors(source)
    pool_ids = pool.candidates(source, graph.n)
    out_set = set(out.tolist())
    pool_set = set(pool_ids.tolist())
    reverse_set = set(inbound[source])
    reverse_set.discard(source)
    missed_graph_in_pool = len(out_set - pool_set)
    pnovel = pool_set - out_set
    rnovel = reverse_set - out_set
    combined = sorted(pnovel | rnovel)
    ids = np.array(combined, dtype=np.int64)
    novel, near, _ = angles_and_distances(source, ids, out, vectors.rows,
                                           math.cos(math.radians(cone_deg)), distance_ratio)
    low = indegree[ids] < 2
    both = novel & near
    from_reverse = np.isin(ids, list(rnovel), assume_unique=True)
    from_pool = np.isin(ids, list(pnovel), assume_unique=True)
    return {
        'source': int(source), 'outdegree': int(len(out)), 'indegree': int(indegree[source]),
        'slack': int(graph.maxdeg - len(out)), 'pool_count': int(len(pool_ids)),
        'graph_outside_pool': missed_graph_in_pool,
        'pool_new': int(len(pnovel)), 'reverse_new': int(len(rnovel)),
        'union_new': int(len(combined)), 'pool_and_reverse_new': int(len(pnovel & rnovel)),
        'distance_feasible': int(np.count_nonzero(near)),
        'angular_novel': int(np.count_nonzero(novel)),
        'angle_and_distance': int(np.count_nonzero(both)),
        'low_indegree_destination_candidates': int(np.count_nonzero(low)),
        'any_gate_feasible': int(np.count_nonzero(near & (novel | low))),
        'reverse_gate_feasible': int(np.count_nonzero(near & (novel | low) & from_reverse)),
        'pool_gate_feasible': int(np.count_nonzero(near & (novel | low) & from_pool)),
        'incoming_nonreciprocal': int(len(rnovel)),
        # one plausible PREVIEW only; using this as an actual algorithm needs
        # a SAME-ARC-BUDGET graph and native search comparisons.
        'has_candidate_under_any_gate': bool(np.any(near & (novel | low))),
    }


def analyze(args):
    graph = Graph(args.graph)
    pool = Pool(args.pool, graph.n, args.capacity)
    vec = Fbin(args.fbin, graph.n)
    if args.expected_n and graph.n != args.expected_n:
        raise ValueError('Unexpected n')
    if args.expected_maxdeg and graph.maxdeg != args.expected_maxdeg:
        raise ValueError('Unexpected maxdeg')
    if args.verify_sha:
        ghash = sha256(args.graph)
        phash = sha256(args.pool)
        if not args.no_pins and (ghash != GRAPH_PIN or phash != POOL_PIN):
            raise ValueError('Locked R26a SHA mismatch: refusing audit')
    else:
        if not args.no_pins:
            raise ValueError('For R26a, do not skip --verify-sha without --no-pins')
        ghash = phash = 'NOT_CHECKED'
    indegree = graph.indegrees()
    if indegree.sum() != graph.arcs:
        raise AssertionError('indegree conservation failed')
    rng = np.random.default_rng(args.seed)
    sources = np.sort(rng.choice(graph.n, min(args.sample, graph.n), replace=False))
    inbound = graph.incoming_for_sample(sources)
    stats = [selected_stats(int(u), graph, pool, vec, indegree, inbound,
                            args.cone_deg, args.distance_ratio) for u in sources]
    def total(key): return int(sum(s[key] for s in stats))
    def quantiles(key):
        arr=np.array([s[key] for s in stats]);return {
            'min':int(arr.min()), 'median':float(np.median(arr)),
            'p90':float(np.quantile(arr,0.9)), 'max':int(arr.max())}
    zero = np.flatnonzero(indegree == 0)
    result = {
        'audit':'CORE-SLACK-R0', 'status':'READ_ONLY_STRUCTURAL_DIAGNOSTIC_NOT_BUILD_OR_RECALL',
        'source_pinned_graph_format':SOURCE, 'graph_file':str(args.graph),
        'pool_file':str(args.pool), 'fbin_file':str(args.fbin),
        'graph_sha256':ghash, 'pool_sha256':phash,
        'n':graph.n, 'd':vec.d, 'max_degree':graph.maxdeg,
        'graph_arcs':graph.arcs,
        'graph_bytes':os.stat(args.graph).st_size,
        'candidate_capacity':pool.capacity,
        'global_outdegree_mean':float(graph.arcs/graph.n),
        'global_outdegree_lt_cap':int(np.count_nonzero(graph.degrees < graph.maxdeg)),
        'global_indegree_zero_count':int(len(zero)),
        'global_indegree_lt_2_count':int(np.count_nonzero(indegree < 2)),
        'global_indegree_zero_ids_sample':zero[:12].tolist(),
        'sample':int(len(sources)), 'seed':args.seed,
        'sample_ids_sha256':hashlib.sha256(sources.astype('<u4').tobytes()).hexdigest(),
        'cone_degree_threshold_proxy':args.cone_deg,
        'cone_similarity_gate':math.cos(math.radians(args.cone_deg)),
        'candidate_distance_to_median_out_distance_max_ratio':args.distance_ratio,
        'sample_profile':{
          'outdegree':quantiles('outdegree'), 'indegree':quantiles('indegree'),
          'slack':quantiles('slack'), 'pool_count':quantiles('pool_count'),
          'pool_new':quantiles('pool_new'), 'reverse_new':quantiles('reverse_new'),
          'union_new':quantiles('union_new'),
        },
        'sample_totals':{key:total(key) for key in [
          'pool_count','graph_outside_pool','pool_new','reverse_new','pool_and_reverse_new',
          'union_new','distance_feasible','angular_novel','angle_and_distance',
          'low_indegree_destination_candidates','any_gate_feasible','reverse_gate_feasible',
          'pool_gate_feasible','incoming_nonreciprocal']},
        'sample_sources_with_slack':sum(s['slack']>0 for s in stats),
        'sample_sources_with_any_gate_feasible_candidate':sum(s['has_candidate_under_any_gate'] for s in stats),
        'max_additional_arcs_without_global_budget_control':min(graph.n*2, int(np.sum(np.minimum(2,np.maximum(graph.maxdeg-graph.degrees.astype(np.int64),0))))),
        'sample_rows_first_12':stats[:12],
        'warnings':[
            'No graph or candidate file was modified. No replacement/augmentation applied.',
            'Geometric angular novelty (cosine relative to existing outgoing directions) is a PROXY, NOT native 12-bit HashPrune angular hashes or 64-bit compressed super-cone flags.',
            'Recomputed L2 geometry on sample: contradicts any claim of zero extra distance work in this offline audit.',
            'Slack is per-vertex; even delta_max=2 does not guarantee matched total arcs. A full new graph must replace arcs under an explicit total arc budget.',
            'Reverse proposals derive from ALL incoming arcs of the pinned graph; backup candidates derive from source candidate pool; sampled source analyses do not constitute graph-level topology improvement.',
            'No locality/query-distance evaluation. Do NOT infer better Recall, QPS, navigability or BUILD time.',
        ],
    }
    if args.output:
        dst=Path(args.output);dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return result


def test():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        n,d,cap=6,2,4
        X=np.array([[0,0],[1,0],[0,1],[1,1],[3,0],[3,1]],dtype='<f4')
        f=td/'base.fbin'
        with f.open('wb') as out:
            out.write(struct.pack('<ii',n,d));out.write(X.tobytes())
        neighbors=[[1,2],[0,3],[0],[1],[5],[]]
        g=td/'g.graph'
        with g.open('wb') as out:
            out.write(struct.pack('<II',n,3))
            out.write(np.array([len(row) for row in neighbors],dtype='<u4').tobytes())
            out.write(np.array([v for row in neighbors for v in row],dtype='<u4').tobytes())
        rows=np.array([[1,2,3,-1],[0,3,2,-1],[0,3,-1,-1],[1,2,-1,-1],[5,1,-1,-1],[4,-1,-1,-1]],dtype='<i4')
        pool=td/'pool.i32'; pool.write_bytes(rows.tobytes())
        params=argparse.Namespace(graph=g,pool=pool,fbin=f,capacity=cap,
            expected_n=n,expected_maxdeg=3,verify_sha=True,no_pins=True,
            sample=n,seed=123,cone_deg=30.,distance_ratio=2.0,output=td/'out.json')
        result=analyze(params)
        assert result['graph_arcs']==7
        assert result['global_indegree_zero_count']==1  # vertex 4 has no incoming edge
        assert result['sample']==6
        assert result['sample_totals']['reverse_new']>=1
        assert result['sample_totals']['pool_new']>=1
        assert result['graph_bytes']==8+4*n+4*7
        # wrong format and wrong pool dimensions must fail cleanly
        with open(g,'ab') as fh:fh.write(b'X')
        try:Graph(g)
        except ValueError:pass
        else:raise AssertionError('Failed to reject malformed graph length')
        print('R37_SELFTEST_PASS: graph layout, inbound reverse, candidate pool and safeguards')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('selftest')
    a=sub.add_parser('audit')
    a.add_argument('--graph',required=True)
    a.add_argument('--pool',required=True)
    a.add_argument('--fbin',required=True)
    a.add_argument('--capacity',type=int,default=160)
    a.add_argument('--expected-n',type=int,default=1000000)
    a.add_argument('--expected-maxdeg',type=int,default=32)
    a.add_argument('--sample',type=int,default=512)
    a.add_argument('--seed',type=int,default=20261030)
    a.add_argument('--cone-deg',type=float,default=30.)
    a.add_argument('--distance-ratio',type=float,default=2.)
    a.add_argument('--verify-sha',action=argparse.BooleanOptionalAction,default=True)
    a.add_argument('--no-pins',action='store_true',help='Only for synthetic fixture, not R26a')
    a.add_argument('--output')
    args=ap.parse_args()
    if args.command=='selftest':test();return
    if args.sample <= 0:
        ap.error('--sample must be >=1')
    if not (0 < args.cone_deg < 180) or not (args.distance_ratio>0):
        ap.error('Invalid cone/deviation threshold')
    analyze(args)

if __name__=='__main__':main()
