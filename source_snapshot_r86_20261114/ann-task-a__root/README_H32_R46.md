# H32-R46 — R45 native miss reclassification and graph exposure (chỉ đọc)

## Trạng thái khoa học

R45 đã PASS parity giữa native ParlayANN gốc và bản trace, trên 256 truy vấn SIFT1M, k=10, Q=100. Tổng 2.535/2.560 strict hits, 2.540/2.560 native tie-eligible hits; 25 strict-missing IDs, gồm 20 `not_adjacent_to_expanded` và 5 `expanded_but_not_returned`. **Không được suy ra 20 `not_adjacent_to_expanded` là đúng 20 native miss:** tín chỉ đồng hạng có thể bù một strict GT khác trong **cùng truy vấn**.

R46 **không chạy ParlayANN**, không rebuild PiPNN, không sửa graph, không thay đổi nguồn hoặc dùng ảnh query để chọn cạnh. Nó chỉ đọc báo cáo R45, 256 raw query trace, và graph gốc đã khóa SHA.

## Lệnh Ubuntu

1. Tải ZIP `H32_R46_Native_Miss_Reclassification.zip` vào `~/Downloads`.

```bash
cd ~/ann-task-a
unzip -o ~/Downloads/H32_R46_Native_Miss_Reclassification.zip -d ~/ann-task-a
python3 ann_task_a_r46_native_miss_audit.py selftest
mkdir -p experiments/H46
R26A="$PWD/experiments/H32/H32_R26a_pool_20261029_172452_132314"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 ann_task_a_r46_native_miss_audit.py audit \
  --r45 experiments/H45/native_q100_256/R45_native_query_trace.json \
  --traces experiments/H45/native_q100_256/traces \
  --graph "$R26A/dump.graph" \
  --output experiments/H46/r46_native_miss_reclassified.json \
  > experiments/H46/r46_native_miss_reclassified.stdout
cat experiments/H46/r46_native_miss_reclassified.stdout
```

Để in các truy vấn native thật sự chưa đủ 10 hit (khác với strict miss):

```bash
python3 - <<'PY'
import json
p='experiments/H46/r46_native_miss_reclassified.json'
d=json.load(open(p))
print('Counts:',d['counts'])
print('Strict categories in native-failing queries:',d['strict_missing_categories_within_queries_that_still_fail_native'])
print('Not-adjacent frontier:',d['nonadjacent_subcategories'])
print('Not-adjacent 2-hop horizon:',d['nonadjacent_twohop_horizon'])
for x in d['missed_query_details']:
    if x['native_deficit']:
        print('q',x['query_id'],'strict misses=',x['strict_misses'],
              'native deficit=',x['native_deficit'],
              'tie credits=',x['tie_credits'],
              'categories=',[m['category'] for m in x['misses']])
PY
```

## Các kiểm tra và ý nghĩa chính xác

- Khóa SHA R26a `.graph` = `d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef` và R45 query ID sample SHA thông qua report; không chấp nhận dữ liệu thiếu parity.
- Mỗi query trace có 5 cặp `SEARCH`/`EVAL` đồng nhất. Recompute `strict_hits`, `native_tie_hits`, native deficit, `tie_credits` từ returned IDs và native tie-eligible GT set. So khớp với summary và category R45.
- `queries_strict_miss_but_native_full`: một hoặc nhiều GT rank1–10 vắng mặt nhưng 10 trả về đều thuộc native tie-eligible set; không là một truy vấn lỗi native theo độ đo này.
- `queries_native_miss`: có ít nhất một returned ID ngoài tập tie-eligible. `native_deficit` là **số ô kết quả** không được native GT công nhận, không phải danh sách GT-ID bị miss xác định duy nhất khi có ties.
- `strict_missing_categories_within_queries_that_still_fail_native`: category của các GT nghiêm ngặt bị miss **trong query native-failing**, chứ không phải ánh xạ 1-1 tới native missing slots.
- `adjacent_to_unexpanded_final_frontier`: trong graph có cạnh từ node còn trong frontier cuối, chưa expanded, tới GT strict-miss; có thể cho thấy giới hạn mở rộng, nhưng **không chứng minh GT sẽ được thăm nếu tăng Q**.
- `graph_twohop_from_expanded`: GT strict-miss nằm trong tối đa 2 cạnh có hướng xuất phát từ một đỉnh thực sự đã expanded. Không chứng minh đường đó sẽ được beam search thực hiện. Không đánh giá Recall/QPS hay BUILD mới.

## Quyết định

R46 là phép phân loại *hậu kiểm* với dữ liệu R45 đã có, không sinh thuật toán. Chỉ khi phân loại theo **query native-failing** cho thấy cơ chế lỗi cụ thể lặp lại, mới cân nhắc instrumentation sâu hơn để phân biệt seen/cutoff/beam eviction trên chính các query lỗi. Không mở H33 nếu chỉ có các tỷ lệ mô tả.
