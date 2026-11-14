# H32-R37 — CORE-Slack-R0 (chỉ đọc, chưa sinh graph mới)

Ngày 30/10/2026 · Task A / PiPNN / graph topology. **Mục đích:** xác minh tính khả thi sơ bộ của C02/CORE-Slack bằng đúng candidate pool và graph SIFT1M đã khóa ở H32-R26a. Công cụ này **không** chỉnh sửa graph, không chạy BUILD, không đo Recall và **không** chứng nhận algorithm novelty.

## 1. Dữ liệu đã có trên Ubuntu

```
~/ann-task-a/experiments/H32/H32_R26a_pool_20261029_172452_132314/
├── dump.candidates.i32  # 640,000,000 B; 1m rows × C160 × int32
├── dump.graph           #  95,190,528 B; graph stock; ParlayANN binary
├── nodump.graph         #  95,190,528 B; graph control
└── r26a_report.json
~/ann-task-a/data/sift1m.fbin  # float32, 1m ×128
```

Đầu vào và SHA kỳ vọng:

- Pool: `7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8` (user đã kiểm lại).
- Stock graph: `d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef` (cần kiểm lại lượt này).
- Graph theo ParAlg/PiPNN `algorithms/utils/graph.h`, commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`: `uint32 n`, `uint32 max_degree`, **n** `uint32 outdegree`, sau đó **sum(outdegree)** neighbor ID `uint32`. KHÔNG phải graph record degree và neighbors đan xen.
- Candidate pool là các ID int32, padding `-1`. Nó **không lưu sẵn** mã nón 12-bit hay đầy đủ khoảng cách cạnh.

Mã nguồn đồ thị: https://github.com/ParAlg/PiPNN/blob/443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd/algorithms/utils/graph.h

## 2. Tải, thử mã và kiểm SHA

Tải file `H32_R37_CORE_Slack_Precheck.zip` vào Downloads, rồi:

```bash
cd ~/ann-task-a
unzip -o ~/Downloads/H32_R37_CORE_Slack_Precheck.zip -d ~/ann-task-a
python3 ann_task_a_r37_coreslack.py selftest

R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"
sha256sum "$R26A/dump.candidates.i32" "$R26A/dump.graph" "$R26A/nodump.graph"
```

Phải dừng nếu SHA của `dump.graph` không khớp R26a. `dump.graph` và `nodump.graph` chỉ được xem là byte-identical nếu cả SHA bằng nhau.

## 3. Chạy CORE-Slack-R0 trên 512 đỉnh nguồn

```bash
cd ~/ann-task-a
mkdir -p experiments/H37
R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 ann_task_a_r37_coreslack.py audit \
  --graph "$R26A/dump.graph" \
  --pool "$R26A/dump.candidates.i32" \
  --fbin "$PWD/data/sift1m.fbin" \
  --capacity 160 \
  --sample 512 \
  --seed 20261030 \
  --cone-deg 30 \
  --distance-ratio 2.0 \
  --output experiments/H37/coreslack_precheck_512.json \
  > experiments/H37/coreslack_precheck_512.stdout
```

Chương trình tự tính lại SHA cả graph lẫn pool, kiểm `n=1m, R=32, size`, graph degree/edge count và định dạng; từ chối audit nếu SHA không đúng. `--no-pins` chỉ dùng cho dữ liệu toy, **không** sử dụng cho kết quả thật.

## 4. In bảng tóm tắt

```bash
python3 - <<'PY'
import json
p='experiments/H37/coreslack_precheck_512.json'
d=json.load(open(p))
print('Status:',d['status'])
print('Graph arcs:', d['graph_arcs'])
print('Zero-indegree:', d['global_indegree_zero_count'])
print('Indegree <2:', d['global_indegree_lt_2_count'])
print('Outdegree < cap:', d['global_outdegree_lt_cap'])
print('Sample:',d['sample'],'Source SHA:',d['sample_ids_sha256'])
print('Sample sources with slack:',d['sample_sources_with_slack'])
print('Sample sources with any gated candidate:', d['sample_sources_with_any_gate_feasible_candidate'])
print('Sample outdegree:', d['sample_profile']['outdegree'])
print('Sample slack:', d['sample_profile']['slack'])
for k,v in d['sample_totals'].items(): print(k,':',v)
PY
```

## 5. Cách hiểu chỉ số

- `pool_new`: các ID trong `dump.candidates.i32` của nguồn nhưng chưa là cung đi ra của nguồn.
- `reverse_new`: các nguồn hàng xóm đang có cung đến nguồn, nhưng chưa có cung ngược chiều; được tìm bằng cách quét **toàn bộ** danh sách cung graph.
- `union_new`: hợp của hai loại, chỉ đếm duy nhất theo nguồn.
- `angular_novel`: ứng viên lệch ít nhất 30° với **mọi** hướng cạnh hiện tại của nguồn. Đây là **proxy hình học** bằng cos, không phải HashPrune LSH cone hash của tác giả.
- `distance_feasible`: khoảng cách Euclidean đến ứng viên không quá 2× trung vị độ dài các cạnh đi ra hiện tại. Đầu vào 128 chiều gốc; không phải giả định bảo toàn thứ hạng L2 sau quantization.
- `low_indegree_destination_candidates`: ứng viên đích có indegree dưới 2 trong graph gốc.
- `any_gate_feasible`: đồng thời thỏa độ dài, và (độ mới góc **hoặc** indegree đích thấp). Chỉ là số cơ hội có thể cân nhắc, không phải số cạnh đề nghị thêm.
- `global_indegree_zero_count`: đỉnh không có cạnh **đi vào**. Điều này không đồng nghĩa số đỉnh unreachable từ entry point.
- `graph_outside_pool`: nếu >0, có cạnh cuối graph không nằm trong raw row pool của cùng nguồn; không được giả định mọi cung gốc có thể tái dựng chỉ từ row pool.

**Kiểm soát ngân sách:** Nếu thêm tối đa 2 cung/đỉnh (1m đỉnh), có thể phát sinh tới 2m cung (~8,77% so với 22,797,630). Không thể tuyên bố “matched 22.8m arcs” chỉ nhờ R=32 hoặc delta_max=2. Trước khi xây graph mới, bắt buộc thiết kế **thay thế** cạnh hoặc ngân sách toàn cục và so Recall–comparisons cùng searcher/arc-count.

## 6. Kết quả / tiêu chí dừng

- **Selftest pass** xác nhận parser/proxy hoạt động trên graph và pool tổng hợp; không phải SIFT1M result.
- Nếu graph hoặc pool sai SHA, dừng ngay, không kết hợp dữ liệu khác protocol.
- Nếu chỉ tìm được candidate xa/không mới góc hoặc đa số hướng đã đủ phân tán, CORE-Slack chưa có cơ sở.
- Nếu thấy nhiều ứng viên phù hợp, vẫn **chưa** kết luận cải thiện Recall. Phải định nghĩa thay cạnh có thể kiểm chứng, chạy graph mới một cách độc lập (không ghi đè R26a), và so với nearest/backfill/random/FG no-spine cùng ngân sách 22.8m cung, chung ParlayANN Q80/100/120/160.
- R36 Centroid-CHARM NO-GO; R30 LOSF naive ordering NO-GO; H17 engineering baseline; PiPNN II official matched end-to-end benchmark blocked; H33 chưa mở.
