#!/usr/bin/env python3
"""R83.6: four real single-thread D0/E ANN BUILDs on a pinned SIFT100K prefix.

Uses ONLY pre-built R83.5 matched ELF binaries, and writes a new H83 output dir.
Verifies source/binary provenance, graph file structural invariants, same-arm
reproducibility, cross-arm adjacency identity; reports differences without hiding
failures. No Git changes, H70/H80 mutations, SIFT100K mutations, or Recall claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

COMMIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BINARY_PINS = {
    "D0": "254fe67c42a5568fc78062b51ee65ebcf13d03b6689c2470bc465423f9aad7e6",
    "E":  "d6ba7dcf7ed4fce1f40b646bc90bcd4cafa9fd668630d9b5a8922ad02e32615f",
}
SOURCE_PINS = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "algorithms/utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "algorithms/utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}
STAGE_PINS = {
    "algorithms/PipNN/pipnn.h": "1788d8541db1727c3aaa39e84c9e915c240847338f69b53d8ff5e0c72e57e1a6",
    "algorithms/PipNN/pipnn_utils.h": "17941f13594fdbd2479464ea417878d899e71ce546835ffe0d711bee6713f669",
}
ROWS, DIM, MAX_DEGREE = 8192, 128, 64


def need(cond, code):
    if not cond:
        raise RuntimeError(code)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin_files(base, pins, label):
    for relative, expected in pins.items():
        p = base / relative
        need(p.is_file() and sha(p) == expected, f"{label}_SHA_GATE_FAIL {p}")


def parse_fbin(path):
    need(path.is_file(), f"R83_6_DATASET_MISSING {path}")
    with path.open("rb") as f:
        head = f.read(8)
    need(len(head) == 8, "R83_6_FBIN_HEADER_SHORT")
    n, d = struct.unpack("<II", head)
    need(n >= ROWS and d == DIM, f"R83_6_FBIN_DIMENSION_MISMATCH n={n} d={d}")
    need(path.stat().st_size == 8 + n * d * 4,
         "R83_6_FBIN_SIZE_MISMATCH")
    return n, d


def make_sample(src, dest):
    # The prefix is byte-for-byte identical to SIFT100K vector rows; no
    # resampling, quantization, or transformation of point coordinates.
    with src.open("rb") as f:
        f.seek(8)
        payload = f.read(ROWS * DIM * 4)
    need(len(payload) == ROWS * DIM * 4, "R83_6_SAMPLE_SHORT_READ")
    need(not dest.exists(), "R83_6_SAMPLE_DEST_ALREADY_EXISTS")
    with dest.open("xb") as f:
        f.write(struct.pack("<II", ROWS, DIM))
        f.write(payload)
    need(dest.stat().st_size == 8 + ROWS * DIM * 4,
         "R83_6_SAMPLE_WRITE_SIZE_FAIL")
    return sha(dest)


def read_graph(path, expected_n=ROWS, max_degree=MAX_DEGREE):
    need(path.is_file(), f"R83_6_GRAPH_MISSING {path}")
    raw = path.read_bytes()
    need(len(raw) >= 8, "R83_6_GRAPH_TRUNCATED_HEADER")
    n, degree = struct.unpack_from("<II", raw, 0)
    need(n == expected_n and degree == max_degree,
         f"R83_6_GRAPH_HEADER_UNEXPECTED n={n} maxdeg={degree}")
    need(len(raw) >= 8 + 4 * n, "R83_6_GRAPH_TRUNCATED_DEGREES")
    degrees = struct.unpack_from(f"<{n}I", raw, 8)
    need(all(x <= degree for x in degrees), "R83_6_GRAPH_DEGREE_OVER_CAP")
    arcs = sum(degrees)
    need(len(raw) == 8 + 4 * n + 4 * arcs,
         f"R83_6_GRAPH_FILE_SIZE_MISMATCH bytes={len(raw)} arcs={arcs}")
    entries = struct.unpack_from(f"<{arcs}I", raw, 8 + 4 * n)
    need(all(v < n for v in entries), "R83_6_GRAPH_BAD_VERTEX_ID")
    offsets = []
    cursor = 0
    self_edges = dup_edges = 0
    for u, k in enumerate(degrees):
        adj = entries[cursor:cursor + k]
        self_edges += adj.count(u)
        dup_edges += k - len(set(adj))
        offsets.append((cursor, cursor + k))
        cursor += k
    need(cursor == arcs, "R83_6_GRAPH_INTERNAL_ARC_COUNT_MISMATCH")
    return {"n": n, "max_degree": degree, "arcs": arcs,
            "graph_sha256": hashlib.sha256(raw).hexdigest(),
            "graph_bytes": len(raw), "self_edges": self_edges,
            "repeated_neighbours": dup_edges}, (degrees, entries, offsets)


def compare_graphs(a, b):
    """Exact ordered adjacency comparison with unordered diagnostic fallback."""
    da, ea, oa = a
    db, eb, ob = b
    count_diff = order_or_contents = membership_diff = 0
    examples = []
    for u in range(len(da)):
        row_a = ea[oa[u][0]:oa[u][1]]
        row_b = eb[ob[u][0]:ob[u][1]]
        if da[u] != db[u]:
            count_diff += 1
        if row_a != row_b:
            order_or_contents += 1
            if sorted(row_a) != sorted(row_b):
                membership_diff += 1
            if len(examples) < 5:
                examples.append({"u": u,
                                 "d0": list(row_a[:12]), "e": list(row_b[:12]),
                                 "d0_degree": da[u], "e_degree": db[u]})
    return {"different_degree_rows": count_diff,
            "different_ordered_adjacency_rows": order_or_contents,
            "different_unordered_adjacency_rows": membership_diff,
            "examples": examples}


def flags(dataset, graph):
    return ["-base_path", str(dataset),
            "-graph_outfile", str(graph),
            "-num_clusters", "2",
            "-cluster_size", "1024",
            "-fanout", "30",
            "-fanout_scheme", "10,3,1",
            "-top_level_leaders", "100",
            "-mst_deg", "2",
            "-alpha", "1.2",
            "-prune", "1",
            "-prune_all", "1",
            "-prune_degree", str(MAX_DEGREE),
            "-table_size", "160",
            "-hash_bits", "12",
            "-k", "0"]


def provenance(root):
    base = root / "experiments/H70/pipnn-clean-443a328"
    stage = root / "experiments/H83/r83_3_source_stage"
    r4 = root / "experiments/H83/r83_4b_syntax_gate/r83_4_summary.json"
    r5 = root / "experiments/H83/r83_5_matched_binary"
    r5_summary = r5 / "r83_5_summary.json"
    need(base.is_dir(), "R83_6_H70_BASE_MISSING")
    head = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip()
    need(head == COMMIT, "R83_6_SOURCE_COMMIT_MISMATCH")
    pin_files(base, SOURCE_PINS, "R83_6_H70")
    pin_files(stage, STAGE_PINS, "R83_6_H83_STAGE")
    need(r4.is_file() and r5_summary.is_file(), "R83_6_GATE_SUMMARIES_MISSING")
    g4, g5 = json.loads(r4.read_text()), json.loads(r5_summary.read_text())
    need(g4.get("source_commit") == COMMIT and g5.get("source_commit") == COMMIT,
         "R83_6_UPSTREAM_SUMMARY_COMMIT_MISMATCH")
    need(all(g4.get("compiled", {}).get(v, {}).get("exit_code") == 0 for v in BINARY_PINS),
         "R83_6_R83_4B_SYNTAX_NOT_PASS")
    binaries = {}
    for arm, wanted in BINARY_PINS.items():
        g = g5.get("variants", {}).get(arm, {})
        need(g.get("compile_exit") == 0 and g.get("link_exit") == 0,
             f"R83_6_{arm}_COMPILE_LINK_SUMMARY_NOT_PASS")
        need(g.get("binary_sha256") == wanted,
             f"R83_6_{arm}_SUMMARY_SHA_NOT_PINNED")
        path = r5 / arm / TARGET
        need(path.is_file() and sha(path) == wanted and path.read_bytes()[:4] == b"\x7fELF",
             f"R83_6_{arm}_BINARY_SHA_OR_ELF_MISMATCH")
        need(Path(g.get("binary_path", "")).resolve() == path.resolve(),
             f"R83_6_{arm}_REPORT_PATH_MISMATCH")
        compile_cmd = (r5 / arm / "compile_command.txt")
        need(compile_cmd.is_file(), f"R83_6_{arm}_COMPILER_COMMAND_MISSING")
        cmd = compile_cmd.read_text()
        for define in ("-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1"):
            need(define in cmd, f"R83_6_{arm}_FLAG_MISSING {define}")
        need(("-DR83_COMPACT_FANOUT=1" in cmd) == (arm == "E"),
             f"R83_6_{arm}_COMPACT_FLAG_GATE_FAIL")
        binaries[arm] = path
    return binaries


def execute(root, sample, output, binaries):
    need(Path("/usr/bin/time").is_file(), "R83_6_GNU_TIME_NOT_FOUND")
    env = dict(os.environ)
    env.update({"PARLAY_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                "BLIS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"})
    results, graphs = {}, {}
    counts = {"D0": 0, "E": 0}
    # Interleave arms to mitigate order effects. Same-arm repeats are a
    # necessary control before interpreting strict cross-arm byte parity.
    for i, arm in enumerate(("D0", "E", "E", "D0"), 1):
        counts[arm] += 1
        key = f"{arm}_r{counts[arm]}"
        dest = output / key
        dest.mkdir(exist_ok=False)
        graph_path = dest / "graph.bin"
        cmd = [str(binaries[arm]), *flags(sample, graph_path)]
        (dest / "command.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2) + "\n")
        print(f"R83_6_BUILD_START arm={arm} run={key} threads=1", flush=True)
        start = time.perf_counter()
        with (dest / "build.log").open("w") as f:
            proc = subprocess.run(["/usr/bin/time", "-f", "R83_6_WALL_SECONDS=%e\nR83_6_PEAK_RSS_KiB=%M",
                                   "-o", str(dest / "resource.log"), *cmd],
                                  cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=240, check=False)
        elapsed = time.perf_counter() - start
        info = {"arm": arm, "name": key, "exit_code": proc.returncode,
                "python_elapsed_s": round(elapsed, 5),
                "binary_sha256": BINARY_PINS[arm]}
        (dest / "result.json").write_text(json.dumps(info, indent=2) + "\n")
        need(proc.returncode == 0,
             f"R83_6_{key}_BUILD_FAILED_EXIT_{proc.returncode} log={dest/'build.log'}")
        logtext = (dest / "build.log").read_text(errors="replace")
        need("R70_RESERVOIR_VARIANT=TIER_B64_C160" in logtext and
             "R71_SELECTION_VARIANT=H17_PACKED_TOP2" in logtext,
             f"R83_6_{key}_VARIANT_PROVENANCE_LOG_MISSING")
        graph_info, graph_data = read_graph(graph_path)
        rs = (dest / "resource.log").read_text()
        metrics = dict(re.findall(r"(R83_6_(?:WALL_SECONDS|PEAK_RSS_KiB))=([0-9.]+)", rs))
        need(len(metrics) == 2, f"R83_6_{key}_RESOURCE_METRICS_MISSING")
        info.update(graph_info)
        info["gnu_wall_s"] = float(metrics["R83_6_WALL_SECONDS"])
        info["peakRSS_KiB"] = int(float(metrics["R83_6_PEAK_RSS_KiB"]))
        (dest / "result.json").write_text(json.dumps(info, indent=2) + "\n")
        results[key] = info
        graphs[key] = graph_data
        print(f"R83_6_BUILD_RESULT arm={arm} run={key} wall_s={info['gnu_wall_s']} "
              f"peakRSS_KiB={info['peakRSS_KiB']} arcs={graph_info['arcs']} "
              f"graph_sha256={graph_info['graph_sha256']}", flush=True)
    return results, graphs


def summarize(results, graphs):
    pairs = {"D0_REPEAT": ("D0_r1", "D0_r2"),
             "E_REPEAT": ("E_r1", "E_r2"),
             "D0_E_R1": ("D0_r1", "E_r1"),
             "D0_E_R2": ("D0_r2", "E_r2")}
    comparisons = {}
    for name, (x, y) in pairs.items():
        v = compare_graphs(graphs[x], graphs[y])
        v["byte_identical"] = results[x]["graph_sha256"] == results[y]["graph_sha256"]
        comparisons[name] = v
        print("R83_6_GRAPH_COMPARE", name, json.dumps(v, sort_keys=True), flush=True)
    repeat_ok = comparisons["D0_REPEAT"]["byte_identical"] and comparisons["E_REPEAT"]["byte_identical"]
    parity_ok = comparisons["D0_E_R1"]["byte_identical"] and comparisons["D0_E_R2"]["byte_identical"]
    if repeat_ok and parity_ok:
        result = "R83_6_1T_EXACT_GRAPH_PARITY_PASS"
    elif not repeat_ok:
        result = "R83_6_1T_REPEATS_NOT_BYTE_STABLE_NO_STRICT_PARITY_CLAIM"
    else:
        result = "R83_6_1T_CROSS_ARM_GRAPH_DRIFT_INVESTIGATE"
    return comparisons, result


def test_self():
    # Exercising the graph validator with known binary fixtures, no PiPNN.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        p = Path(tmp) / "tiny_graph.bin"
        # Graph with 3 nodes, maxDeg 2, degrees [1, 2, 0], edges [1, 0, 2].
        raw = struct.pack("<2I", 3, 2) + struct.pack("<3I", 1, 2, 0) + struct.pack("<3I", 1, 0, 2)
        p.write_bytes(raw)
        meta, data = read_graph(p, 3, 2)
        assert meta["arcs"] == 3 and meta["n"] == 3
        assert compare_graphs(data, data)["different_ordered_adjacency_rows"] == 0
        bad = bytearray(raw)
        struct.pack_into("<I", bad, len(bad) - 4, 4)
        p.write_bytes(bad)
        try:
            read_graph(p, 3, 2)
        except RuntimeError as exc:
            assert "BAD_VERTEX_ID" in str(exc)
        else:
            raise AssertionError("invalid vertex id accepted")
    a = flags(Path("/tmp/data"), Path("/tmp/graph"))
    assert "-table_size" in a and a[a.index("-table_size") + 1] == "160"
    print("R83_6_RUNNER_SELFTEST_PASS", flush=True)


def run(root):
    test_self()
    binaries = provenance(root)
    source = root / "data/sift100k.fbin"
    n, dim = parse_fbin(source)
    print(f"R83_6_PINNED_SOURCE_AND_BINARY_GATE_PASS n_base={n} dim={dim}", flush=True)
    print(f"R83_6_INPUT_SHA256 {sha(source)}", flush=True)
    out = root / "experiments/H83/r83_6_graph_parity"
    need(not out.exists(), "R83_6_OUTPUT_EXISTS_FAIL_CLOSED")
    out.mkdir(parents=True, exist_ok=False)
    sample = out / "sift8k_prefix.fbin"
    sample_sha = make_sample(source, sample)
    print(f"R83_6_DATASET_PREFIX_CREATED rows={ROWS} dim={DIM} sha256={sample_sha}", flush=True)
    summary = {"experiment": "R83.6", "source_commit": COMMIT,
               "base": str(source), "base_sha256": sha(source),
               "sample": str(sample), "sample_sha256": sample_sha,
               "n": ROWS, "dim": DIM, "threads": 1,
               "binary_sha256": BINARY_PINS,
               "status": "BUILDS_STARTED", "runs": {}}
    report = out / "r83_6_summary.json"
    report.write_text(json.dumps(summary, indent=2) + "\n")
    try:
        results, graphs = execute(root, sample, out, binaries)
        summary["runs"] = results
        comparisons, status = summarize(results, graphs)
        summary["comparisons"] = comparisons
        summary["status"] = status
        report.write_text(json.dumps(summary, indent=2) + "\n")
        print(status, flush=True)
        print("R83_6_NOT_SIFT100K_BENCHMARK_NOT_RECALL_NOT_FULL_BUILD_GAIN", flush=True)
        print("R83_6_REPORT", report, flush=True)
        if status != "R83_6_1T_EXACT_GRAPH_PARITY_PASS":
            raise RuntimeError(status)
    except Exception as exc:
        if summary.get("status") == "BUILDS_STARTED":
            summary["status"] = "STOP_INCOMPLETE_REVIEW_ARTIFACTS"
            summary["error"] = str(exc)
            report.write_text(json.dumps(summary, indent=2) + "\n")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=False, default=str(Path.home() / "ann-task-a"))
    parser.add_argument("--selftest", action="store_true")
    a = parser.parse_args()
    try:
        if a.selftest:
            test_self()
        else:
            run(Path(a.root).expanduser().resolve())
    except Exception as e:
        print("R83_6_STOP", e, file=sys.stderr, flush=True)
        sys.exit(1)
