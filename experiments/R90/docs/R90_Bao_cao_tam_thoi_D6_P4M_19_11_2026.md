# BÁO CÁO THỰC NGHIỆM TẠM THỜI — R90 H17 + FAST V2

**Ngày:** 19/11/2026  
**Trạng thái:** Kết quả D6/P4M đã kiểm toán; R90-P4R đo lặp QPS mới được chuẩn bị, **chưa chạy native**.  
**Phạm vi:** PiPNN, Stage 2 Pick/ProcessLeafTop2, `MST_DEG=2`, đối chứng Stock → H17 → H17+Fast v2.

## 1. Mục tiêu và cơ chế

PiPNN xây dựng graph qua (1) Partition/Randomized Ball Carving, (2) tính ma trận khoảng cách trong leaf và chọn Top-2, (3) Merge/HashPrune + Final RobustPrune. Stock sử dụng `packFloatAndInt`, hàng đợi ứng viên và `VQPartialSort`. H17 thay bộ chọn bằng hai biến Top-2. Fast v2 giữ logic H17 nhưng kiểm tra ngưỡng FP32 của ứng viên trước khi cần Pack và so sánh packed 64-bit; trường hợp bằng ngưỡng đi vào đường xử lý chính để giữ tie-breaking.

**Phạm vi tối ưu:** Không thay thế thuật toán PiPNN, không cắt chi phí tính toàn bộ ma trận khoảng cách `dist_mat`, không rút ngắn danh sách cặp ứng viên cần đọc. H17 + Fast v2 không tự động được xác nhận là đóng góp thuật toán mới so với prior art, đặc biệt cần đối chiếu PiPNN II.

## 2. Đếm công việc thực nghiệm D6: SIFT10K → SIFT1M

Nguồn gốc: file `work_summary_1m.json` và `manifest_1m.json`, commit GitHub **`1dca8b14820f7f1d934255f16819376e4511924c`**, đối chiếu từng mục với tab `R90_D6_SCALING!A20:S29`.

| Counter Top-2 | SIFT10K | SIFT100K | SIFT1M |
|---|---:|---:|---:|
| `leaf_calls` | 991 | 16.664 | 180.064 |
| `leaf_point_visits` | 453.297 | 5.999.243 | 59.999.552 |
| `candidate_scans` (H17 và Fast giống nhau) | 274.608.788 | 2.972.620.700 | 28.123.433.514 |
| H17 `pack_calls` | 274.608.788 | 2.972.620.700 | 28.123.433.514 |
| Fast `pack_calls` | 5.955.297 | 77.482.551 | 756.889.237 |
| **Giảm Pack** | **97,831%** | **97,393%** | **97,309%** |
| H17 `value_comparisons` | 545.150.665 | 5.892.945.778 | 55.738.900.272 |
| Fast `value_comparisons` (FP32 check + packed) | 281.545.877 | 3.063.291.694 | 29.009.246.128 |
| **Giảm so sánh giá trị** | **48,354%** | **48,018%** | **47,955%** |
| H17 `first + second` assignments | 9.350.976 | 120.773.942 | 1.171.278.938 |
| Fast `first + second + cutoff` assignments | 15.305.953 | 198.250.814 | 1.924.687.745 |
| Gán cutoff bổ sung (Fast) | 5.954.977 | 77.476.872 | 753.408.807 |

- `first_assignments` và `second_assignments` giữa H17/Fast bằng nhau ở từng quy mô; tổng số gán Fast tăng đúng bằng số gán biến cutoff kiểu float.
- Ở SIFT1M, Fast tránh khoảng **27,37 tỷ** lần Pack và giảm ròng **26,73 tỷ** so sánh giá trị Top-2 theo đúng định nghĩa counter; không được đồng nhất các chỉ số này với FLOPs hoặc số lệnh máy toàn BUILD.
- Với ba quy mô, `candidate_scans` tăng khoảng **102,41×** khi `n` tăng 100×, hệ số khớp thực nghiệm `W(n) ∝ n^1,0052` **chỉ trong phạm vi Top-2 và tập dữ liệu/cấu hình đã đo**. Đây không phải chứng minh thời gian toàn PiPNN là `O(n)`.

## 3. BUILD 4 CPU và Search trên hai dataset

### SIFT1M

- BUILD 4 CPU (`0,2,4,6`): H17 trung bình **35,437 s**, Fast v2 **32,720 s** (nhanh hơn khoảng **7,665%**).
- Search D7, sáu graph (ba graph độc lập mỗi arm), 10.000 queries: H17 và Fast đều đạt quality floor 0,990 ở beam **76** và 0,998 ở beam **140**. Chênh QPS trung bình Fast/H17 **+0,311%** và **−0,234%** tương ứng.

### MS-Turing1M

C160/K1024/N2; ba graph BUILD độc lập/arm, bốn CPU khi BUILD, một CPU0 khi Search trên 100.000 public queries.

| Chỉ số | Stock | H17 | H17 + Fast v2 |
|---|---:|---:|---:|
| BUILD trung bình (s) | 42,051 | 36,478 | **33,797** |
| Peak RSS trung bình (MiB) | 3.052,70 | 3.057,37 | 3.048,83 |
| Tested-grid beam đạt Recall@10 ≥0,990 | 368 | 368 | **368** |
| Recall trung bình tại beam 368 | 0,990430 | 0,990424 | 0,990422 |
| QPS trung bình tại beam 368 | 1.269,48 | 1.273,39 | 1.267,92 |
| Tested-grid beam đạt Recall@10 ≥0,998 | 880 | 880 | **880** |
| Recall trung bình tại beam 880 | 0,998105 | 0,998082 | 0,998083 |
| QPS trung bình tại beam 880 | 571,05 | 570,53 | 570,25 |

Fast v2 giảm BUILD **7,351%** so với H17 và **19,630%** so với Stock trong thí nghiệm này. P4M v1.1 Full audit PASS: **9/9 graph** cùng vượt hai ngưỡng ở các beam **368/880** trên *lưới tám beam đã đo*. Mỗi graph mới đo **một lượt Search** trong P4M; QPS Fast so với H17 thấp hơn trung bình **0,429%** tại beam 368 và **0,050%** tại beam 880. Các tỷ lệ này **chưa đủ để suy ra suy giảm hệ thống hoặc equivalence thống kê**.

## 4. Phạm vi và giới hạn phải trình bày với thầy

1. `C160/K1024/N2`, `MST_DEG=2`, hai dataset quy mô 1M: chưa có kết quả tổng quát cho mọi loại vector, phân bố hay quy mô 100M–1B.
2. P4M cung cấp **quality floor trên lưới đã thử**, không phải beam tối thiểu toàn cục hay độ trễ đo trực tiếp tại Recall chính xác 0,990/0,998.
3. Độ trễ `1e6/QPS` chỉ là **throughput-equivalent proxy**, không phải latency p95/p99. Hiện chưa đo p95/p99.
4. `avg_cmps` của evaluator R86 v4 ở beam cao (bao gồm 880/896) **không hợp lệ do lỗi tràn 32-bit**. Không trích thành Search NDC; cần bộ đếm sửa 64-bit nếu muốn phân tích phần này.
5. Đối chứng Stock trên MS-Turing dùng ELF từ R86, H17/Fast dùng ELF R90: có **source/binary vintage confound**. Phép so sánh H17 → Fast đáng tin cậy hơn cho câu hỏi hiệu quả micro-kernel.
6. D6 đếm công việc chọn Top-2; **không** đếm đầy đủ SYRK/dist_mat, Partition/RBC, HashPrune, Merge hay FLOPs toàn BUILD. Giả thuyết khác biệt graph 4 CPU do scheduling/bfloat16 chưa được kiểm định nhân quả.
7. Kết quả đo hiệu năng không tự chứng minh tính mới. Cần taxonomy/prior-art so PiPNN II và các kỹ thuật early rejection, Top-K vectorized/fused trước khi tuyên bố đóng góp nghiên cứu mới.

## 5. Thí nghiệm còn mở R90-P4R

Đã chuẩn bị runner riêng `r90_p4r_mst1m_repeated_qps_v1.py`, SHA256 `581cb423039b44e414ffeee6240a93d27aa00b12a834ad7402f29727e1043b5c`.

- Chỉ đọc **chín graph MS-Turing1M đã khóa**, không BUILD mới.
- Mỗi graph chạy **ba lượt Search mới** trên 100.000 queries, hai beam 368/880: **27 evaluator calls, 54 beam observations** dự kiến.
- Đổi thứ tự beam theo vòng và xoay thứ tự arm để giảm lệch đo do thứ tự; lưu stdout/timefile SHA và nhận dạng graph/ELF/data.
- Kết quả dùng trung vị ba lượt Search **trong từng graph**, sau đó tổng hợp trên **ba graph**/arm. Không coi 27 processes là 27 graph độc lập; không tuyên bố formal noninferiority chỉ dựa vào trung vị.
- **Trạng thái hiện tại: runner syntax + synthetic selftest PASS, Ubuntu native PREFLIGHT/RUN/AUDIT chưa thực hiện.** Không có QPS mới để điền vào bảng.

## 6. Quyết định tạm thời

**Đóng D6 counter backfill: PASS.** Giữ P4M Full: PASS theo quality floor đã thử. **Tiếp tục R90-P4R native repeat Search: PENDING.** Chưa mở tối ưu mới cho tới khi kết quả QPS lặp được kiểm toán và phần prior art được cập nhật. Sau đó cân nhắc profiling/thuật toán để loại bỏ hoặc giảm chi phí *trước/tại* tính `dist_mat`, hoặc giảm Partition/HashPrune có đối chứng cơ chế.

### Nguồn kiểm toán

- [Google Sheets Metric Registry, R90_D6_SCALING và R90_P4M_FULL](https://docs.google.com/spreadsheets/d/12ApqgMV8YykflyFXUT2VMbUhgyiGirtoOmRWCXCz3Ek/edit)
- [D6 work_summary_1m.json](https://github.com/nuyntai19/ann-task-a-research/blob/1dca8b14820f7f1d934255f16819376e4511924c/experiments/R90/r90_d6_h17_fastv2_top2_exact_counters_v1/work_summary_1m.json)
- [D6 manifest_1m.json](https://github.com/nuyntai19/ann-task-a-research/blob/1dca8b14820f7f1d934255f16819376e4511924c/experiments/R90/r90_d6_h17_fastv2_top2_exact_counters_v1/manifest_1m.json)
- [P4M v1.1 Full manifest](https://github.com/nuyntai19/ann-task-a-research/blob/1dca8b14820f7f1d934255f16819376e4511924c/experiments/R90/r90_p4m_mst1m_matched_recall_100kq_v1_1/full_manifest.json)
- [P4M v1.1 Full summary](https://github.com/nuyntai19/ann-task-a-research/blob/1dca8b14820f7f1d934255f16819376e4511924c/experiments/R90/r90_p4m_mst1m_matched_recall_100kq_v1_1/full_matched_summary.json)
