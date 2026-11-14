#!/usr/bin/env python3
"""R82.2 Hash collision prevalence diagnostic, no ANN graph builds.

Reads exact pinned H18 proposal capture and SIFT1M fbin. Compiles an isolated
C++ diagnostic using original PiPNN hash.h and Parlay headers. Never edits H70/H80.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
import time

HEAD = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
HASH_BLOB = '3d4a2c2f06b7d3eef3a637d8022a2e3ac14c6391'
CAPTURE_SHA = '13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95'
N, LEAVES, EVENTS = 1_000_000, 85_529, 59_990_170
SAMPLE = 128
MAGIC = b'H18R1P01'


def cmd(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sample_records(path: Path):
    expected_bytes = 32 + 8 * (LEAVES+1) + 8 * EVENTS
    if path.stat().st_size != expected_bytes:
        raise RuntimeError('R82_2_CAPTURE_SIZE_FAIL')
    with path.open('rb') as f:
        if struct.unpack('<8sQQQ', f.read(32)) != (MAGIC, N, LEAVES, EVENTS):
            raise RuntimeError('R82_2_CAPTURE_HEADER_FAIL')
        offsets = struct.unpack(f'<{LEAVES+1}Q', f.read(8*(LEAVES+1)))
    if offsets[0] != 0 or offsets[-1] != EVENTS:
        raise RuntimeError('R82_2_OFFSETS_BOUNDARY_FAIL')
    if any(x > y for x, y in zip(offsets, offsets[1:])):
        raise RuntimeError('R82_2_OFFSETS_ORDER_FAIL')

    rng = random.Random(20261106)
    ids = sorted(rng.sample(range(LEAVES), SAMPLE))
    result = bytearray()
    expected_rows = 0
    with path.open('rb') as f:
        for slot, leaf_id in enumerate(ids):
            a, b = offsets[leaf_id], offsets[leaf_id+1]
            f.seek(32 + 8 * (LEAVES+1) + 8*a)
            raw = f.read(8*(b-a))
            if len(raw) != 8*(b-a):
                raise RuntimeError('R82_2_CAPTURE_SHORT_READ')
            # Preserve exact per-source observation. Archive does not contain
            # real concurrent reservoir arrival sequence.
            pairs = {}
            for (packed,) in struct.iter_unpack('<Q', raw):
                src, dst = packed >> 32, packed & 0xffffffff
                if src >= N or dst >= N or src == dst:
                    raise RuntimeError('R82_2_BAD_PROPOSAL_ID')
                pairs.setdefault(src, []).append(dst)
            for src, v in pairs.items():
                if len(v) != 2 or v[0] == v[1]:
                    raise RuntimeError('R82_2_NOT_TOP2_SAMPLED_SOURCE_ROW')
                result.extend(struct.pack('<IIII', slot, src, v[0], v[1]))
                expected_rows += 1
    return ids, expected_rows, bytes(result)


def parse_kv(line: str):
    return {key: int(val) for key, val in re.findall(r'([a-z_]+)=(\d+)', line)}


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--root', default=str(Path.home()/'ann-task-a'))
    pa.add_argument('--output', default='r82_2_summary.json')
    args = pa.parse_args()
    root = Path(args.root).expanduser().resolve()
    base = root/'experiments/H70/pipnn-clean-443a328'
    cap = root/'experiments/H18/phase2_candidate_audit/leaf_proposals.bin'
    data = root/'data/sift1m.fbin'
    kit = Path(__file__).resolve().parent
    output = kit/args.output
    binary = kit/'r82_2_hash_probe_native'
    if output.exists():
        raise RuntimeError('R82_2_OUTPUT_ALREADY_EXISTS_FAIL_CLOSED')
    if cmd('git', '-C', str(base), 'rev-parse', 'HEAD') != HEAD:
        raise RuntimeError('R82_2_HEAD_MISMATCH')
    actual_blob = cmd('git', '-C', str(base), 'hash-object', 'algorithms/utils/hash.h')
    if actual_blob != HASH_BLOB:
        raise RuntimeError('R82_2_HASH_H_CONTENT_MISMATCH')
    if not (base/'parlaylib/include/parlay/random.h').is_file():
        raise RuntimeError('R82_2_PARLAY_HEADERS_MISSING')
    with data.open('rb') as f:
        d = f.read(8)
    if len(d) != 8 or struct.unpack('<II', d) != (N, 128) or data.stat().st_size != (N*128*4+8):
        raise RuntimeError('R82_2_SIFT1M_BASE_FORMAT_FAIL')
    if sha256(cap) != CAPTURE_SHA:
        raise RuntimeError('R82_2_CAPTURE_SHA_FAIL')
    print('R82_2_SOURCE_AND_CAPTURE_GATES_PASS', flush=True)
    leaf_ids, expected_rows, raw = sample_records(cap)
    print(f'R82_2_TOP2_ROWS_PASS leaves={len(leaf_ids)} rows={expected_rows}', flush=True)

    # Only native projection-family and source-compatible float sketch sums;
    # NO run of original full PiPNN BUILD or live reservoir instrumentation.
    compiler = ['/usr/bin/c++', '-std=c++17', '-O2', '-ffp-contract=off', '-pthread',
                '-I'+str(base), '-I'+str(base/'parlaylib/include'),
                str(kit/'r82_2_hash_probe.cc'), '-o', str(binary)]
    cp = subprocess.run(compiler, capture_output=True, text=True)
    if cp.returncode:
        print(cp.stdout[-9000:], file=sys.stderr)
        print(cp.stderr[-16000:], file=sys.stderr)
        raise RuntimeError('R82_2_NATIVE_COMPILE_BLOCKED')
    print('R82_2_NATIVE_PROBE_COMPILE_PASS', flush=True)
    cp = subprocess.run([str(binary), str(data)], input=raw, capture_output=True)
    if cp.returncode:
        print(cp.stdout.decode(errors='replace')[-5000:], file=sys.stderr)
        print(cp.stderr.decode(errors='replace')[-10000:], file=sys.stderr)
        raise RuntimeError('R82_2_NATIVE_EXECUTION_FAIL')
    lines = cp.stdout.decode().splitlines()
    if not lines or lines[-1] != 'R82_2_CPP_HASH_DIAGNOSTIC_PASS':
        raise RuntimeError('R82_2_NATIVE_PASS_MARKER_MISSING')
    top = [x for x in lines if x.startswith('R82_2_COUNTS ')]
    ls = [x for x in lines if x.startswith('R82_2_LEAF ')]
    if len(top) != 1 or len(ls) != SAMPLE:
        raise RuntimeError('R82_2_NATIVE_OUTPUT_SCHEMA_FAIL')
    counts = parse_kv(top[0])
    leaves = [parse_kv(s) for s in ls]
    if counts.get('rows') != expected_rows or sum(x['rows'] for x in leaves) != expected_rows:
        raise RuntimeError('R82_2_COUNTS_FAIL')
    if not (0 <= counts['definite'] <= counts['nominal'] + counts['sensitive'] <= counts['rows'] * 2):
        raise RuntimeError('R82_2_COUNT_SANITY_FAIL')
    if not (counts['definite'] <= counts['possible'] <= counts['rows']):
        raise RuntimeError('R82_2_COLLISION_INTERVAL_FAIL')
    result = {
        'status': 'DIAGNOSTIC_ONLY_NOT_GRAPH_BUILD_NOT_RECALL',
        'source_commit': HEAD, 'source_hash_h_git_blob': HASH_BLOB,
        'capture_sha256': CAPTURE_SHA,
        'dataset': 'SIFT1M 1m x 128 float32',
        'sample_seed': 20261106, 'sampled_leaf_ids': leaf_ids,
        'hash_method': 'Original pinned Hash_Family hyperplanes; source-matching per-point float accumulation, 12-bit relative sketches, seed=0',
        'hash_float_caveat': 'Native standalone probe compiled without FMA; not a recorded hash from original build. 1e-6 relative boundary is a heuristic sensitivity flag, NOT rigorous numerical error bound.',
        'counts': counts, 'per_leaf': leaves,
        'nominal_rate': counts['nominal']/counts['rows'],
        'conservative_lower_rate': counts['definite']/counts['rows'],
        'conservative_possible_rate': counts['possible']/counts['rows'],
        'candidate_s3_effect_not_measured': True,
        'data_provenance': 'H18 R1 proposals not R26a, no real mutex arrival order or pre-reservoir rejected events.'
    }
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('R82_2_HASH_COLLISION_DIAGNOSTIC_PASS')
    print('R82_2_COUNTS', json.dumps(counts, sort_keys=True))
    print(f"R82_2_RATES nominal={result['nominal_rate']:.6%} conservative_lower={result['conservative_lower_rate']:.6%} conservative_possible={result['conservative_possible_rate']:.6%}")
    print('R82_2_REPORT', output)
    print('R82_2_NOT_ANN_BUILD_NOT_RECALL_NOT_NOVELTY')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
