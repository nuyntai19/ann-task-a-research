# Nhật ký thử nghiệm adaptive fanout — 2026-11-18

Mọi thay đổi nằm trong thư mục này. Không sửa source R86 gốc, runner cục bộ
đang dùng, binary cũ hoặc các thư mục kết quả cũ.

## Source thuật toán

`source/` là snapshot cây `experiments/R86/r86_v1_2_source/`. Hai file được sửa:

- `algorithms/PipNN/pipnn_utils.h`: nhận depth ở assign_leaders; chọn fanout
  theo ngưỡng tỷ lệ khoảng cách; compact in-place các assignment giữ lại;
  ghi histogram và đếm directed proposals thực sự sinh ra tại leaf.
- `algorithms/PipNN/pipnn.h`: truyền depth, ghi W_A theo số assignment thực,
  đặt seed được khai báo, ghi leaf workload, mức đầy reservoir và dump telemetry.

`source_changes.patch` chứa chính xác khác biệt với source gốc.
`adaptive_fanout.h` chứa policy/config và telemetry mới.

## Build và evaluator

- `CMakeLists.txt`, `setup.sh`: build riêng, dùng source snapshot và dependency
  đã pin chỉ đọc. H17 ON, R86 counters OFF cho các phép đo này.
- Snapshot `evaluate.cc`, `instrument_latency.py`, `latency_probe.h` bổ sung
  per-query hit/Recall và BFS reachable count; search algorithm không thay đổi.
- File generated headers và object/static libs nằm trong `build/` ở đây.

## Script và dữ liệu

- `ground_truth.py`: snapshot helper đọc/kiểm chứng GT có sẵn.
- `run.py`: chuẩn bị dữ liệu đóng băng một lần, build/search từng arm, quản lý
  seed/policy, đo native wall/RSS, audit graph và thu per-query metrics.
- `campaign.py`: calibration bảy arm rồi xác nhận lựa chọn theo protocol.
- `refine.py`: refinement năm arm được ghi trước khi xem adaptive holdout,
  tái sử dụng baseline cùng source/binary/dataset/seed.
- `protocol_versions/campaign_initial_v1.py`: bản driver trước khi tách hàm
  báo cáo chung để dùng cho refinement; logic thống kê được giữ nguyên.
- Sau khi campaign hoàn tất, CLI validation được siết chặt cho tên run,
  danh sách beam, split và giá trị số. Việc này không đổi phép đo đã chạy.

## Kiểm tra và kết quả

- `policy_test.cc`: ngưỡng squared L2, floor, ties/zero, monotonicity.
- `control_validation.json`: fixed graph byte-identical với binary gốc ở
  smoke một thread; counters proposals/W_A/W_L khớp.
- `validate.py`, `validation.json`: audit20 run, bucket histograms, graph,
  per-query Recall và232 checksum của workflow cũ.
- `RESEARCH.md`, `refinement_protocol.json`: giả thuyết và tiêu chí quyết định.
- `RESULTS.md`, `case_results.csv`: kết quả và giới hạn kết luận.
- `runs/`, `data/`, `logs/`, `build/` chứa artifact cục bộ, được Git ignore
  nhưng vẫn giữ trên ổ đĩa máy này. Không xóa kết quả benchmark cũ.

Kết quả hiện tại không đạt tiêu chí giữ chất lượng trên mọi beam, nên không
promote adaptive thành mặc định. Runner cũ tiếp tục là control.

## So sánh hai graph người dùng đã chạy

- `compare_saved.py`: đọc graph fixed `sift1m_h17_on_q10000_t4_r2` và adaptive
  `af_eps015_sift1m_r1`, kiểm tra dữ liệu khớp SHA256, tìm beam đạt cùng ngưỡng
  Recall, rồi đo search bằng cùng evaluator, 4 core vật lý và 6 lượt đổi thứ tự.
- `comparisons/user_af_eps015_vs_fixed_r2/`: báo cáo tiếng Việt `comparison.md`,
  CSV, protocol, từng lượt đo và kiểm tra checksum. Không build lại graph.
- Search chỉ đọc các graph cũ. 232 file workflow gốc và hai graph giữ nguyên
  checksum; toàn bộ artifact so sánh nằm trong thư mục thử nghiệm này.
