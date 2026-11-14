#!/usr/bin/env python3
"""Prepare a *separate* MS-Turing1M evaluator source from pinned R85 source.

Does not compile, run search, touch existing graph/data, or edit R85 source.
Refuses any source provenance mismatch or unexpected existing destination.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys

HOME = Path.home()
ROOT = HOME / "ann-task-a"
SRC = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall.cc"
BIN = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall"
DEST = ROOT / "experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall.cc"
SRC_EXPECT = "a2b4f27e8dd9f7cd428c5568b1691eb6dc810d2cb7813a4e421ea238c13fb2c0"
BIN_EXPECT = "11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fail(reason: str) -> None:
    raise RuntimeError("R86_MSTURING_EVAL_SOURCE_HOLD " + reason)


def main() -> None:
    for p, want, kind in ((SRC, SRC_EXPECT, "R85_SOURCE"), (BIN, BIN_EXPECT, "R85_BINARY")):
        if not p.is_file():
            fail(f"{kind}_NOT_FOUND {p}")
        have = sha256(p)
        if have != want:
            fail(f"{kind}_SHA_MISMATCH expected={want} actual={have}")
        print(f"{kind}_PIN_PASS sha256={have} path={p}")

    content = SRC.read_text(encoding="utf-8")
    edits = (
        ("base.dimension() != 128", "base.dimension() != 100"),
        ("queries.size() != 10000", "queries.size() != 100000"),
        ("queries.dimension() != 128", "queries.dimension() != 100"),
    )
    for old, new in edits:
        count = content.count(old)
        if count != 1:
            fail(f"UNEXPECTED_MATCH_COUNT count={count} expression={old}")
        content = content.replace(old, new, 1)

    # Keep the original native graph parser and Search/Recall code unchanged.
    required = (
        "base.size() != 1000000",
        "gt.size() != queries.size()",
        "gt.dimension() < 10",
        "graph.size() != base.size()",
        "graph.max_degree() != 64",
        "groundTruth<indexType> gt(argv[4]);",
        "QueryParams qp(10L, beam, 1.35",
        "checkRecall<PR, PR, PR, indexType>",
    )
    for phrase in required:
        if phrase not in content:
            fail(f"PINNED_NATIVE_SEMANTIC_MARKER_MISSING {phrase}")

    outbytes = content.encode("utf-8")
    derived = hashlib.sha256(outbytes).hexdigest()
    if DEST.exists():
        if not DEST.is_file() or DEST.read_bytes() != outbytes:
            fail(f"DEST_ALREADY_EXISTS_BUT_DIFFERS {DEST}")
        print("DESTINATION_ALREADY_IDENTICAL_NO_OVERWRITE")
    else:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        with DEST.open("xb") as f:
            f.write(outbytes)
        print("SEPARATE_SOURCE_CREATED_NO_ORIGINAL_OVERWRITE")

    if sha256(DEST) != derived:
        fail("WRITTEN_SOURCE_SHA_MISMATCH")
    print(f"R86_MSTURING_EVAL_SOURCE_SHA256={derived}")
    print(f"R86_MSTURING_EVAL_SOURCE_PATH={DEST}")
    print("R86_MSTURING_EVAL_ONLY_THREE_INPUT_CHECK_EDITS_PASS")
    print("R86_MSTURING_EVAL_BUILD_PENDING_NOT_YET_APPROVED_FOR_SEARCH")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, UnicodeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
