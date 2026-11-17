# H32-R20b — Kiểm toán trực tiếp H19-R2.1 (không BUILD)

## Tại sao cần sửa R20?

R20 quét các tệp H17 trước, đạt ngưỡng `MAX_FILES=3000` rồi dừng trước khi kiểm tra hết H19/H26; vì vậy `MATCHES_H19=0` KHÔNG có nghĩa H19 không có log RAM. R20b không quét chung 3.000 tệp nữa: mở đúng 9 log ở `experiments/H19/phase2_perf_scaling/w{1,2,4}_rep{1,2,3}.log` và `summary.json` đã được ghi trong phụ lục H19 của Google Docs gốc.

Script chỉ đọc 10 file này (mỗi log tối đa 8 MiB); không sửa graph, không BUILD, không chạy ANN Search, không chạy PiPNN II. Nó chỉ công nhận số RSS nếu mỗi log có đúng **một** dòng thuộc định dạng rõ ràng như `Maximum resident set size (kbytes): 1849076` hoặc `VmHWM: 1849076 kB`. Các định dạng khác được lưu trong JSON để xem lại, không tự tính median.

## Lệnh Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H32/R20b_kit
cd ~/ann-task-a/experiments/H32/R20b_kit
unzip -o ~/Downloads/H32_R20b_targeted_H19_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r20b_targeted.py --mode selftest
python3 h32_r20b_targeted.py --mode audit --root ~/ann-task-a
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R20b_2* | head -n 1)
cat "$OUT/h32_r20b_summary.txt"
```

## Diễn giải

`STRICT_LOG_MEDIANS_ALL_MATCH_DOC=YES`: 9 file log nguồn đúng định dạng và 3 median RSS khớp các số H19 gốc đã ghi trong báo cáo. `NOT_VERIFIED`: chưa chứng minh nguồn hoặc định dạng không khớp; **không** được suy H19 RSS bằng 0. Không thể suy lịch sử RAM trống, swap/OOM, bandwidth, hay hiệu năng PiPNN II chỉ từ số đo này.

Tất cả tệp báo cáo nằm trong thư mục H32 mới có timestamp, không ghi đè bất kỳ tệp đã có.
