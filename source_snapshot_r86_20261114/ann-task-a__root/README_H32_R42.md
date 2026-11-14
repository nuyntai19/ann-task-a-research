# H32-R42 — Kiểm tra mất cạnh trực tiếp và khả năng cứu bằng đường đi 2 bước

## Mục tiêu

R41 đo tỷ lệ **exact base-anchor Top-10** có mặt trực tiếp trong `dump.candidates.i32` và `dump.graph`. Tuy nhiên, một cạnh trực tiếp bị RobustPrune loại bỏ có thể vẫn có một đường đi ngắn qua đỉnh trung gian. R42 kiểm tra **đúng 32 nguồn/320 đích Top-10 trong JSON R41** mà không chạy lại exhaustive kNN scan.

- **Direct**: cạnh có trong hàng `graph[u]`.
- **Reachable within 2 hops**: đường đi có hướng `u→t` hoặc `u→v→t` trong chính `dump.graph`.
- **Monotone within 2 hops (toward base target t)**: tồn tại `u→v→t` với `||X[v]-X[t]||² < ||X[u]-X[t]||²` (hoặc có cạnh trực tiếp). **Đây không phải monotonic navigability cho mọi query.**
- **Pool captured but pruned**: `t∈pool[u]` và `t∉graph[u]`.
- **Missing before pool**: `t∉pool[u]` và `t∉graph[u]`.

R42 dùng chính danh sách `knn10_ids` trong R41, đối chiếu lại từng nguồn `pool_hit/graph_hit/pruned/missing_before_pool`, khóa cùng SHA256 graph/pool và SHA danh sách source của R41. Mọi thao tác đều READ-ONLY. Chỉ có đánh giá cấu trúc 2 hop đối với **base targets**; không đo Recall@10, QPS, BUILD wall, đường tìm kiếm HNSW/ParlayANN, hay tính mới thuật toán.

## Cài đặt Ubuntu

```bash
cd ~/ann-task-a
unzip -o ~/Downloads/H32_R42_TwoHop_Rescue_Kit.zip -d ~/ann-task-a
python3 ann_task_a_r42_twohop.py selftest
```

Yêu cầu trong cùng thư mục: `ann_task_a_r37_coreslack.py` (R37), `ann_task_a_r41_attribution.py` (chỉ cho self-test), NumPy đã cài. Dữ liệu R26a và JSON R41 giữ nguyên.

## Thực nghiệm SIFT1M

```bash
cd ~/ann-task-a
mkdir -p experiments/H42
R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ann_task_a_r42_twohop.py audit \
  --r41 experiments/H41/r41_exact32.json \
  --graph "$R26A/dump.graph" \
  --pool "$R26A/dump.candidates.i32" \
  --fbin data/sift1m.fbin \
  --capacity 160 \
  --output experiments/H42/r42_twohop_exact32.json \
  > experiments/H42/r42_twohop_exact32.stdout
```

Nếu SHA, sample source SHA hoặc các count R41 không khớp, chương trình **từ chối chạy tiếp**. Không thêm `--no-pins` cho dữ liệu thật.

## In kết quả

```bash
python3 - <<'PY'
import json
r = json.load(open('experiments/H42/r42_twohop_exact32.json'))
print('SOURCE SHA:', r['protocol']['r41_source_ids_sha256'])
for group, x in r['summary'].items():
    print('\n', group, 'sources:', x['sources'], 'GT:', x['gt_total'])
    if not x['sources']: continue
    print('Direct:', x['direct'], '2-hop:', x['reachable_within_2_hops'], 'monotone-2-hop:', x['monotone_to_base_target_within_2_hops'])
    for k in ['pool_captured_but_pruned','missing_before_pool']:
        c=x[k]
        print(k, ': missing=', c['n'], '2-hop-rescued=', c['reachable_2hop'], 'monotone-rescued=', c['monotone_2hop'])
PY
```

## Diễn giải và gate

R41: 320 exact Top-10 cặp trong 32 nguồn, `207 direct`, `71 captured_but_pruned`, `42 missing_before_pool`. R42 phải bảo toàn tổng này. Nếu nhiều đích bị loại nhưng có đường đi 2-hop đơn điệu tới chính base target, điều đó **giảm mức khẩn cấp của việc phục hồi cạnh trực tiếp**, nhưng **không chứng minh searcher sẽ tìm thấy đường đi**. Nếu thiếu cả 2-hop, đó là vấn đề cấu trúc đáng xem tiếp nhưng chưa đủ quy kết recall giảm. Để nghiên cứu thuật toán thật, cần sau đó xem trace truy vấn heldout, matched graph arc budget, native Recall/QPS và prior art về navigability.

R42 là **một phép đo chẩn đoán cuối cùng giá rẻ tận dụng R41**, không mở H33 và không tạo thuật toán mới.
