# H26-P0: Profiling BUILD PiPNN (stock / Top-2 scan replica)

## Mục tiêu

H26 chỉ đo **bottleneck của BUILD** sau kết quả âm H25. Chưa đề xuất thuật toán mới. Bộ công cụ **KHÔNG sửa repo PiPNN/H25 hiện tại**; nó tạo **Git worktree ở commit PiPNN 443a328** và sử dụng lại source dependency của CMake hiện có. `stock` dùng VQPartialSort gốc; `top2` là một **bản tái hiện Top-2 scan riêng cho H26**, KHÔNG được gọi là mã H17 chính xác của nhóm nếu chưa đối chiếu hash/commit.

Bốn chỉ số chính:

- `dist_worker_s`: tổng thời gian các leaf gọi `eigen_build_distmat` (distance matrix, bao gồm GEMM và các thành phần liên quan).
- `select_worker_s`: tổng thời gian build candidate list mỗi leaf, gồm pack distance, Top-k và tạo directed records. **Không phải chỉ thời gian VQPartialSort**.
- `merge_worker_s`: tổng thời gian merge candidate cho graph (gồm khóa, HashPrune/hashing và các thành phần hiện hữu tùy GraphH).
- `total_process_wall_s_includes_graph_output`: GNU `/usr/bin/time -v` trên toàn process, bao gồm BUILD **và ghi graph**, nên không phải BUILD-only wall. Các `*_worker_s` là tổng elapsed times trên nhiều leaf chạy song song; **không được cộng với `total_process_wall_s`**.

Cuối BUILD, các phase `buckets time`, `build leaf time` và `Final prune time` vốn có trong PiPNN cũng nằm trong log.

## Bước 1 — Giải nén và self-test

Tải `H26_postH17_profile_kit.zip` về `~/Downloads`:

```bash
mkdir -p ~/ann-task-a/experiments/H26/kit
cd ~/ann-task-a/experiments/H26/kit
unzip -o ~/Downloads/H26_postH17_profile_kit.zip -d .
python3 h26_selftest.py
```

## Bước 2 — Preflight và tạo workspace tách biệt

```bash
python3 h26_workspace.py --mode check
python3 h26_workspace.py --mode create
```

`--mode check` **không thay đổi file**, kiểm tra commit và các cached dependencies trong repo `$HOME/ann-task-a/src/PiPNN/build/_deps`. `--mode create` tạo worktree `~/ann-task-a/experiments/H26/PiPNN-H26-src`, gắn instrumentation đúng source pinned. Nó **từ chối ghi đè** nếu đích đã tồn tại. Nếu thiếu submodule `external/mirage`, nó **dừng**; không tự tải mạng, không trộn nguồn hoặc đo sai bản build.

Sau khi tạo workspace, script ghi `~/ann-task-a/experiments/H26/configure_H26.sh`.

## Bước 3 — Biên dịch ở workspace riêng

```bash
bash ~/ann-task-a/experiments/H26/configure_H26.sh
```

Nếu CMake báo lỗi do dependency/submodule, **không chạy tiếp BUILD**; gửi lỗi để xử lý đúng đường dẫn. Đừng quay về sửa repo H25.

## Bước 4 — Thử semantics Top-2 (không dùng để đo thời gian)

Chạy một lượt kiểm tra so Top-2 scan với Highway `VQPartialSort` ở những row được lấy mẫu. Nếu sai sẽ `H26_FAIL_CLOSED`. Phép thử này có overhead và không dùng trong số liệu benchmark.

```bash
SRC=~/ann-task-a/experiments/H26/PiPNN-H26-src
mkdir -p ~/ann-task-a/experiments/H26/preflight
PARLAY_NUM_THREADS=4 H26_SELECTOR=top2 H26_CHECK_TOP2=1 \
  taskset -c 0,2,4,6 "$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN" \
  -base_path ~/ann-task-a/data/sift1m.fbin \
  -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
  -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
  -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
  -graph_outfile ~/ann-task-a/experiments/H26/preflight/validate_top2.graph \
  > ~/ann-task-a/experiments/H26/preflight/validate_top2.log 2>&1

grep -E 'H26_PROFILE,top2_checks|H26_FAIL_CLOSED' ~/ann-task-a/experiments/H26/preflight/validate_top2.log
```

Nếu `top2_checks=0`, không coi semantic validation đã đủ; kiểm tra log và tần suất sampling. Sample check **không** bảo đảm full equivalence. Trước khẳng định identical graph, cần đối chiếu cơ chế tied distances và repeated builds.

## Bước 5 — PROFILE cùng một binary, hai selector

```bash
cd ~/ann-task-a/experiments/H26/kit
H26_ROUNDS=2 bash h26_run.sh
```

`h26_run.sh` xuất tên thư mục `H26_OUTPUT=...` và chạy thứ tự đảo chiều: `stock → top2`, rồi `top2 → stock` (2 repetitions mỗi phương án). Nó KHÔNG dùng graph H25 và không thay source H25. Nếu muốn thí điểm ngắn chỉ một lượt thì `H26_ROUNDS=1 bash h26_run.sh`, nhưng không dùng 1 lượt để kết luận speedup.

Từ folder output:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_profile_* | head -n 1)
cat "$OUT/h26_summary.txt"
cat "$OUT/h26_summary.json"
```

Gửi **`h26_summary.txt`, `h26_summary.json`** và đoạn log các phase chính để đánh giá H26-P0. Xem thêm `h26_runs.csv` nếu cần so theo từng BUILD.

## Đánh giá GO / NO-GO (chỉ cho bước tìm cơ chế)

1. Nếu **selection vẫn chiếm lớn** trong profile Top-2 → xem packing/candidate materialization, chứ không lập tức thử Top-k hay SIMD vì novelty thấp.
2. Nếu **merge chiếm lớn** → xác nhận contention/HashPrune bằng profiler bổ sung; không tự claim semisort/batch grouping là mới (ParlayANN đã nghiên cứu).
3. Nếu **distance matrix chiếm lớn** → không suy ra giảm pair work dễ dàng; H18/H22/H23 đã có kết quả âm; cần lý do toán học và chứng minh giảm random-access overhead trước khi pilot.
4. Nếu `BUILD time`, counter, Recall/QPS chưa đo đủ → kết luận **bottleneck only**, không có claims Pareto/novelty.

## Sai lệch/phòng ngừa

- Bộ công cụ không tự khôi phục H17 custom patch của nhóm; `top2` là reimplementation phục vụ profiling. So sánh với H17 trước đây chỉ là định hướng, **không được gộp thống kê BUILD khác binary**.
- Đây là instrumentation *mức leaf*: nếu leaf chạy đồng thời, worker elapsed sum có thể lớn hơn BUILD wall.
- Không tách riêng SIMD selection và packing tại granularity từng row vì timer mỗi row có thể làm perturb timing; một phiên bản sample microprofile sẽ có ích sau khi tìm bottleneck.
- Source `external/mirage` trong worktree liên kết đến checkout gốc để dùng dependency đã tồn tại, không tải lại. Phiên bản CMake dependencies được pin vào **cached source hiện tại**, không phải chứng minh reproducibility cross-machine.
- Do chạy trên CPU giới hạn bằng `taskset`, nhớ theo dõi nhiệt/CPU frequency và noise khi so chênh lệch nhỏ.

## Prior-art guard trước H26-P1

- **PiPNN (2026):** https://arxiv.org/abs/2602.21247 — sử dụng dense distance computation, overlapping partitions và HashPrune. Tối ưu một primitive trong leaf không đủ claim topology novelty.
- **Three Composable Stages (2026):** https://arxiv.org/abs/2610.09041 — tái cấu trúc pool/ending/spine cho search-free ANN; mọi phương án redesign candidate selection/ending phải audit paper và code này.
- **ParlayANN (PPoPP 2024):** https://www.cs.ucr.edu/~yihans/papers/2024/PPoPP24/parlayann.pdf — batching và song song cập nhật graph; không được claim batching/semisort là đóng góp mới.

H26-P0 chỉ đo work/latency distribution. H26-P1 (nếu có) phải gắn giả thuyết giảm **work thực, synchronization hoặc span**, có model chi phí, đối chứng xây graph và kiểm chứng Recall–QPS **tại matched Recall + matched bytes**. Nếu profile không xác lập bottleneck cụ thể có thể can thiệp mới, NO-GO đổi thuật toán tùy tiện.
