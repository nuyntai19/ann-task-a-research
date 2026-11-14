# H32-R38 — CORE-Slack R1: kiểm thử **thay 1 cạnh**, chỉ đọc

**Trạng thái:** Mã và self-test đã chạy trong môi trường tạo công cụ, **chưa chạy SIFT1M trên Ubuntu của bạn**. Không phát sinh graph mới. Không gọi native ParlayANN search, không đo Recall@10, QPS hay BUILD. Không tuyên bố cơ chế mới.

## Lý do cần R38 sau R37

Kết quả R37 bạn gửi: 22.797.630 cung, `indegree=0`: 0 đỉnh; 765.720 đỉnh chưa chạm degree cap32. Trên 512 nguồn có 8.032 candidate mới (7.300 từ pool, 3.782 reverse, giao 3.050). Bộ lọc góc ≥30° và độ dài ≤2× trung vị giữ **7.396/8.032 (~92,08%)**, tức **không có khả năng chọn lọc tốt**. 512/512 nguồn có candidate qua gate, nhưng 119/512 nguồn không có slot tăng độ bậc. Muốn đảm bảo bằng đúng 22.797.630 cung, cần một rule *thay thế cạnh* thay vì bổ sung tràn lan.

R38 làm **một kiểm thử mô phỏng không thay đổi file**:

- Lấy ngẫu nhiên 512 nguồn, seed `20261030` (cùng kích thước mẫu R37), và 64 **truy vấn heldout SIFT1M** từ `data/sift1m_queries.fbin`, seed `20261101`.
- Các đối chứng **chọn candidate không nhìn queries**: `random_union`, `nearest_union`, `nearest_pool`, `nearest_reverse`, `max_angular_novelty` (độ mới góc tối đa), `low_indegree_union` (indegree đích thấp nhất).
- Hai quy tắc chọn **một cung ra để bỏ**: `farthest` (cạnh dài nhất L2 từ nguồn) và `most_directionally_redundant` (hướng cosine giống một hướng cũ khác nhiều nhất).
- Mỗi cách: *thay một neighbor bằng một candidate*, degree và tổng cung **giữ nguyên nếu thay thực sự**. Nếu không có candidate thì **không thay** và ghi 64 lần so sánh `unchanged`; nếu outdegree nguồn bằng 0 thì bỏ qua nguồn đó.
- Chỉ so khoảng cách của **neighbor tốt nhất sau một bước** đến mỗi heldout query: `before − after`, chuẩn hóa bằng `max(d(source,query),1e−9)`. Số dương nghĩa là cải thiện proxy một bước, số âm nghĩa là xấu đi. Cũng báo % cải thiện, % xấu đi, số nguồn có candidate. **Không phải một lệnh ANN graph search**.

**Quan trọng:** Các heldout query chỉ dùng *đánh giá*, không được dùng để chọn cạnh mới/victim. Tuy nhiên vì tiếp tục đo nhiều phương án trên cùng queries có thể overfit, coi R38 là *sàng lọc* và không tuning sau khi thấy kết quả. Thử một lần, sau đó nếu hiệu ứng đáng kể mới cân nhắc graph pilot đồng ngân sách cùng native searcher.

## Các bước trên Ubuntu

Cần có `ann_task_a_r37_coreslack.py` ngay trong `~/ann-task-a`, và NumPy hoạt động.

```bash
cd ~/ann-task-a
unzip -o ~/Downloads/H32_R38_Virtual_Replacement_Kit.zip -d ~/ann-task-a
python3 ann_task_a_r38_virtual.py selftest
```

Self-test dự kiến:

```text
R38_SELFTEST_PASS: parsers, stable selection, equal arc virtual replacement, 12 comparisons, conservation
```

Chạy SIFT1M:

```bash
cd ~/ann-task-a
mkdir -p experiments/H38
R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 ann_task_a_r38_virtual.py audit \
  --graph "$R26A/dump.graph" \
  --pool "$R26A/dump.candidates.i32" \
  --fbin data/sift1m.fbin \
  --queries data/sift1m_queries.fbin \
  --queries-n 10000 \
  --capacity 160 \
  --sources 512 \
  --targets 64 \
  --seed 20261030 \
  --query-seed 20261101 \
  --output experiments/H38/virtual_replace_512.json \
  > experiments/H38/virtual_replace_512.stdout
```

Chương trình tự SHA256 graph và pool, chặn mismatch. **Không dùng** `--no-pins` trên SIFT1M thật. `--queries-n=10000` kiểm header query base; nếu file truy vấn có kích thước khác, không tự đoán — kiểm file trước.

In bảng rút gọn:

```bash
python3 - <<'PY'
import json
p='experiments/H38/virtual_replace_512.json'
d=json.load(open(p))
print('Status:', d['status'])
print('Sources:', d['protocol']['sources'], 'Targets:',d['protocol']['targets'])
print('Full-cap sources:',d['sample']['sources_full_at_cap'])
print('Zero-out-degree sources:',d['sample']['sources_zero_outdegree_excluded'])
print('Sample IDs SHA:',d['protocol']['sample_source_ids_sha256'])
for arm,x in d['comparisons'].items():
    y=x['mean_normalized_best_neighbor_improvement']
    print(f'{arm:54s} n={x["n_sources_with_replacement"]:3d} '
          f'mean_delta={y:+.6f} improved={x["fraction_improved"]:.2%} '
          f'harmed={x["fraction_harmed"]:.2%} '
          f'progress_net={x["net_progress_changes"]}')
PY
```

## Diễn giải nghiêm ngặt

- R37 gần như không có sức chọn lọc: `distance_feasible=8.030/8.032` (~99,98%); `angular_novel=7.295/8.032` (~90,82%); `(angle & distance)=7.293`; `low_indegree_destination_candidates=131/8.032` (~1,63%). `any_gate_feasible=7.396` vượt `angle_and_distance=7.293` đúng 103 trường hợp được cứu nhờ indegree thấp. Vì không có đỉnh indegree 0, gate low indegree ở đây chỉ trỏ tới indegree 1.
- `reverse_gate_feasible` và `pool_gate_feasible` **có giao nhau**, không được cộng trực tiếp; `pool_new+reverse_new−intersection=union_new`.
- `n_sources_with_replacement` nhỏ hơn 512 nếu một cách chọn không có candidate trên vài nguồn; nhóm đó được tính **no-op** để giữ mẫu so sánh như nhau (trừ các nguồn degree 0).
- Nếu `mean_delta > 0`, chỉ có bằng chứng **một bước** tốt hơn trên 64 truy vấn mẫu. Một cạnh dài có thể quan trọng để nối xa nhiều bước; `farthest` không phải một chính sách prune chắc chắn an toàn.
- Nếu phương án dựa góc/indegree không vượt nearest/random và không có hiệu ứng tích cực ổn định, **không** đi tiếp full BUILD hoặc graph edit. Nếu có hiệu ứng thì chỉ mở *graph PILOT ở cùng 22.797.630 directed arcs* với parity bytes, same searcher, Recall/QPS và baseline đối chứng. Cần prior-art kiểm tra trước phát biểu novelty.

## Mã và nguồn

Công cụ: `ann_task_a_r38_virtual.py`; thư viện loader: `ann_task_a_r37_coreslack.py` (đã cài từ R37). Source graph layout: [PiPNN graph.h](https://github.com/ParAlg/PiPNN/blob/443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd/algorithms/utils/graph.h).
