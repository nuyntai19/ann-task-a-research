#!/usr/bin/env python3
"""H32-R34: sampled global OUTGOING Top-2 candidate-union rescue across overlapping H18 leaves.

Uses the real H18LEAF1 membership and SIFT1M fbin; NO graph BUILD, no HashPrune,
no reverse candidate proposals, no genuine leader/Core flags, no Recall.

Requires ann_task_a_r29.py in the same folder and NumPy.
"""
import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
from ann_task_a_r29 import LeafIndex, Fbin


def make_core(m, x, mode, gamma, seed, leaf_id):
    k = int(round(m * gamma))
    k = min(m, max(0, k))
    mask = np.zeros(m, dtype=np.bool_)
    if mode == 'random':
        # Stable per-leaf permutation; nested choices for all gamma values.
        local_seed = ((int(seed) << 32) ^ int(leaf_id) ^ 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
        rng = np.random.default_rng(local_seed)
        mask[rng.permutation(m)[:k]] = True
    elif mode == 'centroid-proxy':
        z = x.astype(np.float64)
        ctr = z.mean(axis=0)
        norms = np.sum((z - ctr) ** 2, axis=1)
        mask[np.argsort(norms, kind='stable')[:k]] = True
    else:
        raise ValueError('Only cheap-Core controls are supported (random, centroid-proxy)')
    return mask


def report(a):
    start = time.monotonic()
    rng = random.Random(a.seed)
    ix = LeafIndex(a.leaves)
    try:
        vec = Fbin(a.fbin, ix.n)
        sources = sorted(rng.sample(range(ix.n), min(a.sources, ix.n)))
        nsrc = len(sources)
        lookup = np.full(ix.n, -1, dtype=np.int32)
        lookup[np.asarray(sources, dtype=np.int64)] = np.arange(nsrc, dtype=np.int32)
        affected = {}  # leaf -> list of sampled source indices present in that leaf
        memberships = np.zeros(nsrc, dtype=np.int32)
        for leaf_id in range(ix.nleaves):
            ids = ix.leaf(leaf_id)
            hits = lookup[ids]
            which = hits[hits >= 0]
            if which.size:
                if len(np.unique(which)) != len(which):
                    raise RuntimeError(f'duplicate sampled point within leaf={leaf_id}')
                affected[leaf_id] = which.tolist()
                memberships[which] += 1
        if np.any(memberships == 0):
            raise RuntimeError('Some sampled sources are absent from all leaves; inspect input')

        gammas = sorted(set(a.gamma))
        modes = list(dict.fromkeys(a.modes))
        keys = [(g, mode) for g in gammas for mode in modes]
        orig = [set() for _ in range(nsrc)]
        reduced = {key: [set() for _ in range(nsrc)] for key in keys}
        local_preserved = {key: 0 for key in keys}
        missed_events = {key: [[] for _ in range(nsrc)] for key in keys}
        accounted_pairs = {key: [0, 0] for key in keys}
        local_events = 0

        for leaf_id, hit_src_indexes in affected.items():
            ids_unsorted = ix.leaf(leaf_id).astype(np.int64)
            order = np.argsort(ids_unsorted, kind='stable')
            ids = ids_unsorted[order]
            x = np.asarray(vec.rows[ids], dtype=np.float32)
            m = len(ids)
            if m < 3:  # H18 real leaves >= 61; safety for synthetic fixtures.
                continue
            local_index = {int(xid): i for i, xid in enumerate(ids)}
            masks = {key: make_core(m, x, key[1], key[0], a.seed, leaf_id) for key in keys}
            for key, mask in masks.items():
                halo = m - int(mask.sum())
                accounted_pairs[key][0] += m * (m - 1) // 2
                accounted_pairs[key][1] += halo * (halo - 1) // 2

            for src_no in hit_src_indexes:
                src_id = sources[src_no]
                pos = local_index[src_id]
                # Squared L2 row computed in f32; ties broken by ascending global id.
                diff = np.asarray(x - x[pos], dtype=np.float32)
                d2 = np.einsum('ij,ij->i', diff, diff, dtype=np.float32)
                d2[pos] = np.inf
                full_idx = np.argsort(d2, kind='stable')[:2]
                full_neighbors = tuple(map(int, ids[full_idx]))
                orig[src_no].update(full_neighbors)
                local_events += 2

                for key, mask in masks.items():
                    if mask[pos]:
                        chosen = full_neighbors
                    else:
                        eligible = np.flatnonzero(mask)
                        if not len(eligible):
                            chosen = ()
                        else:
                            order2 = np.argsort(d2[eligible], kind='stable')[:2]
                            chosen = tuple(map(int, ids[eligible[order2]]))
                    reduced[key][src_no].update(chosen)
                    retained = len(set(chosen).intersection(full_neighbors))
                    local_preserved[key] += retained
                    for node in full_neighbors:
                        if node not in chosen:
                            missed_events[key][src_no].append(node)

        result = {
            'audit': 'H32-R34_GLOBAL_OUTGOING_TOP2_UNION_DIAGNOSTIC',
            'status': 'SAMPLED_SOURCE_OFFLINE_ONLY',
            'limitations': ('Only OUTGOING per-source Top2 proposals; excludes proposals inserted '
                            'via other sources or symmetric edge updates, HashPrune, final prune, '
                            'true original Core/leader flags, index quality and ANN Recall.'),
            'leaf_file': str(a.leaves), 'fbin_file': str(a.fbin),
            'n_base': ix.n, 'dimension': vec.d, 'n_leaves_total': ix.nleaves,
            'sources_requested': a.sources, 'sample_sources': nsrc, 'seed': a.seed,
            'sample_source_ids_sha256': hashlib.sha256(np.array(sources, dtype='<u4').tobytes()).hexdigest(),
            'source_memberships_total': int(memberships.sum()),
            'source_memberships_mean': float(memberships.mean()),
            'incident_leaves_scanned': len(affected),
            'source_selection': 'uniform point-ID sample; all leaves containing each sampled source',
            'core_selection': 'deterministic per-leaf random or centroid-proxy; NOT true leader lineage',
            'local_directed_top2_events': local_events,
            'baseline_outgoing_unique_candidate_count': sum(len(s) for s in orig),
            'scenarios': []
        }
        for g, mode in keys:
            key = (g, mode)
            bsum = sum(len(s) for s in orig)
            kept = sum(len(orig[i].intersection(reduced[key][i])) for i in range(nsrc))
            cnt_missed = sum(len(e) for e in missed_events[key])
            rescued = sum(sum((z in reduced[key][i]) for z in missed_events[key][i]) for i in range(nsrc))
            local_keep = local_preserved[key]
            ratios = [len(orig[i].intersection(reduced[key][i])) / len(orig[i]) if orig[i] else 1.0 for i in range(nsrc)]
            allpairs, skipped = accounted_pairs[key]
            result['scenarios'].append({
                'gamma': g, 'mode': mode,
                'pair_savings_fraction_on_incident_leaves': skipped / max(allpairs, 1),
                'local_event_coverage': local_keep / max(local_events, 1),
                'global_outgoing_unique_candidate_coverage': kept / max(bsum, 1),
                'source_level_coverage_mean': float(np.mean(ratios)),
                'source_level_coverage_min': float(np.min(ratios)),
                'sources_with_missing_baseline_candidates': sum(len(orig[i].difference(reduced[key][i])) > 0 for i in range(nsrc)),
                'baseline_outgoing_unique_candidates': bsum,
                'retained_unique_candidates': kept,
                'missed_local_events': cnt_missed,
                'missed_local_events_rescued_elsewhere': rescued,
                'overlap_rescue_fraction_among_missed_local_events': rescued / max(cnt_missed, 1),
            })
        result['elapsed_seconds'] = round(time.monotonic() - start, 2)
        if a.output:
            target = Path(a.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        ix.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--leaves', required=True)
    p.add_argument('--fbin', required=True)
    p.add_argument('--sources', type=int, default=64)
    p.add_argument('--seed', type=int, default=20261030)
    p.add_argument('--gamma', type=float, nargs='+', default=[0.25, 0.5, 0.75])
    p.add_argument('--modes', nargs='+', choices=['random', 'centroid-proxy'], default=['random', 'centroid-proxy'])
    p.add_argument('--output')
    a = p.parse_args()
    if a.sources < 1 or any(not 0 <= g <= 1 for g in a.gamma):
        p.error('sources must be >=1 and all gamma values must be within [0,1]')
    report(a)

if __name__ == '__main__':
    main()
