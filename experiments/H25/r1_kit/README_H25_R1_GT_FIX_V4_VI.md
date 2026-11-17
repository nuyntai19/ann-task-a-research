# H25-R1 — Sửa lỗi `GT shape invalid` và tiếp tục từ baseline (v4)

## Nguyên nhân

`h25_r1_common_search.cpp` cũ chỉ chấp nhận `sift1m_gt.ibin` dạng `[uint32 n][uint32 k][uint32 IDs (n*k)]`. File của nhóm là `[uint32 n][uint32 k][uint32 IDs (n*k)][float32 L2 distances (n*k)]`, tức 8.000.008 byte khi n=10.000, k=100. Lỗi nằm ở evaluator. **Không sửa GT, không BUILD lại PiPNN baseline.**

## Cài bản sửa — trên máy Ubuntu (terminal)

Tải `H25_R1_GT_FIX_v4.zip` vào `~/Downloads` rồi chạy:

```bash
cd ~/ann-task-a/experiments/H25/r1_kit
unzip -o ~/Downloads/H25_R1_GT_FIX_v4.zip -d .

g++ -std=c++17 -O3 -pthread h25_r1_common_search.cpp -o h25_r1_common_search
python3 h25_r1_test.py
```

Bước `h25_r1_test.py` sẽ biên dịch lại evaluator và kiểm tra trường hợp GT IDs-only tổng hợp. Bản sửa đã được kiểm thử riêng trên cả layout IDS-only và IDS+distances.

Trước khi chạy tiếp, **xác minh BUILD baseline trước đó**:

```bash
OUT=~/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42
ls -lh "$OUT/baseline.graph"
grep -E 'H25_R1_VERIFY:|H25_R1_VERIFY_PASS' "$OUT/baseline_build.log"
```

Kỳ vọng `checked_rows=20784/20784 applied_patches=0/0` và `H25_R1_VERIFY_PASS`.

Tiếp tục bằng công cụ mới (KHÔNG gọi lại script `h25_r1_run_native.sh` cũ):

```bash
cd ~/ann-task-a/experiments/H25/r1_kit
bash h25_r1_resume_after_gt_fix.sh
```

Script từ chối ghi đè, kiểm tra baseline graph/log, đúng PiPNN executable SHA và cấu hình cũ, kiểm tra kích thước GT trước khi BUILD thêm, rồi:

1. Chạy common SEARCH **baseline.graph sẵn có** (không BUILD lại).
2. Native BUILD + common SEARCH **nearest**.
3. Native BUILD + common SEARCH **random**.
4. Tạo `summary.json` và `final_edge_presence.json`.

Gửi báo cáo:

```bash
cat ~/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42/summary.json
cat ~/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42/final_edge_presence.json
```

## Lưu ý học thuật và an toàn

- Đây vẫn là **offline hindsight intervention** H25-R1. Chi phí `Top8`, quyết định bù ứng viên và đồng bộ khi triển khai online **chưa** được cộng vào BUILD. Vì vậy **không** dùng BUILD time trong kết quả để khẳng định thuật toán mới nhanh hơn.
- Kết quả chỉ dùng GT IDs thật của SIFT1M, không lấy mảng distances làm IDs.
- `h25_r1_test.py` kiểm tra synthetic. Việc compile C++ và self-test không có nghĩa R1 trên máy Ubuntu đã chạy xong.
- Script resume chỉ dành cho tình huống cụ thể: **baseline.graph và baseline_build.log đã tạo**, lỗi SEARCH xảy ra **trước nearest/random BUILD**, chưa có `baseline_eval.csv` hay `summary.json`. Nếu tình huống khác, script từ chối chạy để tránh ghi đè hoặc trộn kết quả.
- Bản sửa không động đến `pipnn.h`, `pipnn_utils.h`, hook hoặc tệp dữ liệu H18–H24.
