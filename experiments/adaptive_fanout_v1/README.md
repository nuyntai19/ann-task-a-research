# Thử nghiệm fanout thích nghi, tách riêng khỏi runner cũ

Mọi source sửa đổi, build, dữ liệu đóng băng và kết quả của thử nghiệm nằm
trong `experiments/adaptive_fanout_v1/`. Lệnh cũ tại
`local_setup/khoa-linux/run.py` và binary cũ không bị thay đổi.

Đọc `RESEARCH.md` cho giả thuyết, công thức và tiêu chí kiểm tra. Kết quả thực
nghiệm sau khi chạy nằm trong `RESULTS.md` và report JSON của campaign.

## Build

Từ repository root:

```bash
bash experiments/adaptive_fanout_v1/setup.sh
```

Script dùng dependency đã pin trong `local_setup/khoa-linux/deps/` theo chế
độ offline, chỉ đọc source thư viện; build output nằm trong `build/` ở đây.
H17 ON, R86_COUNTERS OFF; telemetry nhẹ AF được bật cho cả fixed/adaptive.

## Chạy một cấu hình

Baseline fanout cố định, cùng pipeline và cùng seed:

```bash
python3 experiments/adaptive_fanout_v1/run.py \
  --rows 1000000 --queries 10000 --threads 4 --mode fixed \
  --seed 555 --run-name fixed_sift1m_r1
```

Fanout thích nghi theo từng điểm trong bucket, giữ root nguyên trạng:

```bash
python3 experiments/adaptive_fanout_v1/run.py \
  --rows 1000000 --queries 10000 --threads 4 --mode adaptive \
  --epsilon 0.03 --min-fanout 1 --min-depth 1 \
  --seed 555 --run-name adaptive_eps003_sift1m_r1
```

`epsilon` càng nhỏ thì cắt mạnh hơn; tăng nó tiến gần fanout cố định.
`--min-fanout 2` giữ ít nhất hai leader tại các tầng có cap>=2.
`--min-depth 1` giữ nguyên root; đặt 0 là một thử nghiệm khác với protocol chính.
`--beams 40,60,80,100,120,140,160,240` chọn beam search, không ảnh hưởng build.
Thay `--rows 10000 --queries 128` để chạy nhanh kiểm tra chức năng.

Tên sau `--run-name` là tên chính xác của thư mục dưới `runs/` trong thử
nghiệm, báo lỗi nếu đã tồn tại. Không dùng chung thư mục với runner cũ.

## Campaign đánh giá giả thuyết

```bash
python3 experiments/adaptive_fanout_v1/campaign.py \
  --rows 1000000 --queries 10000 --threads 4 --repeats 3 \
  --calibration-queries 1000 --run-name my_sift1m_campaign_r1
```

Campaign chạy pilot bảy cấu hình, chọn bằng calibration, đóng băng lựa chọn,
rồi xác nhận trên ba build seed và 9.000 query holdout. Mỗi arm chỉ build graph
một lần, search nhiều beam trên graph đó. Campaign có thể mất vài phút; log
in START_RUN/RUN_PASS, nguồn GT và đường dẫn report khi hoàn tất.

SIFT1M dùng GT có sẵn. Các prefix SIFT nhỏ hơn tính lại GT bằng float64 GEMM
theo block. Mọi arm dùng cùng dữ liệu đóng băng trong `data/` của thử nghiệm.

Pilot đầu chưa đạt điều kiện calibration ở beam80. Đã định trước một refinement
bảo thủ hơn trong `refinement_protocol.json` trước khi phân tích holdout adaptive:
epsilon .10/floor2, .15/floor1 hoặc2, .20/floor1 hoặc2. Dùng lại ba baseline
fixed đã đo, cùng binary/dataset/protocol, và chọn bằng calibration như cũ.

```bash
python3 experiments/adaptive_fanout_v1/refine.py \
  --rows 1000000 --queries 10000 --threads 4 --repeats 3 \
  --calibration-queries 1000 --baseline-prefix sift1m_lower_depth_v1 \
  --run-name my_refined_campaign_r1
```

Không dùng holdout để quyết định các ngưỡng refinement. Các lần xác nhận
adaptive refinement chạy sau baseline nên timing có thể chịu drift theo thời
gian; báo cáo giữ đây là giới hạn thay vì coi speedup là kết quả chắc chắn.

## File kết quả mỗi arm

- `index.graph`, `build.log`, `search.log`, `summary.json`: graph và số đo.
- `time.txt`: native build wall time và peak RSS, không tính GT/preparation.
- `adaptive_summary.json`: tổng công việc và phân bố theo độ sâu.
- `buckets.jsonl`: kích thước bucket, số leader, nominal/actual assignments,
  histogram fanout riêng từng bucket; có thể xem các cụm thích nghi khác nhau.
- `query_metrics.csv`: beam/query_id/latency_us/recall_at_10/hits_at_10.

Campaign lưu `protocol.json`, `selection.json`, `report.json` trong thư mục
campaign; các arm cùng prefix nằm cạnh nó. report chứa so sánh median, CI
Recall holdout và matched-recall trên lưới beam. Chỉ kết luận trong phạm vi
dataset/seed/tolerance đã thử; không có bảo đảm chất lượng cho mọi dữ liệu.

## Kiểm tra và bảo toàn bản cũ

```bash
g++ -std=c++17 -O2 -pthread -I experiments/adaptive_fanout_v1 \
  experiments/adaptive_fanout_v1/policy_test.cc -o /tmp/pipnn-af-policy-test
/tmp/pipnn-af-policy-test
python3 experiments/adaptive_fanout_v1/validate.py
```

`control_validation.json` ghi graph fixed mode trùng byte và work counters
khớp binary gốc trên bài kiểm tra một thread. `protected_originals.sha256.json`
ghi checksum source/config/binary cũ; runner kiểm tra chúng trước/sau.
`source_snapshot.sha256.json` và `source_changes.patch` ghi rõ phần sửa source.
