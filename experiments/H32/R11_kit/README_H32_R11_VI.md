# H32-R11 — Kiểm toán nguyên nhân thiếu GT (giai đoạn A, chỉ đọc)

Ngày giao bộ công cụ: 29/10/2026. Kế thừa H31-R0/R2/R2b, H32-R8 và **H32-R10 chạy thực tế trên Ubuntu**. Chương trình là bộ đánh giá khoa học, **không phải thuật toán ANN mới**.

## Mục tiêu, giả thuyết và giới hạn

H32-R10 xác nhận Vamana: 205 node unreachable từ entry 0, 12 vị trí GT@10 không reachable, 12 query bị ảnh hưởng; Stock/Top2: 1 node unreachable nhưng không có GT@10 unreachable. H31 Q100 Recall Vamana=0.983140, Stock=Top2=0.990870. R11-A tiếp tục mô tả: GT@10 nằm cách entry 0 bao nhiêu *hop* trên graph có hướng, indegree các GT ra sao, và xác định 12 query. BFS shortest-hop **không phải đường thuật toán ANN đã đi**, và indegree không chứng minh chất lượng search.

R11-B chỉ thực sự phân loại **per-query** nếu có file Top-10 native result IDs với binary/graph/config provenance. Các file `h31_r2_results.json`/`runs.json` thông thường chứa chỉ số tổng hợp; không được suy ra danh sách result IDs từ Recall và QPS. Nếu thiếu dữ liệu này, R11 ghi `PREDICTION_IDS=NOT_AVAILABLE_IN_CURRENT_INPUT` và `SEARCH_MISSES_NOT_CLASSIFIABLE`; đó là kết quả hợp lệ, không phải script bị lỗi.

**Cảnh báo entry:** R10/R11 chứng minh reachable từ đỉnh 0. Muốn áp trần cấu trúc làm *giới hạn của H31 native SEARCH*, phải xác nhận từ source/invocation rằng từng query thực sự bắt đầu tại đỉnh 0, chỉ đi theo cạnh có hướng, không thêm seed/fallback. Kit này **không độc lập xác minh** điểm đó. Không nói 12 vị trí chắc chắn là missed slots H31 nếu chưa xác nhận search-entry.

## Chạy trên Ubuntu, KHÔNG tạo BUILD hay ANN SEARCH mới

Tải `H32_R11_structural_triage_kit.zip` vào `~/Downloads` rồi chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H32/R11_kit
cd ~/ann-task-a/experiments/H32/R11_kit
unzip -o ~/Downloads/H32_R11_structural_triage_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r11_audit.py --mode selftest
python3 h32_r11_audit.py --mode audit --root ~/ann-task-a
```

Nếu hiển thị `H32R11_DONE`, xem báo cáo:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R11_2* | head -n 1)
cat "$OUT/h32_r11_summary.txt"
```

Gửi lại nội dung summary và (nếu muốn) hai file kết quả nhỏ `h32_r11_report.json`, `h32_r11_affected_queries.csv` để tiếp tục đánh giá. **Không cần gửi `.fbin`, `.ibin` hay `.graph`.** Nếu `H32R11_FAIL_CLOSED` hãy gửi đúng thông báo lỗi, không sửa file gốc hoặc bỏ kiểm tra SHA.

## Input đã khóa

- Ba graph SIFT1M tại đường dẫn H31/H26, SHA, bytes, số cạnh đúng như H32-R10.
- Dataset `sift1m.fbin`, `sift1m_queries.fbin` và GT `sift1m_gt.ibin` (header+size, *không tự tính lại exact GT*).
- H31 inventory `experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json`.
- **R10 report thực tế** `experiments/H32/H32_R10_20261029_145742_261037/h32_r10_report.json`; đóng vai trò checkpoint để R11 đối chiếu lại graph SHA, unreachable và M. Đường dẫn đã khóa theo log bạn cung cấp, không tự chọn lần chạy khác.

## Output và cách diễn giải

Chỉ tạo **thư mục kết quả mới** `experiments/H32/H32_R11_<timestamp>`, không ghi vào graph/dữ liệu/log cũ:

- `h32_r11_summary.txt`: PASS/FAIL và thống kê gọn theo graph.
- `h32_r11_report.json`: SHA, số GT unreachable, BFS hop histogram, degree information, giới hạn diễn giải.
- `h32_r11_affected_queries.csv`: đúng những query có GT@10 không thể đi tới từ entry 0 (dự kiến 12 dòng Vamana).
- `h32_r11_gt_query_matrix.csv`: 10.000 dòng/graph, thống kê reachable/hop/GT của từng query. Đây **không phải** actual native ANN search result.

Nếu H31 Q100 thực sự bắt đầu từ entry0 và chỉ đi theo cạnh có hướng, 12/1686 vị trí miss Vamana là bất khả truy cập; **1.674 vị trí còn lại có đường đi trên graph nhưng vẫn bị miss**. Tuy nhiên đây là phân rã *tổng số vị trí*, không xác định được cụ thể query/result ID nào bị lỡ, và không cho biết vì sao thuật toán không tới đó.

## Tùy chọn R11-B: có thật Top-10 result IDs theo query

Chỉ khi bạn đã xuất được **actual native result IDs** có provenance thì có thể chạy thêm:

```bash
python3 h32_r11_audit.py --mode audit --root ~/ann-task-a \
  --predictions /DUONG_DAN_TUYET_DOI/h31_q100_native_top10.jsonl
```

Không cần chạy bước này nếu chưa có file kết quả từng query; cũng **không tự tạo file giả** từ H31 aggregate logs. JSONL cần 1 dòng cho 1 query/role, với `role` (`VAMANA`/`STOCK`/`TOP2`), `query_index` (0..9999), `ids` (10 unique vector IDs), `graph_sha256`, `binary_sha256`, `Q` (=100), `k` (=10), `entry_id` (=0), `source` (mô tả đường dẫn log/binary). Công cụ yêu cầu đúng 10.000 query cho từng role đã có trong file, trừ khi chỉ rõ `--allow-partial` (dữ liệu thử); bản thân metadata khai báo không thay thế cho việc kiểm tra source/search invocation thật.

Nếu có file phù hợp, bộ công cụ sẽ sinh `h32_r11_verified_per_query_misses.csv` phân loại GT được tìm thấy, GT unreachable bị miss và GT reachable bị miss. **Ngay cả khi có query result IDs, vẫn phải cần per-node expansion trace hoặc ablation để kết luận miss là do beam pruning, stopping hay topology**.

## Điều kiện nghiên cứu tiếp theo

- Nếu các đặc trưng hop/indegree không tạo thành câu hỏi cụ thể có tính bác bỏ, không mở H33 và không sửa orphan.
- Nếu cần kiểm tra nguyên nhân miss, trước tiên phải kiểm toán search entry=0 và xác định cách xuất native per-query top-k, sau đó thiết kế trace nhỏ có giới hạn với graph SHA/Q/search policy cố định.
- Giữ tính công bằng khi so Vamana vs PiPNN: hiện graph bytes/edge budget khác nhau. Không tuyên bố novelty hoặc Pareto superiority từ số liệu hiện tại.
