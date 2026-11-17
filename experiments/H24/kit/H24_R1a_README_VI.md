# H24-R1a — Phép thử can thiệp hàng cạnh LOW→HIGH (SIFT1M)

**Thời điểm:** 26/10/2026. **Trạng thái:** CHƯA CHẠY trên Ubuntu của bạn. Không phải thuật toán STH, không phải oracle tối ưu.

## Mục tiêu khoa học

Kiểm tra xem việc thay thế có chọn lọc **các hàng cạnh đi ra** của graph Dense LOW (`m=3`) bằng đúng hàng từ graph Dense HIGH (`m=5`) có cải thiện Recall–QPS khi chỉ thay 5% hoặc 10% số đỉnh không. Phép thử dùng toàn bộ graph ở H24-R0f và *chính xác bộ C++ search chung R0f*. Không rebuild LOW/HIGH/PiPNN; không cần chạy Graft mới. Không có graph-search harvest, predictor hay local repair thực tế.

Đối chứng ban đầu:
- **hindsight**: ưu tiên hàng chứa nhiều cạnh HIGH-only nhất (`HIGH[u] \\ LOW[u]`); yêu cầu phải biết graph HIGH hoàn chỉnh; đây chỉ là *hindsight structural prioritization*, không phải oracle tối ưu về recall và không khả thi như predictor giá rẻ trên LOW.
- **random**: chọn ngẫu nhiên số hàng bằng hệt, seed cố định 20261026.
- **degree_matched_random** (chỉ chế độ full): chọn ngẫu nhiên có khớp histogram out-degree LOW theo bốn bucket [0,8), [8,16), [16,32), [32,+∞) với tập hindsight cùng ngân sách.

Ở mỗi tỷ lệ p, **đúng p% hàng nguồn được thay**; không thay đổi các hàng khác. Cả hàng gốc LOW lẫn hàng thay HIGH được giữ nguyên thứ tự; một hàng mới có thể xóa cạnh LOW chứ không chỉ thêm cạnh HIGH. Như vậy, can thiệp không bắt buộc giữ tính đối xứng hoặc số bậc tối đa giống LOW; thống kê reachability từ entry=0 và zero-in-degree được xuất để phát hiện suy giảm topology. Số cạnh và graph bytes vẫn có thể thay đổi, chưa phải equal-degree benchmark.

## Dữ liệu/đường dẫn bắt buộc

- `~/ann-task-a/experiments/H24/r0f_common_search_sift1m_seed42/low.graph`, `high.graph`, `comparison.json` và `h24_r0f_common_search`.
- `~/ann-task-a/data/sift1m.fbin`, `sift1m_queries.fbin`.
- `~/ann-task-a/experiments/H24/r0f_common_search_sift1m_seed42/gold10.rawi32`, `entries_1.rawu32`, logs `search_low_entry1.log`, `search_high_entry1.log`.
- Các graph LOW/HIGH phải khớp SHA256 đã lưu ở `comparison.json`; nếu không chương trình dừng.

## Thực hiện

Tải `H24_R1a_row_transplant_kit.zip` vào `~/Downloads`, rồi chạy:

```bash
cd ~/ann-task-a/experiments/H24/kit
unzip -o ~/Downloads/H24_R1a_row_transplant_kit.zip -d .
source ~/ann-task-a/.venv/bin/activate
python3 h24_r1_transplant_gate.py --mode selftest
python3 h24_r1_transplant_gate.py --mode plan
```

Nếu `plan` PASS, chạy pilot (bốn graph lai: hindsight/random ở p=5/10):

```bash
python3 h24_r1_transplant_gate.py --mode run --phase pilot
```

Để xem lại kết quả mà không tạo graph hoặc BUILD:

```bash
python3 h24_r1_transplant_gate.py --mode inspect
cat ~/ann-task-a/experiments/H24/r1a_row_transplant_sift1m_seed42/report.json
```

Chỉ khi pilot hữu ích mới cân nhắc mở rộng 1%, 2%, 5%, 10%, ba selection policies (12 graph):

```bash
python3 h24_r1_transplant_gate.py --mode run --phase full
```

**Không chạy `--phase full` ngay.** Mỗi graph lai cỡ ~100 MB, chế độ pilot sinh ~400 MB, full có thể tốn >1,2 GB và nhiều lượt tìm kiếm độc lập. Chương trình yêu cầu tối thiểu 3 GiB RAM khả dụng và 3 GiB disk trống; dùng 1-thread evaluator, cùng ef=60/100/140/200/300 và 1.000 query × 2 lần đo. Mỗi lần được lưu dưới `experiments/H24/r1a_row_transplant_sift1m_seed42/`. Nó không ghi đè graph R0f hay kết quả trước. Các log dở dang sẽ dừng chứ không tự ghi đè.

## Chỉ số và ngưỡng quyết định

- `recovery_fraction(ef) = (Recall(mixed,ef) − Recall(LOW,ef)) / (Recall(HIGH,ef) − Recall(LOW,ef))`, chỉ ở ef có khoảng cách HIGH–LOW dương. Giá trị có thể âm hoặc >1; không phải xác suất.
- So sánh cùng ef cho kiểm tra effect, và xem curve threshold 99%, 99.5%, 99.8% khi đủ ef; quan trọng là QPS *tại Recall tương đương* chứ không phải cùng ef.
- Báo cáo directed edges/bytes, reachability từ entry0, zero-indegree, selected-row count, kết quả random controls.
- Nếu không có lợi ích thực tế hơn random hoặc chỉ đạt được bằng p lớn và graph phình, chính sách **hindsight này** không đáng mở rộng. Tuy nhiên, thất bại không bác bỏ mọi oracle chọn tập hàng tối ưu hay mọi STH khác; dữ liệu chỉ bác bỏ policy đã thử.
- Nếu có lợi ích ≥80% gap tại p≤10% ở các Recall mục tiêu, chỉ được phép nghiên cứu *cơ chế khả thi* với chi phí BUILD và predictor từ LOW; **không** tự nâng STH lên GO. Con số 80% là screening gate tự đăng ký, không là ngưỡng học thuật của paper.

## Vì sao R1a chưa thể chứng minh novelty và BUILD?

Một graph lai tạo *sau khi đã xây cả LOW và HIGH* không cho thời gian xây dựng nhanh hơn. Bản này kiểm tra tiềm năng can thiệp topology. Nó có thể **kém hơn** do mất reverse support hoặc thêm hub; không nên quy toàn bộ thiệt hại cho hard-tail. Tính mới hiện rất mong manh vì FastKCNA, Graft/FGraft, NGFix/RFix, PIGR và Three Composable Stages. STH vẫn **HOLD**; Dense LOW làm nền đã không thắng PiPNN về BUILD.

**Nên gửi lại cho tôi:** `report.json` và `comparison.json` gốc của R0f nếu cần xác minh. Google Docs gốc đã được cập nhật đến H24-R0f; R1a hiện vẫn PLANNED, chỉ ghi COMPLETED sau khi có số đo thật.
