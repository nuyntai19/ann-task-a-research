# H32-R10 — Kiểm định GT Top-10 × Directed Reachability (Ubuntu, chỉ đọc)

**Mục tiêu khoa học**: Với ba graph SIFT1M đã khóa SHA256 của H31 (VAMANA / PiPNN STOCK / H17 TOP2), xác định bao nhiêu vị trí ground-truth Top-10 của 10.000 queries thuộc các node **không thể đi tới từ entry 0** qua cạnh có hướng.

**KHÔNG** xây lại graph, không chạy ANN Search, không sửa adjacency, không tải lên bất kỳ dữ liệu nào. Không có tuyên bố thuật toán mới hay so sánh equal-budget.

## Các lệnh chạy trên Ubuntu

1. Tải ZIP về `~/Downloads/H32_R10_reachability_gt_kit_v2.zip` (không cần thay vị trí dataset/graph).
2. Mở Terminal rồi chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H32/R10_kit
cd ~/ann-task-a/experiments/H32/R10_kit
unzip -o ~/Downloads/H32_R10_reachability_gt_kit_v2.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r10_reach_gt.py --mode selftest
python3 h32_r10_reach_gt.py --mode audit --root ~/ann-task-a
```

Sau khi có `H32R10_DONE=...`, đọc output đã tạo:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R10_2* | head -n 1)
cat "$OUT/h32_r10_summary.txt"
```

Gửi lại nội dung `h32_r10_summary.txt` (hoặc hai file summary/JSON nhỏ). **Không gửi** `.graph`, `.fbin`, `.ibin`.

Nếu hiện `H32R10_FAIL_CLOSED`, **dừng**, gửi nguyên thông báo lỗi để sửa vấn đề định dạng/nguồn; không đổi file nguồn, không bypass hash để chạy tiếp.

## Dữ liệu đầu vào cố định

- `data/sift1m.fbin` — header 1.000.000 × 128 float32 (512.000.008 byte)
- `data/sift1m_queries.fbin` — header 10.000 × 128 float32 (5.120.008 byte)
- `data/sift1m_gt.ibin` — `[uint32 n=10000, uint32 k=100] + toàn bộ IDs + toàn bộ distances` (8.000.008 byte)
- Ba graph: chính xác SHA256, kích thước và số cạnh đã ghi trong H31-R7/R8. Đường dẫn source cố định và đã được khóa trong script.
- H31 inventory: `experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json`.

## Đọc kết quả

`M_G` là số vị trí trong GT Top-10 trỏ tới node không reachable. Nếu chỉ đi từ entry0 qua cạnh có hướng (không teleport/fallback), `Recall@10 <= 1 - M_G/(10*10000)`. Đây là **trần cấu trúc**, không phải Recall thực tế, và không phải mức tăng Recall sau khi sửa graph.

Nếu `M_G=0`: bác bỏ giả thuyết **GT Top-10 unreachable là nguyên nhân** của miss trên 10.000 query này. Không mở H33 dựa trên orphan repair. Nếu `M_G>0`: chỉ có bằng chứng về floor, cần cân nhắc prior art NSG/FGIM, lỗi benchmark và equal-budget trước khi bàn sửa topology. Dù 205 node không reachable, chưa chắc có node nào trong GT@10.

**Giới hạn:** checksum chứng nhận khớp file graph đã khóa, không chứng minh dataset GT đã được tính lại bằng exact brute-force. Input SIFT1M không rời máy. Script mới là bản tái dựng v2 từ protocol H32-R10; checksum khác ZIP đã mô tả trong tài liệu nghiên cứu trước đó.
