# Kết quả thử nghiệm adaptive fanout v1

## Kết luận

**Khả thi về triển khai và giảm công việc, nhưng chưa đạt mục tiêu giảm cạnh
mà giữ nguyên chất lượng/đem lại lợi ích tốc độ ở protocol đã thử. Không thay
thế runner cũ.** Bản epsilon=.15/floor1 khá gần baseline ở beam>=100, nhưng
có Recall giảm ở beam thấp và không đạt kiểm định noninferiority đồng thời.

## Protocol

SIFT1M (1.000.000 base ×128), 10.000 queries, GT có sẵn; H17 ON, C160,
leaf256, R64, alpha1.1, cap fanout10,3,1. Root cố định; chỉ thích nghi từ
depth1. Cùng một experimental binary, R86 counters OFF. Ba seed555/556/557,
bốn thread. Calibration1.000 query đầu; holdout9.000 query còn lại.

Pilot thử bảy cấu hình, chưa cấu hình nào đạt tiêu chí calibration. Một
refinement bảo thủ gồm năm cấu hình được ghi trước khi phân tích holdout
adaptive, chỉ dùng calibration để chọn epsilon=.15/floor1. Tiêu chí giữ nguyên:
giảm >=5% proposals và mất Recall tuyệt đối không quá .002 tại các beam
80/100/120/140/160; holdout phải có bound một phía Bonferroni >=-.002.

## Median ba build seed: fixed so với epsilon=.15/floor1

Cột giảm: dương là adaptive ít hơn, âm là adaptive nhiều hơn/chậm hơn.

| Số đo | Fixed | Adaptive | Giảm so với fixed |
|---|---:|---:|---:|
| Native build (giây) | 19.63 | 20.55 | -4.69% |
| Peak RSS (GiB) | 2.625 | 2.608 | +0.66% |
| Directed proposals | 59,999,972 | 54,588,392 | +9.02% |
| Cạnh graph cuối | 23,475,264 | 22,959,812 | +2.20% |
| Tổng leaf_size² | 4,688,301,660 | 4,261,528,133 | +9.10% |

Đã giảm khoảng 9% ứng viên nhưng graph cuối chỉ giảm khoảng 2,2% cạnh.
C160 vẫn giữ nguyên và flat reserve theo cap, vì thế RAM chỉ giảm khoảng
0,66%. Median build tăng khoảng 4,69%, chưa cho thấy speedup. Baseline dùng
lại từ stage trước; timing refinement chịu khả năng drift CPU/OS và không
phải bằng chứng nhân quả về chậm/nhanh hơn.

## Recall@10 trên 9.000 query holdout

Recall là trung bình cả ba seed. Delta và CI có đơn vị điểm phần trăm.
CI95 paired bootstrap gồm resample build pairs và query IDs.

| Beam | Fixed | Adaptive .15/min1 | Delta pp | CI95 delta pp |
|---:|---:|---:|---:|---:|
| 40 | 95.0178% | 94.7059% | -0.3119 | [-0.4515, -0.1689] |
| 80 | 98.6263% | 98.5233% | -0.1030 | [-0.1833, -0.0211] |
| 100 | 99.1270% | 99.0978% | -0.0293 | [-0.0896, +0.0356] |
| 120 | 99.4141% | 99.4067% | -0.0074 | [-0.0700, +0.0519] |
| 140 | 99.6107% | 99.5981% | -0.0126 | [-0.0604, +0.0311] |
| 160 | 99.7311% | 99.7181% | -0.0130 | [-0.0489, +0.0222] |
| 240 | 99.9000% | 99.9052% | +0.0052 | [-0.0200, +0.0293] |

Beam80: lower bound một phía có hiệu chỉnh Bonferroni là
-0.201856 điểm phần trăm, thấp hơn ngưỡng
-0.20 đã đặt. Đây là **chưa đủ bằng chứng noninferiority trên toàn bộ beam
bảo vệ**, không phải chứng minh mức mất chất lượng thật luôn vượt 0.20.
Point estimate beam80 giảm khoảng .103pp; CI95 của delta không chứa zero.
Ở beam100, Recall 99.1270% ->99.0978%, giảm .0293pp; không được gọi là bằng nhau.

## Kết quả calibration các ngưỡng

Worst delta là beam tệ nhất trong 80/100/120/140/160; đây là phần calibration,
không dùng các số này như kết quả holdout độc lập. min1/2 là fanout tối thiểu.

| Epsilon L2 | Min fanout | Giảm proposals seed555 | Worst Recall delta pp | Đạt calibration |
|---:|---:|---:|---:|---|
| 0.00 | 1 | 66.66% | -4.5900 | False |
| 0.01 | 1 | 60.30% | -3.2700 | False |
| 0.03 | 1 | 47.29% | -1.8900 | False |
| 0.05 | 1 | 36.01% | -1.0800 | False |
| 0.10 | 1 | 17.71% | -0.3200 | False |
| 0.03 | 2 | 27.67% | -0.7000 | False |
| 0.10 | 2 | 11.40% | -0.3200 | False |
| 0.15 | 1 | 9.04% | -0.1800 | True |
| 0.15 | 2 | 5.91% | -0.1200 | True |
| 0.20 | 1 | 5.00% | -0.3500 | False |
| 0.20 | 2 | 3.26% | -0.2600 | False |

Cắt mạnh epsilon=.03/min1 giảm proposals khoảng47%, build pilot từ23.17
xuống13.82 giây, nhưng mất Recall nhiều hơn. Không thể kết luận speedup đó
bảo toàn chất lượng. Bản .10/min1 xác nhận ba seed giảm proposals17,65% và
median build11,00%, nhưng Recall beam80 giảm .2519pp và không đạt tiêu chí.

## Recall ít nhất .99 trên lưới beam

Fixed và .15/min1 đều đạt ít nhất .99 ở beam100. QPS median full batch là
19.965 so với18.787; mean service latency holdout201.82 so với222.32µs.
Đây là chọn beam trên lưới rời rạc, không nội suy để hai Recall chính xác bằng
nhau; timing không được đo trong môi trường CPU độc chiếm.

## Quan sát cơ chế

Ví dụ seed555: ở depth1, có10 triệu lượt điểm-bucket (mỗi điểm đã đi qua
10 root buckets). Fixed gán mỗi lượt vào3 leader. Với .15/min1:

- 941.235 lượt giữ1 leader;
- 830.439 lượt giữ2 leader;
- 8.228.326 lượt vẫn giữ3 leader.

Đó là lượt điểm trong bucket, không phải số điểm base phân biệt. Root vẫn
10 triệu assignment ở cả hai. Số phép tính khoảng cách ở chính depth1 vẫn
không giảm: phương pháp tính khoảng cách tới tất cả leader rồi mới cắt.
Lợi ích chủ yếu ở leaf/downstream và số cạnh ứng viên. Khả năng đi tới node
được đo riêng; thiếu cạnh cục bộ vẫn có thể làm Recall thấp dù graph reachable.

## Kiểm chứng và artifact

- Fixed mode một thread trùng SHA256 graph với binary gốc; proposals/W_A/W_L
  khớp counters gốc: `control_validation.json`.
- 20 case gồm18 build SIFT1M và2 smoke SIFT10K được audit trong `validation.json`.
- Checksum232 file source/config/binary cũ vẫn giữ nguyên.
- `case_results.csv`: số đo từng case.
- `runs/sift1m_lower_depth_v1/`: protocol/selection/report pilot và xác nhận.
- `runs/sift1m_lower_depth_refined_v1/`: protocol/selection/report refinement.
- Mỗi arm có graph, build/search log, per-query metrics, bucket histogram,
  telemetry và resource usage. Source diff ở `source_changes.patch`.

## Hướng tiếp theo

Có thể thử policy chỉ giảm khi margin giữa leader thứ nhất/thứ hai thật lớn,
giữ nguyên toàn bộ cap cho điểm mơ hồ; hoặc chuẩn hóa margin theo ước lượng
bán kính kNN/mật độ cục bộ. Cần thêm dataset, seed và split mới trước khi
khẳng định bảo toàn chất lượng. Các hướng này chưa được triển khai trong v1.

Nguồn heuristic tương tự: SPANN, NeurIPS2021, mục3.2.2 closure assignment:
https://proceedings.neurips.cc/paper_files/paper/2021/file/299dc35e747eb77177d9cea10a802da2-Paper.pdf
