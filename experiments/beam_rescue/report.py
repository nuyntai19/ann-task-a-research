"""Summarize topology, calibration and paired search measurements."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median

from campaign import ARMS, HERE, SEEDS, TARGETS, original, read_rows, save

LABEL = {
    "fixed": "Fixed", "v1": "V1", "v2a": "V2a", "v2b": "V2b", "v3": "V3",
    "rescue": "V2a + Beam-Rescue", "random": "V2a + thay cạnh ngẫu nhiên",
    "fixed_r32": "Fixed + route32", "v2a_r32": "V2a + route32",
    "v2a_r100": "V2a + route100", "rescue_r32": "Beam-Rescue + route32",
}
BASELINES = {
    "v1":"fixed", "v2a":"fixed", "v2b":"v2a", "v3":"v2b", "rescue":"v2a",
    "random":"v2a", "fixed_r32":"fixed", "v2a_r32":"v2a",
    "v2a_r100":"v2a", "rescue_r32":"rescue",
}


def write_csv(path, rows):
    with path.open("w",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def report(root):
    payload=lambda name: json.loads((root/name).read_text())
    survey,timing = payload("survey.json"),payload("timing.json")
    fields=("beam","recall","qps","avg_visited","avg_cmps","mean_us","p95_us")
    raw_map={(r["target"],r["arm"],r["seed"],r["repeat"]):r for r in timing}
    stage, summary, paired = [], [], []
    for target in TARGETS:
        for arm in ARMS:
            for seed in SEEDS:
                samples=[r for r in timing if (r["target"],r["arm"],r["seed"])==(target,arm,seed)]
                if not samples:
                    continue
                if len(samples)!=3 or len({r["beam"] for r in samples})!=1:
                    raise ValueError(f"Incomplete timing {target} {arm} {seed}")
                stage.append(dict(target=target,arm=arm,seed=seed,
                                  **{f:median(r[f] for r in samples) for f in fields}))
            rows=[r for r in stage if (r["target"],r["arm"])==(target,arm)]
            if rows:
                summary.append(dict(target=target,arm=arm,seeds=len(rows),
                                    **{f:median(r[f] for r in rows) for f in fields}))
            refs=([BASELINES[arm]] if arm in BASELINES else [])
            if arm=="rescue":
                refs+=["random"]
            if arm=="rescue_r32":
                refs+=["v2a_r32"]
            for ref in refs:
                for seed in SEEDS:
                    for repeat in range(3):
                        a,b=(raw_map.get((target,x,seed,repeat)) for x in (arm,ref))
                        if a is None or b is None:
                            continue
                        paired.append(dict(target=target,arm=arm,reference=ref,seed=seed,repeat=repeat,
                            beam_delta=a["beam"]-b["beam"],recall_delta_pp=100*(a["recall"]-b["recall"]),
                            qps_pct=100*(a["qps"]/b["qps"]-1),mean_us_pct=100*(a["mean_us"]/b["mean_us"]-1),
                            visited_delta=a["avg_visited"]-b["avg_visited"],
                            cmps_delta=a["avg_cmps"]-b["avg_cmps"]))
    refined, audits = [], []
    frozen=payload("frozen_graphs.json")["graphs"]
    for seed in SEEDS:
        for arm in ("fixed","v2a"):
            path=root/f"{arm}_{seed}"
            rows=read_rows(path/"audit.tsv","\t")
            if len(rows)!=1536*4:
                raise ValueError("Incomplete trace")
            for beam in (64,80,96,128):
                ref=[r for r in rows if int(r["beam"])==beam]
                audits.append(dict(seed=seed,arm=arm,beam=beam,queries=len(ref),
                    query_with_high_only=sum(int(r["high_only_hits"])>0 for r in ref),
                    **{f:sum(int(r[f]) for r in ref) for f in
                       ("hits","high_only_hits","witness_cutoff","witness_merge_drop","witness_eviction")}))
        path=root/f"v2a_{seed}"
        rows=read_rows(path/"candidate_replays.tsv","\t")
        k=frozen[f"rescue_{seed}"]["edits"]
        compare=read_rows(path/"verify.tsv","\t")
        chosen=next(r for r in compare if int(r["swaps"])==k)
        wall=payload(f"v2a_{seed}/time.json")["elapsed_s_includes_graph_load"]
        initial=json.loads((original(seed,"v2a")/"summary.json").read_text())["wall_s"]
        refined.append(dict(seed=seed,replays=len(rows),positive_replays=sum(int(r["hit_delta"])>0 for r in rows),
                            swaps=k,verify_hit_delta=int(chosen["hit_delta"]),verify_visited_saved=int(chosen["visits_saved"]),
                            verify_cmps_saved=int(chosen["cmps_saved"]),reachable=int(chosen["reachable"]),
                            old_v2a_build_s=initial,refinement_trial_s=wall,
                            v2a_plus_refine_trial_s=initial+wall))

    for name,rows in (("survey",survey),("timing",timing),("per_seed",stage),("matched_recall",summary),
                      ("paired",paired),("refinement",refined),("trace_summary",audits)):
        write_csv(root/(name+".csv"),rows)
    md=[
        "# Beam-Rescue và định tuyến trên SIFT1M", "",
        "10.000 query, 4 thread, ba seed 555–557. Mỗi cặp graph/seed dùng beam nhỏ nhất đạt ngưỡng trên lưới khảo sát. "
        "Các số là trung vị ba lượt đo của từng seed rồi trung vị các seed đạt. "
        "Latency và số phép tính khoảng cách của route đã gồm bước chọn leader.",
        "",
    ]
    for target, threshold in TARGETS.items():
        md.extend([f"## Recall@10 ≥ {100*threshold:g}%", "",
            "| Phiên bản | Seed đạt | Beam | Recall thực | QPS | Mean µs | P95 µs | Visited | Distance |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for r in summary:
            if r["target"]!=target:
                continue
            md.append(f"| {LABEL[r['arm']]} | {r['seeds']}/3 | {r['beam']:g} | {r['recall']:.3%} | "
                      f"{r['qps']:,.0f} | {r['mean_us']:.1f} | {r['p95_us']:.1f} | "
                      f"{r['avg_visited']:g} | {r['avg_cmps']:g} |")
        md.append("")
    md.extend(["## Thử thay cạnh", "",
        "| Seed | Replay đơn | Replay tăng hit | Số cạnh thay | Hit tăng trên 512 query kiểm tra | Wall refinement (s) |",
        "|---:|---:|---:|---:|---:|---:|"])
    for r in refined:
        md.append(f"| {r['seed']} | {r['replays']} | {r['positive_replays']} | {r['swaps']} | "
                  f"{r['verify_hit_delta']} | {r['refinement_trial_s']:.2f} |")
    md.extend(["",
        "Thời gian trên gồm tải graph, trace, thử ứng viên, xác nhận và xuất hai graph. "
        "Tạo GT calibration tính riêng trong calibration.json. "
        "Cạnh ra của từng đỉnh được kiểm tra trước khi benchmark. "
        "Mỗi phép thay đổi chỉ chạm một vị trí adjacency đã ghi.",
        "",
        "Đọc [paired.csv](paired.csv) để xem từng cặp seed/lượt đo. "
        "[survey.csv](survey.csv) giữ Recall/QPS theo beam. "
        "[trace_summary.csv](trace_summary.csv) giữ số hit chỉ tìm được tại beam 128 và sự kiện liên quan. "
        "[commands.sh](commands.sh) giữ lệnh và biến môi trường.", "",
    ])
    (root/"REPORT.md").write_text("\n".join(md))
    save(root/"report_validation.json",{"survey_rows":len(survey),"timing_rows":len(timing),
         "trace_rows":sum(r["queries"] for r in audits),"post_patch_graphs":len(frozen),
         "timing_repeats":3,"historical_parity":"validated on common beams by campaign.py",
         "build_budget_status":"User has not set a numeric build cap"})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    report(parser.parse_args().root)
