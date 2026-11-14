#!/usr/bin/env python3
"""R83.9: new-PC pinned D0 vs Compact Fanout E, paired PiPNN SIFT100K 4-P-core builds.

Research-only, isolated /experiments/H83 output. Verifies real ELF binaries from
R83.5 and R83.6 exact single-thread graph gate. Runs 6 native BUILDs, validates
saved graphs, records total wall/peak RSS and per-stage timers; does NOT measure
search quality, prove algorithmic novelty, push code, or touch H70/H80/source data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

COMMIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE_SHA = "e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12"
BINARY_SHA = {
    "D0": "254fe67c42a5568fc78062b51ee65ebcf13d03b6689c2470bc465423f9aad7e6",
    "E":  "d6ba7dcf7ed4fce1f40b646bc90bcd4cafa9fd668630d9b5a8922ad02e32615f",
}
SOURCE_SHA = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "algorithms/utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "algorithms/utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}
STAGE_SHA = {
    "algorithms/PipNN/pipnn.h": "1788d8541db1727c3aaa39e84c9e915c240847338f69b53d8ff5e0c72e57e1a6",
    "algorithms/PipNN/pipnn_utils.h": "17941f13594fdbd2479464ea417878d899e71ce546835ffe0d711bee6713f669",
    "algorithms/PipNN/CMakeLists.txt": "329f237404310ce4036aba103bf01a520ff72a396b9a42f070a0037926e1d35e",
}
N, DIM, GRAPH_DEGREE, THREADS, REPS = 100000, 128, 64, 4, 3
PLAN = (("D0", 1), ("E", 1), ("E", 2), ("D0", 2), ("D0", 3), ("E", 3))
PHASES = ("buckets time", "build leaf time", "Final prune time")
CPU_SET = (0, 2, 4, 6)  # One hardware thread per P-core on the user's i5-14600KF.
PRIOR_QUALITY_VERDICT = 'R83_8_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF'



def gate(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def pins(base, mapping, label):
    for relative, expected in mapping.items():
        file = base / relative
        gate(file.is_file() and digest(file) == expected,
             f"R83_9_{label}_SHA_GATE_FAIL {file}")


def inspect_dataset(path):
    gate(path.is_file(), f"R83_9_BASE_MISSING {path}")
    with path.open("rb") as f:
        raw = f.read(8)
    gate(len(raw) == 8, "R83_9_FBIN_INVALID_HEADER")
    n, d = struct.unpack("<II", raw)
    gate(n == N and d == DIM and path.stat().st_size == 8 + n * d * 4,
         f"R83_9_FBIN_SHAPE_OR_SIZE_INVALID n={n} d={d} size={path.stat().st_size}")
    gate(digest(path) == BASE_SHA, "R83_9_BASE_SHA_MISMATCH")


def inspect_graph(path):
    gate(path.is_file(), f"R83_9_GRAPH_MISSING {path}")
    data = path.read_bytes()
    gate(len(data) >= 8 + 4 * N, "R83_9_GRAPH_TRUNCATED")
    n, degree = struct.unpack_from("<II", data, 0)
    gate(n == N and degree == GRAPH_DEGREE,
         f"R83_9_GRAPH_HEADER_INVALID n={n} degree={degree}")
    degrees = struct.unpack_from(f"<{n}I", data, 8)
    gate(all(k <= degree for k in degrees), "R83_9_GRAPH_DEGREE_EXCEEDS_CAP")
    arcs = sum(degrees)
    gate(len(data) == 8 + 4 * n + 4 * arcs, "R83_9_GRAPH_LENGTH_INVALID")
    edges = struct.unpack_from(f"<{arcs}I", data, 8 + 4 * n)
    gate(all(v < n for v in edges), "R83_9_GRAPH_OUT_OF_RANGE_NEIGHBOR")
    cursor = 0
    self_arcs = dup_arcs = 0
    for u, k in enumerate(degrees):
        row = edges[cursor:cursor+k]
        self_arcs += row.count(u)
        dup_arcs += k - len(set(row))
        cursor += k
    gate(cursor == arcs, "R83_9_GRAPH_ARC_SUM_MISMATCH")
    return {"vertices": n, "maximum_degree": degree, "arcs": arcs,
            "graph_bytes": len(data), "self_arcs": self_arcs,
            "duplicate_neighbors": dup_arcs, "sha256": hashlib.sha256(data).hexdigest()}


def extract_phases(text):
    answer = {}
    for label in PHASES:
        vals = [float(v) for v in re.findall(
            rf"{re.escape(label)}\s*:\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)",
            text, flags=re.I)]
        answer[label] = {"count": len(vals), "individual_s": vals,
                         "sum_s": round(sum(vals), 6)}
    return answer


def command(binary, data, graph):
    return [str(binary), "-base_path", str(data), "-graph_outfile", str(graph),
            "-num_clusters", "2", "-cluster_size", "1024", "-fanout", "30",
            "-fanout_scheme", "10,3,1", "-top_level_leaders", "100",
            "-mst_deg", "2", "-alpha", "1.2", "-prune", "1",
            "-prune_all", "1", "-prune_degree", "64", "-table_size", "160",
            "-hash_bits", "12", "-k", "0"]


def verify(root):
    h70 = root / "experiments/H70/pipnn-clean-443a328"
    stage = root / "experiments/H83/r83_3_source_stage"
    r4 = root / "experiments/H83/r83_4b_syntax_gate/r83_4_summary.json"
    r5 = root / "experiments/H83/r83_5_matched_binary"
    r6 = root / "experiments/H83/r83_6_graph_parity/r83_6_summary.json"
    gate(h70.is_dir(), "R83_9_H70_SOURCE_NOT_FOUND")
    head = subprocess.check_output(["git", "-C", str(h70), "rev-parse", "HEAD"], text=True).strip()
    gate(head == COMMIT, "R83_9_GIT_HEAD_PIN_FAIL")
    pins(h70, SOURCE_SHA, "H70")
    pins(stage, STAGE_SHA, "H83_STAGE")
    gate(r4.is_file() and (r5 / "r83_5_summary.json").is_file() and r6.is_file(),
         "R83_9_PRIOR_GATE_REPORT_MISSING")
    s4 = json.loads(r4.read_text())
    s5 = json.loads((r5 / "r83_5_summary.json").read_text())
    s6 = json.loads(r6.read_text())
    gate(s4.get("source_commit") == COMMIT and s5.get("source_commit") == COMMIT and
         s6.get("source_commit") == COMMIT,
         "R83_9_PRIOR_REPORT_COMMIT_MISMATCH")
    gate(all(s4.get("compiled", {}).get(arm, {}).get("exit_code") == 0 for arm in BINARY_SHA),
         "R83_9_R83_4B_SYNTAX_NOT_PASS")
    gate(s6.get("status") == "R83_6_1T_EXACT_GRAPH_PARITY_PASS" and
         s6.get("threads") == 1 and s6.get("n") == 8192,
         "R83_9_R83_6_PARITY_GATE_NOT_PASS")
    r6runs = s6.get("runs", {})
    gate(all(r6runs.get(k, {}).get("graph_sha256") ==
             "9546734326e6045d6fe777d6d1725a76161bad65ba373f2b78b4efeda9a4b1ae"
             for k in ("D0_r1", "D0_r2", "E_r1", "E_r2")),
         "R83_9_R83_6_GRAPH_SHA_SET_MISMATCH")
    binaries = {}
    for arm, expected in BINARY_SHA.items():
        meta = s5.get("variants", {}).get(arm, {})
        binpath = r5 / arm / TARGET
        gate(meta.get("compile_exit") == 0 and meta.get("link_exit") == 0 and
             meta.get("binary_sha256") == expected,
             f"R83_9_{arm}_R83_5_REPORT_NOT_PASS")
        gate(binpath.is_file() and binpath.read_bytes()[:4] == b"\x7fELF" and
             digest(binpath) == expected and os.access(binpath, os.X_OK),
             f"R83_9_{arm}_ELF_BINARY_OR_SHA_FAIL")
        gate(Path(meta.get("binary_path", "")).resolve() == binpath.resolve(),
             f"R83_9_{arm}_BINARY_REPORTED_PATH_MISMATCH")
        cmd_file = r5 / arm / "compile_command.txt"
        gate(cmd_file.is_file(), f"R83_9_{arm}_COMPILER_COMMAND_NOT_FOUND")
        cmd = cmd_file.read_text()
        gate("-DR70_TWO_TIER=1" in cmd and "-DR71_H17_TOP2=1" in cmd,
             f"R83_9_{arm}_D0_FLAGS_MISSING")
        gate(("-DR83_COMPACT_FANOUT=1" in cmd) == (arm == "E"),
             f"R83_9_{arm}_COMPACT_FLAG_MISMATCH")
        binaries[arm] = binpath
    base = root / "data/sift100k.fbin"
    inspect_dataset(base)
    gate(Path("/usr/bin/time").is_file(), "R83_9_GNU_TIME_MISSING")
    print("R83_9_SOURCE_BINARY_1T_PARITY_DATA_GATES_PASS", flush=True)
    print(f"R83_9_BASE_SHA256 {BASE_SHA} rows={N} dim={DIM}", flush=True)
    return base, binaries


def run_once(root, out, base, binaries, env, arm, rep):
    tag = f"r{rep}_{arm}"
    run = out / tag
    run.mkdir(exist_ok=False)
    graph = run / "graph.bin"
    args = command(binaries[arm], base, graph)
    (run / "command.json").write_text(json.dumps(args, indent=2) + "\n")
    print(f"R83_9_BUILD_START run={tag} variant={arm} threads={THREADS}", flush=True)
    with (run / "build.log").open("w") as f:
        try:
            r = subprocess.run(
                ["/usr/bin/time", "-f", "R83_9_GNU_WALL_S=%e\nR83_9_PEAK_RSS_KiB=%M",
                 "-o", str(run / "resource.log"), *args],
                cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT,
                timeout=240, check=False)
            exit_code = r.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
    (run / "exit_code.txt").write_text(str(exit_code) + "\n")
    gate(exit_code == 0, f"R83_9_{tag}_ANN_BUILD_FAILED_EXIT_{exit_code} log={run/'build.log'}")
    log = (run / "build.log").read_text(errors="replace")
    gate("R70_RESERVOIR_VARIANT=TIER_B64_C160" in log and
         "R71_SELECTION_VARIANT=H17_PACKED_TOP2" in log,
         f"R83_9_{tag}_BUILD_PROVENANCE_MISSING")
    resource = (run / "resource.log").read_text(errors="replace")
    vals = dict(re.findall(r"(R83_9_(?:GNU_WALL_S|PEAK_RSS_KiB))=([0-9.]+)", resource))
    gate(len(vals) == 2, f"R83_9_{tag}_GNU_TIME_METRICS_MISSING")
    gr = inspect_graph(graph)
    phases = extract_phases(log)
    result = {"variant": arm, "rep": rep, "tag": tag, "threads": THREADS,
              "binary_sha256": BINARY_SHA[arm],
              "wall_s": float(vals["R83_9_GNU_WALL_S"]),
              "peakRSS_KiB": int(vals["R83_9_PEAK_RSS_KiB"]),
              "graph": gr, "phases": phases, "exit_code": exit_code}
    (run / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"R83_9_BUILD_RESULT run={tag} variant={arm} wall_s={result['wall_s']:.4f} "
          f"peakRSS_KiB={result['peakRSS_KiB']} arcs={gr['arcs']} sha256={gr['sha256']} "
          f"bucket_s={phases['buckets time']['sum_s']:.4f} "
          f"leaf_s={phases['build leaf time']['sum_s']:.4f}", flush=True)
    return result


def assess(runs):
    by = {arm: sorted([r for r in runs.values() if r["variant"] == arm],
                      key=lambda d: d["rep"]) for arm in BINARY_SHA}
    gate(all(len(by[arm]) == REPS for arm in BINARY_SHA), "R83_9_REPETITION_COUNTS_WRONG")
    medians = {}
    for arm, rr in by.items():
        medians[arm] = {field: statistics.median([r[field] for r in rr])
                        for field in ("wall_s", "peakRSS_KiB")}
        for phase in PHASES:
            medians[arm][phase] = statistics.median([r["phases"][phase]["sum_s"] for r in rr])
    ratios = {field: medians["E"][field] / medians["D0"][field]
              for field in ("wall_s", "peakRSS_KiB")}
    paired = []
    for rep in range(1, REPS + 1):
        d = by["D0"][rep-1]
        e = by["E"][rep-1]
        paired.append({"rep": rep,
                       "wall_E_minus_D0_s": round(e["wall_s"]-d["wall_s"], 5),
                       "rss_E_minus_D0_KiB": e["peakRSS_KiB"]-d["peakRSS_KiB"],
                       "wall_E_over_D0": round(e["wall_s"]/d["wall_s"], 6),
                       "rss_E_over_D0": round(e["peakRSS_KiB"]/d["peakRSS_KiB"], 6),
                       "graph_sha_equal": e["graph"]["sha256"] == d["graph"]["sha256"]})
    wins = {"wall": sum(p["wall_E_minus_D0_s"] < 0 for p in paired),
            "rss": sum(p["rss_E_minus_D0_KiB"] < 0 for p in paired)}
    # Pre-registered screening thresholds, NOT a statistical significance test.
    two_metrics = (ratios["wall_s"] <= 0.97 and ratios["peakRSS_KiB"] <= 0.98)
    stable_pair_direction = wins["wall"] >= 2 and wins["rss"] >= 2
    if two_metrics and stable_pair_direction:
        verdict = "R83_9_TWO_METRIC_PILOT_SCREEN_GO_RECALL_PENDING"
    elif two_metrics:
        verdict = "R83_9_MEDIAN_TWO_METRIC_GAIN_PAIRING_MIXED_HOLD"
    else:
        verdict = "R83_9_TWO_METRIC_SCREEN_NO_GO_OR_HOLD"
    return {"medians": medians, "E_over_D0_medians": ratios,
            "paired": paired, "paired_win_counts": wins, "verdict": verdict,
            "thresholds": {"wall_ratio_max": .97, "rss_ratio_max": .98,
                           "minimum_paired_wins_each": 2},
            "not_claimed": "No heldout Recall, no QPS, no SIFT1M, no algorithmic novelty, no statistical significance; 4-thread graph SHA may differ under concurrency."}


def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p = Path(td) / "graph.bin"
        p.write_bytes(struct.pack("<2I", 3, 2) + struct.pack("<3I", 1, 2, 0) +
                      struct.pack("<3I", 1, 0, 2))
        inf = inspect_graph_for_selftest(p, 3, 2)
        assert inf["arcs"] == 3
        p.write_bytes(p.read_bytes()[:-4])
        try:
            inspect_graph_for_selftest(p, 3, 2)
        except RuntimeError:
            pass
        else:
            raise AssertionError("truncated graph accepted")
    sample = 'Parlay time: buckets time: 1.20\nParlay time: build leaf time: 2.30\nParlay time: buckets time: 3.40\nFinal prune time: 0.50'
    phases = extract_phases(sample)
    assert phases['buckets time']['count'] == 2 and abs(phases['buckets time']['sum_s'] - 4.6) < 1e-9
    assert phases['build leaf time']['count'] == 1
    test = command(Path('/tmp/bin'), Path('/tmp/data.fbin'), Path('/tmp/graph.bin'))
    assert test[test.index('-num_clusters')+1] == '2'
    assert test[test.index('-table_size')+1] == '160'
    assert tuple(PLAN) == (("D0", 1), ("E", 1), ("E", 2), ("D0", 2), ("D0", 3), ("E", 3))
    print("R83_9_RUNNER_SELFTEST_PASS", flush=True)


def inspect_graph_for_selftest(path, n, deg):
    """Tiny graph validator uses the same byte-layout checks, custom size."""
    raw = path.read_bytes()
    gate(len(raw) >= 8 + 4*n, "R83_9_SELFTEST_TRUNCATED")
    gotn, gotdeg = struct.unpack_from('<2I', raw, 0)
    gate((gotn, gotdeg) == (n, deg), 'R83_9_SELFTEST_BAD_HEADER')
    ds = struct.unpack_from(f'<{n}I', raw, 8)
    gate(all(k <= deg for k in ds), 'R83_9_SELFTEST_BAD_DEGREE')
    arcs = sum(ds)
    gate(len(raw) == 8 + 4*n + 4*arcs, 'R83_9_SELFTEST_BAD_SIZE')
    edges = struct.unpack_from(f'<{arcs}I', raw, 8 + 4*n)
    gate(all(v < n for v in edges), 'R83_9_SELFTEST_BAD_NEIGHBOR')
    return {'arcs': arcs}


def check_cpu_affinity():
    """Fail-closed: restrict BUILD to four distinct physical P-cores."""
    gate(hasattr(os, "sched_getaffinity"), "R83_9_AFFINITY_UNAVAILABLE")
    allowed = tuple(sorted(os.sched_getaffinity(0)))
    gate(allowed == CPU_SET,
         f"R83_9_WRONG_AFFINITY got={allowed} expected={CPU_SET} "
         "run with taskset -c 0,2,4,6")
    topology = {}
    physical = set()
    for cpu in CPU_SET:
        base = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        socket_p = base / "physical_package_id"
        core_p = base / "core_id"
        gate(socket_p.is_file() and core_p.is_file(),
             f"R83_9_CPU_TOPOLOGY_NOT_FOUND cpu={cpu}")
        key = (int(socket_p.read_text().strip()), int(core_p.read_text().strip()))
        gate(key not in physical, f"R83_9_SMT_SIBLING_SELECTED cpu={cpu} physical={key}")
        physical.add(key)
        topology[str(cpu)] = {"socket": key[0], "core_id": key[1]}
    gate(len({x[0] for x in physical}) == 1,
         "R83_9_PCORE_AFFINITY_SPANS_NUMA_SOCKETS")
    print('R83_9_PCORE4_AFFINITY_GATE_PASS cpus=0,2,4,6 physical_cores=4', flush=True)
    return {"logical_cpus": list(CPU_SET), "topology": topology}


def check_prior_quality(root):
    old = root / 'experiments/H83/r83_7_sift100k_paired/r83_7_summary.json'
    quality = root / 'experiments/H83/r83_7_sift100k_paired/quality/r83_8_quality_summary.json'
    gate(old.is_file() and quality.is_file(), 'R83_9_R83_7_OR_R83_8_REPORT_MISSING')
    past = json.loads(old.read_text())
    q = json.loads(quality.read_text())
    gate(past.get('status') == 'R83_7_TWO_METRIC_PILOT_SCREEN_GO_RECALL_PENDING',
         'R83_9_R83_7_SCREEN_NOT_PASS')
    gate(q.get('status') == PRIOR_QUALITY_VERDICT and
         q.get('assessment', {}).get('numeric_recall_parsed') is True and
         len(q.get('rows', {})) == 6,
         'R83_9_R83_8_QUALITY_GATE_NOT_PASS')
    gate(q.get('base_sha256') == BASE_SHA,
         'R83_9_QUALITY_BASE_SHA_MISMATCH')
    for tag in [f'r{rep}_{arm}' for arm,rep in PLAN]:
        gate(tag in past.get('runs', {}) and tag in q.get('rows', {}),
             f'R83_9_PRIOR_GRAPH_OR_QUALITY_RECORD_MISSING {tag}')
    print('R83_9_R83_7_TWO_METRICS_AND_R83_8_RECALL_GATES_PASS', flush=True)
    return {'prior_build_report_sha256': digest(old),
            'prior_quality_report_sha256': digest(quality),
            'prior_evaluator_sha256': q.get('evaluator_sha256')}


def hardware_fingerprint():
    """Capture repeatability metadata, without changing governor or system settings."""
    model = None
    microcode = None
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.is_file():
        for ln in cpuinfo.read_text(errors='replace').splitlines():
            if ln.startswith('model name') and model is None:
                model = ln.partition(':')[2].strip()
            if ln.startswith('microcode') and microcode is None:
                microcode = ln.partition(':')[2].strip()
    governor = {}
    max_freq_khz = {}
    for cpu in CPU_SET:
        base = Path(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq')
        for filename, target in [('scaling_governor', governor),
                                 ('cpuinfo_max_freq', max_freq_khz)]:
            f = base / filename
            target[str(cpu)] = f.read_text().strip() if f.is_file() else None
    return {'cpu_model': model, 'microcode': microcode,
            'kernel': platform.release(), 'machine': platform.machine(),
            'cpu_governor': governor, 'cpu_max_freq_khz': max_freq_khz,
            'compiler_arch_build_note': 'Existing R83.5 ELF binary pair compiled with -march=native on earlier host; new-PC native rebuild is a separate later gate.'}


def preflight(root):
    selftest()
    base, binaries = verify(root)
    topology = check_cpu_affinity()
    prior = check_prior_quality(root)
    out = root / 'experiments/H83/r83_9_newpc_pcore4_sift100k'
    gate(not out.exists(), 'R83_9_OUTPUT_EXISTS_FAIL_CLOSED')
    print('R83_9_PREFLIGHT_PASS_NO_BUILD', flush=True)
    return base, binaries, topology, prior, out


def run(root, dry_run=False):
    base, binaries, topology, prior, out = preflight(root)
    if dry_run:
        return
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.update({'PARLAY_NUM_THREADS': str(THREADS), 'OMP_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                'BLIS_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1'})
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
    manifest = {'experiment': 'R83.9', 'source_commit': COMMIT,
                'base': str(base), 'base_sha256': BASE_SHA,
                'binary_sha256': BINARY_SHA, 'threads': THREADS,
                'schedule': [f'r{rep}_{arm}' for arm, rep in PLAN],
                'cpu_allowed': affinity, 'physical_core_affinity': topology,
                'prior_quality_provenance': prior, 'hardware': hardware_fingerprint(),
                'status': 'STARTED', 'runs': {},
                'created_at_utc': datetime.now(timezone.utc).isoformat()}
    report = out / 'r83_9_summary.json'
    report.write_text(json.dumps(manifest, indent=2) + '\n')
    print('R83_9_MATCHED_4THREAD_BUILD_START', flush=True)
    try:
        for arm, rep in PLAN:
            result = run_once(root, out, base, binaries, env, arm, rep)
            manifest['runs'][result['tag']] = result
            report.write_text(json.dumps(manifest, indent=2) + '\n')
        assessment = assess(manifest['runs'])
        manifest.update(assessment)
        manifest['status'] = assessment['verdict']
        report.write_text(json.dumps(manifest, indent=2) + '\n')
        print('R83_9_MEDIANS ' + json.dumps(assessment['medians'], sort_keys=True), flush=True)
        print('R83_9_RATIOS ' + json.dumps(assessment['E_over_D0_medians'], sort_keys=True), flush=True)
        print('R83_9_PAIRED ' + json.dumps(assessment['paired'], sort_keys=True), flush=True)
        print(assessment['verdict'], flush=True)
        print('R83_9_GRAPH_STRUCTURAL_VALIDATION_PASS_6_OF_6', flush=True)
        print('R83_9_RECALL_PRIOR_GRAPH_ONLY_NOT_CURRENT_GRAPH_SEARCH_NOT_SIFT1M_NOT_STATISTICAL_PROOF_NO_PUSH', flush=True)
        print('R83_9_REPORT', report, flush=True)
    except Exception as e:
        manifest['status'] = 'STOP_INCOMPLETE'
        manifest['error'] = str(e)
        report.write_text(json.dumps(manifest, indent=2) + '\n')
        raise


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(Path.home() / 'ann-task-a'))
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--dry-run', action='store_true', help='Validate all gates without BUILD')
    args = ap.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            run(Path(args.root).expanduser().resolve(), dry_run=args.dry_run)
    except Exception as e:
        print('R83_9_STOP', e, file=sys.stderr, flush=True)
        sys.exit(1)
