"""Compare stage-specific, paired SIFT1M measurements and link historical experiments."""
import argparse
from pathlib import Path
from statistics import median
from common import EXP, REFERENCE, SEEDS, rows, csv_write

FOLDERS=("routing_stage1_coverage","routing_stage2_multientry","routing_stage3_partition","routing_stage4_hierarchical")
REFS=(
    {"uniform32":"node0","farthest32":"uniform32","facility32":"uniform32","medoids32":"uniform32"},
    {"top2":"top1","adaptive102":"top1","adaptive105":"top1","adaptive110":"top1"},
    {"route_placebo":"v2a_rebuild","route_aware":"v2a_rebuild"},
    {"flat12":"flat32_best","flat32_local":"flat32_best","hier8x4":"flat12"},
)
TITLES=("Coverage-Aware Route32","Multi-Entry Adaptive Routing","Routing-Aware Adaptive Fanout","Hierarchical Routing")


def main(name):
    selected={}
    paired=[]
    for i,(folder,references) in enumerate(zip(FOLDERS,REFS),1):
        run=EXP/folder/"runs"/name
        aggregate=rows(run/"matched_recall.csv")
        times=rows(run/"timing.csv")
        index={(r["dataset"],r["graph"],r["arm"],r["seed"],r["target"],r["repeat"]):r for r in times}
        selected[i]=aggregate
        for r in times:
            ref=references.get(r["arm"])
            extra=[]
            if i==3 and r["arm"]=="route_aware":
                extra=["route_placebo"]
            if i==4 and r["arm"]=="hier8x4":
                extra=["flat32_best","flat32_local"]
            for comparator in ([ref] if ref else [])+extra:
                a=index.get((r["dataset"],r["graph"],comparator,r["seed"],r["target"],r["repeat"]))
                if a is None:
                    continue
                delta=lambda k:float(r[k])-float(a[k])
                paired.append(dict(stage=i,dataset=r["dataset"],graph=r["graph"],arm=r["arm"],baseline=comparator,
                    seed=int(r["seed"]),target=float(r["target"]),repeat=int(r["repeat"]),
                    beam_delta=delta("beam"),recall_delta_pp=100*delta("recall"),
                    qps_pct=100*(float(r["qps"])/float(a["qps"])-1),
                    latency_pct=100*(float(r["mean_us"])/float(a["mean_us"])-1),
                    visited_delta=delta("visited"),distance_delta=delta("distance")))
    csv_write(EXP/f"routing_{name}_paired.csv",paired)
    report=["# Đối chiếu bốn giai đoạn routing trên SIFT1M","",
      "Recall 99% là mốc chính. Recall 99,5% có trong báo cáo mỗi giai đoạn. "
      "Mỗi dòng là trung vị của các seed và ba lượt timing tại beam đạt ngưỡng của từng graph. "
      "Đối chiếu QPS giữa phiên dùng tỷ lệ ghép với đối chứng chạy lại trong chính giai đoạn đó.","",
      "Bộ official gồm 10.000 query SIFT1M đã dùng ở các vòng trước. "
      "Bộ proxy gồm 3.072 query lấy từ base, giữ riêng khỏi chọn leader và calibration, loại self theo ID. "
      "Đây là đánh giá held-out cùng dataset.","",
      "## Kết quả trước bốn giai đoạn","",
      "| Phiên bản | Beam | QPS tại 99% | Visited | Distance |",
      "|---|---:|---:|---:|---:|"]
    for r in rows(REFERENCE/"matched_recall.csv"):
        if r["target"]=="r99":
            report.append(f"| {r['arm']} | {float(r['beam']):g} | {float(r['qps']):,.0f} | "
                          f"{float(r['avg_visited']):g} | {float(r['avg_cmps']):g} |")
    report.extend(["","Số liệu trên dùng evaluator và phiên timing trước. "
                   "So sánh tác động mới bằng đối chứng ghép trong các bảng tiếp theo.",""])
    for i,(folder,title) in enumerate(zip(FOLDERS,TITLES),1):
        report.extend([f"## Giai đoạn {i} — {title}","",
          "| Bộ query | Graph | Phương án | Seed đạt | Beam | Recall | QPS | Mean µs | Visited | Distance | ΔQPS ghép |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for r in selected[i]:
            if float(r["target"])!=.99:
                continue
            base_arm=REFS[i-1].get(r["arm"])
            pr=[p["qps_pct"] for p in paired if
                (p["stage"],p["dataset"],p["graph"],p["arm"],p["target"],p["baseline"])==
                (i,r["dataset"],r["graph"],r["arm"],.99,base_arm)]
            diff=f"{median(pr):+.2f}%" if pr else "—"
            report.append(f"| {r['dataset']} | {r['graph']} | {r['arm']} | {r['seeds']}/3 | {float(r['beam']):g} | "
                f"{float(r['recall']):.3%} | {float(r['qps']):,.0f} | {float(r['mean_us']):.1f} | "
                f"{float(r['visited']):.1f} | {float(r['distance']):.1f} | {diff} |")
        report.extend(["", f"[Chi tiết, gồm mốc 99,5%]({folder}/runs/{name}/REPORT.md) · "
                            f"[Lệnh đã chạy]({folder}/runs/{name}/commands.sh)",""])
    for stage in (1,4):
        entries=rows(EXP/FOLDERS[stage-1]/"runs"/name/"selection.csv")
        report.extend([f"## Chi phí chọn leader của giai đoạn {stage}","",
                      "| Phương án | Chuẩn bị trung vị (s) | Byte ID |",
                      "|---|---:|---:|"])
        for arm in sorted({r["arm"] for r in entries}):
            data=[r for r in entries if r["arm"]==arm]
            report.append(f"| {arm} | {median(float(r['selection_s']) for r in data):.3f} | {data[0]['id_bytes']} |")
        report.append("")
    build=rows(EXP/FOLDERS[2]/"runs"/name/"build.csv")
    report.extend(["## Chi phí build lại giai đoạn 3","",
        "| Phương án | Build (s) | Chuẩn bị bổ sung và build (s) | RSS build (MiB) | Proposals |",
        "|---|---:|---:|---:|---:|"])
    for arm in sorted({r["arm"] for r in build}):
        data=[r for r in build if r["arm"]==arm]
        mid=lambda k:median(float(r[k]) for r in data)
        report.append(f"| {arm} | {mid('build_s'):.2f} | {mid('one_trial_total_s'):.2f} | "
                      f"{mid('rss_mib'):.1f} | {mid('proposals'):,.0f} |")
    report.append("")
    report.extend(["ΔQPS ghép là trung vị tỷ lệ giữa các lượt có cùng bộ query, graph, seed, ngưỡng và repeat. "
                   "Mỗi giai đoạn lưu beam theo seed và lưới khảo sát đầy đủ.",
                   "",f"[Dữ liệu ghép lượt cho cả hai mốc](routing_{name}_paired.csv)",""])
    (EXP/f"ROUTING_{name}_COMPARISON.md").write_text("\n".join(report))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name",default="sift1m_r1")
    main(parser.parse_args().name)
