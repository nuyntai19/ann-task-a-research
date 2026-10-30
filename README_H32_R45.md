# H32–R45 — Native ParlayANN query failure trace, Q100 (chỉ đọc graph)

## Mục tiêu và phạm vi

R42 chỉ đo 2-hop cho **đỉnh dữ liệu → exact base neighbor**. R45 đo những truy vấn **heldout SIFT1M thực sự bị miss tại Q=100, k=10**, trên đúng graph R26a gốc. Chưa đề xuất H33, không sửa PiPNN topology, không chạy lại BUILD và không biến trace thành benchmarking.

R45 tạo **bản sao tách biệt** `src/ParlayANN` đã khóa commit `a48c6a34e5f959190992aa531cc18454cfcc3dd3`. Chỉ sửa `beamSearch.h` và `check_nn_recall.h` **trong bản sao**. Bản ParlayANN gốc, graph `.graph`, pool `.candidates.i32` và binary gốc vẫn nguyên vẹn. Cả hai binary chạy cùng `10.000` query; `256` query được lấy **ngẫu nhiên không hoàn lại, seed=20261104**, được trace trong 5 lượt nội bộ native.

**Giới hạn:** `visitedElts` là tập đỉnh được mở rộng nhưng được sắp theo khoảng cách đến query, không lưu thứ tự mở rộng. `frontier` là tập còn trong beam khi kết thúc, không phải mọi candidate đã từng vào frontier. Nếu GT là neighbor của một đỉnh `visited`, nó **có thể đã bị has_been_seen, filtering, distance cutoff hoặc eviction**; R45 chưa tách bốn nguyên nhân đó. `not_adjacent_to_expanded` không có nghĩa toàn graph không có đường tới GT. Strict first-ten GT và tie-aware native Recall được báo cáo riêng; so sánh QPS bản trace với baseline là **không hợp lệ** vì có I/O.

## Gói và SHA guard

R45 yêu cầu:

- HEAD ParlayANN: `a48c6a34e5f959190992aa531cc18454cfcc3dd3`; từ chối nếu hai header gốc bị sửa cục bộ so với HEAD.
- Baseline executable SHA256 `ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8`.
- R26a `dump.graph` SHA256 `d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef` (n=1.000.000, max_degree=32).
- `data/sift1m.fbin`, `data/sift1m_queries.fbin` và `data/sift1m_gt.ibin`. Các file phải thuộc protocol SIFT1M 10k query/GT100 đã dùng trước đó; file GT là bố cục `.ibin` riêng của ParlayANN.

Nếu bất kỳ SHA hoặc source gate khác: **STOP**, không bypass. Nếu source/binary thực tế ở vị trí khác, truyền đường dẫn `--source` hoặc `--baseline-binary` nhưng SHA vẫn phải khớp.

## 1. Giải nén và kiểm thử

```bash
cd ~/ann-task-a
unzip -o ~/Downloads/H32_R45_Native_Query_Trace_Kit.zip -d ~/ann-task-a
python3 ann_task_a_r45_native_trace.py selftest
```

Kỳ vọng: `R45_SELFTEST_PASS`. Selftest này và thử C++ snippet trên môi trường công cụ **không thay thế build native đầy đủ** trên Ubuntu.

## 2. Chuẩn bị bản sao và build riêng

```bash
cd ~/ann-task-a
mkdir -p experiments/H45

python3 ann_task_a_r45_native_trace.py prepare \
  --source src/ParlayANN \
  --out experiments/H45/ParlayANN-native-trace \
  --build
```

Kỳ vọng `R45_PATCH_COPY_PASS` và `R45_BUILD_PASS`. Nếu fail build: xem `experiments/H45/ParlayANN-native-trace/R45_BUILD.log` và **dừng**, không sửa source gốc. Không chạy lại `prepare` đè thư mục hiện có; nó cố ý từ chối overwrite. Bản copy có `R45_TRACE_MANIFEST.json` với các SHA trước/sau sửa.

## 3. Chạy hai native executable bằng một protocol duy nhất

```bash
R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"

python3 ann_task_a_r45_native_trace.py run \
  --graph "$R26A/dump.graph" \
  --base data/sift1m.fbin \
  --queries data/sift1m_queries.fbin \
  --gt data/sift1m_gt.ibin \
  --baseline-binary src/ParlayANN/algorithms/vamana/neighbors \
  --traced-binary experiments/H45/ParlayANN-native-trace/algorithms/vamana/neighbors \
  --cpu 0 \
  --limit 256 --seed 20261104 \
  --out experiments/H45/native_q100_256
```

R45 pin CPU0 bằng `taskset -c 0`, `OMP_NUM_THREADS=1`, `PARLAY_NUM_THREADS=1`. Cả hai binary nhận `-data_type float -dist_func Euclidian -base_path -query_path -gt_path -graph_path -Q 100 -k 10 -verbose`. Native chạy 5 repeats trong **một tiến trình mỗi binary**, chưa phải independent experiment seeds. Hai files `baseline_native.log`, `traced_native.log` giữ stdout. `selected_queries.json` khóa seed, 256 query IDs và SHA256 của danh sách little-endian uint32. `traces/q_<id>.trace` là dữ liệu trên 256 query mẫu. Không tạo bất kỳ graph mới nào.

Sau cùng script tự chạy `analyze`. **Điều kiện PASS nghiêm ngặt:** cả 5 repeat trên mẫu đều cho cùng beam/visited/GT; native mean Recall, visited và comparisons của hai binary khớp ở từng lượt; graph đúng SHA; k10/Q100; không đi qua quantized-rerank path; Top-k trace khớp prefix frontier. Nếu khác, script **không xuất kết luận thành công**. Nếu script fail, gửi lỗi/log; không sửa thủ công kết quả.

## 4. In kết quả

```bash
python3 - <<'PY'
import json
p='experiments/H45/native_q100_256/R45_native_query_trace.json'
d=json.load(open(p))
print('Parity:',d['parity'])
print('Sample SHA:',d['query_sample']['sample_sha256'])
print('Sources:',d['protocol']['traced_queries'],'Q:',d['protocol']['Q'])
print('Counts:')
for k,v in d['counts'].items():print(k,v)
print('Example missed queries:')
for x in d['missed_query_details'][:8]:
    print(x['query_id'],x['strict_hits'],'/10',x['misses'][:3])
PY
```

**Phân loại chính:**

- `expanded_but_not_returned`: bản thân GT được mở rộng nhưng không nằm Top-k; có thể do xếp hạng.
- `final_frontier_outside_k`: GT nằm trong beam cuối nhưng xếp sau Top-k.
- `adjacent_to_expanded_but_not_returned`: ít nhất một `visited` node có cạnh đi tới GT; **không suy ra** GT chắc chắn đã chấm khoảng cách hoặc được nhận vào beam.
- `not_adjacent_to_expanded`: không có cạnh trực tiếp từ tập actually-expanded; không suy ra graph bị đứt kết nối.

Nếu có hiện tượng đáng kể và đạt parity, vòng sau mới instrument sâu hơn `has_been_seen`, cutoff và eviction trên **các query miss đã định danh**. Không xây graph mới hoặc mở H33 từ R45.

## Mốc kiểm thử công cụ

- `py_compile`: PASS.
- `selftest`: PASS (anchor patch, double-patch rejection, log format).
- Isolated C++ hook compile/run with g++17 and synthetic point/GT: PASS.
- Native ParlayANN full build and search on user Ubuntu: **CHƯA CHẠY**.
