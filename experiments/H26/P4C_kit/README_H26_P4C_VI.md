# H26-P4c — CPU/PMU Resource Audit (27/10/2026)

**Mục tiêu:** Tách khả năng *CPU/cache pressure* khỏi *scheduler starvation* và *mutex contention*, sau H26-P4a/P4b. P4a đạt leaf concurrency 3.96–3.98/4, load Gini rất thấp. P4b đo wait p50 0.030 µs ở 1T và 4T, wait>10 µs rất hiếm; CPU ratio ≈3.95/4, cho thấy graph mutex hiện không có bằng chứng là bottleneck chính. Bản thân `sample-wait-share≈31%` là chi phí timestamp/acquire cộng vào wait, **không phải thời gian BUILD mất vì tranh chấp lock**.

## Thiết kế

- Dùng **đúng binary H26-P0 Top2 đã biên dịch**, source `~/ann-task-a/experiments/H26/PiPNN-H26-src`; không patch mã, không thay đổi source/graph H25–H26.
- Dataset SIFT1M, pinned commit PiPNN `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`, `-num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12`; CPU set 0/0,2/0,2,4,6.
- Khác H26-P4b: không thêm instrumentation vào C++; dùng Linux `perf stat` lấy tổng counters toàn bộ process. Nếu không có perf, hardware PMU hoặc permission, dừng và xuất lỗi probe, **không sudo và không thay kernel sysctl**.
- Cấu hình thực nghiệm: 4T perf OFF → 4T perf ON → 2T perf ON → 1T perf ON → 4T perf ON → 4T perf OFF. Đây là **pilot**: 1T/2T có 1 run; 4T có 2 runs. Không có CI across BUILD seeds/datasets.
- Đo `task-clock`, `cycles`, `instructions`, và nếu có, `cache-misses/cache-references`, `branch-misses/branches`. IPC = instructions/cycles, cache MPKI = cache-misses ×1000 / instructions. Khi PMU không hỗ trợ cache events, giữ core event only; không giả lập cache counters.
- Quan trọng: counters **cho toàn process** gồm bucket clustering, leaf và prune, không phân tách đúng giai đoạn. `cache-misses` không đo trực tiếp DRAM bytes hay băng thông; IPC thấp không tự chứng minh memory-bound (vectorization, backend stalls, prefetch, clock scaling...). Counter multiplex/scaling (nếu perf phải chia lịch hardware) có thể làm sai lệch. Xem raw `.perf.csv`.
- `perf stat` có thể tác động hiệu năng, nên có hai control OFF trên *cùng binary*. Các khung đo P4c không có graph output, không kiểm Recall/topology/QPS.

## A — Cài kit (không cần biên dịch)

Tải ZIP bằng trình duyệt về `~/Downloads/H26_P4C_cpu_pmu_kit.zip`:

```bash
mkdir -p ~/ann-task-a/experiments/H26/P4C_kit
cd ~/ann-task-a/experiments/H26/P4C_kit
unzip -o ~/Downloads/H26_P4C_cpu_pmu_kit.zip -d .
python3 h26_p4c_selftest.py
```

Kết quả `H26P4C_SYNTHETIC_ANALYZER_PASS` chỉ là self-test parser, không phải đo BUILD.

## B — Probe quyền/counter **trước khi chạy BUILD**

```bash
bash h26_p4c_run.sh probe
```

Nếu xuất hiện `H26P4C_PROBE_DONE`, đủ điều kiện thử tiếp. Nếu xuất hiện `H26P4C_BLOCKED`, xuất `probe.log` và `probe_core.csv` trong thư mục output và gửi thông báo lỗi; không tự sửa `kernel.perf_event_paranoid` hay chạy sudo. Cài `perf` nếu chưa có phù hợp đúng Ubuntu/kernel qua gói hệ thống chuẩn, nhưng trước tiên gửi lỗi cụ thể.

## C — Chạy pilot

```bash
bash h26_p4c_run.sh run
```

Nếu có `H26P4C_DONE`, lấy báo cáo:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P4C_2* | head -n 1)
cat "$OUT/h26_p4c_summary.txt"
```

Nếu bị BLOCKED tại probe, lấy:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P4C_2* | head -n 1)
cat "$OUT/probe_status.txt"
cat "$OUT/probe.log"
cat "$OUT/probe_core.csv"
```

## Kết luận có thể và không thể rút ra

- **Nếu IPC hoặc cache-miss thay đổi đáng kể từ 1T→4T:** có cơ sở **tiếp tục** phase-local cache/PMU profiling, nhưng không khẳng định memory-bound.
- **Nếu không có PMU / counters bị virtualized/đồng hồ không ổn định:** P4c HOLD, không chế dữ liệu; dùng phương án khác để đo CPU/memory.
- **Nếu các chỉ số không có dấu hiệu bất thường:** giảm ưu tiên tối ưu CPU/cache implementation, có thể đóng nhánh P4 và quay lại candidate topology algorithm/paper novelty audit.
- Dù kết quả nào, chỉ profiling, **không phải** tốc độ BUILD tốt hơn, thuật toán mới, Pareto/frontier hay novelty chứng minh.
