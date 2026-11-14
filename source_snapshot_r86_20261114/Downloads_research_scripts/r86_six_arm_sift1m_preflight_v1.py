#!/usr/bin/env python3
"""Read-only R86 six-arm SIFT1M gate: data/query/GT geometry and OFF binary provenance.

NO ANN build, NO output writes, NO modifications. D0 search is advisory only.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import struct
import sys
from pathlib import Path

EXPECTED = {
    "base": "8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e",
    "stock_off": "aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be",
    "h17_off": "5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297",
}
BIN_REL = "algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"


def fail(message: str) -> None:
    raise RuntimeError(message)


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def matrix_shape(path: Path, label: str, expected: tuple[int, int], bytes_per_item: int) -> None:
    if not path.is_file():
        fail(f"{label}_MISSING: {path}")
    if path.stat().st_size < 8:
        fail(f"{label}_HEADER_SHORT")
    with path.open("rb") as f:
        got = struct.unpack("<II", f.read(8))
    if got != expected:
        fail(f"{label}_SHAPE_HOLD: {got} expected={expected}")
    want_bytes = 8 + expected[0] * expected[1] * bytes_per_item
    if path.stat().st_size != want_bytes:
        fail(f"{label}_BYTE_COUNT_HOLD: actual={path.stat().st_size} expected={want_bytes}")
    print(f"{label}_SHAPE_BYTES_PASS shape={got} bytes={want_bytes}", flush=True)


def cmake_vars(cache: Path) -> dict[str, str]:
    if not cache.is_file():
        fail(f"CMAKE_CACHE_MISSING: {cache}")
    vals = {}
    for line in cache.read_text(errors="replace").splitlines():
        if line.startswith("//") or line.startswith("#") or "=" not in line or ":" not in line:
            continue
        vals[line.split(":", 1)[0]] = line.split("=", 1)[1]
    return vals


def binary_off_gate(root: Path) -> None:
    build_base = root / "experiments/R86/gates/highway_r85_four_binary_jvYREW"
    for kind, sub, want_h17 in [("stock_off", "build_stock_off", "OFF"),
                                ("h17_off", "build_h17_off", "ON")]:
        binary = build_base / sub / BIN_REL
        if not binary.is_file():
            fail(f"{kind}_BINARY_MISSING: {binary}")
        got_sha = digest(binary)
        if got_sha != EXPECTED[kind]:
            fail(f"{kind}_PIN_MISMATCH: {got_sha} expected={EXPECTED[kind]}")
        cache = cmake_vars(build_base / sub / "CMakeCache.txt")
        for key, value in {
            "R70_USE_TIER": "OFF", "R71_USE_H17": want_h17,
            "R86_USE_COUNTERS": "OFF", "CMAKE_BUILD_TYPE": "Release",
        }.items():
            if cache.get(key) != value:
                fail(f"{kind}_FLAG_MISMATCH: {key} got={cache.get(key)} expected={value}")
        print(f"{kind.upper()}_BINARY_AND_CMAKE_PIN_PASS sha256={got_sha} path={binary}", flush=True)


def d0_inventory(root: Path) -> None:
    matches = []
    caches_seen = 0
    for cache in (root / "experiments").rglob("CMakeCache.txt"):
        caches_seen += 1
        try:
            c = cmake_vars(cache)
        except (OSError, RuntimeError):
            continue
        if c.get("R70_USE_TIER") == "ON" and c.get("R71_USE_H17") == "ON" and c.get("R86_USE_COUNTERS") == "OFF":
            binary = cache.parent / BIN_REL
            if binary.is_file():
                matches.append((binary, digest(binary)))
    print(f"D0_CMAKE_CACHES_SCANNED={caches_seen} D0_CANDIDATE_BINARIES={len(matches)}")
    for p, h in matches[:15]:
        print(f"D0_CANDIDATE_UNPINNED sha256={h} path={p}")
    if not matches:
        print("D0_OFF_NOT_FOUND_IN_CMAKE_CACHES_PREPARATION_REQUIRED")
    else:
        print("D0_CANDIDATES_FOUND_BUT_SOURCE_AND_EVALUATOR_COMPATIBILITY_NOT_YET_PINNED")


def geometry_spot_check(base: Path, query: Path, gt: Path) -> None:
    try:
        import numpy as np
    except ImportError as e:
        fail(f"NUMPY_REQUIRED_FOR_GEOMETRIC_SPOTCHECK: {e}")
    X = np.memmap(base, dtype="<f4", mode="r", offset=8, shape=(1_000_000, 128))
    Q = np.memmap(query, dtype="<f4", mode="r", offset=8, shape=(10_000, 128))
    G = np.memmap(gt, dtype="<i8", mode="r", offset=8, shape=(10_000, 100))
    lo, hi = int(G.min()), int(G.max())
    print(f"GROUND_TRUTH_ID_RANGE min={lo} max={hi}")
    if lo < 0 or hi >= 1_000_000:
        fail("GT_ID_OUT_OF_RANGE_SIFT1M")
    for idx in [0, 4999, 9999]:
        ids = np.asarray(G[idx], dtype=np.int64)
        if len(set(map(int, ids))) != 100:
            fail(f"GT_ROW_DUPLICATE_IDS q={idx}")
        q = np.asarray(Q[idx], dtype=np.float32)
        gt_dist = float(np.sum((np.asarray(X[int(ids[0])], dtype=np.float32) - q)**2))
        if not np.isfinite(gt_dist):
            fail(f"NONFINITE_GT_DISTANCE q={idx}")
        best = math.inf
        best_id = None
        for start in range(0, 1_000_000, 25_000):
            chunk = np.asarray(X[start:start + 25_000], dtype=np.float32)
            delta = chunk - q
            dsq = np.einsum("ij,ij->i", delta, delta)
            if not np.all(np.isfinite(dsq)):
                fail(f"NONFINITE_BASE_DISTANCE q={idx} start={start}")
            j = int(dsq.argmin())
            candidate = float(dsq[j])
            if candidate < best:
                best, best_id = candidate, start + j
        tolerance = max(1e-3, 1e-6 * max(1.0, best))
        if gt_dist > best + tolerance:
            fail(f"GT_GEOMETRY_TOP1_MISMATCH query={idx} GT_id={int(ids[0])} "
                 f"GT_dist2={gt_dist} exact_id={best_id} exact_dist2={best}")
        print(f"GROUND_TRUTH_TOP1_SPOTCHECK_PASS q={idx} GT_id={int(ids[0])} "
              f"exact_id={best_id} GT_dist2={gt_dist:.4f} best_dist2={best:.4f}", flush=True)
    print("GROUND_TRUTH_GEOMETRY_3_QUERY_SPOTCHECK_PASS_NOT_FULL_10K_PROOF")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.home() / "ann-task-a")
    args = ap.parse_args()
    root = args.root.expanduser().resolve()
    base = root / "data/sift1m.fbin"
    query = root / "data/sift1m_queries.fbin"
    gt = root / "data/sift1m_gt.ibin"
    bigann = root / "data/bigann1m_prefix.fbin"
    matrix_shape(base, "SIFT1M_BASE", (1_000_000, 128), 4)
    matrix_shape(query, "SIFT1M_QUERIES", (10_000, 128), 4)
    matrix_shape(gt, "SIFT1M_GT100_INT64", (10_000, 100), 8)
    sha = digest(base)
    if sha != EXPECTED["base"]:
        fail(f"SIFT1M_BASE_SHA_PIN_MISMATCH: {sha}")
    print(f"SIFT1M_BASE_SHA_PASS {sha}")
    print(f"SIFT1M_QUERY_SHA256 {digest(query)}")
    print(f"SIFT1M_GT_SHA256 {digest(gt)}")
    if bigann.is_file() and bigann.stat().st_size == base.stat().st_size:
        # Byte-for-byte comparison, not an inference from filenames.
        import filecmp
        equal = filecmp.cmp(base, bigann, shallow=False)
        print(f"BIGANN1M_PREFIX_BYTE_IDENTICAL_TO_SIFT1M={equal} "
              "(do not merge historic protocols regardless)")
    else:
        print("BIGANN1M_PREFIX_COMPARISON_NOT_AVAILABLE")
    binary_off_gate(root)
    geometry_spot_check(base, query, gt)
    d0_inventory(root)
    print("R86_SIX_ARM_SIFT1M_DATA_QUERY_GT_STOCK_H17_OFF_PREFLIGHT_PASS")
    print("NOTE_D0_UNPINNED_OR_MISSING_THIS_IS_NOT_A_SIX_ARM_BUILD_PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"R86_SIX_ARM_SIFT1M_PREFLIGHT_HOLD: {exc}", file=sys.stderr)
        sys.exit(2)
