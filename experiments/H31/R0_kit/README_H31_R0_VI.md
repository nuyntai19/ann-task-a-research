# H31-R0 — Existing Graph & Evidence Provenance Audit

**Chỉ đọc; không BUILD, không SEARCH, không sửa graph, không cần `pip install`.**

## Mục tiêu

Kiểm tra file `.graph` của ParlayANN Vamana và PiPNN (Stock/Top-2) đã tồn tại trong `~/ann-task-a`. Đọc header, toàn bộ degrees, toàn bộ neighbor IDs để kiểm tra schema, đếm zero in/out-degree, tính SHA256 và tổng số directed edges; kiểm tra kích thước/header dữ liệu SIFT1M; ghi danh mục file evidence đã tìm thấy.

**Không** được hiểu nội dung này là kết quả search mới, Pareto matched Recall–QPS, tính mới thuật toán, hay xác minh seed/build flags: các yếu tố đó cần log và đối chứng riêng.

## Cách chạy từ Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H31/R0_kit
cd ~/ann-task-a/experiments/H31/R0_kit
unzip -o ~/Downloads/H31_R0_existing_graph_audit_kit.zip -d .
python3 h31_r0_audit.py --mode selftest
python3 h31_r0_audit.py --mode discover
python3 h31_r0_audit.py --mode auto
```

Nếu `auto` in `H31R0_NEEDS_EXPLICIT_SELECTION`, đó là tình huống an toàn khi thiếu/không duy nhất các file. Dùng đường dẫn chính xác từ `discover`; **không đổi tên graph và không tự lấy graph 100K làm SIFT1M**.

```bash
python3 h31_r0_audit.py --mode run \
  --graph VAMANA=/absolute/path/to/vamana_sift1m_4t.graph \
  --graph STOCK=/absolute/path/to/r1_stock.graph \
  --graph TOP2=/absolute/path/to/r1_top2.graph
```

Chú ý: ba đường dẫn trong ví dụ trên là **placeholder**, cần thay theo `discover`, không copy nguyên nếu file không tồn tại.

Khi lệnh in `H31R0_DONE=...`:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H31/H31_R0_2* | head -n 1)
cat "$OUT/h31_r0_summary.txt"
```

Gửi summary kèm (nếu cần) danh mục log. File `h31_r0_inventory.json` ghi graph file SHA, cấu trúc, dataset status và evidence log paths.

## Chính sách công bố

- `zero_indegree_vertices` không phải reachable-from-entry. H27 đã chạy BFS với graph H26, không cần lặp lại trong H31-R0.
- `graph_only_bytes_per_vector` không bao gồm base-vector bytes, index metadata đầy đủ.
- Chỉ tên graph hoặc SHA **không xác nhận cùng seed, args, source commit**; nếu file không rõ nguồn, dán log để kiểm định trước khi kết luận.
- H17 và H26 P0 giảm BUILD wall trên SIFT1M 4 lõi nhưng không chứng minh algorithm novelty.
- H31-R0 **không** khẳng định Vamana và PiPNN đã có đúng matched degree/index bytes, Recall, hay tìm kiếm nội truy vấn đa luồng.
- Kết quả lịch sử được ghi trong JSON để đối chiếu nguồn, không là phép đo mới của H31.
- Không gọi `sudo`, `perf`, `sysctl`, hay thay đổi repository.

Graph format tham chiếu: `cmuparlay/ParlayANN@a48c6a3 algorithms/utils/graph.h` và `ParAlg/PiPNN@443a328 algorithms/utils/graph.h`, little-endian uint32 header + degrees + packed neighbors.
