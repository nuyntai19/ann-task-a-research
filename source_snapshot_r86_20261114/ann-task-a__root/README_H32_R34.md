# H32-R34 — Global outgoing Top-2 overlap-rescue audit (SIFT1M)

## Mục tiêu

Sau quét CHARM-R0 γ=0.25/0.50/0.75 trên 64 leaf, số `top2_event_coverage` chỉ đo mức **giữ proposal trong chính leaf**. Bộ kiểm toán này đánh giá xem **cùng một nguồn và một láng giềng** bị bỏ ở một leaf có xuất hiện lại trong *một leaf khác chứa cùng nguồn* hay không. Chỉ lấy mẫu 64 đỉnh nguồn, nhưng quét mọi leaf chứa mỗi nguồn đó.

Không xây graph, không tạo Top-K PiPNN II chính thức, không đánh giá Recall/QPS/HashPrune, không có nhãn Core thật. **Chỉ tính outgoing Top-2 của đỉnh nguồn**, không tính các incoming/symmetric candidates do hàng khác đề xuất. Kết quả tuyệt đối không được gọi là toàn bộ HashPrune candidate pool coverage.

## Cài/chạy

Đặt `ann_task_a_r34_global.py` cùng thư mục với `ann_task_a_r29.py` tại `~/ann-task-a`. Đã có NumPy từ thử nghiệm R29.

```bash
cd ~/ann-task-a
mkdir -p experiments/H34
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ann_task_a_r34_global.py \
  --leaves experiments/H18/phase1_leaf_overlap/sift1m.leaves.bin \
  --fbin data/sift1m.fbin \
  --sources 64 --seed 20261030 \
  --gamma 0.25 0.50 0.75 \
  --modes random centroid-proxy \
  --output experiments/H34/global_outgoing_64.json \
  > experiments/H34/global_outgoing_64.stdout
```

Nếu có thể, chạy lại với `--sources 256 --seed 20261031` để kiểm tra độ ổn định. Không bắt buộc cho bước đầu. Không dùng `.fbin` queries làm dữ liệu base.

## Xem kết quả gọn

```bash
python3 - <<'PY'
import json
p='experiments/H34/global_outgoing_64.json'
d=json.load(open(p))
print('Sampled sources:',d['sample_sources'],'Incident leaves:',d['incident_leaves_scanned'])
print('Source memberships:',d['source_memberships_total'])
for s in d['scenarios']:
    print(f"gamma={s['gamma']:.2f} mode={s['mode']:15s} "
          f"local={s['local_event_coverage']:.2%} "
          f"global_unique_outgoing={s['global_outgoing_unique_candidate_coverage']:.2%} "
          f"rescued_lost_events={s['overlap_rescue_fraction_among_missed_local_events']:.2%} "
          f"missing_sources={s['sources_with_missing_baseline_candidates']}/{d['sample_sources']}")
PY
```

## Các chỉ số cần hiểu đúng

- `local_event_coverage`: bao nhiêu outgoing Top-2 proposals trên **tất cả leaf chứa nguồn được lấy mẫu** vẫn nằm trong selected Core-Halo pair set, theo cách tính nguồn-đích của chương trình mới.
- `global_outgoing_unique_candidate_coverage`: lấy union các outgoing candidates trên mọi leaf của từng nguồn rồi đếm phần giao. Đây là bước thử khả năng bù trùng lặp giữa leaf, **chỉ cho outgoing proposals**.
- `overlap_rescue_fraction_among_missed_local_events`: tỷ lệ event bị bỏ trong một leaf nhưng có cùng neighbor trong union reduced ở leaf khác.
- `sources_with_missing_baseline_candidates`: số nguồn mẫu thiếu ít nhất một candidate unique theo baseline.
- `pair_savings_fraction_on_incident_leaves`: chỉ trên những leaf được đụng bởi mẫu nguồn; không đại diện toàn bộ 85.529 leaf.

**Lưu ý tính công bằng:** Đây là protocol *source sampling toàn bộ membership*, khác hẳn protocol *uniform 64-leaf sampling* của R32/R33; không so trực tiếp các tỷ lệ `local_event_coverage` giữa hai thiết kế. Mã đang dùng squared L2 Float32 theo từng hàng (khác công thức GEMM của R29/Eigen về rounding); ties/gần-ties có thể khiến candidate hơi khác. Các nhãn random theo seed ổn định mỗi leaf và nested theo γ, centroid là proxy hình học — cả hai không phải leader provenance.

## Kiểm thử được thực hiện trong phiên ChatGPT

Trên toy dataset 8 vector, 4 leaf, 20 memberships, chương trình chạy thành công và ghi `r34_synthetic_selftest.json`. Đây là dữ liệu tổng hợp **không phải số liệu SIFT1M**.

## Kill gate khoa học

Nếu độ phủ unique outgoing vẫn thấp đối với centroid γ=.50 và pair saving đáng kể, giảm ưu tiên CHARM dạng centroid; **không** kết luận giảm Recall cùng tỷ lệ. Nếu độ phủ cao nhờ overlap, nghiên cứu tiếp cơ chế nhãn Core thực, matched-fanout, symmetrical proposal pool, HashPrune và Recall. Tránh bám oracle, vì oracle tính full matrix trước, không phải giải pháp tiết kiệm thực tế.
