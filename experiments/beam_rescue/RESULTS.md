# Kết luận Beam-Rescue trên SIFT1M

Đã chạy Beam-Rescue, thay cạnh cùng ngân sách, đối chứng ngẫu nhiên và cluster routing. Đối chiếu lại cả năm graph cũ trong cùng phiên đo. Mốc chính là Recall@10 99%. Mốc phụ là 99,5%. Dữ liệu gồm 10.000 query, 4 thread, 3 seed và 3 lượt timing xen kẽ mỗi seed.

| Nhánh | Kết quả đạt | Giới hạn quan sát được |
|---|---|---|
| Fixed | Mốc ổn định để so graph và routing. Beam trung vị 95 tại 99%. | Chi phí xây/thăm cạnh cao hơn các hướng adaptive. |
| V1 | Build lịch sử nhanh nhất trong các bản fanout, trung vị 18,15 giây so với 19,24 của Fixed. | QPS ở 99% chưa có lợi thế ổn định qua các phiên. |
| V2a | Ở 99% dùng ít phép tính khoảng cách hơn Fixed. Là đối chứng trực tiếp của thay cạnh và routing. | Cần beam trung vị 96 so với 95 của Fixed trong lưới mới. |
| V2b | Giữ mức giảm proposals gần V2a. | Ước lượng bán kính thêm chi phí. Ở 99%, phép tính khoảng cách và visited nhiều hơn V2a trong phiên này. |
| V3 | Đổi chọn leader cùng histogram fanout với V2b. | Chưa giảm beam tại 99% so với V2a và chưa có lợi thế QPS nhất quán. |
| Beam-Rescue | 1.194/1.446 replay một cạnh tăng hit trên query tìm cạnh. Giữ đúng số cạnh ra từng đỉnh và toàn bộ reachability của V2a. | 0 hit tăng trên tập kiểm tra 512 query của từng seed. Giữ cùng beam ở hai mốc đánh giá. Thời gian refinement trung vị 4,88 giây. |
| Thay cạnh ngẫu nhiên | Đối chứng dùng đúng nguồn, slot và cạnh bị bỏ, cùng pool hai hop với nhóm độ dài gần nhau. | Cùng beam và Recall như V2a tại các mốc chính. Dao động QPS cùng cỡ với Beam-Rescue. |
| Fixed + route32 | Tại 99%, QPS tăng trên cả ba seed so với Fixed. Trung vị tỷ lệ theo cặp là +4,53%. Giảm 6 visited và 92 phép tính khoảng cách/query theo cặp, đã tính routing. | Ở 99,5%, mức tăng QPS thay đổi theo seed. Vẫn giữ chi phí build của Fixed. |
| V2a + route32 | QPS trung vị cao nhất tại 99% là 20.752 và mean latency thấp nhất là 192,2 µs. Trung vị QPS theo cặp cao hơn V2a 5,12%. Giảm 6 visited và 84 phép tính khoảng cách/query theo cặp, đã tính routing. | Một seed QPS giảm nhẹ ở 99%. Ở 99,5% chưa thấy lợi thế nhất quán trên cả ba seed. |
| V2a + route100 | Giảm số đỉnh mở rộng thêm so với route32. | Tốn thêm phép tính chọn leader. QPS trung vị ở 99% thấp hơn route32 trên V2a. |
| Beam-Rescue + route32 | Có cùng visited, distance và Recall với V2a + route32 ở hai mốc. | Phần thay cạnh chưa tạo thêm tín hiệu. QPS theo cặp thay đổi chiều giữa các seed. |

Trace tại beam 80 trên ba seed ghi 430 hit chỉ có ở beam 128 với Fixed và 490 với V2a, từ cùng 1.536 query base mỗi seed. Có witness cutoff, merge-drop và eviction ở cả hai graph. Một witness là một sự kiện trên đỉnh trung gian có cạnh tới target đang thiếu, vì vậy một target có thể có nhiều witness. Kết quả replay cho thấy có thể cứu ca cụ thể, nhưng batch 16/64/16 thay cạnh chưa chuyển thành lợi ích tìm kiếm ở query khác. Trên 10.000 query SIFT chuẩn, G2 và V2a có cùng số hit tại beam 80 và 96 trên cả ba seed. Tại beam 40, G2 mất ba hit ở seed 556 và bằng V2a ở hai seed kia.

Wall thử refinement khoảng 4,83–5,03 giây/graph gồm tải graph, phân tích và xuất hai arm. Cộng với thời gian build V2a lịch sử, ước lượng trial là 23,18–23,93 giây/graph. Đây là phép cộng của hai giai đoạn đo riêng. Chuẩn bị GT calibration exact mất 93,89 giây một lần cho cả dataset, đo riêng vì có thể dùng lại giữa các seed trên cùng base. Nếu phải chuẩn bị lại cho base mới, cần tính chi phí này trong ngân sách tương ứng. Chưa có trần build bằng số để kết luận đạt ràng buộc. Routing lấy lại leader đã chọn bởi builder và tính chi phí chọn entry trong thời gian search.

Ưu tiên xác nhận route32. Fixed + route32 có dấu hiệu lặp lại tốt nhất theo seed ở 99%. V2a + route32 có điểm vận hành trung vị tốt nhất trong nhóm đã đo và giữ cấu hình build V2a. Cần thêm tập query hoặc dataset để xác nhận ngoài benchmark SIFT1M đã dùng trước đây. Beam-Rescue nên dùng tiếp như công cụ chẩn đoán. Kết quả âm hiện tại giới hạn ở pool hai hop và quy tắc chọn batch đã thử.

- [Bảng đầy đủ ở 99% và 99,5%](runs/sift1m_rescue_r1/REPORT.md)
- [Số đo theo seed](runs/sift1m_rescue_r1/per_seed.csv) và [so sánh ghép lượt](runs/sift1m_rescue_r1/paired.csv)
- [Quét theo beam](runs/sift1m_rescue_r1/survey.csv) và [tổng hợp trace](runs/sift1m_rescue_r1/trace_summary.csv)
- [Chi phí refinement](runs/sift1m_rescue_r1/refinement.csv), [graph đã chốt và SHA256](runs/sift1m_rescue_r1/frozen_graphs.json), [lệnh đã chạy](runs/sift1m_rescue_r1/commands.sh)
