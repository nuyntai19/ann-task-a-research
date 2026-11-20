R90 P0-B — G11 Counter64 trên 9 graph P4 (READ ONLY, NO BUILD)
Ngày: 2026-11-19

MỤC TIÊU
Đo avg_cmps 64-bit trên đúng chín graph MS-Turing1M Stock/H17/Fast × 3,
beams [368,880], 100K public queries, taskset CPU0. Đây là số phép tính
khoảng cách Search; KHÔNG đo thao tác BUILD và KHÔNG thay QPS P4R.

G11 previously verified parity on another graph A0 beam896:
Recall 0.99819499 unchanged, avg_visited 740 unchanged, avg_cmps diagnostic 31008
vs corrupted original near 2^32.

Script khóa binary diagnostic G11 SHA256 a98b8748b92787e6ccbf52556a8eef2c24bff4580c6275c9fa464dd82af4d3a4.
Đối chiếu original evaluator SHA, G11 stats/source, P4M summary SHA, cả 9 graph SHA
và SHA base/query/GT. Chạy stock r1 trước và bắt Recall ±5e-5 + avg_visited parity.
Chỉ khi pilot pass mới tiếp tục tám graph còn lại.

Native Ubuntu chưa chạy, local syntax + selftest giả lập PASS.

CHẠY CHÍNH
  bash "$HOME/Downloads/r90_p0b_counter64_p4nine_v1_Ubuntu_run.sh"

File cần gửi sau PASS:
  ~/ann-task-a/experiments/R90/r90_p0b_counter64_p4nine_v1/summary.json
  ~/ann-task-a/experiments/R90/r90_p0b_counter64_p4nine_v1/full_results.json
  ~/R90_P0B_COUNTER64_9GRAPH_100KQ_v1.log

Nếu HOLD: giữ nguyên thư mục/log, KHÔNG xóa và không thay artifact frozen.
Script giai đoạn run không tự resume; nếu HOLD giữa chừng cần kiểm toán receipt
trước khi thiết kế runner tiếp nối, không xóa kết quả đã tạo để bấm lại.
