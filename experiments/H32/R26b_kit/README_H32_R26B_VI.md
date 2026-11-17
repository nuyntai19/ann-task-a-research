# H32-R26b — Thí nghiệm thăm dò SIFT1M với cùng candidate pool và cùng native searcher

## Mục tiêu và phạm vi

Chỉ **một** graph FGraft được xây từ candidate pool PiPNN R26a đã xác minh. Phương án là `dense-prune=1` (prune, reverse, reprune), **không có spine**, `dense-C=160`, `harvest-cap=32`, `harvest-alpha=1.2`, 4 luồng vật lý. So sánh với graph **đúng cùng pool/seed** của R26a, không lấy graph H31 khác seed. Cả hai graph được tìm kiếm bằng **cùng binary ParlayANN**, 10.000 query, k=10, Q=80/100/120/160, mỗi Q có 5 vòng tìm kiếm nội bộ. Không phải benchmark PiPNN II.

## Hướng dẫn Ubuntu

Tải `H32_R26b_sift1m_paired_pilot_kit.zip` vào `~/Downloads` rồi chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H32/R26b_kit
cd ~/ann-task-a/experiments/H32/R26b_kit
unzip -o ~/Downloads/H32_R26b_sift1m_paired_pilot_kit.zip -d .
sha256sum -c SHA256SUMS.txt
bash h32_r26b_paired_pilot.sh
```

Tất cả chạy trong một `bash` con; không `source`. Khi gặp lỗi, Terminal cha vẫn mở. Log và kết quả nằm trong `~/ann-task-a/experiments/H32/H32_R26b_sift1m_<timestamp>`. Nếu lỗi, giữ nguyên thư mục và gửi 60–80 dòng cuối của log tương ứng. Không cần chạy lại R26a.

## Chuỗi kiểm chứng

1. Ghim hash binary FGraft, ParlayANN, PiPNN graph, PiPNN candidate pool; kiểm tra source SHA. Không thay source hay graph cũ.
2. Tạo NPY `sift_X`, `sift_Q`, `sift_GT100` từ bản `.fbin/.ibin` bằng NumPy memmap theo block. **GT chỉ dùng cho đánh giá**, không dùng để chọn cạnh trong FGraft.
3. Build duy nhất một graph FGraft từ cùng pool, không spine; ghi tệp graph và stdout/log tài nguyên (`/usr/bin/time -v`). **Tổng wall của FGraft còn chứa kiểm thử local completeness 800 base points và query benchmark của FGraft. Không được so sánh trực tiếp tổng wall này với BUILD PiPNN.**
4. Kiểm tra định dạng graph, vertex IDs, duplicate/self edges, arcs và graph-only bytes trên cả hai. **Cùng cap32 không bảo đảm cùng số cạnh/bytes**.
5. Chạy common native ParlayANN searcher: 1 worker/CPU0; Q=80,100,120,160, 5 lượt nội bộ cho mỗi graph/Q. Bóc ra Recall tie-aware theo native code, median QPS và average distance comparisons. Kết quả xuất `r26b_report.json` và `r26b_summary.txt`.

## Quy tắc diễn giải khoa học

- R26b là **feasibility/pilot**, một seed và một FG build. Nếu chênh lệch arcs lớn hơn 5%, không được gọi phương án nào thắng về chất lượng/hiệu năng; trước khi kết luận phải điều chỉnh cap theo **graph budget** bằng số cạnh, tránh dùng heldout Recall để tuning.
- Cùng Q ≠ cùng Recall. Cần so đường cong Recall–distance comparisons/latency ở Recall tương ứng; QPS đo trong các lượt cùng process, không phải confidence interval.
- Không có single-query p95 latency; QPS không đủ suy ra p95. Không có equal-budget build/peak-RSS comparison. Không tuyên bố PiPNN II baseline hoặc novelty.
- Paper Three Composable Stages đã có cơ chế pool + ending + reverse edges/spine; phép tái lập là prior-art study, không phải đề xuất thuật toán mới.

## Dừng và lỗi

Dừng nếu pin hash/input không đúng; NPY lỗi; FGraft process lỗi, đồ thị thiếu/hỏng; common native searcher không in đủ năm kết quả mỗi Q. **Không** tự nâng cấp thư viện, sửa thuật toán hoặc chạy lặp không có kiểm soát. Không xây lại PiPNN.
