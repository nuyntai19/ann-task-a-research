# H25-R1 — Native Graph Quality Gate cho Duplicate Backfill (SIFT1M)

**Đọc trước:** H25-R0/R0b cho thấy candidate coverage có thể tăng, nhưng không chứng minh Recall/QPS. Bộ kit này tạo **can thiệp offline** cho 64 leaf đã khảo sát (rank 8, sample seed 42), đưa các thay thế qua **chính PiPNN `merge_neighbors`/HashPrune và `robustPrune` cuối**, sau đó đánh giá 3 graph bằng một C++ single-thread searcher chung. Đây **không phải implementation của một thuật toán backfill online khả thi**, và **không chứng minh BUILD speedup**.

## Mức bằng chứng

- H25-R0b: 64/85.529 leaf; 20.784 hàng khôi phục Top2 đúng; random Top8 20.729 new full-union directed keys, nearest 19.234, nhưng tất cả chỉ là candidate.
- H25-R1: kiểm tra xem *những can thiệp đã chọn* ảnh hưởng thế nào đến graph sau HashPrune/final pruning và Recall–QPS.
- Cần kiểm tra chính xác 20.784 hàng **trong native BUILD**. Nếu không khớp nguồn H18, chương trình phải dừng, không được coi graph là hợp lệ.
- `H25_R1_PATCH_FILE` không phải là thuật toán song song thực tế; kế hoạch biết toàn bộ capture để xác định occurrence đầu tiên. Tính toán Top8, kiểm tra trùng, grouping và tạo patches xảy ra **trước** BUILD và không được tính vào thời gian BUILD instrumented. Vì vậy BUILD instrumentation R1 không dùng được để chứng minh Pareto/production cost.
- Searcher trong kit có thể **khác implementation R0f/H24**; QPS chỉ so sánh **bên trong cùng kit R1**, không trộn với số QPS H24.

## Các file

- `h25_r0_backfill_gate.py` — sử dụng lại nguyên mô-đun R0 để khôi phục Top8 và các chính sách trên H18.
- `h25_r1_make_plan.py` — tính toàn bộ (không cắt trace) patch records, xuất `expected_rows.bin`, `patch_baseline.bin`, `patch_nearest.bin`, `patch_random.bin`, `patch_hindsight.bin` cùng `plan.json`.
- `h25_r1_hook.h` — native runtime hook: kiểm tra từng hàng Top2 theo leaf ID/src, thay điểm đích/weight từ distance matrix gốc ngay trước graph merge, và từ chối build nếu thiếu/mismatch bất kỳ row/patch.
- `h25_r1_patch_source.py` — kiểm tra/patch/restore **hai source headers** từ PiPNN; có backup và không chạm kết quả H17–H24.
- `h25_r1_run_native.sh` — chạy BUILD baseline/nearest/random sau khi instrument; sau đó SEARCH chung; không overwrite thư mục output.
- `h25_r1_common_search.cpp` + `h25_r1_test.py` — evaluator 1 luồng (entry0), exact GT, ef grid, reachable0, indegree; có self-test trên graph synthetic.
- `h25_r1_edge_survival.py` — đọc graph final để đếm sự hiện diện các `u->v` được yêu cầu bù; chỉ là association, không chắc do riêng injection sinh ra.
- `h25_r1_summarize.py` — so sánh Recall–QPS/graph bytes và gắn cờ confounders.

## Bước 1 — Giải nén và kiểm thử (không sửa PiPNN)

```bash
mkdir -p ~/ann-task-a/experiments/H25/r1_kit
cd ~/ann-task-a/experiments/H25/r1_kit
unzip -o ~/Downloads/H25_R1_graph_gate_kit.zip -d .
source ~/ann-task-a/.venv/bin/activate
python3 h25_r1_make_plan.py --mode selftest
python3 h25_r1_test.py
```

Kỳ vọng `SELFTEST PASS` cả hai. `h25_r1_test.py` chỉ sinh một graph nhỏ trong temp, biên dịch searcher bằng `g++` và tính Recall@10=1.0. Cần `numpy`, `g++`, `taskset`, `/usr/bin/time`, PiPNN dependencies đã cài.

## Bước 2 — Xuất R1 intervention plan từ đúng H18 capture

```bash
python3 h25_r1_make_plan.py --mode plan
cat ~/ann-task-a/experiments/H25/r1_graph_gate_sift1m_seed42/plan.json
```

Mặc định dùng:
`~/ann-task-a/experiments/H18/phase2_candidate_audit/leaf_proposals.bin` (SHA256 bắt buộc `13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95`) và `~/ann-task-a/data/sift1m.fbin`.

Kỳ vọng 64 leaf, 20.784 rows; `patch_counts.nearest` = 23.584 và `patch_counts.random` = 23.584. Nếu khác: DỪNG và gửi log.

Quá trình `np.unique` trên 59.990.170 proposals có thể ngốn RAM lớn. Công cụ chặn nếu `MemAvailable <5 GiB`; không bỏ `--skip-sha` khi chạy thực tế.

## Bước 3 — Kiểm tra patch cho **PiPNN source hiện có**

```bash
cd ~/ann-task-a/experiments/H25/r1_kit
python3 h25_r1_patch_source.py --repo ~/ann-task-a/src/PiPNN --mode check
```

- **Khuyên dùng một bản sao PiPNN riêng** trước khi `apply`, để không làm ảnh hưởng source H17. Đường dẫn mặc định `~/ann-task-a/src/PiPNN` chỉ là giả định theo các log trước. Nếu clone của bạn nằm vị trí khác, thay bằng đường dẫn thực.
- `check` chỉ xem anchors, không chỉnh source. Nếu `FAIL CLOSED` do H17 thay `VQPartialSort` hoặc đổi cấu trúc hàm, **KHÔNG** tự ép patch; cần dựa vào source/diff thực tế.
- Nếu có đủ dung lượng, sao chép **source sạch** sang một thư mục `~/ann-task-a/experiments/H25/pipnn_source_r1` và truyền `--repo` tới đó. Bản sao phải có submodules/dependencies và CMake configured tương ứng. Đừng `git reset --hard` trên source đã sửa.

## Bước 4 — Cài hook lên source thực nghiệm và biên dịch

**Chỉ sau khi `--mode check` PASS và đã chọn đúng source thực nghiệm:**

```bash
python3 h25_r1_patch_source.py --repo ~/ann-task-a/src/PiPNN --mode apply
cmake --build ~/ann-task-a/src/PiPNN/build --target neighbors-pipnn_FLOAT_T_EUCLIDEAN -j 4
```

Nếu bạn dùng bản sao source khác, thay hai đường dẫn tương ứng và đặt biến `PIPNN_REPO` khi chạy.

Hook thay `eigen_knn(..., MST_DEG)` thành `eigen_knn(..., MST_DEG, leaf_id)` và sửa `RunLeaf` tương ứng. Để trở lại source trước thử nghiệm:

```bash
python3 h25_r1_patch_source.py --repo ~/ann-task-a/src/PiPNN --mode restore
cmake --build ~/ann-task-a/src/PiPNN/build --target neighbors-pipnn_FLOAT_T_EUCLIDEAN -j 4
```

Backup mang đuôi `.h25r1_original`; KHÔNG xóa backup nếu chưa xác nhận phục hồi. Hook không thay source/graph khi chế độ `check`.

## Bước 5 — Native BUILD và common SEARCH

```bash
cd ~/ann-task-a/experiments/H25/r1_kit
bash h25_r1_run_native.sh
```

Hoặc, nếu repo là bản sao:

```bash
PIPNN_REPO=~/ann-task-a/experiments/H25/pipnn_source_r1 bash h25_r1_run_native.sh
```

Runner dùng `PARLAY_NUM_THREADS=4`, `taskset -c 0,2,4,6`, `num_clusters=1`, `fanout=30`, `fanout_scheme=10,3`, `cluster_size=1024`, `mst_deg=2`, `alpha=1.2`, `prune_all=1`, `prune_degree=32`, `hash_bits=12` theo H18/PiPNN. **Sample seed42 chỉ quyết định chọn 64 leaf offline, không phải seed chính của PiPNN**.

Nếu native BUILD không còn cùng leaf realization H18, sẽ báo `H25_R1_FAIL_CLOSED` hoặc thiếu `H25_R1_VERIFY_PASS`; **DỪNG**, không sử dụng graph xuất ra.

Output mặc định là thư mục mới `~/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42/` gồm:

- `baseline.graph`, `nearest.graph`, `random.graph` — graph final từ **PiPNN thật**.
- `*_build.log` — BUILD logs kèm `/usr/bin/time -v`, `H25_R1_VERIFY_PASS`, peak RSS.
- `*_eval.csv` và `*_search.log` — Recall@10/QPS trên cùng searcher single-thread.
- `summary.json`, `final_edge_presence.json` — số liệu chính; `graph_sha256.txt`.

Nếu thư mục output đã tồn tại, runner từ chối overwrite. Sau lỗi giữa chừng, hãy xem log, giải quyết lỗi rồi chỉ chạy lại với một tên thư mục mới:

```bash
H25_R1_RUN_OUT=~/ann-task-a/experiments/H25/r1_native_retry1 bash h25_r1_run_native.sh
```

## Bước 6 — Gửi kết quả

```bash
cat ~/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42/summary.json
cat ~/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42/final_edge_presence.json
```

Nếu lỗi, gửi 50 dòng cuối log phương án lỗi và nội dung `plan.json`, không sửa source theo phỏng đoán.

## Gate khoa học và các tình huống NO-GO

1. **Integrity:** Nếu bất kỳ native Top2 row/source/leaf không trùng R0b/H18, từ chối so sánh. Cùng tham số nhưng lệch partition != matched graph intervention.
2. **Structural:** Nếu candidates mới gần như không tồn tại trong graph final sau real merge/final prune, H25 trên Top8 backfill ưu tiên NO-GO.
3. **Quality:** Nếu graph mới không cải thiện Recall–QPS qua nhiều ef và seed, dù unique candidate coverage tăng, NO-GO.
4. **Budget:** Nếu index bytes hoặc số cạnh khác nhau, KHÔNG gọi là Pareto memory-matched; cần degree/bytes matched controls ở bước khác.
5. **True algorithm cost:** Native injection R1 bỏ qua chi phí chọn Top8, duplicate detection và synchronization. Kết quả BUILD R1 không phải BUILD của feasible parallel backfill. Nếu quality gain đủ lớn, phải thiết kế và đo một thuật toán live có bounded memory, work/span rõ ràng, rồi kiểm tra novelty đối chiếu PiPNN/Three Stages/ParlayANN.

**Ghi chú:** Dù cả 20.784 selected rows khớp và ba graph BUILD hợp lệ, do concurrent merges có thể nondeterministic, một lần BUILD/phương án chưa đủ chứng minh causal effects hoặc significance. Tăng số repetitions ở giai đoạn tiếp theo.
