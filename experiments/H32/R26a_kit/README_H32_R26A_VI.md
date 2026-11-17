# H32-R26a — SIFT1M cùng seed: PiPNN không dump / có dump

## Mục tiêu khoa học

Xác minh trên **SIFT1M 1.000.000 ×128 float32** rằng bản PiPNN gốc đã áp dụng patch tác giả Three Stages xây hai graph **bitwise-identical** khi chỉ khác bật/tắt xuất reservoir ứng viên trước final prune. Khi vượt qua gate này, giữ **đúng pool SIFT1M đó** để cho chạy các ending khác nhau. Không tái sử dụng graph H31 nếu graph được xây từ seed/params khác.

**Không phải** PiPNN II, H17 speed comparison, final Recall search benchmark hoặc thuật toán H33. Các BUILD là kiểm tra tính đúng, hai lượt không đủ đánh giá throughput và chạy tuần tự không cân bằng thứ tự; `table_size=160` là tham số khảo sát pool, không mặc định bằng H17 gốc.

## Chạy trên máy Ubuntu

Tải ZIP vào `~/Downloads`, mở Terminal và chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H32/R26a_kit
cd ~/ann-task-a/experiments/H32/R26a_kit
unzip -o ~/Downloads/H32_R26a_sift1m_pool_gate_kit.zip -d .
sha256sum -c SHA256SUMS.txt
bash h32_r26a_build_and_dump.sh
```

Không dùng `source` hoặc `. h32_r26a_build_and_dump.sh`. Shell chính không tự đóng nếu script lỗi. Nếu lỗi, xem log trong output timestamp được thông báo. Không cần chạy lại R22, R23, R24, R25.

## Tham số cố định

- Source PiPNN original commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`, author patch + local CMake fix + pinned portability header. Executable SHA256 `5bc2bb9fb1c41e8dcfc7f052b63afde8ff977fec8aa810e81a1cfe3e3e49a68c`.
- Input `~/ann-task-a/data/sift1m.fbin`; file header (`uint32` N,D) và dung lượng 512000008 bytes được kiểm tra.
- `PARLAY_NUM_THREADS=4`, `taskset -c 0,2,4,6`; các CPU ID này phải nằm trong allowed CPU affinity.
- `PIPNN_SEED=20261029`, `PIPNN_DETERMINISTIC=1`.
- `-num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 -table_size 160 -k 10`.
- Hai BUILD cùng cấu hình, một `nodump.graph`, một `dump.graph` + `dump.candidates.i32` từ `PIPNN_DUMP_C=160`.
- Dự kiến file dump theo định dạng `1,000,000 ×160 ×4 = 640,000,000 bytes` (~610,35 MiB). Đây là **kích thước file**, không phải peak RAM. Trước khi BUILD script ghi free/df; `/usr/bin/time -v` ghi peak RSS riêng từng process.
- Không truyền query hoặc GT vào binary, nên ANN Search không chạy. Graph đã được lưu, không chép ghi đè vào H31/H32.

## Kết quả và dừng

Output `~/ann-task-a/experiments/H32/H32_R26a_pool_<timestamp>/` chứa: raw BUILD logs, `nodump.time.log`, `dump.time.log`, cả hai graph, `dump.candidates.i32`, provenance.txt, SHA đầu vào/binary, `r26a_report.json`, `r26a_summary.txt`.

Script kiểm tra toàn bộ edges theo khối để phát hiện out-of-range, self-loop, duplicate directed edge, lệch `n/degree/maxdegree` và kích thước serialized graph. Matrix ứng viên được đọc bằng NumPy memmap theo khối, kiểm tra ID, -1 padding, SHA, candidate slots, self-candidate count. Sau đó so sánh **SHA256 hai graph**.

Chỉ khi thấy `R26A_GATE=R26A_SOURCE_POOL_GRAPH_GATE_PASS` và `R26A_GRAPH_NONINTERFERENCE=PASS` mới coi R26a khả thi. Nếu graph khác, `R26A_GRAPH_NONINTERFERENCE=FAIL` và R26a STOP; do nguyên nhân nondeterminism hoặc dump interaction chưa rõ, **không tự ghi là thuật toán lỗi**.

Nếu script dừng, xem `R26A_STOP code=...` và các file `.build.log`, `.time.log`. Không tự đổi commit/source, seed, graph, searcher hoặc phiên bản thư viện. Không làm clean hoặc xóa output lỗi trước khi điều tra.

Sau R26a PASS: cần chuyển sang kết thúc một graph SIFT1M trên cùng pool rồi đánh giá bằng **native ParlayANN searcher**, với graph arc/bytes cap và Recall tradeoff. Do các ending và spine vốn có trong prior art Three Stages, chỉ tái lập chúng chưa chứng minh tính mới.
