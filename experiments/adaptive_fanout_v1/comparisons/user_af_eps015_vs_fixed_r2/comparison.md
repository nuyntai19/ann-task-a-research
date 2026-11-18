# So sánh hai lần chạy của người dùng — 18/11/2026

Adaptive giảm công việc sinh cạnh nhưng chưa cho thấy lợi ích tốc độ search khi đạt cùng ngưỡng Recall@10. Đây là so sánh hai graph cụ thể, chưa phải kết luận cho mọi seed/dataset.

## Đối tượng và cách đo

- Fixed: `/home/khoa/research/PiPNN/ann-task-a-research/local_setup/khoa-linux/runs/sift1m_h17_on_q10000_t4_r2`.
- Adaptive: `/home/khoa/research/PiPNN/ann-task-a-research/experiments/adaptive_fanout_v1/runs/af_eps015_sift1m_r1`; epsilon=0.15, min-fanout=1, min-depth=1, seed=555.
- Cùng SIFT1M, toàn bộ 10.000 query, GT giống nhau từng byte (SHA256 trong protocol.json). Tham số build H17, R64, C160, alpha1.1, leaf256 và fanout cap10,3,1 khớp.
- Giữ hai graph đã có; chỉ chạy lại search bằng cùng evaluator, 4 thread, ghim vào 4 core vật lý 0,2,4,6. Một lượt warmup mỗi graph; 6 lượt đo mỗi graph, đổi thứ tự fixed/adaptive và thứ tự beam.
- Với mỗi ngưỡng Recall, tìm beam nguyên đạt ngưỡng trong các khoảng đã đo, kiểm tra beam liền trước chưa đạt. Recall không hoàn toàn đơn điệu (xem matched_beams.json), nên không tuyên bố beam nhỏ nhất trên toàn bộ miền. Không nội suy thời gian.
- Bảng bên dưới là trung vị 6 lượt của từng chỉ số. Latency là service time của một query, đơn vị microsecond; không gồm đợi trong scheduler hoặc I/O. QPS là thông lượng tổng 4 thread nên latency không bằng 1/QPS.
- Các số search được đo lại cùng phiên, không lấy QPS cũ buổi chiều so trực tiếp với QPS mới. Không build lại hoặc tính lại GT.

## Search tại cùng ngưỡng Recall

| Ngưỡng Recall@10 | Beam fixed / adaptive | Recall thực fixed / adaptive (%) | QPS fixed / adaptive | Mean latency fixed / adaptive (µs) |
|---|---|---|---|---|
| 95.0% | 41 / 43 | 95.098 / 95.177 | 37,284 / 36,248 | 107.2 / 110.2 |
| 98.0% | 67 / 70 | 98.004 / 98.041 | 24,973 / 24,877 | 160.1 / 160.6 |
| 99.0% | 93 / 96 | 99.028 / 99.002 | 19,158 / 18,699 | 208.4 / 213.6 |
| 99.5% | 125 / 131 | 99.504 / 99.505 | 14,842 / 13,683 | 269.2 / 291.7 |
| 99.7% | 152 / 158 | 99.701 / 99.700 | 12,522 / 11,533 | 319.0 / 345.8 |
| 99.9% | 232 / 236 | 99.900 / 99.902 | 8,736 / 8,678 | 457.8 / 460.0 |

Hai bên cùng đạt ngưỡng, nhưng Recall thực chênh nhẹ do beam là số nguyên. Ví dụ 99,5%: fixed 99,504%, adaptive 99,505%; 99,7%: fixed 99,701%, adaptive 99,700%.

## Dao động thời gian và latency đuôi

| Ngưỡng | Median thay đổi QPS trong từng cặp lượt (%) | P95 fixed / adaptive (µs) | P99 fixed / adaptive (µs) |
|---|---|---|---|
| 95.0% | -2.78% | 148.0 / 152.0 | 170.1 / 174.9 |
| 98.0% | -2.00% | 218.7 / 219.3 | 247.5 / 247.5 |
| 99.0% | -1.57% | 283.3 / 289.9 | 318.4 / 326.4 |
| 99.5% | -3.68% | 366.7 / 386.1 | 411.7 / 476.8 |
| 99.7% | -3.61% | 441.3 / 488.6 | 495.5 / 561.7 |
| 99.9% | -0.11% | 668.5 / 672.4 | 749.2 / 758.0 |

Thay đổi QPS trong bảng này là median của sáu tỷ lệ adaptive/fixed của cùng lượt, khác tỷ lệ hai median tổng hợp trong report.json. Cách ghép lượt giảm ảnh hưởng drift theo thời gian. QPS cả hai phía giảm khoảng 10% từ đầu đến cuối phiên; một lượt adaptive ở 99,5% có spike P99 ~3,3 ms. Vì vậy không quy toàn bộ chênh lệch median thời gian cho thuật toán; chưa có bằng chứng adaptive nhanh hơn. Khoảng min/max từng chỉ số được giữ trong report.json, sáu tỷ lệ trong paired_repeat_summary.json. Chưa thực hiện kiểm định ý nghĩa thống kê.

## Công việc build và graph

| Chỉ số | Fixed | Adaptive | Giảm |
|---|---|---|---|
| Cạnh ứng viên có hướng | 59,999,964 | 54,574,146 | 9.04% |
| Cạnh graph cuối | 23,475,273 | 22,956,179 | 2.21% |
| Tổng bình phương kích thước leaf (W_L) | 4,688,301,660 | 4,261,528,133 | 9.10% |

Log gốc ghi build fixed 20.12 s, adaptive 22.75 s. Hai builder bật instrumentation khác nhau (R86 counters ON ở fixed, OFF ở adaptive cộng AF telemetry), chạy khác thời điểm, nên chưa thể dùng hai thời gian này kết luận mức tăng/giảm tốc build. Giảm cạnh/công việc logic không đồng nghĩa giảm thời gian tương ứng. Giảm cạnh cuối không suy ra RAM giảm cùng tỷ lệ.

Kết quả phù hợp với việc bớt assignment làm giảm số cạnh ứng viên nhưng mất một phần chất lượng graph ở cùng beam; cần tăng beam để bù. Đây là cách diễn giải các số đo, chưa xác định nhân quả riêng cho từng thành phần. Nếu ưu tiên tốc độ search, hai graph này chưa cho lý do chọn adaptive thay fixed.

## Artifact và kiểm tra

- `protocol.json`: input/hash, affinity, evaluator và cách đo.
- `matched_recall.csv`, `report.json`: toàn bộ số tổng hợp; `paired_repeat_summary.json`: biến động theo cặp lượt.
- `matched_beams.json`: các beam đã thử và Recall; `measurement_commands.json`: lệnh và từng lượt; `raw/`: log và CSV 10.000 query mỗi beam.
- `validation.json`: 232 file workflow gốc giữ nguyên SHA256; hai graph giữ nguyên SHA256; dữ liệu hai run khớp.
- Driver ở `../../compare_saved.py`. Để chạy một phiên mới: `python3 experiments/adaptive_fanout_v1/compare_saved.py --name TEN_MOI`. Script từ chối ghi đè thư mục kết quả đã tồn tại.
