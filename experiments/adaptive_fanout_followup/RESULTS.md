# Kết quả Adaptive Fanout trên SIFT1M

V2a, V2b và V3 đều đã chạy khi hoàn tất từng phiên bản. Sau ba lượt này, Fixed, V1 và ba bản mới được build lại bằng cùng binary trên ba seed và chạy 24 beam. Tất cả kết quả dùng SIFT1M với 10.000 query và 4 thread ghim lõi.

| Phiên bản | Build (s) | Proposals (triệu) | Cạnh cuối (triệu) | Recall@10 beam 80 | QPS tại ngưỡng 99,5% |
|---|---:|---:|---:|---:|---:|
| Fixed | 19,24 | 60,00 | 23,48 | 98,617% | 16.034 |
| V1 | 18,15 | 54,59 | 22,96 | 98,520% | 16.045 |
| V2a | 18,90 | 54,61 | 22,82 | 98,512% | 16.280 |
| V2b | 18,29 | 54,63 | 22,83 | 98,502% | 16.204 |
| V3 | 18,33 | 54,63 | 22,83 | 98,520% | 16.087 |

Trung vị trên ba seed. Cột cuối dùng beam nhỏ nhất trên lưới thử có Recall trung vị từ 99,5% trở lên. Cả năm arm được chọn tại beam 131. V2b đạt ngưỡng trên 2/3 seed ở beam này, bốn arm còn lại đạt trên 3/3 seed. Recall trung vị thực tế nằm trong 99,517–99,539%. QPS trung vị các arm chênh dưới 1,6% so với Fixed và số đo theo seed dao động, nên chưa xác nhận cải thiện QPS.

- **V1 so với Fixed.** Proposals giảm 9,02%. Build trung vị ngắn hơn 5,7% và đo được mức giảm trên cả ba cặp seed. Giai đoạn xử lý leaf giảm từ 7,44 s xuống 6,79 s theo trung vị. Fixed vẫn có Recall cao hơn cả bốn biến thể adaptive trên beam 40 và 80 theo trung vị. RSS của các biến thể chỉ thay đổi khoảng vài đến 16 MiB.
- **V2a so với V1.** Đổi sang margin L2 tuyệt đối giữ mức giảm proposals tương tự và tạo graph ít cạnh hơn. Ở beam 80 dùng 2.033 phép tính khoảng cách mỗi query so với 2.048 ở V1, nhưng Recall chênh ít và đổi chiều theo seed. Build trung vị dài hơn V1 0,75 s. Margin tuyệt đối dễ phân tích, còn hiệu quả tuyến tìm kiếm chưa tách rõ khỏi thay đổi về số cạnh.
- **V2b so với V2a.** Ước lượng bán kính theo bucket tốn thêm khoảng 3,27 triệu phép tính khoảng cách khi build. Ở beam 80, V2b dùng nhiều phép tính khoảng cách hơn V2a trên cả ba seed. Recall biến động từ −0,015 đến +0,002 điểm phần trăm. Thử nghiệm này chưa cho lý do ưu tiên thang theo bucket. Build wall time đo được thấp hơn V2a, nhưng đây là tổng thời gian của cả đường build và không cô lập chi phí riêng của phép chuẩn hóa.
- **V3 so với V2b.** Histogram fanout tại depth 1 giống hệt trên từng seed, với 19.115–20.810 lượt đổi sang leader thứ ba. Recall beam 80 tăng 0,009–0,027 điểm phần trăm trên ba seed. Ở beam 240, V3 đạt ít nhất 99,9% trên 3/3 seed, V1 đạt trên 2/3, Fixed/V2a/V2b mỗi bản đạt trên 1/3. Hai seed của V3 chỉ vừa đạt 99,900%, và 240 là beam cuối của lưới. Tín hiệu đáng theo dõi nằm ở Recall cao. Số đỉnh mở rộng ở beam 80 vẫn xấp xỉ V2b, và QPS tại Recall 99,5% chưa cải thiện rõ.

Nếu ưu tiên giảm thời gian build, V1 là đối chứng adaptive thực dụng nhất cho vòng sau. Nếu ưu tiên cải thiện search, giữ V3 làm nhánh nghiên cứu. Đo một mẫu các lượt V3 đổi leader để kiểm tra chúng có sinh proposal mới, cạnh còn sau pruning và đường tìm kiếm có tiến gần query sớm hơn hay không. Có thể nâng beam tối đa và đo lặp xen kẽ ở vùng Recall 99,9% để kiểm tra tín hiệu đuôi. Dùng thêm query hoặc dataset độc lập khi xác nhận vì bộ query SIFT1M hiện tại từng được dùng trong V1.

Fixed seed 556 search đủ query, nhưng từ node 0 chỉ tới được 999.999 đỉnh. Driver ban đầu dừng ở điều kiện kết nối toàn bộ. Campaign tiếp tục từ 10 kết quả đã hoàn tất và ghi số đỉnh ngoài tầm như một chỉ số của graph. 15 run dùng cùng hash dữ liệu, builder và evaluator. Kiểm tra SIFT10K một luồng xác nhận Fixed và V1 trùng SHA256 graph và các work counter so với bản lưu trước.

- [Bảng đầy đủ theo ngưỡng Recall và beam](runs/sift1m_fanout_comparison/REPORT.md)
- [So sánh theo seed và beam](runs/sift1m_fanout_comparison/paired_same_beam.csv)
- [Kết quả chạy ngay sau từng phiên bản](runs/sift1m_fanout_comparison/stages.csv)
- [Lệnh của 15 lượt so sánh](runs/sift1m_fanout_comparison/commands.sh)
- [Kiểm tra campaign](runs/sift1m_fanout_comparison/validation.json) và [kiểm tra tương thích](runs/sift1m_fanout_comparison/compatibility.json)
