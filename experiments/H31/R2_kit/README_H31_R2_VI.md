# H31-R2 — Controlled Common-Searcher Sweep (không BUILD)

Mục tiêu: đánh giá **Vamana, H26 Stock và H26 Top-2** trên cùng executable ParlayANN Vamana của người nghiên cứu, cùng **SIFT1M / 10.000 queries / GT top-100**, `k=10`, cùng tham số search `-Q`, 1 CPU lõi logic, 5 lượt lặp nội bộ mỗi tổ hợp graph×Q.

## Trước khi chạy

- H31-R0 graph schema/hash PASS; H31-R0b GT ID+distance PASS; H31-R1 directed BFS PASS.
- Đây là **SEARCH ONLY**: chỉ đọc graph và dataset; ghi log/JSON trong `~/ann-task-a/experiments/H31/H31_R2_<timestamp>`; không biên dịch, BUILD, đổi graph, chỉnh kernel hay dùng `sudo`.
- Đường dẫn binary mặc định `~/ann-task-a/src/ParlayANN/algorithms/vamana/neighbors` đúng theo báo cáo máy Ubuntu. Nếu binary ở chỗ khác, truyền `--binary /đường/dẫn/thật`.
- SHA256 của **từng graph** được so với H31-R0 trước khi chạy. `VAMANA`, `STOCK`, `TOP2` cùng được chọn từ manifest H31-R0, không đo một graph tên gần giống.
- `-Q` là beam width, không phải số lượng truy vấn; `-verbose` buộc ParlayANN in 5 dòng `search:` và kit lấy trung vị QPS của 5 lần.
- Chỉ dùng build binary pin a48c6a3 nếu có thể: script in git source HEAD và SHA256 binary; git HEAD khác nguồn mã pin sẽ cảnh báo (không ngăn, vì binary có thể là bản build độc lập).
- **Kích thước graph và số cạnh hiện chưa matched.** Đây là descriptive cross-graph comparison trên các graph hiện có, KHÔNG phải proof Pareto superiority. BFS hop/zero indegree không thay cho Recall–QPS.

## Lệnh Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H31/R2_kit
cd ~/ann-task-a/experiments/H31/R2_kit
unzip -o ~/Downloads/H31_R2_common_search_kit.zip -d .

python3 h31_r2_common_search.py --mode selftest
python3 h31_r2_common_search.py --mode preflight

# Thăm dò 3 beam widths trước: cùng searcher và 5 lần lặp/bộ.
python3 h31_r2_common_search.py --mode run --qs 100,120,160

# Sau khi thăm dò không lỗi, có thể mở rộng đường cong (là lượt chạy KHÁC).
# python3 h31_r2_common_search.py --mode run --qs 80,100,108,112,120,140,160,180,200
```

**Lấy báo cáo kết quả:**

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H31/H31_R2_2* | head -n 1)
cat "$OUT/h31_r2_summary.txt"
```

Nếu `H31R2_FAIL_CLOSED`, lấy log trong thư mục `H31_R2_...` (nếu đã tạo) và gửi lỗi. **Không chạy lại BUILD** để xử lý lỗi tìm kiếm. Nếu `preflight` không tìm thấy binary, kiểm tra bằng `find ~/ann-task-a/src/ParlayANN -type f -name neighbors -perm -111` rồi truyền `--binary` cho cả preflight và run.

## Điều bộ công cụ đo, và KHÔNG đo

- `Recall@10`, `QPS`, average visited/comparisons từ native ParlayANN `-verbose`, 5 lượt tìm kiếm trên graph không đổi và 10k queries, cùng CPU affinity `taskset -c 0` và `PARLAY_NUM_THREADS=1`.
- `-R 32 -L 64 -alpha 1.2` cùng `-Q` và `-k10`, `-file_type bin`, `-data_type float`, `-dist_func Euclidian`; `-quantize_bits` mặc định 0, không thay query code.
- Chuỗi Q đặt chẵn/lẻ đảo thứ tự role để giảm bớt nhiễu warmup; log đầy đủ cho từng Q×graph, `h31_r2_runs.json`, `h31_r2_results.json`, `h31_r2_summary.txt`.
- Không kiểm toán GT exact từ base/query; H31-R0b chỉ xác minh định dạng và phạm vi giá trị.
- Không đo BUILD, memory peak BUILD, intra-query parallelism, SCC, topology invariant, hoặc novelty. QPS same `-Q` **khác** QPS matched Recall; cần đánh giá đường cong gần cùng Recall với chênh budget để đưa kết luận thích hợp.

**Nguồn CLI:** `cmuparlay/ParlayANN` commit `a48c6a3`: `algorithms/bench/neighborsTime.C`, `algorithms/utils/check_nn_recall.h`, `algorithms/vamana/neighbors.h`.
