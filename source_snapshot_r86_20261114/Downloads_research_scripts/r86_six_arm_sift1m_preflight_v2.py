#!/usr/bin/env python3
"""Read-only SIFT1M six-arm preflight v2: split u32 IDs + float32 GT distances.

Pins source data, query, GT and OFF binary SHA256. Samples exact brute-force
L2 top-100 on 3+ queries; no ANN builds and no user-file writes.
D0 search remains advisory: an identified binary is not yet an approved arm.
"""
from __future__ import annotations

import argparse
import filecmp
import hashlib
import math
import struct
import sys
from pathlib import Path

BASE_SHA = "8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e"
QUERY_SHA = "9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65"
GT_SHA = "047418d19f3981e4fc2dd28ae3b6f72fa7108f40d9336bd2d80b07829885ba13"
STOCK_SHA = "aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be"
H17_SHA = "5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297"
BIN_REL = "algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
N, D, QN, K = 1_000_000, 128, 10_000, 100


def need(ok: bool, label: str) -> None:
    if not ok:
        raise RuntimeError(label)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_matrix(path: Path, name: str, shape: tuple[int, int], bytes_each: int = 4) -> None:
    need(path.is_file(), f"{name}_MISSING {path}")
    with path.open("rb") as fh:
        hdr = fh.read(8)
    need(len(hdr) == 8, f"{name}_SHORT_HEADER")
    got = struct.unpack("<II", hdr)
    need(got == shape, f"{name}_SHAPE_MISMATCH got={got} expected={shape}")
    expected = 8 + shape[0] * shape[1] * bytes_each
    need(path.stat().st_size == expected, f"{name}_SIZE_MISMATCH got={path.stat().st_size} expected={expected}")
    print(f"{name}_SHAPE_BYTES_PASS {shape} bytes={expected}", flush=True)


def cache_vars(p: Path) -> dict[str, str]:
    need(p.is_file(), f"CACHE_MISSING {p}")
    out: dict[str, str] = {}
    for line in p.read_text(errors="replace").splitlines():
        if line.startswith(("//", "#")) or ":" not in line or "=" not in line:
            continue
        out[line.split(":", 1)[0]] = line.split("=", 1)[1]
    return out


def verify_off_binaries(root: Path) -> None:
    build_root = root / "experiments/R86/gates/highway_r85_four_binary_jvYREW"
    for name, directory, expected_sha, h17 in [
        ("STOCK_OFF", "build_stock_off", STOCK_SHA, "OFF"),
        ("H17_OFF", "build_h17_off", H17_SHA, "ON"),
    ]:
        exe = build_root / directory / BIN_REL
        need(exe.is_file(), f"{name}_BINARY_MISSING {exe}")
        got = sha256(exe)
        need(got == expected_sha, f"{name}_BINARY_SHA_MISMATCH {got}")
        cache = cache_vars(exe.parents[2] / "CMakeCache.txt")
        expected = {"R70_USE_TIER": "OFF", "R71_USE_H17": h17,
                    "R86_USE_COUNTERS": "OFF", "CMAKE_BUILD_TYPE": "Release"}
        for key, val in expected.items():
            need(cache.get(key) == val, f"{name}_CMAKE_FLAG_MISMATCH {key} got={cache.get(key)} expected={val}")
        print(f"{name}_SHA_CMAKE_PASS {got} {exe}", flush=True)


def inspect_d0(root: Path) -> None:
    candidates = []
    caches = 0
    for p in (root / "experiments").rglob("CMakeCache.txt"):
        caches += 1
        try:
            c = cache_vars(p)
        except (OSError, RuntimeError):
            continue
        if (c.get("R70_USE_TIER"), c.get("R71_USE_H17"), c.get("R86_USE_COUNTERS")) != ("ON", "ON", "OFF"):
            continue
        exe = p.parent / BIN_REL
        if exe.is_file():
            candidates.append((exe, sha256(exe)))
    print(f"D0_CMAKE_CACHES_INSPECTED {caches} CANDIDATES {len(candidates)}")
    for p, s in candidates[:12]:
        print(f"D0_CANDIDATE_UNPINNED sha256={s} path={p}")
    print("D0_NEEDS_SEPARATE_SOURCE_BINARY_EVALUATOR_GATE")


def check_geometry(base: Path, queries: Path, gt: Path, count: int) -> None:
    import numpy as np

    X = np.memmap(base, dtype="<f4", mode="r", offset=8, shape=(N, D))
    Q = np.memmap(queries, dtype="<f4", mode="r", offset=8, shape=(QN, D))
    IDs = np.memmap(gt, dtype="<u4", mode="r", offset=8, shape=(QN, K))
    Dists = np.memmap(gt, dtype="<f4", mode="r", offset=8 + QN*K*4, shape=(QN, K))

    low, high = int(IDs.min()), int(IDs.max())
    need(low >= 0 and high < N, f"GT_ID_RANGE_HOLD low={low} high={high}")
    finite = bool(np.isfinite(Dists).all())
    need(finite and bool((Dists >= 0).all()), "GT_DISTANCE_NONFINITE_OR_NEGATIVE")
    print(f"GT_SPLIT_UINT32_IDS_PASS min={low} max={high}")
    print(f"GT_FLOAT32_DISTANCE_RANGE min={float(Dists.min()):.6g} max={float(Dists.max()):.6g}")
    diff = np.diff(Dists, axis=1)
    descending = int(np.count_nonzero(diff < -1e-4))
    print(f"GT_DISTANCE_MONOTONICITY_DECREASES={descending} (normally 0 for sorted 100-NN)")
    need(descending == 0, "GT_DISTANCES_NOT_SORTED")

    all_qs = [0, 4999, 9999, 17, 173, 731, 2025, 7777, 999]
    selected = all_qs[:count]
    need(1 <= count <= len(all_qs), "INVALID_SPOTCHECK_COUNT")
    conventions = []
    for qi in selected:
        ids = np.asarray(IDs[qi], dtype=np.int64)
        need(len(set(map(int, ids))) == K, f"GT_DUPLICATE_IDS q={qi}")
        q = np.asarray(Q[qi], dtype=np.float32)
        need(bool(np.isfinite(q).all()), f"QUERY_NONFINITE q={qi}")
        best_ids = np.empty((0,), dtype=np.int64)
        best_sq = np.empty((0,), dtype=np.float32)
        for start in range(0, N, 25_000):
            stop = min(N, start + 25_000)
            x = np.asarray(X[start:stop], dtype=np.float32)
            delta = x - q
            squared = np.einsum("ij,ij->i", delta, delta, optimize=True)
            need(bool(np.isfinite(squared).all()), f"DISTANCE_NONFINITE q={qi} chunk={start}")
            keep = min(K, stop-start)
            ix = np.argpartition(squared, keep - 1)[:keep]
            chunk_ids = start + ix.astype(np.int64)
            chunk_sq = squared[ix]
            merged_ids = np.concatenate((best_ids, chunk_ids))
            merged_sq = np.concatenate((best_sq, chunk_sq))
            selected_ix = np.argpartition(merged_sq, min(K, len(merged_sq))-1)[:K]
            best_ids = merged_ids[selected_ix]
            best_sq = merged_sq[selected_ix]
        cutoff = float(best_sq.max())
        gt0 = int(ids[0])
        gt_delta = np.asarray(X[gt0], dtype=np.float32) - q
        gt_top1_sq = float(np.dot(gt_delta, gt_delta))
        exact_top1_sq = float(best_sq.min())
        tol_sq = max(0.03, 2e-5 * max(1.0, cutoff))
        need(gt_top1_sq <= exact_top1_sq + tol_sq,
             f"GT_TOP1_GEOMETRY_MISMATCH q={qi} id={gt0} gt_sq={gt_top1_sq} exact_sq={exact_top1_sq}")
        missing_ids = set(map(int, ids)) - set(map(int, best_ids))
        if missing_ids:
            missing = np.asarray(sorted(missing_ids), dtype=np.int64)
            diff_missing = np.asarray(X[missing], dtype=np.float32) - q
            ds = np.einsum("ij,ij->i", diff_missing, diff_missing, optimize=True)
            need(float(ds.max()) <= cutoff + tol_sq,
                 f"GT_TOP100_SET_MISMATCH q={qi} missing={len(missing_ids)} cutoff={cutoff} max_missing_sq={float(ds.max())}")
        stored = float(Dists[qi, 0])
        true_l2 = math.sqrt(gt_top1_sq)
        if abs(stored-true_l2) <= max(0.1, 0.001 * true_l2):
            convention = "L2"
        elif abs(stored-gt_top1_sq) <= max(0.1, 0.001 * gt_top1_sq):
            convention = "L2_SQUARED"
        else:
            convention = "UNMATCHED"
        need(convention != "UNMATCHED",
             f"GT_DISTANCE_VALUE_MISMATCH q={qi} stored={stored} L2={true_l2} squared={gt_top1_sq}")
        conventions.append(convention)
        print(f"GT_EXACT_L2_TOP100_PASS q={qi} exact_common={100-len(missing_ids)}/100 "
              f"cutoff_sq={cutoff:.3f} stored_d0={stored:.4f} convention={convention}",flush=True)
    need(len(set(conventions))==1, "GT_DISTANCE_SEMANTICS_MIXED")
    print(f"GROUND_TRUTH_SPLIT_LAYOUT_EXACT_L2_{len(selected)}_QUERY_SPOTCHECK_PASS convention={conventions[0]}")
    print("NOTE_SPOTCHECK_NOT_FULL_10000_QUERY_VALIDATION")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "ann-task-a")
    parser.add_argument("--spotchecks", type=int, default=3, choices=range(1,10))
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    base, queries, gt = (root/"data/sift1m.fbin", root/"data/sift1m_queries.fbin", root/"data/sift1m_gt.ibin")
    check_matrix(base,"SIFT1M_BASE", (N,D))
    check_matrix(queries,"SIFT1M_QUERY", (QN,D))
    check_matrix(gt,"SIFT1M_GT_IDS_AND_DIST_SPLIT", (QN,K),8)
    for label, path, expected in [("BASE",base,BASE_SHA),("QUERY",queries,QUERY_SHA),("GT",gt,GT_SHA)]:
        got=sha256(path)
        need(got==expected, f"{label}_SHA_MISMATCH {got} expected={expected}")
        print(f"{label}_SHA_PASS {got}",flush=True)
    bigann = root/"data/bigann1m_prefix.fbin"
    if bigann.is_file():
        print(f"BIGANN1M_PREFIX_SAME_BYTES={filecmp.cmp(base,bigann,shallow=False)} (keep datasets separate)")
    verify_off_binaries(root)
    check_geometry(base,queries,gt,args.spotchecks)
    inspect_d0(root)
    print("R86_SIX_ARM_SIFT1M_GT_LAYOUT_L2_OFF_PIN_PREFLIGHT_PASS")
    print("D0_IS_NOT_YET_AN_APPROVED_BINARY; NO_BUILD_NO_WRITES")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"R86_SIX_ARM_SIFT1M_V2_PREFLIGHT_HOLD: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
