> **Bản vá v2 (27/10/2026):** Khắc phục lỗi `sort fallback and emit: expected one exact anchor, got 0` của v1. Nguyên nhân là dòng trống có bốn dấu cách trong `pipnn_utils.h` sau khi áp dụng H26-P0. Bản v2 chấp nhận khoảng trắng **chỉ ở dòng trống xác định**, còn các anchor khác vẫn phải khớp chính xác. `h26_p3b_workspace.py` không tạo worktree nếu preflight thất bại; chạy lại sau khi giải nén ghi đè v2. Các số -6,95% in trong selftest là **dữ liệu mô phỏng để thử analyzer, không phải số đo SIFT1M**.

# H26-P3b — Fused packed Top-2 selection (implementation-only pilot)

## Mục tiêu và giới hạn

H26-P3a quan sát trong mẫu 1.346/85.529 leaf rằng Q assembly (clear+pack) chiếm ~69,96% **worker elapsed trên mẫu**, selector ~27,70%, emit ~2,35%. Đó KHÔNG phải tỷ lệ toàn BUILD. P3b kiểm tra giả thuyết tiết kiệm materialization của vector `Q` và lượt quét thứ hai bằng cách cập nhật đúng hai packed candidates trong vòng đọc khoảng cách.

**Không phải đóng góp thuật toán ANN.** Không thay đổi số leaf, tập pair distances, số proposal (k=2), hash prune, graph export, hoặc final prune theo thiết kế. Cần kiểm tra graph quality vì việc thay thứ tự thực thi/timing có thể đổi thứ tự merge trong parallel BUILD và tác động topology.

P3b dựa trên **worktree PiPNN-H26-src (P0 instrumented)**, không vá chồng lên P3a hoặc H25. Mã PiPNN ghim commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd` và reuse những dependency đã có, không fetch version mới. Vì P0 có instrumentation và P3b được chèn thêm điều kiện, không so số BUILD P3b trực tiếp với H17 năm trước.

### A. Cài đặt / tự kiểm tra

```bash
mkdir -p ~/ann-task-a/experiments/H26/P3B_kit
cd ~/ann-task-a/experiments/H26/P3B_kit
unzip -o ~/Downloads/H26_P3B_fused_selection_kit.zip -d .
python3 h26_p3b_selftest.py
```

Cần các dòng:
- `H26P3B_PATCH_FAIL_CLOSED_SELFTEST_PASS`
- `H26P3B_CPP_STREAMING_TOP2_PASS`
- `H26P3B_ANALYZER_SELFTEST_PASS`

C++ standalone so streaming selection với `std::partial_sort`, không thay cho so sánh thực tế Highway trong binary PiPNN.

### B. Tạo worktree riêng và biên dịch

```bash
python3 h26_p3b_workspace.py
bash ~/ann-task-a/experiments/H26/configure_H26_P3B.sh
```

Cần `Built target neighbors-pipnn_FLOAT_T_EUCLIDEAN`. Nếu lỗi `H26P3B_FAIL_CLOSED` hay `CMake Error`, dừng và đưa log. Không chạy lại `h26_p3b_workspace.py` nếu worktree đã được tạo; không xóa build H26-P0.

### C. Native semantics preflight trên 10^6 điểm (KHÔNG đo thời gian)

```bash
cd ~/ann-task-a/experiments/H26/P3B_kit
SRC=~/ann-task-a/experiments/H26/PiPNN-H26-P3B-src
mkdir -p ~/ann-task-a/experiments/H26/P3B_preflight
PARLAY_NUM_THREADS=4 H26_SELECTOR=fused H26_CHECK_TOP2=0 H26P3B_CHECK=1 \
 taskset -c 0,2,4,6 "$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN" \
 -base_path ~/ann-task-a/data/sift1m.fbin \
 -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
 -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
 > ~/ann-task-a/experiments/H26/P3B_preflight/fused_semantics.log 2>&1
EXIT=$?
echo "P3B_PREFLIGHT_EXIT=$EXIT"
grep -E '^H26_PROFILE,top2_checks,|^H26P3B,|H26P3B_FAIL_CLOSED' \
 ~/ann-task-a/experiments/H26/P3B_preflight/fused_semantics.log
```

PASS khi exit=0, `top2_checks>0`, `fused_rows=29995085`, `fused_leaves=85529`, không có lỗi. Các hàng được lấy mẫu theo `active_indices[i] & 1023u`; kết quả không phải chứng minh đầy đủ. Tiền kiểm tăng chi phí do gọi Highway trên mẫu; **không đưa thời gian này vào báo cáo BUILD**.

### D. Pilot trong cùng binary, đảo thứ tự chạy

```bash
cd ~/ann-task-a/experiments/H26/P3B_kit
H26P3B_ROUNDS=3 bash h26_p3b_run.sh
```

Chương trình không ghi graph, chạy lần lượt `top2, fused / fused, top2 / top2, fused`, 4 CPU logic qua taskset, cùng cấu hình SIFT1M, cùng instrumented binary và output thư mục mới. Mỗi BUILD đều kiểm `leaf_count=85529`, `rows=29995085`, `proposals=59990170`, fused coverage toàn bộ.

Khi `H26P3B_DONE=...`:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P3B_2* | head -n 1)
cat "$OUT/h26_p3b_summary.txt"
cat "$OUT/h26_p3b_summary.json"
```

Gửi `h26_p3b_summary.txt` và nếu có nghi vấn, `h26_p3b_summary.json`.

### E. Gate quyết định

- **Speed pilot GO:** fused phải giảm wall time BUILD không ghi graph lặp lại rõ ràng trên phần lớn round, đi cùng giảm selection worker time, trong khi dist/merge và work counts gần như không đổi. Hiệu quả vài phần trăm có thể chỉ là noise → cần thêm rounds/crossover.
- **Correctness gate độc lập:** nếu pilot tốt, sẽ build graph từ cả top2 và fused **ở cùng binary**, đánh giá graph structural/Recall@10 với 10k queries, kiểm tra exact packed Top2 và potential parallel nondeterminism, rồi mới nói về việc đưa fused vào optimized baseline.
- **Không GO cho novelty:** streaming Top-2 fusion, tránh materialization là tối ưu phần mềm thông thường. Bất kỳ đề xuất đóng góp ANN mới nào phải có cơ chế mới, prior-art audit và chứng minh tác động algorithmic.

### Phương pháp và caveat

- `wall_s` trong pilot dùng `/usr/bin/time -v`, *không ghi graph*; đây là process wall, khác số BUILD P0 có ghi graph.
- `*_worker_s` cộng dồn trên các leaf song song, không bằng wall time.
- So sánh top2/fused **trong cùng binary** nhưng có nhánh điều kiện mới cho cả hai, cần xác minh lại control overhead so với P0 khi kết quả bất thường.
- `VQPartialSort` được kiểm trên các hàng được lấy mẫu, không phải 29.995.085 hàng.
- Các ước lượng sample P3a không được dùng làm speedup dự đoán. Thời gian/thiết kế P3b là giả thuyết cho đến khi chạy thật.
