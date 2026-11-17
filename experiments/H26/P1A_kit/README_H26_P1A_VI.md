# H26-P1a — Breakdown of distance matrix after Top-2

## Mục đích

H26-P0 trên SIFT1M cho thấy worker time ở phần `eigen_build_distmat` khoảng 61.6 giây; selection Top-2 khoảng 38.8 giây. Chỉ riêng các số này **không chứng minh** rằng GEMM là bottleneck chính trong distmat. H26-P1a phân rã chi phí distance matrix.

**Không sửa H26-P0, H25 hoặc đồ thị đã tạo.** Tạo worktree độc lập `~/ann-task-a/experiments/H26/PiPNN-H26-P1A-src` từ commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd` và copy file instrumented H26-P0 đã kiểm chứng. Nếu đã tạo đích, công cụ từ chối ghi đè.

## Năm nhóm đo

Tất cả là **worker elapsed sum**, không phải BUILD wall time:

- `buffers_worker_ns`: đọc kích thước + cấp phát/lấy thread-local point/dist buffer, kể cả **cold initialization**.
- `copy_worker_ns`: sao chép/coerce point coordinates vào point matrix.
- `norm_zero_worker_ns`: khởi tạo Eigen map, squared norms, và D.setZero().
- `rankupdate_worker_ns`: `D.selfadjointView<Eigen::Lower>().rankUpdate(P)` (không đồng nghĩa gọi riêng BLAS `sgemm` trong mọi trường hợp).
- `finalize_worker_ns`: đổi tích vô hướng thành khoảng cách bình phương hoặc dạng tương ứng.

Các phép đo cần được hiểu là thời gian bên trong vùng nguồn tương ứng. Chúng không phân rã memory bandwidth/cache contention hay critical path, không phải căn cứ để công bố speedup.

## Cách chạy trên Ubuntu

1. Tải ZIP `H26_P1A_dist_breakdown_kit.zip` về thư mục `~/Downloads`.

```bash
mkdir -p ~/ann-task-a/experiments/H26/P1A_kit
cd ~/ann-task-a/experiments/H26/P1A_kit
unzip -o ~/Downloads/H26_P1A_dist_breakdown_kit.zip -d .
python3 h26_p1a_selftest.py
```

2. Chuẩn bị source riêng và build:

```bash
python3 h26_p1a_workspace.py
bash ~/ann-task-a/experiments/H26/configure_H26_P1A.sh
```

Nếu có `H26P1A_FAIL_CLOSED`, `CMake Error` hoặc build error, **không chạy tiếp**; gửi lỗi. CMake tái sử dụng cache dependency gốc, vì thế đòi hỏi P0 worktree và original PiPNN hiện hữu.

3. Phân rã chi phí, hai lần BUILD giống nhau (không ghi graph để tránh thêm I/O/dung lượng):

```bash
H26P1A_ROUNDS=2 bash h26_p1a_run.sh
```

4. Lấy kết quả từ dòng `H26P1A_DONE=...`:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P1A_* | head -n 1)
cat "$OUT/h26_p1a_summary.txt"
cat "$OUT/h26_p1a_summary.json"
```

**Chú ý:** Do không ghi graph, `process_wall_s_no_graph_output` của P1a **không** được so trực tiếp với H26-P0 `process_wall_s` (có ghi graph). Việc instrument P1a cũng làm tăng overhead; mục tiêu chỉ là attribution, không xác nhận speedup.

## Điều kiện kiểm toán

- Từng lượt phải xuất `H26P1A,version,H26_P1A_v1`, P0 `H26_PROFILE,selector,top2` và `calls=leaf_count=85529`.
- Năm con số worker sum nên xấp xỉ vùng `P0 dist worker` đo tại `eigen_knn`. Chênh lệch nhỏ có thể là overhead vùng/timer. Chênh lệch lớn: rà lại mức can thiệp và bộ đếm.
- Cần đọc kết quả trước khi chọn cơ chế H26-P1b. H26-P1a **không** chọn thuật toán mới.
