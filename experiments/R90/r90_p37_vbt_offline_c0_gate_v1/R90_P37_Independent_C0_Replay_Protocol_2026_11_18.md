# R90-P3.7 — Kiểm toán replay C0 độc lập (v1, 2026-11-18)

## Mục tiêu

Sau kiểm toán archive gốc và kiểm toán FP64 độc lập **128/128 anchor không lệch GT Top-10**, cần kiểm tra phần còn thiếu: các tử số `raw_hits` và `post_top2_hits` của 72 cấu hình. Không được đồng nhất `AUDIT_PASS` nội bộ của v1 với phép kiểm toán C0 độc lập.

## Nguồn khóa

- Bằng chứng người dùng tải lên: `R90_P37_EVIDENCE_v1.tar.gz`, SHA256 `43cc4bcf7bf7b6ad43f5967c160d98a38acd2183aa4dc57d768b37777cc5fec9`.
- Source tạo dữ liệu: `r90_p37_vbt_offline_c0_gate_v1.py`, SHA256 `7090021f62af082abe38fa3cca54492cc0afebf589caea57dc914532baabb4cf`.
- SIFT100K `.fbin` ở Ubuntu: SHA256 `e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12`.
- GT10 tại 2.000 anchor: SHA256 `2f838dab19b8e48006b97f5bc263f4d3b2a9ec2847b320e065300c1bae12a2b4`.

## Phương pháp

1. Xác minh đúng ba thành phần archive, SHA của dữ liệu, manifest, qids, exact Top-10 và 72 dòng CSV.
2. Import source gốc **chỉ sau khi xác minh SHA**, tái tạo sáu phân hoạch ứng với seed 555/556/557 × random/1%-k-means. So byte SHA `coarse_map` và `tile_map` với manifest. HOLD nếu khác.
3. Tái dựng ba chính sách nối ô tại `kb = 8,12,16,20` từ cùng phân hoạch. Mỗi chính sách tạo bộ cặp ô nối riêng.
4. Tính lại Raw C0 qua ma trận adjacency ô **bằng đường đếm khác** với `edge_id + np.isin` của v1.
5. Tính lại mask Top-2 hai chiều ở từng cặp (điểm, ô đích) theo L2 trực tiếp bằng hiệu tọa độ và `sum`, sắp thứ tự theo `(distance, ID)`. So cặp GT 20.000 cặp mỗi phân hoạch; nếu bất kỳ Post-Top2 count không khớp CSV, HOLD.
6. Đếm lại `within` và `cross` cells, số tile joins, chi phí gán coarse + đánh giá tâm cuối + huấn luyện; 72/72 dòng phải khớp chính xác CSV.
7. Nếu toàn bộ PASS: xuất `independent_c0_replay_audit.json` và **`independent_c0_replay_trace.npz`** chứa sáu `tile_map`, sáu Post-Top2 masks và 72 danh sách cạnh nối ô. Trace là bằng chứng cần tải lên cho vòng tái kiểm độc lập chỉ dựa trên mảng dữ liệu.

## Giới hạn khoa học

- Phân hoạch và chính sách nối ô được **tái dựng từ source v1 đã khóa**, không phải một thuật toán phân hoạch được viết hoàn toàn độc lập. Việc kiểm toán độc lập nằm ở đường tính C0, Top-2 và work-count từ phân hoạch đã tái dựng, có kiểm tra SHA với manifest.
- `post_top2_C0` là **mô phỏng FP32 trên các cặp ô**, không phải tập cạnh sau HashPrune/RobustPrune và không phải ANN query Recall.
- Kết quả đầy đủ của 72-arm chưa so được với **RBC N1/N2 trên cùng 2.000 anchor**, bao gồm cả độ phủ thô và hồ ứng viên Top-2 native. Vì thế, bất kể replay PASS, quyết định thuật toán vẫn là **HOLD**; chưa GO builder.
- Kiểm tra FP64 trước đó mới bao phủ 128/2.000 anchor. Không suy diễn thành 2.000/2.000.

## Cổng kết luận

- `R90_P37_C0_INDEPENDENT_72ARM_REPLAY_PASS 72` → độ tin cậy của phép đo C0 tăng rõ; tiếp tục đối chứng RBC đúng mẫu.
- `R90_P37_C0_REPLAY_HOLD ...` → không sửa CSV/manifest cũ; giữ log, kiểm tra nguyên nhân SHA/numeric/membership/work-count khác.
- Cần upload **`independent_c0_replay_trace.npz` và `independent_c0_replay_audit.json`** để kiểm toán riêng, không chỉ cung cấp SHA.
