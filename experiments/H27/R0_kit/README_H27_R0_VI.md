# H27-R0 — Kiểm toán độ ổn định topology của các graph H26-P0 (KHÔNG BUILD)

**Mục tiêu:** dùng lại 4 graph native PiPNN từ H26-P0 và so sánh chính xác tập directed edges (không nhầm với row order), số hàng thay hàng xóm, degree/indegree và tùy chọn reachability entry0. Đây là kiểm toán cơ sở để loại sớm một hướng nghiên cứu, KHÔNG phải đề xuất thuật toán, bằng chứng schedule gây khác biệt hoặc kiểm tra novelty.

**Cấu trúc file xác minh từ mã nguồn gốc:** `ParAlg/PiPNN`, commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`, `algorithms/utils/graph.h`, method `Graph::save()` ghi `uint32 n`, `uint32 max_degree`, `uint32 degrees[n]`, rồi `uint32 edges[sum(degrees)]`, little-endian. Script chỉ đọc và xác thực chính xác kích thước, ID, degree. So sánh cặp bằng sorted unique 64-bit `(src<<32)|dst`, theo các block để giới hạn RAM. Header endian/ID không đúng => FAIL_CLOSED.

**Chuẩn bị trên Ubuntu:** tải ZIP vào `~/Downloads/H27_R0_topology_stability_kit.zip`. Python 3 + `numpy` (venv ANN đã có). Không cần C++, perf hoặc quyền root.

```bash
mkdir -p ~/ann-task-a/experiments/H27/R0_kit
cd ~/ann-task-a/experiments/H27/R0_kit
unzip -o ~/Downloads/H27_R0_topology_stability_kit.zip -d .
python3 h27_r0_topology_audit.py --mode selftest
```

Phải thấy `H27R0_GRAPH_SCHEMA_AND_EXACT_EDGE_SET_SELFTEST_PASS`.

**Tìm file graph có sẵn (không sửa, không BUILD):**

```bash
python3 h27_r0_topology_audit.py --mode discover
```

Script tìm các file `.graph`/`.bin` với tên chứa duy nhất `r1_stock`, `r1_top2`, `r2_stock`, `r2_top2` trong thư mục `~/ann-task-a/experiments/H26/H26_profile_20261026_222107_gcgcqF`. Nếu báo thiếu hoặc nhiều file, không đổi tên hoặc xóa graph. Hãy xem đường dẫn thực bằng:

```bash
find ~/ann-task-a/experiments/H26/H26_profile_20261026_222107_gcgcqF \
  -maxdepth 3 -type f -printf '%p %s bytes\n' | sort
```

Sau đó truyền chính xác đường dẫn bằng 4 `--graph` (mỗi label một lần); **không đoán tên file**.

**Nếu discovery thấy đúng 4 graph:**

```bash
python3 h27_r0_topology_audit.py --mode run --bfs
```

Khi in `H27R0_DONE=...`, copy đường dẫn báo cáo hoặc tìm gần nhất bằng:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H27/H27_R0_topology_* | head -n 1)
cat "$OUT/h27_r0_summary.txt"
```

Nếu script `FAIL_CLOSED` hoặc discovery không thấy đủ 4 file, gửi nguyên log; đừng tải lại graph hay chạy BUILD.

**Quan hệ so sánh:** `r1_stock`–`r1_top2`, `r2_stock`–`r2_top2`, `r1_stock`–`r2_stock`, `r1_top2`–`r2_top2`. Hai run độc lập, không giả định chung random seed/lịch chạy. Vì H26-P0 Top2 vs Highway có sampled semantic checks chứ chưa full proof, không gán edge differences cho scheduler. Thứ tự hàng xóm trong file không phải topology khác nhau; comparison là set, không phải bytewise SHA.

**Giới hạn:** Chỉ 2 BUILD/arm, một dataset, chưa cross-seed, cross-thread. Exact edge overlap không chứng minh QPS/Recall như nhau. Nếu edge variation nhỏ và Recall H26-P0 gần như không đổi, dừng nhánh schedule sensitivity; nếu lớn, kiểm toán confound random seed/algorithm/intervention trước. Deterministic parallel ANN đã được ParlayANN (PPoPP 2024) nghiên cứu, nên không claim novelty.
