# Beam-Rescue trên SIFT1M

Thử nghiệm dùng graph đã lưu của Fixed, V1, V2a, V2b và V3. Nó tạo hai graph từ V2a cho mỗi seed, một dùng các phép thay cạnh qua replay và một đối chứng ngẫu nhiên. Thử riêng entry point chọn từ 32 hoặc 100 root leader. Bản kết hợp dùng graph Beam-Rescue và 32 leader.

## Chạy lại

Từ thư mục `../adaptive_fanout_followup`:

```bash
cmake -S . -B build -DPIPNN_BUILD_BEAM_RESCUE=ON -DR70_USE_TIER=OFF -DR71_USE_H17=ON -DR86_USE_COUNTERS=OFF
cmake --build build --target beam_rescue_mine beam_rescue_eval --parallel 2
```

Từ thư mục này, đặt một tên chưa có:

```bash
python3 -B campaign.py --name sift1m_rescue_r2
python3 -B report.py runs/sift1m_rescue_r2
```

Cần ba graph seed 555–557 của mỗi arm từ `adaptive_fanout_followup` và dữ liệu SIFT1M đóng băng từ `adaptive_fanout_v1`. Lệnh dùng bốn CPU vật lý 0,2,4,6 của máy benchmark. `commands.sh` ghi argv và biến môi trường thực tế.

## Quy trình

- Chuẩn bị GT exact cho 1.536 điểm base được lấy mẫu bằng seed cố định. Loại self theo ID. 1.024 điểm dùng để tìm cạnh, 512 để kiểm tra và chọn kích thước batch. Các điểm ở cùng khoảng cách với láng giềng thứ 10 được tính là hit.
- Trace Fixed và V2a ở beam 64, 80, 96, 128. Trace đọc cùng thuật toán search, với kiểm tra top-10, danh sách visited và distance count khi bật/tắt sự kiện. Witness chỉ ra đỉnh bị loại có cạnh tới target đang thiếu. Một đỉnh có thể phát sinh nhiều sự kiện và witness chưa chứng minh duyệt qua đỉnh đó sẽ cứu target.
- Với lỗi beam 80 được tìm thấy ở beam 128, xem tối đa sáu phép thay mỗi query. Chọn đích hai hop, nằm trong nhóm gần nhất mà beam cao mở rộng và beam thấp chưa mở rộng. Lọc theo cutoff tại nguồn, bước tiến về query và giới hạn độ dài. Thay một cạnh có đường hai hop thay thế và giữ hai cạnh gần nhất. Xếp hạng các phép thay có hit tăng theo kết quả replay, số đỉnh và phép tính tiết kiệm. Chọn trong các tiền tố 16/64/256 theo hit, visited và distance trên tập kiểm tra. Mỗi nguồn chỉ thay một slot. Nếu các batch hòa điểm, giữ batch ít cạnh hơn. Pilot đánh giá batch hợp lệ có điểm tốt nhất, kể cả khi điểm bằng no-op.
- Đối chứng ngẫu nhiên giữ nguyên nguồn, slot và cạnh bị bỏ. Lấy ngẫu nhiên trong tối đa tám đích hai hop gần nhất về độ dài cạnh so với cạnh Beam-Rescue. Kiểm tra graph sau khi sửa giữ từng out-degree, chỉ đổi những slot đã ghi, không mất reachability từ node 0.
- Lấy lại đúng mẫu 100 root leader từ seed và phương pháp lấy mẫu của builder. Route32 lấy 32 vị trí cố định trải đều trên mẫu đó. Chọn top-1 theo L2. Tính toàn bộ chi phí chọn leader vào latency/QPS và số phép tính khoảng cách. Số phép tính khoảng cách vẫn dùng định nghĩa native, cộng phép tính routing.
- Chốt graph/hash trước khi dùng 10.000 query SIFT1M chuẩn. Bộ này đã xuất hiện trong benchmark trước. Khảo sát beam, sau đó đo lại ba lượt xen kẽ cho từng graph/seed ở beam nhỏ nhất trên lưới đạt 99% và 99,5%. So parity evaluator với lượt lưu trước tại các beam trùng. QPS là batch throughput 4 thread. Mean/P95 là thời gian xử lý query. Log trace không nằm trong vùng đo tốc độ.

Kết quả gồm patch manifest, graph sau khi thay cạnh, số đo query, trace/witness, lệnh, mã băm graph và báo cáo. Chi phí chuẩn bị calibration được đo riêng. Wall time refinement pilot gồm tải graph, trace, replay, kiểm tra và xuất cả graph thử lẫn đối chứng.
