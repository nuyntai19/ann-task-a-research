# H32-R15 — Kiểm toán khác biệt cạnh của PiPNN Stock và H17 Top2 (29/10/2026)

## 1. Vì sao cần bước này?

H32-R14 trên 10.000 SIFT1M queries, Q=100, k=10, ghi nhận **10.000/10.000 query** có **đúng cùng thứ tự 10 ID dự đoán** giữa graph Stock và Top2. Hai graph vẫn có SHA256 khác nhau, 22.793.556 và 22.794.064 cạnh có hướng (+508 cạnh Top2). H32-R15 trả lời một câu hỏi giới hạn: *các cạnh khác nhau nằm ở bao nhiêu node, mức độ khác biệt bao nhiêu, và có thay đổi thứ tự hàng xóm hay không?*

Đây là **audit mô tả**, không khẳng định những khác biệt do tối ưu H17 tạo ra: cần BUILD seed, điều kiện cây/phân mảnh và trạng thái trung gian giống nhau để xác định nhân quả. Hai file Stock/Top2 thuộc H26-P0 và có thể chịu ảnh hưởng random seed hoặc nondeterministic construction. Không có bằng chứng về tính mới thuật toán.

## 2. Việc script sẽ làm

1. Xác minh H32-R14 JSON PASS, 10.000 query có cùng thứ tự dự đoán và SHA source graph từ H32-R13.
2. Xác minh hash SHA256 và định dạng graph đã khóa của H26 Stock/Top2.
3. So sánh *từng node* về bậc, thứ tự hàng xóm, đa tập cạnh có hướng (giữ được cạnh lặp nếu có), cạnh chung, chỉ-Stock, chỉ-Top2, Jaccard toàn graph.
4. Ghi ra tệp **mới** trong `~/ann-task-a/experiments/H32/H32_R15_<timestamp>/`, tuyệt đối không sửa graph gốc, code PiPNN, ParlayANN hoặc các bản H31–H32.

**Không có ANN Search, không có BUILD, không có sửa topology.** Dùng Python >=3.9 little-endian, thư viện chuẩn. Tập hai graph đọc khoảng 190 MB; script chạy quét theo node, có thể mất nhiều thời gian trên CPU laptop. Dung lượng tệp kết quả phụ thuộc số node khác nhau.

## 3. Chạy trên Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H32/R15_kit
cd ~/ann-task-a/experiments/H32/R15_kit
unzip -o ~/Downloads/H32_R15_stock_top2_edge_audit_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r15_edge_diff.py --mode selftest
python3 h32_r15_edge_diff.py --mode audit --root ~/ann-task-a
```

Sau khi chạy thành công:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R15_2* | head -n 1)
cat "$OUT/h32_r15_summary.txt"
```

Gửi lại **`h32_r15_summary.txt`**, không cần upload graph hoặc dataset SIFT1M. Nếu in `H32R15_FAIL_CLOSED`, gửi nguyên thông báo và chưa sửa file gốc.

## 4. Đọc đúng kết quả

- `NODES_SAME_ORDER`: hàng xóm y hệt và đúng thứ tự.
- `NODES_SAME_MULTISET_DIFF_ORDER`: cùng đa tập cạnh, khác thứ tự.
- `NODES_CHANGED_EDGE_MULTISET`: đa tập cạnh hướng khác nhau (tính cả multiplicity).
- `STOCK_ONLY_ARCS_MULTISET`, `TOP2_ONLY_ARCS_MULTISET`: cạnh chỉ xuất hiện ở một graph; **hiệu** của hai số phải là +508, nhưng từng số có thể lớn hơn 508 nhiều lần.
- `EDGE_MULTISET_JACCARD`: tỷ lệ cạnh chung / tổng hợp cạnh của hai graph, có xét cạnh lặp.
- `h32_r15_changed_vertices.csv`: danh sách node có thay đổi đa tập cạnh; không phải báo cáo lỗi.
- `h32_r15_arc_diff_samples.csv`: **mẫu 100** cung thay đổi, không phải danh sách đầy đủ.

**Giới hạn rất quan trọng:** 10.000 query có dự đoán trùng chỉ trong R13 (Q100, k10). Không chứng minh mọi query, Q khác, máy khác, index độc lập, hoặc mọi graph từ H17 đều cho kết quả trùng. Không chứng minh SEARCH nhanh hơn và không thay thế benchmark của PiPNN II năm 2026. Nếu R15 xác nhận graph khác nhưng đầu ra Q100 trùng, kết luận là *quality/output non-regression quan sát*, không phải topology mechanism mới.
