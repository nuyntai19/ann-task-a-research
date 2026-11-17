#!/usr/bin/env python3
"""R55 source-linked, SYNTHETIC numerical gate for PiPNN LSHGraph::merge_neighbors.

This is NOT the original compiled C++ implementation and does not inspect
SIFT1M candidate streams. It models specific, cited comparisons in pinned
ParAlg/PiPNN commit 443a328 (algorithms/utils/graph.h, L738-L835).
"""
import argparse
import json
import math
import os
import struct
from pathlib import Path

SOURCE_URL = ("https://github.com/ParAlg/PiPNN/blob/"
              "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd/"
              "algorithms/utils/graph.h#L738-L835")


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def bf16_rne(x):
    """Emulate IEEE bfloat16 round-nearest-even via a float32 bit pattern.

    Assumption: Eigen::bfloat16 uses round-to-nearest-even for normal finite
    inputs. A native Eigen/C++ fixture is required to validate that assumption.
    """
    x = f32(x)
    assert math.isfinite(x)
    bits = struct.unpack('<I', struct.pack('<f', x))[0]
    hi = (bits + 0x7fff + ((bits >> 16) & 1)) >> 16
    return struct.unpack('<f', struct.pack('<I', hi << 16))[0]


def simulated_merge(order, cap):
    """Simulate the decisive source lines, not an entire graph build.

    Candidates are (ID, float32 squared-distance, 16-bit relative hash).
    The input stream is intentionally one candidate per merge-call. The exact
    C++ loop performs an early break, collision replacement, and bounded
    replacement; here every fixture candidate shares a hash, so the
    non-colliding array-shift branch is deliberately out of scope.
    """
    slots = []
    for pid, dist, hsh in order:
        dist = f32(dist)
        if len(slots) == cap:
            max_val = max(bf16_rne(old_dist) for _, old_dist, _ in slots)
            if dist >= max_val:  # C++ full-reservoir early break
                continue
        for i, (old_id, old_dist, old_hash) in enumerate(slots):
            if old_hash == hsh:
                if bf16_rne(old_dist) > dist:  # C++ collision comparison
                    slots[i] = (pid, dist, hsh)
                break
        else:
            if len(slots) < cap:
                slots.append((pid, dist, hsh))
            else:
                # Not used in the controlled collision examples below.
                raise AssertionError('fixture violates same-hash precondition')
    return [id for id, _, _ in slots]


def exact_float_reference(seq):
    # History independent reference winner, distinct distances by design.
    return min(seq, key=lambda r: (f32(r[1]), r[0]))[0]


def compute():
    a = (101, 1.002, 7)  # farther; rounds down to bfloat16 1.0
    b = (202, 1.001, 7)  # nearer; also rounds down to 1.0
    fixtures = {}
    for cap in (1, 2):
        ab = simulated_merge([a, b], cap)
        ba = simulated_merge([b, a], cap)
        assert ab == [101] and ba == [202], (cap, ab, ba)
        fixtures[str(cap)] = {
            'insertion_AB': ab,
            'insertion_BA': ba,
            'same_input_multiset': True,
            'different_survivors': ab != ba,
        }
    assert bf16_rne(a[1]) == bf16_rne(b[1]) == 1.0
    assert exact_float_reference([a, b]) == 202

    # Non-collision in representable bfloat16 distances: sanity control.
    c, d = (303, 1.02, 7), (404, 1.0, 7)
    ca = simulated_merge([c, d], 2)
    cb = simulated_merge([d, c], 2)
    assert ca == cb == [404], (ca, cb)

    return {
        'gate': 'R55_SYNTHETIC_BF16_ORDER_COUNTEREXAMPLE_PASS',
        'source': SOURCE_URL,
        'source_provenance': 'pinned GitHub commit, cited compare rules, not compiled native code',
        'precision_assumption': 'normal positive float32 to bfloat16 RNE',
        'model_scope': 'single-hash bucket, one candidate per merge call',
        'candidate_A': {'id': a[0], 'dist_f32': f32(a[1]), 'dist_bf16': bf16_rne(a[1])},
        'candidate_B': {'id': b[0], 'dist_f32': f32(b[1]), 'dist_bf16': bf16_rne(b[1])},
        'exact_float32_reference_winner': exact_float_reference([a, b]),
        'fixture_caps': fixtures,
        'distinct_bf16_control': {'AB': ca, 'BA': cb},
        'scientific_limitations': [
            'Does not prove original compiled Eigen C++ behaves identically.',
            'Does not estimate incidence on actual SIFT1M proposals or R26a graph.',
            'Does not refute ideal-real-distance HashPrune history-independence theorem.',
            'This is a correctness/precision research gate, not algorithm novelty or speedup.',
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['selftest', 'audit'])
    ap.add_argument('--output', default='experiments/H55/r55_bf16_synthetic_gate.json')
    args = ap.parse_args()
    report = compute()
    if args.mode == 'selftest':
        print('R55_SELFTEST_PASS: two insertion permutations differ under bfloat16 tie; float32 control matches')
        return
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open('x', encoding='utf8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write('\n')
    except FileExistsError:
        raise SystemExit(f'R55_BLOCKED: output exists; refusing overwrite: {out}')
    print(report['gate'])
    print('CAP1 AB/BA:', report['fixture_caps']['1']['insertion_AB'], report['fixture_caps']['1']['insertion_BA'])
    print('CAP2 AB/BA:', report['fixture_caps']['2']['insertion_AB'], report['fixture_caps']['2']['insertion_BA'])
    print('R55_REPORT', out)


if __name__ == '__main__':
    main()
