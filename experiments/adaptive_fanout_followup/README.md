# Adaptive fanout trên SIFT1M

Thử nghiệm kế tiếp của `adaptive_fanout_v1`. Builder và evaluator dùng snapshot cùng dependency đã pin của bộ chạy cục bộ. `run.py` đọc bộ SIFT1M đóng băng của V1 và xác minh SHA256 của base, query và ground truth. Graph dùng H17 Top-2, một lượt cây, cap 10/3/1, leaf 256, C160, R64 và alpha 1.1.

| Arm | Quy tắc tại depth 1 |
|---|---|
| Fixed | Giữ đủ ba leader |
| V1 | Giữ leader đến ngưỡng 1,15 lần khoảng cách L2 đến leader gần nhất |
| V2a | Giữ leader gần nhất và từng leader có `d_i - d_1` trong ngưỡng toàn cục |
| V2b | Chia margin cho thang khoảng cách ước lượng riêng của bucket trước khi so ngưỡng |
| V3 | Giữ số assignment như V2b. Khi giữ hai leader, cho phép đổi leader thứ hai sang thứ ba nếu vùng thành viên ít chồng lấp hơn và điểm vẫn đủ gần |

V2a và V2b được chọn ngưỡng một lần ở seed 555. Calibration đi qua top 3 leader, lấy hai margin bổ sung mỗi 127 điểm trong từng bucket, giữ nguyên fanout khi build probe. Ngưỡng lấy từ phân vị sao cho mức giảm assignment dự kiến xấp xỉ 9,04% ở depth 1 theo V1. Số Recall đo trong probe chỉ dùng xác thực đường chạy. Với V2b, thang là trung vị của khoảng cách tới mẫu gần thứ 8, từ 32 anchor và tối đa 1.024 reference trong bucket. Khi thang bằng 0, policy giữ toàn bộ cap. Thang này là proxy cho bucket và có thêm chi phí tính khoảng cách.

V3 lấy tối đa 4.096 điểm mỗi bucket. Hai tập được so sánh là nhóm điểm có leader gần nhất của điểm đang được gán trong top 3 và nhóm điểm có leader bổ sung trong top 3. Điểm Jaccard là kích thước giao chia kích thước hợp. Policy chỉ đổi nếu mỗi leader có ít nhất 8 lượt xuất hiện trong mẫu, overlap giảm ít nhất 0,05 và L2 tới leader thứ ba nằm trong cả hai giới hạn 1,15 lần leader thứ nhất và 1,05 lần leader thứ hai. Việc đổi leader giữ nguyên histogram fanout so với V2b trên cùng seed.

Các arm dùng 4 thread trên CPU 0,2,4,6 (bốn lõi vật lý của máy đo). Đây là so sánh khám phá trên SIFT1M và 10.000 query đã dùng ở V1. Mỗi graph chỉ build một lần trong mỗi run rồi search trên lưới beam. Bảng matched Recall dùng ngưỡng rời rạc và báo cả beam, Recall thực, số seed đạt ngưỡng.

Từ thư mục này, sau khi đã có dependency và dữ liệu V1, dùng một tên chiến dịch mới.

```bash
bash setup.sh
python3 -B sift1m.py v2a --name sift1m_fanout
python3 -B sift1m.py v2b --name sift1m_fanout
python3 -B sift1m.py v3 --name sift1m_fanout
python3 -B sift1m.py compare --name sift1m_fanout
python3 -B summarize.py --name sift1m_fanout
```

Mỗi stage lưu lệnh, hệ số và kết quả SIFT1M seed 555. Bước compare làm mới cả 5 arm trên 3 seed với cùng binary. Mỗi run giữ lệnh native, biến môi trường, hash, graph, log, CSV 10.000 query mỗi beam, RSS và latency. Xem `runs/<name>_comparison/REPORT.md` và CSV để đối chiếu.

Có thể tiếp tục bước compare bị gián đoạn bằng `python3 -B sift1m.py compare --name sift1m_fanout --resume`. Driver giữ các run đã có PASS và kiểm tra lịch chạy đã lưu. Report ghi riêng số đỉnh có thể tới từ node 0. Đây là số đo chất lượng graph, kể cả khi mọi query đã được search thành công.
