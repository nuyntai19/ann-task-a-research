# H32-R14 — Kiểm toán paired-query từ H32-R13

## Mục tiêu

R13 đã tạo kết quả Top-10 từ **một chương trình C++ chẩn đoán độc lập** cho 10.000 query (Q=100, k=10) trên Vamana, PiPNN Stock và PiPNN H17 Top2. Dù ba Recall tổng hợp tái tạo đúng H31, số liệu tổng hợp không cho biết Stock và Top2 có cùng lỗi trên cùng query hay không.

R14 đọc các CSV dự đoán R13, file GT và ma trận reachable/unreachable R11 để trả lời:

1. Strict Recall@10 (chính xác theo 10 ID đầu của GT) khác source-style tie-aware Recall bao nhiêu?
2. Các query nào Stock trả lời đúng hơn Top2, và ngược lại?
3. Stock–Top2 trùng toàn bộ **tập** Top-10 hay chỉ cùng số lượng GT đúng? (Đồng thời đo trùng cả thứ tự.)
4. 12 GT@10 unreachable của Vamana nằm ở những query nào? Các graph còn lại phản ứng ra sao ở cùng query?
5. Các GT bị thiếu thường ở thứ hạng 1..10 nào? Đây là vị trí trong GT, **không phải thuật toán đã mở rộng những node nào**.

## Cách chạy trên Ubuntu

Tải `H32_R14_paired_query_audit_kit.zip` vào `~/Downloads` rồi chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H32/R14_kit
cd ~/ann-task-a/experiments/H32/R14_kit
unzip -o ~/Downloads/H32_R14_paired_query_audit_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r14_pairwise_audit.py --mode selftest
python3 h32_r14_pairwise_audit.py --mode audit --root ~/ann-task-a
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R14_2* | head -n 1)
cat "$OUT/h32_r14_summary.txt"
```

Nếu hiển thị `H32R14_FAIL_CLOSED=...`, dừng và gửi nguyên thông báo. Không cần tự sửa mã hoặc thay đổi graph.

## Các tệp tạo mới

- `h32_r14_summary.txt`: tổng hợp để gửi cho nhóm.
- `h32_r14_report.json`: số liệu đầy đủ và SHA256 các CSV dự đoán R13.
- `h32_r14_paired_query_matrix.csv`: bảng 10.000 query với strict/tie hits và khác biệt Stock–Top2, Vamana–Stock.
- `h32_r14_stock_top2_discordant_queries.csv`: query có bộ ID dự đoán khác nhau giữa Stock/Top2.
- `h32_r14_unreachable_cases.csv`: 12 query có Vamana GT@10 unreachable (theo R10/R11).

Tất cả ghi vào **thư mục H32_R14 mới**. Không đọc-ghi sửa bất kỳ graph, dữ liệu SIFT, mã nguồn ParlayANN, binary H31 hoặc kết quả H31–H32-R13.

## Điều kiện an toàn và giới hạn khoa học

- Đối chiếu SHA graph và Recall tổng hợp từ báo cáo R13; từ chối nếu số đếm strict/unreachable không khớp dữ liệu đã ghi nhận. Chỉ đọc CSV dự đoán đã có. Không chạy lại ANN Search.
- Phép so sánh là **paired descriptive analysis** trên bộ dữ liệu hiện có. Khác nhau của Top-10 IDs không chứng minh H17 có lợi ích chất lượng tìm kiếm; cùng Recall cũng không chứng minh output giống nhau.
- Vamana và PiPNN chưa được matched degree/index bytes/Recall nên không suy ưu thế topology nhân quả.
- R13 có aggregate parity H31, nhưng chưa có per-query binary parity của binary cũ.
- R11 BFS cho reachability từ entry 0, không phải trace đường ANN Search; GT chính xác chưa được tính lại độc lập.
- Strict GT@10 và tie-aware Recall phải được báo riêng; không trừ số miss của phép đo này cho phép đo kia.
- Để kết luận 'vì sao tìm kiếm rẽ nhầm, dừng sớm, bị beam prune' cần *expansion traces* có instrument xác nhận, không được suy từ paired-query CSV.
- H17 đã tối ưu Top-2 Scan (engineering), **chưa có đóng góp Parallel ANN mới được xác nhận**, không mở H33 chỉ từ H32-R14.

## Mức độ kiểm thử kit

Script được kiểm tra cú pháp Python và synthetic self-test. Chưa chạy với 3 graph SIFT1M thực tế trong môi trường của người tạo ZIP. Người chạy trên Ubuntu phải gửi lại summary thực tế.
