# H32-R20 — Kiểm kê RAM đã đo và điều kiện so sánh PiPNN II

**Mục tiêu:** rà các log hiện có của H17/H19/H26, không build lại graph. Đối chiếu với số liệu lịch sử H19-R2/R2.1 trong Google Docs. Kiểm tra các thông tin RAM hiện tại (`/proc/meminfo`) nhưng **không coi MemAvailable hiện tại là RAM trống lịch sử trong các BUILD**.

## Thực hiện trên Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H32/R20_kit
cd ~/ann-task-a/experiments/H32/R20_kit
unzip -o ~/Downloads/H32_R20_memory_and_pipnn2_gate_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r20_gate.py --mode selftest
python3 h32_r20_gate.py --mode audit --root ~/ann-task-a
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R20_2* | head -n 1)
cat "$OUT/h32_r20_summary.txt"
```

## Kết quả được xuất

- `h32_r20_summary.txt`: số file và match, H19 RSS lịch sử đã ghi, tổng RAM tại thời điểm chạy, giới hạn diễn giải.
- `h32_r20_report.json`: các dòng text có từ khóa RSS, VmHWM, faults, swap; gồm tên file và số dòng để mở kiểm chứng; **chưa phải xác minh toàn bộ các giá trị đo**.

## Giới hạn khoa học

- H19-R2/R2.1 **đã ghi** median peak RSS 1T/2T/4T = 1.714.432 / 1.758.336 / 1.849.076 KiB trong các profiling builds. Không gán sang H26-P0.
- PiPNN II workshop và công bố tác giả nói về quantized/fused GEMM/TopK, trên máy chủ/ISA khác. Không chạy được chỉ nhờ thay Top2; phải có implementation và build flags của PiPNN II.
- Issue [DiskANN #1030](https://github.com/microsoft/DiskANN/issues/1030) đã đóng, maintainer comment rõ memory consumption của PiPNN nay ngang Vamana float32 build. Do đó không được tuyên bố đây vẫn là khoảng trống chưa ai xử lý.
- Không đọc, di chuyển hoặc hash graph lớn; không gọi compiler hay `make`; không chỉnh sửa dữ liệu gốc.
- Chỉ dùng dữ liệu kiểm kê này để quyết định có cần phép đo đối chứng được kiểm soát hay không. Khi chưa có binary PiPNN II tương đương, `PiPNN II build-time ratio = UNKNOWN`.
