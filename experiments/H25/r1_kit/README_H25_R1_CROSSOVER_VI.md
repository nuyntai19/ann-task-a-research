# H25-R1 crossover — kiểm tra sai lệch do thứ tự chạy

## Mục đích
Sau H25-R1 10.000 queries, Nearest có QPS cao hơn baseline tại 8/8 giá trị ef. Nhưng thứ tự đo luôn Baseline -> Nearest -> Random. Bộ này chỉ kiểm tra **timing repeatability** trên đúng ba graph có sẵn, không xây graph mới, không thực hiện chính sách backfill và không chứng minh novelty hay BUILD speedup.

## Cài và chạy
Giải nén 2 file `.sh`, `.py` cùng thư mục `~/ann-task-a/experiments/H25/r1_kit/` (script mặc định tìm file tại đây); không ghi đè H25-R1 artifacts.

```bash
cd ~/ann-task-a/experiments/H25/r1_kit
unzip -o ~/Downloads/H25_R1_CROSSOVER_GATE.zip -d .
bash h25_r1_crossover_10k.sh
```

## Thiết kế
Ba thứ tự Latin square:
1. Baseline, Nearest, Random
2. Nearest, Random, Baseline
3. Random, Baseline, Nearest

Với mỗi graph và mỗi vòng, đo `ef=140,160,180,200`, 10.000 truy vấn, 3 repetitions. Mỗi `CSV` một tên khác nhau. Script so SHA256 graph trước/sau, kiểm tra RECALL cố định cho từng graph, rồi xuất `crossover_summary.json` + `summary.txt` trong `r1_native_build_sift1m_seed42/crossover_YYYYMMDD_HHMMSS/`.

## Sau khi chạy
Gửi `summary.txt` và `crossover_summary.json`. Quan sát xem lợi thế Nearest vẫn dương qua cả ba vòng và khi thứ tự chạy thay đổi không.

## Giới hạn
Không kết luận tính mới thuật toán, không khẳng định equality về graph/index budget, không đại diện các BUILD độc lập, chưa có policy cost online. Random graph đã mất 1 vertex reachability trong BUILD hiện có. Kiểm chứng tiếp nếu QPS vững: đối chứng sham-build với cùng mã/cấu hình/partition, trace `distance evaluations`, và kiểm tra nhiều BUILD độc lập.
