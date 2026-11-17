# H26-P3a — Phân rã phần candidate selection còn lại sau Top-2

## Mục tiêu khoa học

P2b cho thấy 30,26% pair occurrences trùng, nhưng độ tái sử dụng theo cửa sổ leaf ID nhỏ thấp; vì vậy không xây global distance cache vội. H26-P3a phân tách `selection` của H26-P0 (sau Top-2) thành:

1. **Q assembly**: `Q.clear()`, đọc phần tam giác `dist_mat`, `packFloatAndInt`, `Q.push_back`.
2. **Top-2 scan**: chọn 2 giá trị packed nhỏ nhất.
3. **Proposal materialization**: `unpackDouble`, tra global ID, `directed_edges.emplace_back`.

Mục tiêu là kiểm tra phần nào còn tốn thời gian và có cơ hội giảm thao tác không cần thiết. **Không triển khai thuật toán mới hoặc tuyên bố về tính mới, Pareto, Recall/QPS**.

## Thiết kế an toàn

- Nguồn tham chiếu PiPNN commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`.
- Tạo worktree **riêng** `~/ann-task-a/experiments/H26/PiPNN-H26-P3A-src`, chép từ **H26-P0** đã thành công; giữ nguyên P0, P1a, P1b và H25.
- Reuse CMake source dependencies đã tải, sửa `add_subdirectory(parlaylib ...)` bằng bản CMake đã thành công của P0.
- Chỉ lấy mẫu những leaf chọn theo hash của 8 thành viên đầu + kích thước leaf. Mặc định 1/64 leaf. Không ghi đồng hồ cho mọi row (30 triệu rows) để giảm nhiễu.
- Chỉ `top2` và tắt `H26_CHECK_TOP2` trong phép đo thời gian; P0 từng kiểm tra 29.305 hàng thành công trước đây.
- Không ghi graph ra đĩa để tránh I/O. Worker times cộng dồn trên leaf **không phải BUILD wall time**.
- `Q assembly` vẫn giữ cách pack + tạo vector hiện tại; code profiling không cố gắng tối ưu nó.
- Timer overhead vẫn có thể đáng kể trong sample. Kiểm tra `TIMER_AND_NONSTAGE_GAP` và nếu cần thử `H26P3A_SAMPLE_MOD=32` ở một thí nghiệm thứ hai.
- Kết quả lấy mẫu chỉ dùng quyết định bottleneck, không thể ngoại suy chính xác thành tác động BUILD.

## Bước 1. Giải nén và selftest

```bash
mkdir -p ~/ann-task-a/experiments/H26/P3A_kit
cd ~/ann-task-a/experiments/H26/P3A_kit
unzip -o ~/Downloads/H26_P3A_selection_breakdown_kit.zip -d .
python3 h26_p3a_selftest.py
```

Kỳ vọng: `H26P3A_PATCH_FAIL_CLOSED_SELFTEST_PASS` và `H26P3A_ANALYZER_SELFTEST_PASS`.

## Bước 2. Tạo workspace H26-P3a và biên dịch

```bash
python3 h26_p3a_workspace.py
bash ~/ann-task-a/experiments/H26/configure_H26_P3A.sh
```

Nếu thấy `H26P3A_FAIL_CLOSED` hoặc `CMake Error`, dừng và gửi log, không sửa repo gốc. Không gọi lại workspace create nếu đã tạo.

Kỳ vọng: `Built target neighbors-pipnn_FLOAT_T_EUCLIDEAN`.

## Bước 3. Chạy trên SIFT1M

```bash
cd ~/ann-task-a/experiments/H26/P3A_kit
H26P3A_ROUNDS=2 H26P3A_SAMPLE_MOD=64 bash h26_p3a_run.sh
```

Thí nghiệm dùng 4 threads trên CPUSET `0,2,4,6`, cấu hình chuẩn H26-P0. Hai BUILD theo cùng algorithm Top-2, có lấy mẫu; không ghi graph. Cuối có `H26P3A_DONE=...`.

## Bước 4. Lấy số liệu

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P3A_2* | head -n 1)
cat "$OUT/h26_p3a_summary.txt"
cat "$OUT/h26_p3a_summary.json"
```

Chỉ cần gửi kết quả TXT để bước đầu phân tích. Nếu phần `TIMER_AND_NONSTAGE_GAP` cao (ví dụ >10–15%), phần trăm subphase chỉ là một chỉ báo thô, cần đo bằng trace sampling ít hơn.

## Phương pháp phân tích

- Đơn vị: **sample worker nanoseconds**, không phải process wall.
- `sampled_rows` thể hiện khối lượng thực tế được bấm giờ; `sampled_candidates` là tổng `n(n-1)` các ứng viên scan trong sample.
- `outer_select_ns` là thời gian chọn ứng viên của sampled leaves, bao gồm logging overhead và các thao tác ngoài subphase.
- Tổng các subphase có thể khác `outer_select_ns` vì overhead gọi đồng hồ và các phần ngoài các mốc giờ.
- Nếu `pack` lớn: chỉ mới có chẩn đoán; phương án direct-distance Top-2 cần xem xét tie behavior và kết quả graph.
- Nếu `scan` lớn: tìm nguyên nhân memory bandwidth, vector traversal hoặc branch, không tự claim novelty.
- Nếu `emit` lớn: đo allocation và graph updates; không tự suy ra có thể gộp cạnh mà không thay topology.

