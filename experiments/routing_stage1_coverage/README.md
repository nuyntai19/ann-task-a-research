# Giai đoạn 1 — Coverage-Aware Route32

Dùng lại graph Fixed và V2a trên ba seed 555–557. Bốn cách chọn 32 đỉnh dùng đúng cùng pool 100 root leader. So cả entry mặc định node 0. Greedy Facility Location giảm mean L2 tới leader gần nhất. Farthest-first bắt đầu từ medoid một tâm rồi tăng khoảng phủ. Bản k-medoids thử tối đa bốn hoán đổi sau greedy trên cùng hàm mục tiêu. Dùng mẫu base 8.192 điểm để chọn bộ đại diện.

Evaluator dùng kernel beam search gốc. QPS và thời gian query bao gồm định tuyến, khởi tạo entry và tìm kiếm. Tính Recall ngoài vùng đo thời gian. Distance là số phép tính khoảng cách do kernel báo cộng chi phí routing.

Chuẩn bị ground truth exact cho 1.024 query calibration và 3.072 query proxy giữ riêng, không trùng ID với mẫu chọn leader. Query proxy là vector base tham chiếu trực tiếp trong bộ nhớ và đối chiếu leave-one-out, loại self. Đây là kiểm tra trên mẫu query chưa tham gia fit, cùng phân bố base. Bộ query SIFT1M chuẩn 10.000 điểm có lịch sử sử dụng và được tách riêng trong báo cáo.

Các giai đoạn chạy theo thứ tự. Từ checkout thí nghiệm, compile bằng:

```bash
cmake -S ../adaptive_fanout_followup -B ../adaptive_fanout_followup/build -DPIPNN_BUILD_ROUTING_STAGES=ON -DR71_USE_H17=ON -DR86_USE_COUNTERS=OFF -DR70_USE_TIER=OFF
cmake --build ../adaptive_fanout_followup/build --target staged_route_eval staged_route_build --parallel 2
mkdir -p runs/sift1m_r2
taskset -c 0,2,4,6 python3 -B prepare.py ../adaptive_fanout_v1/data/sift_n1000000_q10000/base.fbin runs/sift1m_r2/data
taskset -c 0,2,4,6 python3 -B run.py --name sift1m_r2
```

Mỗi stage có thư mục run riêng. Manifest ghi SHA256 graph, dữ liệu, cấu hình và evaluator. CSV khảo sát và timing ghi theo beam, seed, query set và lượt đo. Quét beam theo lưới lưu trong manifest, chọn beam đầu tiên đạt ngưỡng theo từng graph/seed. Chạy warmup và ba lượt timing xen kẽ.
