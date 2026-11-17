# H26-P4b — Kiểm toán sampled mutex wait/hold trong graph merge (27/10/2026)

## Vì sao P4b?

H26-P4a cho thấy ở 4 luồng có khoảng 98,3–99,1% thời gian tồn tại đủ 4 lời gọi xử lý leaf, worker load Gini thấp (0,0008–0,0027), và tốc độ leaf phase chỉ ≈3,2× so với 1 luồng. **Concurrency của leaf không phải CPU utilization.** H26-P4b đo sample mutex wait/hold và process-level CPU time để quyết định có đáng điều tra contention sâu hay không, **không phải full critical path**.

## Định nghĩa và giới hạn

- Vùng được lấy mẫu: khóa `locks[i].Lock()` / `Unlock()` **trong `LSHGraph::merge_neighbors`**, graph mặc định PiPNN trên pinned commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`; không đổi logic chọn candidate/merge. Dự kiến mỗi directed proposal gọi hai merge, tổng ≈119.980.340 lần acquire mỗi BUILD.
- `wait_ns = steady_clock(acquired) - steady_clock(before Lock)`; gồm overhead clock, thực chờ mutex, khả năng OS descheduling; **không phải pure mutex contention**.
- `hold_ns = steady_clock(before Unlock) - steady_clock(acquired)`; gồm thao tác bên trong critical section, khả năng OS deschedule. Record CSV sau Unlock để không tính overhead logging vào hold.
- `sample_mod=1024` nghĩa lấy ngẫu nhiên giả theo mỗi thread, xác suất 1/1024; dự kiến ~117.168 mẫu/BUILD, 300.000 slots dự trữ. Chỉ có 1/512–1/8192 được cho phép. Không được tự nâng 1/128 vì overflow buffer.
- Instrumentation adds a branch/random on **every merge call** even when sampled flag false. Bắt buộc so **3 arm** P0-original Top2, P4b binary OFF, P4b binary ON trong 2 vòng đảo thứ tự. Do khác binaries/codegen, P0-vs-OFF không phải controlled A/B cùng binary; nếu OFF regression lớn, **STOP/HOLD**.
- Process CPU ratio = (GNU user time + system time) / elapsed process wall. Chỉ là process-level CPU occupancy proxy (gồm buckets/prune), không phải trực tiếp leaf-CPU utilization, IPC/cache miss hay work/span.
- P4b không ghi graph: không có topology quality / Recall / QPS / equivalence check. Mỗi arm có cùng counts but counts≠graph identity. Không suy ước lượng total lock wait cộng dồn sang critical-path time.
- **Chưa đo:** CPU PMU (IPC, cache miss, memory bandwidth), exact per-worker CPU activity, sync DAG critical path, phase-specific CPU ratios, graph quality, cross-seed variance. Kết luận nếu có chỉ đủ làm diagnostic.

## Yêu cầu

Ubuntu, `~/ann-task-a/src/PiPNN` có pin commit, cached dependencies CMake giống H26-P0; source `~/ann-task-a/experiments/H26/PiPNN-H26-src`, compiled binary P0; SIFT1M `~/ann-task-a/data/sift1m.fbin`; `g++`, Python3, `taskset`, `/usr/bin/time`.

## A — Tạo thư mục, giải nén và self-test

```bash
mkdir -p ~/ann-task-a/experiments/H26/P4B_kit
cd ~/ann-task-a/experiments/H26/P4B_kit
unzip -o ~/Downloads/H26_P4B_lock_audit_kit.zip -d .
python3 h26_p4b_selftest.py
```

Kỳ vọng `H26P4B_PATCH_FAIL_CLOSED_SELFTEST_PASS`, `H26P4B_CPP_MULTITHREAD_RECORDER_PASS`, `H26P4B_ANALYZER_SELFTEST_PASS`. Selftest dùng log **synthetic**, không có perf claim.

## B — Fail-closed preflight và create worktree

```bash
python3 h26_p4b_workspace.py --mode check
python3 h26_p4b_workspace.py --mode create
bash ~/ann-task-a/experiments/H26/configure_H26_P4B.sh
```

Kỳ vọng `H26P4B_PREFLIGHT_PASS`, `H26P4B_PREPARED` và `[100%] Built target neighbors-pipnn_FLOAT_T_EUCLIDEAN`.

**Cảnh báo:** Nếu check fail-closed, dừng và gửi nguyên lỗi. Không copy source từ P4a/P3b hoặc sửa P0. Nếu worktree đã tồn tại, không overwrite tự động.

## C — Chạy audit

```bash
cd ~/ann-task-a/experiments/H26/P4B_kit
H26P4B_SAMPLE_MOD=1024 bash h26_p4b_run.sh
```

Gồm 7 BUILD: r1_p0 (4t original), r1_off (4t instrumentation OFF), r1_on (4t sampled), r1_1t_on (1t sampled), r2_on (4t sampled), r2_off (4t OFF), r2_p0 (4t original). Điều kiện như H26-P4a, không output graph; `taskset -c 0,2,4,6` cho 4t và CPU 0 cho 1t. Order ABBA-like, không phải matched 2x random seeds.

## D — Lấy báo cáo

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P4B_2* | head -n 1)
cat "$OUT/h26_p4b_summary.txt"
```

Gửi thêm JSON nếu cần debug:

```bash
cat "$OUT/h26_p4b_summary.json"
```

## Gate quyết định

- **HOLD** nếu P4b OFF chậm bất thường so P0 gốc hoặc P4b ON slowdown > mức nhiễu; không suy mutex chậm từ timer perturbation.
- Nếu 4t `wait p90/p99` cao hơn rõ so 1t, **và** process CPU thấp/merge worker lớn, mới chuẩn bị H26-P4c focused contention profiler (e.g. bpf/perf, if permitted). Đây không phải kết luận nguyên nhân tự động.
- Nếu wait p90/p99 4t≈1t và tỷ lệ >10µs hiếm, **NO-GO** cho ưu tiên graph-lock contention trên SIFT1M/4t; cần xem memory bandwidth/cache hoặc topology work, không tự chọn new algorithm.
- Dù data PASS, chưa có novelty, speedup, matched Recall, multiple BUILD seeds/CPU configs hoặc TRUE critical path evidence.
