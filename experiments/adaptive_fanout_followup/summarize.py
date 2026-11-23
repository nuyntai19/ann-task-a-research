#!/usr/bin/env python3
"""Aggregate the common SIFT1M benchmark and retain the individual measurements."""
import argparse
import csv
import json
import re
from statistics import median

from run import run_name, save
from sift1m import ARMS, ROOT, SEEDS

TARGETS = (.95, .98, .99, .995, .997, .999)
LABELS = dict(zip(ARMS, ("Fixed", "V1 .15/min1", "V2a", "V2b", "V3")))


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def medians(rows, fields):
    return {field: median(row[field] for row in rows) for field in fields}


def summarize(name):
    directory = ROOT / f"{name}_comparison"
    builds = []
    search = []
    manifests = []
    for arm in ARMS:
        for seed in SEEDS:
            run_id = f"{name}_{arm}_s{seed}"
            summary = json.loads((ROOT / run_id / "summary.json").read_text())
            if summary["status"] != "PASS" or not 1 <= summary["reachable_from_start0"] <= 1000000:
                raise ValueError(f"Incomplete {run_id}")
            manifests.append(summary["data_manifest"]["sha256"])
            t = summary["telemetry"]
            d = next(row for row in t["by_depth"] if row["depth"] == 1)
            build_log = (ROOT / run_id / "build.log").read_text()
            phase_names = {
                "bucket_s": "buckets time",
                "leaf_s": "build leaf time",
                "prune_s": "Final prune time",
            }
            phases = {key: float(re.search(rf"Parlay time: {label}: ([0-9.]+)", build_log)[1])
                      for key, label in phase_names.items()}
            builds.append(dict(arm=arm, seed=seed, run_id=run_id, wall_s=summary["wall_s"],
                               peak_rss_mib=summary["peak_rss_kib"]/1024,
                               reachable=summary["reachable_from_start0"],
                               proposals=t["directed_proposals"], final_edges=summary["graph"]["edges"],
                               leaf_squared_work=t["leaf_squared_work"],
                               leader_distance_pairs=t["leader_distance_pairs"],
                               depth1_nominal=d["nominal_assignments"], depth1_actual=d["actual_assignments"],
                               depth1_fanout1=d["fanout_histogram"].get("1", 0),
                               depth1_fanout2=d["fanout_histogram"].get("2", 0),
                               depth1_fanout3=d["fanout_histogram"].get("3", 0),
                               swaps=t.get("diversity_swaps", 0), density_pairs=t.get("density_distance_pairs", 0),
                               graph_sha256=summary["graph"]["sha256"], binary_sha256=summary["binary_sha256"],
                               evaluator_sha256=summary["evaluator_sha256"], **phases))
            for r in summary["search"]:
                search.append(dict(arm=arm, seed=seed, run_id=run_id, beam=r["beam"],
                                   recall=r["recall_at_10"], qps=r["qps"], avg_cmps=r["avg_cmps"],
                                   avg_visited=r["avg_visited"],
                                   **{f"latency_{k}_us": v for k,v in r["latency_us"].items()}))
    for key in ("binary_sha256", "evaluator_sha256"):
        if len({r[key] for r in builds}) != 1:
            raise ValueError(f"Inconsistent {key}")
    if any(entry != manifests[0] for entry in manifests):
        raise ValueError("Inconsistent dataset hashes")

    build_fields = [k for k in builds[0] if k not in ("arm", "seed", "run_id") and not k.endswith("sha256")]
    search_fields = [k for k in search[0] if k not in ("arm", "seed", "beam", "run_id")]
    median_build = [dict(arm=arm, **medians([r for r in builds if r["arm"] == arm], build_fields)) for arm in ARMS]
    same_beam = []
    matched = []
    beams = sorted({r["beam"] for r in search})
    for arm in ARMS:
        results = [r for r in search if r["arm"] == arm]
        beam_rows = [dict(arm=arm, beam=beam, **medians([r for r in results if r["beam"] == beam], search_fields))
                     for beam in beams]
        same_beam.extend(beam_rows)
        for target in TARGETS:
            selected = next((r for r in beam_rows if r["recall"] >= target), None)
            if selected is None:
                matched.append(dict(target=target, seeds_at_target=0, arm=arm, beam=None,
                                    **dict.fromkeys(search_fields)))
            else:
                count = sum(r["recall"] >= target for r in results if r["beam"] == selected["beam"])
                matched.append(dict(target=target, seeds_at_target=count, **selected))
    paired = []
    for arm, reference in (("adaptive","fixed"), ("v2a","adaptive"),
                           ("v2b","v2a"), ("v3","v2b")):
        for seed in SEEDS:
            for beam in beams:
                a, b = [next(r for r in search if r["arm"] == name and r["seed"] == seed and r["beam"] == beam)
                        for name in (arm, reference)]
                paired.append(dict(arm=arm, reference=reference, seed=seed, beam=beam,
                                   recall_delta_pp=100*(a["recall"]-b["recall"]),
                                   qps_delta_pct=100*(a["qps"]/b["qps"]-1),
                                   avg_cmps_delta=a["avg_cmps"]-b["avg_cmps"],
                                   avg_visited_delta=a["avg_visited"]-b["avg_visited"]))
    for filename, rows in (("paired_same_beam", paired), ("build", builds), ("search", search), ("median_build", median_build),
                           ("same_beam", same_beam), ("matched_recall", matched)):
        write_csv(directory / (filename + ".csv"), rows)

    stages = []
    for arm in ARMS[2:]:
        run_id = f"{name}_{arm}_s555_stage"
        result = json.loads((ROOT / run_id / "summary.json").read_text())
        telemetry = result["telemetry"]
        depth = next(row for row in telemetry["by_depth"] if row["depth"] == 1)
        for r in result["search"]:
            stages.append(dict(arm=arm, run_id=run_id, margin=result["margin"],
                               depth1_actual=depth["actual_assignments"], proposals=telemetry["directed_proposals"],
                               wall_s=result["wall_s"], final_edges=result["graph"]["edges"],
                               swaps=telemetry.get("diversity_swaps", 0), beam=r["beam"],
                               recall=r["recall_at_10"], qps=r["qps"], avg_cmps=r["avg_cmps"],
                               avg_visited=r["avg_visited"], p95_us=r["latency_us"]["p95"]))
    write_csv(directory / "stages.csv", stages)

    checks = {}
    for seed in SEEDS:
        a, b = [next(r for r in builds if r["arm"] == arm and r["seed"] == seed) for arm in ("v2b", "v3")]
        keys = ("depth1_actual", "depth1_fanout1", "depth1_fanout2", "depth1_fanout3")
        if any(a[k] != b[k] for k in keys) or not 0 < b["swaps"] <= b["depth1_fanout2"]:
            raise ValueError(f"Invalid V3 count for seed {seed}")
        checks[seed] = {"v2b_v3_same_depth1_fanout_histogram": True, "swaps": b["swaps"]}
    unreachable = {r["run_id"]: 1000000 - r["reachable"] for r in builds if r["reachable"] < 1000000}
    save(directory / "validation.json", dict(status="PASS", unreachable_from_0=unreachable, builds=len(builds), search_rows=len(search),
                                               matching_binaries=True, matching_datasets=True, seed_checks=checks))

    md = [
        "# SIFT1M adaptive fanout", "",
        "1.000.000 base, 10.000 query, 4 thread trên CPU 0,2,4,6. Ba seed 555/556/557 cho mỗi cấu hình.",
        "Cùng binary build, evaluator, dataset và tham số graph. Thứ tự arm thay đổi theo seed.",
        "Các bảng ghi trung vị trên ba seed. QPS và latency là số đo khám phá trên máy dùng chung.",
        "Bảng cùng ngưỡng Recall chọn beam đầu tiên trên lưới đo có Recall trung vị đạt ngưỡng.",
        "", "| Phiên bản | Build (s) | RSS (MiB) | Assignment depth 1 | Proposals | Cạnh cuối | Đổi leader |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in median_build:
        md.append(f"| {LABELS[r['arm']]} | {r['wall_s']:.2f} | {r['peak_rss_mib']:.1f} | "
                  f"{r['depth1_actual']:,} | {r['proposals']:,} | {r['final_edges']:,} | {r['swaps']:,} |")
    md.extend(["", "| Phiên bản | Recall beam 40 | Recall beam 80 | Recall beam 120 | Tính khoảng cách @80 | Mở rộng đỉnh @80 |",
               "|---|---:|---:|---:|---:|---:|"])
    for arm in ARMS:
        a,b,c = [next(r for r in same_beam if r["arm"] == arm and r["beam"] == beam) for beam in (40,80,120)]
        md.append(f"| {LABELS[arm]} | {a['recall']:.4%} | {b['recall']:.4%} | {c['recall']:.4%} | {b['avg_cmps']:.1f} | {b['avg_visited']:.1f} |")
    md.extend(["", "| Ngưỡng | Phiên bản | Beam | Recall | Seed đạt | QPS | P95 (µs) |",
               "|---|---|---:|---:|---:|---:|---:|"])
    for r in matched:
        arm = LABELS[r["arm"]]
        if r["beam"] is None:
            md.append(f"| {r['target']:.1%} | {arm} | — | — | — | — | — |")
        else:
            md.append(f"| {r['target']:.1%} | {arm} | {r['beam']} | {r['recall']:.4%} | "
                      f"{r['seeds_at_target']}/3 | {r['qps']:,.0f} | {r['latency_p95_us']:.1f} |")
    if unreachable:
        md.extend(["", "Đỉnh ngoài tầm từ node 0 theo run: " +
                   ", ".join(f"{run} ({count})" for run, count in unreachable.items()) + "."])
    md.extend(["", "Các lệnh nằm trong [commands.sh](commands.sh). Đọc [build.csv](build.csv) và [search.csv](search.csv) để xem từng seed.",
               "Mỗi thư mục run giữ summary, graph, log build/search, telemetry, CSV theo query và SHA256.", ""])
    (directory / "REPORT.md").write_text("\n".join(md))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", type=run_name, required=True)
    summarize(parser.parse_args().name)
