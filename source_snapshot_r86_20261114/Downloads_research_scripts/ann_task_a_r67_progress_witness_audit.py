#!/usr/bin/env python3
"""H32-R67: SIFT1M PiPNN same-build candidate-pool vs graph progress witnesses.

Read-only for every existing input. Never builds, searches ANN, or modifies a graph.
Only writes one new report JSON using exclusive-create; refuses overwrites.

Scientific object: sampled BASE-to-BASE one-step alpha-progress witnesses under
SIFT1M Float32 Euclidean, in (i) post-reservoir candidate pool and (ii) final
graph from the SAME pinned R26a run. Not a global navigability certificate,
query Recall test, or evidence that swapping edges improves anything.
"""
import argparse
import hashlib
import json
import math
import os
import struct
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

PIN_GRAPH = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
PIN_POOL = '7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8'
R26A_DIR = 'experiments/H32/H32_R26a_pool_20261029_172452_132314'
GRAPH_REL = R26A_DIR + '/nodump.graph'
POOL_REL = R26A_DIR + '/dump.candidates.i32'
BASE_REL = 'data/sift1m.fbin'
DEFAULT_N = 1_000_000
DEFAULT_D = 128
DEFAULT_C = 160
DEFAULT_MAXDEG = 32
DEFAULT_ARCS = 22_797_630
DEFAULT_SEED = 20261104
DEFAULT_SOURCES = 512
DEFAULT_PROBES = 256
ALPHAS = (1.0, 1.2)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def checked_regular_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing/not regular or symlink: {path}')
    return path.stat().st_size


def load_inputs(root, *, n, d, c, maxdeg, arcs, graph_sha, pool_sha):
    """Validate pinned provenance BEFORE sampling, then return read-only mmap arrays."""
    base_path = root / BASE_REL
    graph_path = root / GRAPH_REL
    pool_path = root / POOL_REL
    expected_base_bytes = 8 + n * d * 4
    if checked_regular_file(base_path) != expected_base_bytes:
        raise ValueError('SIFT base file size does not match configured Float32 fbin shape')
    with base_path.open('rb') as f:
        header = f.read(8)
    if len(header) != 8 or struct.unpack('<ii', header) != (n, d):
        raise ValueError('SIFT base fbin header mismatch')

    graph_bytes = checked_regular_file(graph_path)
    if graph_bytes != 8 + 4 * (n + arcs):
        raise ValueError('R26a graph exact expected file size mismatch')
    with graph_path.open('rb') as f:
        header = f.read(8)
    if len(header) != 8 or struct.unpack('<II', header) != (n, maxdeg):
        raise ValueError('R26a graph header mismatch')
    got_graph_sha = sha256_file(graph_path)
    if got_graph_sha != graph_sha:
        raise ValueError('R26a GRAPH SHA256 MISMATCH: refuse cross-run comparison')

    pool_bytes = checked_regular_file(pool_path)
    if pool_bytes != n * c * 4:
        raise ValueError('R26a post-reservoir pool exact file size mismatch')
    got_pool_sha = sha256_file(pool_path)
    if got_pool_sha != pool_sha:
        raise ValueError('R26a POOL SHA256 MISMATCH: refuse cross-run comparison')

    # Graph::save(): uint32 n,maxdegree | uint32 degrees[n] | uint32 neighbor_ids[sum(degrees)]
    degrees = np.memmap(graph_path, dtype='<u4', mode='r', offset=8, shape=(n,))
    if np.any(degrees > maxdeg):
        raise ValueError('graph degree exceeds max degree')
    offsets = np.empty(n + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(degrees, dtype=np.int64, out=offsets[1:])
    if int(offsets[-1]) != arcs:
        raise ValueError('graph degree sum does not match pinned arcs')
    neighbors = np.memmap(graph_path, dtype='<u4', mode='r', offset=8 + 4 * n, shape=(arcs,))
    candidates = np.memmap(pool_path, dtype='<i4', mode='r', shape=(n, c))
    base = np.memmap(base_path, dtype='<f4', mode='r', offset=8, shape=(n, d))
    return {
        'base': base, 'degrees': degrees, 'offsets': offsets, 'neighbors': neighbors,
        'candidates': candidates,
        'provenance': {
            'base_path': BASE_REL, 'base_n': n, 'base_d': d,
            'base_bytes': expected_base_bytes, 'base_sha256': sha256_file(base_path),
            'graph_path': GRAPH_REL, 'graph_bytes': graph_bytes,
            'graph_sha256': got_graph_sha, 'graph_n': n, 'graph_maxdegree': maxdeg,
            'graph_directed_arcs': arcs, 'pool_path': POOL_REL,
            'pool_bytes': pool_bytes, 'pool_sha256': got_pool_sha,
            'pool_capacity': c, 'graph_pool_same_run': 'R26a_ARCHIVE_DOCUMENTED_AND_HASH_PINNED',
        },
    }


def checked_row(source, inp, n):
    """Return candidate / graph IDs; ensure sampled graph row is a subset of pool row."""
    raw = np.asarray(inp['candidates'][source], dtype=np.int64)
    if np.any(raw < -1) or np.any(raw >= n):
        raise ValueError(f'pool IDs outside -1 / [0,{n}) at source {source}')
    first_pad = np.flatnonzero(raw == -1)
    if first_pad.size and np.any(raw[first_pad[0]:] != -1):
        raise ValueError(f'non-contiguous pool -1 padding at source {source}')
    cands = raw[raw != -1]
    if np.any(cands == source) or np.unique(cands).size != len(cands):
        raise ValueError(f'self or duplicate candidate at source {source}')
    beg, end = int(inp['offsets'][source]), int(inp['offsets'][source+1])
    graph = np.asarray(inp['neighbors'][beg:end], dtype=np.int64)
    if np.any(graph < 0) or np.any(graph >= n):
        raise ValueError(f'invalid graph neighbor ID at source {source}')
    if np.any(graph == source) or np.unique(graph).size != len(graph):
        raise ValueError(f'self/duplicate outgoing graph edge at source {source}')
    missing = np.setdiff1d(graph, cands, assume_unique=True)
    return cands, graph, [int(x) for x in missing]


def distance2_one(a, b):
    delta = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    return float(np.dot(delta, delta))


def distances2_many(base, indices, target):
    if len(indices) == 0:
        return np.empty(0, dtype=np.float64)
    # Efficient vectorized squared Euclidean distances for each sampled source's small row.
    vals = np.asarray(base[np.asarray(indices, dtype=np.int64)], dtype=np.float64)
    t = np.asarray(base[target], dtype=np.float64)
    delta = vals - t
    return np.einsum('ij,ij->i', delta, delta)


def witness(distances2, threshold2):
    """Three-valued conservative floating-boundary predicate: 1,0 or UNKNOWN.

    All original Float32 coordinates are promoted exactly to Float64; tolerance
    is only for borderline threshold comparisons (especially alpha1.2).
    """
    if not math.isfinite(threshold2) or threshold2 < 0:
        raise ValueError('non-finite or negative threshold')
    if not np.all(np.isfinite(distances2)) or np.any(distances2 < 0):
        raise ValueError('non-finite or negative squared L2')
    tol = 1e-12 * max(1.0, abs(threshold2))
    if np.any(distances2 < threshold2 - tol):
        return 1
    if np.any(np.abs(distances2 - threshold2) <= tol):
        return 'UNKNOWN_BOUNDARY'
    return 0


def probe_near_target(base, source, n, rng, probes):
    """Closest among `probes` uniform random other BASE points; not true kNN/GT."""
    raw = rng.choice(n - 1, size=probes, replace=False)
    ids = raw + (raw >= source)
    ds = distances2_many(base, ids, source)
    if not np.all(np.isfinite(ds)):
        raise ValueError('nonfinite probe distances')
    # argmin ties by sampled order; reproducible with fixed numpy RNG.
    chosen = int(ids[int(np.argmin(ds))])
    return chosen


def pair_result(base, source, target, cands, graph, alpha):
    if source == target:
        raise ValueError('source must not equal target')
    src_to_target2 = distance2_one(base[source], base[target])
    if not math.isfinite(src_to_target2) or src_to_target2 < 0:
        raise ValueError('invalid base-point pair distance')
    threshold2 = src_to_target2 / (alpha * alpha)
    pc = witness(distances2_many(base, cands, target), threshold2)
    pg = witness(distances2_many(base, graph, target), threshold2)
    return {
        'source': int(source), 'target': int(target), 'alpha': alpha,
        'source_target_distance2': src_to_target2, 'progress_threshold2': threshold2,
        'candidate_progress': pc, 'graph_progress': pg,
    }


def summarize_pairs(records, alphas):
    summaries = []
    for stratum in ('uniform_global', 'probe_near_256'):
        for alpha in alphas:
            part = [r for r in records if r['stratum'] == stratum and r['alpha'] == alpha]
            counts = Counter()
            for r in part:
                pc, pg = r['candidate_progress'], r['graph_progress']
                if pc == 'UNKNOWN_BOUNDARY' or pg == 'UNKNOWN_BOUNDARY':
                    counts['UNKNOWN_NUMERICAL_BOUNDARY'] += 1
                elif pc == 0 and pg == 1:
                    counts['VIOLATION_PC0_PG1'] += 1
                else:
                    counts[f'PC{pc}_PG{pg}'] += 1
            summaries.append({
                'stratum': stratum, 'alpha': alpha, 'source_target_pairs': len(part),
                'counts': {x: int(counts[x]) for x in (
                    'PC0_PG0','PC1_PG0','PC1_PG1','VIOLATION_PC0_PG1','UNKNOWN_NUMERICAL_BOUNDARY')},
                'interpretation': 'DESCRIPTIVE_FIXED_SAMPLE_NOT_GLOBAL_ALPHA_NAVIGABILITY',
            })
    return summaries


def sample_study(inp, *, n, samples, probes, seed, alphas):
    if not (2 <= samples <= n and 1 <= probes <= n - 1):
        raise ValueError('invalid sample_sources/probes for n')
    rng = np.random.default_rng(seed)
    sources = rng.choice(n, size=samples, replace=False)
    src_rows = {}
    violations = []
    for s in sources:
        s = int(s)
        cands, graph, missing = checked_row(s, inp, n)
        src_rows[s] = (cands, graph)
        if missing:
            violations.append({'source':s, 'missing_graph_neighbor_ids':missing})
    if violations:
        return {
            'state':'BLOCKED_GRAPH_NOT_SUBSET_OF_POST_RESERVOIR_POOL',
            'subset_checked_rows': samples, 'subset_violating_rows': len(violations),
            'subset_violations_first20': violations[:20],
            'note': 'Do not compute PC/PG category counts under an invalid subset premise.'
        }
    records = []
    all_ids = []
    for s in sources:
        s = int(s)
        cands, graph = src_rows[s]
        rand = int(rng.integers(0, n-1))
        t_global = rand + (rand >= s)
        t_near = probe_near_target(inp['base'], s, n, rng, probes)
        for stratum, t in (('uniform_global',t_global),('probe_near_256',t_near)):
            all_ids.extend((s, int(t)))
            for a in alphas:
                rec = pair_result(inp['base'], s, int(t), cands, graph, a)
                rec.update(stratum=stratum, candidate_degree=len(cands), graph_outdegree=len(graph))
                records.append(rec)
    serial = np.asarray(all_ids, dtype='<u4').tobytes()
    summary = summarize_pairs(records, alphas)
    violations2 = sum(s['counts']['VIOLATION_PC0_PG1'] for s in summary)
    if violations2:
        return {'state':'BLOCKED_PROGRESS_MONOTONICITY_INCONSISTENT',
                'subset_checked_rows':samples, 'summary':summary,
                'sample_id_stream_sha256':hashlib.sha256(serial).hexdigest()}
    return {
        'state':'PASS_DESCRIPTIVE_HEADROOM_ONLY',
        'subset_checked_rows':samples,'subset_violating_rows':0,
        'unique_sampled_sources':samples,'pair_targets_per_source':2,
        'sample_id_stream_sha256':hashlib.sha256(serial).hexdigest(),
        'summary':summary,'records':records,
    }


def report_exclusive(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create; never replace historical reports. UTF-8, flush and fsync.
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def audit(args):
    root = Path(args.root).expanduser().resolve(strict=True)
    if args.samples > 10000 or args.probes > 8192:
        raise ValueError('sampling resource guard exceeded')
    # Output refusal happens before any expensive disk reading.
    output = Path(args.output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'report already exists, refuse overwrite: {output}')
    inp = load_inputs(root, n=DEFAULT_N,d=DEFAULT_D,c=DEFAULT_C,
                      maxdeg=DEFAULT_MAXDEG,arcs=DEFAULT_ARCS,
                      graph_sha=PIN_GRAPH,pool_sha=PIN_POOL)
    result = sample_study(inp, n=DEFAULT_N,samples=args.samples,
                          probes=args.probes,seed=args.seed,alphas=ALPHAS)
    payload = {
        'study':'H32-R67_SAME_BUILD_ALPHA_PROGRESS_WITNESS_AUDIT',
        'scientific_status':'NOT_NEW_ALGORITHM_NOT_ANN_RECALL_NOT_GLOBAL_NAVIGABILITY',
        'execution_status':result['state'],
        'root':str(root),
        'source_commit':'ParAlg/PiPNN@443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd',
        'provenance':inp['provenance'],
        'design':{
            'sampling_seed':args.seed,
            'source_sampling':'uniform without replacement from 1m BASE points',
            'uniform_target':'one uniformly sampled distinct BASE ID per source',
            'probe_near_target':f'closest by exact Float64 L2 among {args.probes} uniformly sampled distinct BASE IDs per source; NOT true kNN',
            'sample_sources':args.samples,'sample_pairs_per_stratum':args.samples,
            'alphas':ALPHAS,'witness_rule':'d2(u,t) < d2(s,t) / (alpha^2)',
            'float_processing':'Float32 base promoted to Float64; classify borderline |d2-threshold2| <= 1e-12*max(1,threshold2) UNKNOWN',
            'graph_subset_check':'all outgoing neighbors in sampled rows must be in post-reservoir pool row',
            'leakage_control':'BASE ids only; no heldout query ground truth',
            'inference_limit':'sample descriptive only, no claims about all n*(n-1) ordered pairs, query Recall or global alpha guarantee',
        },
        'result':result,
    }
    report_exclusive(output,payload)
    print('R67_READONLY_SAMPLE_AUDIT_COMPLETED')
    print('R67_GRAPH_SHA PASS')
    print('R67_POOL_SHA PASS')
    print('R67_BASE_FORMAT PASS')
    print('R67_SAMPLED_GRAPH_SUBSET', 'PASS' if result['state']=='PASS_DESCRIPTIVE_HEADROOM_ONLY' else result['state'])
    if result['state']=='PASS_DESCRIPTIVE_HEADROOM_ONLY':
        for s in result['summary']:
            c=s['counts']
            print('R67_PROGRESS',s['stratum'],f"alpha={s['alpha']:g}",
                  f"PC0PG0={c['PC0_PG0']}",f"PC1PG0={c['PC1_PG0']}",
                  f"PC1PG1={c['PC1_PG1']}",f"UNKNOWN={c['UNKNOWN_NUMERICAL_BOUNDARY']}")
    else:
        print('R67_GATE HEADROOM BLOCKED_REQUIRE_PROVENANCE_REVIEW')
    print('R67_GATE H33 NOT_OPEN')
    print('R67_REPORT',str(output))
    return 0 if result['state']=='PASS_DESCRIPTIVE_HEADROOM_ONLY' else 2


def _write_fixture(tempdir):
    """Create a tiny fixed graph + valid pool for smoke/audit tests."""
    root = Path(tempdir)
    n, d, c, maxdeg = 8, 2, 3, 2
    base = np.array([[0,0],[-1,0],[9,0],[10,0],[0,7],[11,3],[20,0],[4,9]],dtype='<f4')
    b = root/BASE_REL
    b.parent.mkdir(parents=True,exist_ok=True)
    with b.open('wb') as f:
        f.write(struct.pack('<ii',n,d)); f.write(base.tobytes())
    # row0 graph neighbor1 is bad for target3, but candidate2 progresses.
    graph_rows = [[1],[0],[3],[2],[0],[3],[3],[5]]
    cand_rows = [[1,2,-1],[0,-1,-1],[3,-1,-1],[2,-1,-1],
                 [0,-1,-1],[3,-1,-1],[3,-1,-1],[5,-1,-1]]
    graph_p = root/GRAPH_REL
    graph_p.parent.mkdir(parents=True,exist_ok=True)
    arcs = sum(map(len,graph_rows))
    with graph_p.open('wb') as f:
        f.write(struct.pack('<II',n,maxdeg))
        f.write(np.array([len(r) for r in graph_rows],dtype='<u4').tobytes())
        for row in graph_rows:
            f.write(np.asarray(row,dtype='<u4').tobytes())
    pool_p = root/POOL_REL
    with pool_p.open('wb') as f:
        f.write(np.array(cand_rows,dtype='<i4').tobytes())
    return {'n':n,'d':d,'c':c,'maxdeg':maxdeg,'arcs':arcs,
            'graph_sha':sha256_file(graph_p),'pool_sha':sha256_file(pool_p)}


def selftest():
    with tempfile.TemporaryDirectory(prefix='ann_r67_selftest_') as tmp:
        params=_write_fixture(tmp)
        inp=load_inputs(Path(tmp),**params)
        c,g,missing=checked_row(0,inp,8)
        assert not missing and list(c)==[1,2] and list(g)==[1]
        one=pair_result(inp['base'],0,3,c,g,1.0)
        assert (one['candidate_progress'],one['graph_progress'])==(1,0)
        two=pair_result(inp['base'],0,3,c,g,1.2)
        assert (two['candidate_progress'],two['graph_progress'])==(1,0)
        assert witness(np.array([1.0]),1.0)=='UNKNOWN_BOUNDARY'
        assert witness(np.array([0.9]),1.0)==1
        assert witness(np.array([1.1]),1.0)==0
        rs=sample_study(inp,n=8,samples=6,probes=4,seed=9,alphas=ALPHAS)
        assert rs['state']=='PASS_DESCRIPTIVE_HEADROOM_ONLY'
        assert len(rs['records'])==24
        assert sum(x['source_target_pairs'] for x in rs['summary'])==24
        # Check fail-closed hash pin.
        try:
            load_inputs(Path(tmp),**dict(params,graph_sha='0'*64))
            raise AssertionError('hash mismatch accepted')
        except ValueError as e:
            assert 'SHA256 MISMATCH' in str(e)
        # Check subset violation detection on deliberately invalid graph-only neighbor.
        fake={**inp,'neighbors':np.array([7,0,3,2,0,3,3,5],dtype=np.uint32)}
        _,_,missing=checked_row(0,fake,8)
        assert missing==[7]
        bad=sample_study(fake,n=8,samples=8,probes=4,seed=9,alphas=ALPHAS)
        assert bad['state']=='BLOCKED_GRAPH_NOT_SUBSET_OF_POST_RESERVOIR_POOL'
        outfile=Path(tmp)/'selftest_report.json'
        report_exclusive(outfile,{'result':'PASS'})
        try:
            report_exclusive(outfile,{'result':'SHOULD_FAIL'})
            raise AssertionError('overwriting report accepted')
        except FileExistsError:pass
        assert json.loads(outfile.read_text())['result']=='PASS'
    print('R67_SYNTHETIC_SELFTEST_PASS')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('selftest',help='run tests on only synthetic tiny graph/pool')
    a=sub.add_parser('audit',help='audit immutable R26a archived SIFT1M')
    a.add_argument('--root',default='.',help='~/ann-task-a root')
    a.add_argument('--output',default='experiments/H67/r67_alpha_progress_witness.json',help='fresh JSON report path')
    a.add_argument('--samples',type=int,default=DEFAULT_SOURCES)
    a.add_argument('--probes',type=int,default=DEFAULT_PROBES)
    a.add_argument('--seed',type=int,default=DEFAULT_SEED)
    args=ap.parse_args()
    try:
        if args.command=='selftest': selftest(); return 0
        return audit(args)
    except Exception as e:
        print('R67_FAIL_CLOSED',type(e).__name__,str(e),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
