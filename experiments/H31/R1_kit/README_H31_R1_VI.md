# H31-R1 — Directed reachability từ entry 0 (READ ONLY)

**Mục đích:** Kiểm toán directed BFS trên ba file graph có sẵn trong inventory H31-R0, sau khi H31-R0b đã xác nhận định dạng và miền giá trị GT. Không BUILD lại, không chỉnh graph, không chạy SEARCH/Recall/QPS và không sử dụng `numpy`, `perf` hoặc `sudo`.

## Tại sao entry=0?

Mã ParlayANN được ghim ở commit `a48c6a3`, file `algorithms/vamana/neighbors.h`, trong `ANN_Quantized()`, gán `start_point=0` cả khi đọc graph đã BUILD (graph_built) lẫn sau khi BUILD. Đây là **entry của native ParlayANN common searcher** mà nhóm đã dùng. Không suy rằng entry này luôn đúng với tất cả phần mềm hoặc các bản fork khác. Nguồn: https://github.com/cmuparlay/ParlayANN/blob/a48c6a3/algorithms/vamana/neighbors.h

## Chạy Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H31/R1_kit
cd ~/ann-task-a/experiments/H31/R1_kit
unzip -o ~/Downloads/H31_R1_entry_bfs_kit.zip -d .
python3 h31_r1_bfs.py --mode selftest
python3 h31_r1_bfs.py --mode run \
  --inventory ~/ann-task-a/experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json
```

Nếu `H31R1_DONE=/home/tai/...`, lấy báo cáo:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H31/H31_R1_2* | head -n 1)
cat "$OUT/h31_r1_summary.txt"
```

Nếu gặp `H31R1_FAIL_CLOSED`, dán nguyên lỗi, **không** BUILD lại hoặc sửa dữ liệu/graph. Script kiểm tra lại SHA256 của ba graph trước BFS, fail-closed nếu nội dung graph đổi so với inventory H31-R0. Script đọc graph bằng mmap readonly và BFS bằng queue `array('I')` để giảm RAM.

## Giới hạn diễn giải

- `REACH0`/`UNREACH0`: số vertex có thể/không thể đi đến từ node 0 theo directed edges. **Không** bằng số đỉnh indegree=0.
- `BFS_HOPS_MAX`, `P50/P95/P99_HOPS`: số bước ngắn nhất **không trọng số theo graph**, khác số expansion hay hop của beam/greedy ANN search.
- Vamana ~27,64 triệu cạnh và PiPNN ~22,79 triệu cạnh — khác ngân sách graph; mọi so sánh là descriptive, không phải chứng minh ưu thế equal-index-budget.
- Không đo search QPS, Recall, graph navigability theo beam, search-path diversity hoặc intra-query parallelism. Muốn trả lời các câu hỏi đó phải có H31-R2 phù hợp.
- H31-R0b đã PASS định dạng/giá trị GT, không cần chạy lại GT ở R1. Chỉ khi chạy lại native search cần khớp source/seed/search flags.

## Kiểm thử trước khi giao

Selftest trên graph synthetic 5 nodes gồm hai SCC tách rời và không có đỉnh zero-indegree (chứng minh indegree 0 không đồng nghĩa số unreachable), thêm graph orphan, SHA tampering, truncated graph, invalid target ID; kiểm tra file output tổng hợp trên synthetic khi gọi code trực tiếp. Những kiểm thử này **không thay thế** thực nghiệm trên SIFT1M.
