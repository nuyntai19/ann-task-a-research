# H31-R0b — Sửa kiểm toán ground truth SIFT1M (KHÔNG sửa file GT)

## Lỗi của H31-R0

`H31-R0` cũ tính độ dài `.ibin` là `8 + n*k*4`. Điều này thiếu mảng khoảng cách Float32.
Trong `cmuparlay/ParlayANN@a48c6a3`, `algorithms/utils/types.h`, cấu trúc `groundTruth<uint>` có format little-endian:

- Header: `uint32 n`, `uint32 k` (8 bytes).
- Block 1: `uint32 ids[n*k]` (4*n*k bytes).
- Block 2: `float distances[n*k]` (4*n*k bytes).

Do đó SIFT1M query GT `(n=10000,k=100)` có **8,000,008 bytes**, đúng file người dùng báo cáo. **KHÔNG chuyển đổi sang int64, KHÔNG cắt 4 MB cuối, KHÔNG ghi đè GT.**

## Lệnh Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H31/R0B_kit
cd ~/ann-task-a/experiments/H31/R0B_kit
unzip -o ~/Downloads/H31_R0B_gt_layout_fix_kit.zip -d .
python3 h31_r0b_verify_gt.py --mode selftest
python3 h31_r0b_verify_gt.py --mode run
OUT=$(ls -td ~/ann-task-a/experiments/H31/H31_R0B_2* | head -n 1)
cat "$OUT/h31_r0b_summary.txt"
```

Nếu H31-R0 trước nằm ở thư mục khác, truyền `--inventory /path/h31_r0_inventory.json`.

**Không đọc toàn bộ graph lần nữa**: kiểm tra header và size base/query, full ID range + all finite distances trong GT (8 MB), SHA256 file GT, và đối chiếu SHA Vamana đã ghi trong old H31 inventory. Không chạy tìm kiếm, build, không sửa source.

## Giới hạn

`STRUCTURE_AND_FULL_ID_DISTANCE_VALUE_PASS` chỉ là xác nhận cấu trúc và miền giá trị của GT, chưa independently recompute exact kNN trên SIFT1M. Mã gốc ParlayANN dùng `groundTruth<uint>` với mảng IDs và khoảng cách tách block. Giữ H31-R0 original report nguyên trạng để audit, nhưng xem trường `DATASET_STATUS` của báo cáo cũ là **false negative của validator** khi R0b xác nhận PASS.
