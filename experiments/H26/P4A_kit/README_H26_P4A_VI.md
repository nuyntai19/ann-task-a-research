# H26-P4a — Parallel Leaf Execution Envelope (SIFT1M, PiPNN)

## Mục tiêu và phạm vi

Sau khi H26-P3b bị NO-GO so với H26-P0 Top-2, P4a đo **độ bao phủ và mất cân bằng tải ở cấp leaf** theo 1/2/4 threads. P4a **không đo DAG critical path/work-span thật** và **chưa đo thời gian chờ khóa** của LSHGraph. Các thời lượng trên mỗi worker là elapsed time (bao gồm chờ khóa và bị OS deschedule), KHÔNG phải CPU utilization. Mỗi event chỉ đo `eigen_knn` trong leaf: bắt đầu trước `eigen_build_distmat`, kết thúc sau candidate merge.

Công cụ tạo worktree độc lập `~/ann-task-a/experiments/H26/PiPNN-H26-P4A-src` từ commit **443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd**, chỉ chép bản `pipnn_utils.h` **H26-P0** đã instrumented (và giữ selection Top-2 của P0), sau đó thêm timeline recorder và sửa CMake out-of-tree dependency. Không thay H25, P0, P1/P2/P3. Không BUILD graph ra đĩa. Khác binary so với P0, nên so sánh thời gian trực tiếp xuyên binary chưa được khẳng định chính xác.

**Không đọc số liệu H26-P3b selftest giả lập như một BUILD thật.** P4a lấy các log chạy thực từ Ubuntu.

## A. Cài đặt

Tải `H26_P4A_parallel_trace_kit.zip` về `~/Downloads`, chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H26/P4A_kit
cd ~/ann-task-a/experiments/H26/P4A_kit
unzip -o ~/Downloads/H26_P4A_parallel_trace_kit.zip -d .
python3 h26_p4a_selftest.py
python3 h26_p4a_workspace.py --mode check
python3 h26_p4a_workspace.py --mode create
bash ~/ann-task-a/experiments/H26/configure_H26_P4A.sh
```

Tự dừng `H26P4A_FAIL_CLOSED` nếu cấu trúc mã P0/commit không khớp. Không chạy lại `--mode create` sau khi đã tạo thành công.

Kết thúc CMake phải có `Built target neighbors-pipnn_FLOAT_T_EUCLIDEAN`; warnings thư viện không đồng nghĩa error.

## B. Native profiling

Sau khi biên dịch:

```bash
cd ~/ann-task-a/experiments/H26/P4A_kit
bash h26_p4a_run.sh
```

Mặc định `H26P4A_SCOPE=full`:
- r1_4t_off: 4 worker, không ghi leaf CSV
- r1_4t_on: 4 worker, bật leaf CSV
- r1_2t_on: 2 worker, bật leaf CSV (**chỉ 1 lần**, chưa đủ replication cho scaling)
- r1_1t_on: 1 worker, bật leaf CSV (**chỉ 1 lần**, chưa đủ replication)
- r2_4t_on: 4 worker, bật leaf CSV
- r2_4t_off: 4 worker, không ghi leaf CSV

Trật tự 4-thread on/off đảo giữa hai vòng. Pin CPU tương ứng `0`, `0,2`, `0,2,4,6`, `PARLAY_NUM_THREADS=1/2/4`. Nếu chỉ muốn kiểm tra phần overhead 4 threads, chạy `H26P4A_SCOPE=quick bash h26_p4a_run.sh` (4 lượt 4t) trước. Mỗi run build toàn SIFT1M nhưng **không ghi graph**.

File log `r*_*.log` + `r*_*.csv` + `manifest.txt` xuất vào thư mục mới `H26_P4A_...` không ghi đè. Mỗi trace có 85.529 leaf events. Runner so sánh các counter 85.529 leaves, 29.995.085 rows và 59.990.170 proposals; nếu sai dừng ngay.

## C. Gửi kết quả

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P4A_2* | head -n 1)
cat "$OUT/h26_p4a_summary.txt"
```

Gửi TXT và, nếu có lỗi, 40 dòng cuối log của run lỗi. KHÔNG cần dán hàng chục nghìn dòng CSV.

## D. Cách diễn giải

- `leaf_envelope_span_s`: từ lúc leaf đầu tiên vào `eigen_knn` đến khi leaf cuối cùng ra; không bao gồm phân cụm, final prune, graph writing.
- `leaf_elapsed_sum_s`: tổng thời gian `eigen_knn` trên các leaf; bao gồm blocked/scheduler elapsed nên không phải CPU-work.
- `average_concurrent_leaf_calls = sum leaf elapsed / envelope`: số leaf có lệnh `eigen_knn` đang mở trung bình, không chứng tỏ CPU chạy 100%.
- `concurrency_time_pct_by_active_leaf_count`: thời gian có N leaf calls đang mở. Có thể chứa chờ khóa và deschedule.
- `worker_leaf_elapsed_gini`/`longest_one_percent_leaf_share_of_elapsed_sum_pct`: chỉ báo straggler/load concentration, **chưa chứng minh scheduler gây chậm**.
- `paired_4thread_instrumentation_overhead` dùng riêng **phase build leaf wall**; process wall của trace=on tính cả ghi 85.529 dòng CSV ở exit, không phù hợp suy overhead của hot loop.
- Nếu instrumentation gây ảnh hưởng đáng kể, không dùng traced run làm benchmark tốc độ. Lấy trace chỉ để định hướng.

P4a không đo time-to-acquire `LSHGraph::locks[i]`, không có dependency edges để suy critical path toán học, và không có topology/Recall/QPS. Nếu kết quả cho thấy `merge_worker` đáng kể hoặc tail chờ đồng bộ, phải thiết kế P4b với **sampled lock acquisition latency + overhead control**. Nếu bão hòa worker tốt, tiếp tục đánh giá giai đoạn bucket/final prune hoặc tìm delta thuật toán mới và prior art.

## E. Các rủi ro và giới hạn

- Mã source dựa vào một commit và nguyên gốc H26-P0; kiểm tra strict anchors, không vá mã H25.
- Quan sát từ 1 BUILD với 1/2 workers không chứng minh scalable speedup; 4t có 2 lượt nhưng vẫn ít.
- Mô hình không cho phép số cluster rounds >1 trong trace mode; nếu cấu hình khác dừng để tránh sai provenance.
- Thread token không phải physical CPU core; thread có thể bị migration trong cpuset.
- C++ logger ghi CSV khi hủy singleton ở cuối process; nếu bị crash hoặc `kill -9`, trace có thể chưa được flush. Không coi thiếu CSV là thành công.
- Chỉ coi H26-P4a là **profiling**, không phải ANN algorithm novelty, final performance claim hoặc Pareto.
