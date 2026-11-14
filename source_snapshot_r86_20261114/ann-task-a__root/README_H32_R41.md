# H32-R41 — Exact kNN Anchor Attribution: Pool vs Graph

**Purpose:** Xác định phần nào trong các láng giềng *chính xác của điểm trong BASE SIFT1M* đã nằm trong (1) `dump.candidates.i32`, (2) `dump.graph` của **cùng build R26a**. Chỉ phân tích đọc-only. Đây không phải Recall@10 trên query, không phải phép đo PiPNN II, không sửa graph và không chứng minh thuật toán mới.

## Tiền điều kiện

- Ubuntu, Python 3 + NumPy (đã cài trong R37).
- `~/ann-task-a/ann_task_a_r37_coreslack.py` tồn tại. Script R41 sử dụng trực tiếp các lớp kiểm tra file và hash pin từ R37.
- Hai file R26a phải có đúng SHA256:
  - graph `d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef`
  - pool `7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8`
- Vector gốc `data/sift1m.fbin`: 1,000,000 × 128 float32, 512,000,008 bytes. **Không thay bằng `sift1m_queries.fbin`.**

## 1. Giải nén và self-test

```bash
cd ~/ann-task-a
unzip -o ~/Downloads/H32_R41_Exact_Anchor_Attribution.zip -d ~/ann-task-a
python3 ann_task_a_r41_attribution.py selftest
```

Expected: `R41_SELFTEST_PASS: ...`.

## 2. Chạy R41 trên SIFT1M thật — single audit, no rebuild

Mẫu **32 base anchors**, seed mới `20261103`, chính xác k={10,32}. Đối chiếu trên **toàn bộ 1 triệu điểm base** cho mỗi nguồn, không sử dụng GT query. Quét float64, tie-break theo global ID; thuật toán brute-force streaming O(s×n×d), **có thể tốn CPU**, không phải ANN search. Working memory giới hạn bởi `--chunk 16384`; không cấp phát ma trận n×n.

```bash
cd ~/ann-task-a
mkdir -p experiments/H41
R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 ann_task_a_r41_attribution.py audit \
  --graph "$R26A/dump.graph" \
  --pool "$R26A/dump.candidates.i32" \
  --fbin data/sift1m.fbin \
  --capacity 160 --sources 32 --seed 20261103 \
  --k 10 32 --chunk 16384 \
  --output experiments/H41/r41_exact32.json \
  > experiments/H41/r41_exact32.stdout
```

The tool reads only; it does not modify the R26a graph/pool. To follow along during scan, in a second terminal:

```bash
tail -f ~/ann-task-a/experiments/H41/r41_exact32.stdout
```

## 3. Print focused result

```bash
python3 - <<'PY'
import json
p='experiments/H41/r41_exact32.json'
d=json.load(open(p))
print('Sources:',d['protocol']['source_count'])
print('Source SHA:',d['protocol']['source_ids_sha256'])
print('Graph SHA:',d['provenance']['graph_sha256'])
print('Pool SHA:',d['provenance']['pool_sha256'])
for group in ['uniform_sample_all','sample_outdegree_full','sample_outdegree_slack']:
    g=d['summary'][group]
    print('\n===',group,'n=',g['n'],'===')
    if not g['n']:continue
    print('Mean pool candidates:',round(g['mean_pool_count'],3),'outdegree:',round(g['mean_outdegree'],3))
    for k in [10,32]:
        a=g[f'k{k}']
        print(f'k={k}: pool={a["pool_coverage"]:.2%} graph={a["graph_coverage"]:.2%}',
              'missed before pool=',a['lost_before_pool'],
              'captured but pruned=',a['captured_but_pruned'],
              'graph rescued outside pool=',a['graph_recovered_outside_pool'],
              'graph missing=',a['graph_missing'],
              'CI pool=',a['bootstrap_source_CI_95_pool_coverage'],
              'CI graph=',a['bootstrap_source_CI_95_graph_coverage'])
PY
```

## Kết quả phải được hiểu đúng

- `pool_coverage = |exact base Top-k ∩ pool rows|/k` tổng hợp trên 32 anchors.
- `graph_coverage = |exact base Top-k ∩ outgoing graph neighbors|/k`.
- `lost_before_pool`: số cặp `(u,v)` thuộc **base-ground-truth** nhưng không nằm trong pool của u.
- `captured_but_pruned`: cặp exact kNN *có trong pool* nhưng không còn trong outgoing graph.
- `graph_recovered_outside_pool`: cặp exact kNN trong graph nhưng không có ở pool (cần ghi lại nếu xảy ra; không giả định graph luôn là subset pool).
- Đẳng thức kiểm tra: `graph_missing = lost_before_pool + captured_but_pruned - graph_recovered_outside_pool`.
- Kết quả source split `outdegree_full/slack` **không phải** nhóm mẫu được thiết kế cân bằng, chỉ là mô tả hậu nghiệm trong mẫu uniform.
- Bootstrap CI mô tả biến thiên giữa **source points trên cùng SIFT1M**, không phải CI hiệu năng đa corpus. 32 mẫu chỉ là vòng chẩn đoán đầu.
- **Không gọi** hai coverage trên là query Recall@10; đồ thị navigable cần cạnh dài/đa dạng và beam search, không chỉ chứa kNN chính xác của các base points.
- Không sử dụng query vector hay heldout ground truth để chọn graph. Không tạo H33 chỉ từ hiệu ứng thống kê.

## Tiêu chí chuyển pha nghiên cứu (không phải tiêu chí chứng minh thuật toán)

- Nếu pool Top10 coverage thấp và graph gần pool: nghiên cứu pool coverage/fanout, nhưng đã có PiPNN partition and Three Stages zero-clustering prior art.
- Nếu pool Top10 coverage cao nhưng graph thấp: tìm nguyên nhân edge ending, đối chiếu RobustPrune, HashPrune và Three Stages, không mặc định kNN-only sẽ tăng search.
- Nếu pool & graph Top10 coverage cao nhưng native search Recall hoặc QPS kém: đo trace navigability/search failure, đối chiếu Almost Navigable Graphs/SODA 2026; không chỉnh graph theo query GT.
- Nếu không có khoảng trống đáng kể hoặc không chỉ ra được cơ chế độc lập mạnh: STOP, quay lại đọc/đối chiếu nguồn chính thống.

**Source evidence:** ParAlg/PiPNN graph serialization; H32-R26a pinned real build; PiPNN paper arXiv:2602.21247; Three Composable Stages arXiv:2610.09041; Almost Navigable Graphs arXiv:2607.14564.
