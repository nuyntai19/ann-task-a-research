# H26-P1b: Phân rã `Eigen::rankUpdate` theo kích thước leaf — PiPNN Task A

## Tại sao đo?

P1a trên SIFT1M, sau Top-2: `rankUpdate` chiếm khoảng **44.858 worker-seconds** (~72.32% dist worker time). Nhưng chưa rõ chi phí đến từ số lượng rất lớn leaf nhỏ hay một nhóm leaf lớn. Bước P1b **chỉ đo**, không thay đổi thuật toán ANN hoặc graph.

Phương pháp: tạo worktree riêng tại `~/ann-task-a/experiments/H26/PiPNN-H26-P1B-src`, copy mã H26-P1a đã build, và gắn một bộ histogram nguyên tử theo 9 khoảng `n` (số điểm trong leaf): `2-63`, `64-127`, `128-255`, `256-383`, `384-511`, `512-767`, `768-1023`, `1024-1535`, `1536+`.

Đo cho mỗi bin:
- `leaves`: số lần tính ma trận của leaf;
- `rows`: tổng n;
- `pairs`: tổng n(n+1)/2, tính cả đường chéo;
- `pair_dims`: tổng n(n+1)d/2 (ước lượng lượng công việc hình học, **không phải FLOPs thực đo**);
- `rank_ns`: worker elapsed nanoseconds chỉ của `Eigen::rankUpdate`;
- `dist_ns`: worker elapsed nanoseconds toàn `eigen_build_distmat` đến trước các bộ đếm của P1a.

**Tính đúng đắn số liệu:** bộ phân tích đối chiếu tổng `leaves=85529`, tổng `rows=29995085`, rank histogram = counter P1a rankUpdate, distance histogram = tổng các counter P1a subphase. Mọi sai lệch ngoài tolerance đều FAIL CLOSED. Thu thập histogram diễn ra sau mốc thời gian P1a, làm tăng overhead ở ngoài vùng rank đo; *không dùng P1b để so sánh BUILD wall speedup với P0/P1a*.

## Chạy trên Ubuntu

Tải `H26_P1B_leafsize_kit.zip` vào `~/Downloads`, rồi chạy theo thứ tự:

```bash
mkdir -p ~/ann-task-a/experiments/H26/P1B_kit
cd ~/ann-task-a/experiments/H26/P1B_kit
unzip -o ~/Downloads/H26_P1B_leafsize_kit.zip -d .
python3 h26_p1b_selftest.py
```

Nếu hai SELFTEST_PASS, tiếp tục:

```bash
python3 h26_p1b_workspace.py
bash ~/ann-task-a/experiments/H26/configure_H26_P1B.sh
```

Chỉ chạy sau dòng `Built target neighbors-pipnn_FLOAT_T_EUCLIDEAN`:

```bash
H26P1B_ROUNDS=2 bash h26_p1b_run.sh
```

Sau khi có `H26P1B_DONE`, lấy kết quả:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P1B_* | head -n 1)
cat "$OUT/h26_p1b_summary.txt"
cat "$OUT/h26_p1b_summary.json"
```

**Không xóa hoặc sửa H26-P0, P1a hay H25.** Bộ tạo worktree từ chối ghi đè thư mục P1B đã tồn tại. Nếu `H26P1B_FAIL_CLOSED` hoặc lỗi CMake/build, dừng và gửi log.

## Tiêu chí ra quyết định

- Nếu phần lớn `rank_ns` nằm ở ít leaf lớn: tìm chi phí theo n/d và hiệu suất kernel; cân nhắc đối chứng kernel/library, nhưng không claim novelty.
- Nếu rất nhiều leaf vừa/nhỏ làm rankUpdate chiếm phần lớn: điều tra chi phí launch/kernel, memory locality, thay vì cho rằng GEMM/BLAS đạt throughput lý tưởng.
- Nếu %rank ns và %pair_dims khác nhau mạnh giữa các bin: một số kích thước đang được xử lý kém hiệu quả — cần benchmark kiểm soát theo n.
- Không suy ra memory-bound/compute-bound chỉ từ timing; cần `perf stat`, cache misses, instruction counters và thay đổi d nếu khả thi.
- Không suy ra speedup tổng BUILD từ worker elapsed, và không coi cải tiến Eigen/SYRK thông thường là novelty của Parallel ANN Task A.
