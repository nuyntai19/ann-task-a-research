# H24-R0f — Đối chứng PiPNN với Dense LOW/HIGH trên SIFT1M

**Mục tiêu:** kiểm tra liệu Dense LOW/HIGH còn là baseline đáng cải tiến khi đánh giá cùng một bộ tìm kiếm, cùng ID dữ liệu SIFT1M, cùng truy vấn và ground truth. Đây **không phải phép thử STH**, không có graph-search rescue và không khẳng định novelty.

## 1. Kết quả đã có trước R0f

| Baseline cũ | BUILD | Lưu ý |
|---|---:|---|
| PiPNN f30 / H17, 4 nhân vật lý | 49,76 giây | Baseline cũ, chưa tuning-matched với Dense |
| Dense LOW `L=1200,m=3,C=200`, 4 luồng | 91,39 giây | H24-R0e, một seed |
| Dense HIGH `L=1200,m=5,C=200`, 4 luồng | 151,53 giây | H24-R0e, một seed |

Số liệu H24-R0e là **BUILD**, không phải thời gian của CLI gồm cả tìm kiếm. Trên cùng lưới `ef` nhưng dưới searcher native khác nhau, QPS **không đủ điều kiện** đối chiếu xuyên-baseline PiPNN ↔ Dense. R0f giải quyết đúng điểm này.

## 2. Giao thức tìm kiếm chung

- Cả ba graph được đọc từ cùng định dạng CSR của ParlayANN: `u32 n`, `u32 max_degree`, `u32 degree[n]`, `u32 edge_ids[Σdegree]`.
- **Một evaluator C++ độc lập**; một luồng tìm kiếm; khoảng cách Euclidean bình phương float32; một quy tắc best-first beam, cùng các `ef=60,100,140,200,300,400`.
- Cùng `sift1m.fbin`, 1.000 truy vấn đầu `sift1m_queries.fbin`, cùng Top-10 GT đã lưu tại H24-R0e.
- Hai chế độ khởi tạo: `entry1` (đỉnh 0) và `entry8` (cùng tám ID cố định). Mọi chi phí tính khoảng cách từ entry đều được đếm.
- Hai lượt đo mỗi ef sau warmup; lưu riêng wall/QPS, distances/query, Recall@10, số cạnh graph và graph bytes.
- Phân tích Pareto trên các ngưỡng Recall 99,0%, 99,5%, 99,8% **tại các điểm ef đã đo**, không nội suy.
- **Giới hạn:** `entry1`/`entry8` không phải searcher được tuning của các paper. Mục tiêu là kiểm soát searcher chung, không thay thế benchmark native chính thức. Số cạnh/degree cap của PiPNN và Dense chưa matched; so sánh chỉ định hướng cổng nghiên cứu.

## 3. Tại sao phải dựng lại Dense?

Lần H24-R0e xuất `gate_results.json`, nhưng log BUILD **không chứa toàn bộ cạnh**. Để đo bằng cùng searcher, ta cần dump CSR graph. Bộ chạy R0f sẽ dựng lại Dense m=3 và m=5 **một lượt mỗi cấu hình** với đúng commit và tham số đã dùng, thêm duy nhất `--dump-graph`. Graph PiPNN có sẵn ở `~/ann-task-a/results/pipnn_sift1m_4t.graph`, nên **không** dựng lại PiPNN.

Đây là khoảng 2 lượt BUILD bản gốc để xuất graph. Thư mục R0e, kết quả H17–H23, source Graft và graph PiPNN **được giữ nguyên**. Nếu phát hiện graph export đã tồn tại, chương trình kiểm tra định dạng và tái dùng; nếu thấy log dở dang thì dừng, không ghi đè.

## 4. Thực hiện trên Ubuntu

Tải file `H24_R0f_common_search_kit.zip` về `~/Downloads/`, sau đó chạy:

```bash
cd ~/ann-task-a/experiments/H24/kit
unzip -o ~/Downloads/H24_R0f_common_search_kit.zip -d .
source ~/ann-task-a/.venv/bin/activate

# Kiểm tra đường dẫn, không BUILD, không xuất graph
python3 h24_r0f_compare.py --mode plan

# Chỉ sau khi xác nhận các đường dẫn đúng
python3 h24_r0f_compare.py --mode run
```

**Không cần tải lại dữ liệu hoặc biên dịch lại PiPNN.** R0f sẽ kiểm tra Graft commit đúng `a032c2d6cfb2c087d3b8abca028c745186501976`, bộ nhớ/disk, và kiểm tra **toàn bộ** ánh xạ ID + vector của file `X.npy` H24 so với `sift1m.fbin`. Ở n=1M, tập con sort chính là 0..999999; nếu dữ liệu sai, tự dừng, không so sánh.

Nếu file PiPNN ở chỗ khác, chỉ rõ:

```bash
python3 h24_r0f_compare.py --mode run --pipnn-graph '/duong/dan/graph_pipnn_cu.graph'
```

Có thể xem file graph PiPNN thật bằng:

```bash
find ~/ann-task-a/results -maxdepth 2 -type f -name '*.graph' -printf '%p  %s bytes\n'
```

## 5. Xem kết quả

```bash
OUT=~/ann-task-a/experiments/H24/r0f_common_search_sift1m_seed42
cat "$OUT/comparison.json"

# Chỉ đọc lại kết quả đã có, không BUILD
python3 ~/ann-task-a/experiments/H24/kit/h24_r0f_compare.py --mode inspect
```

Trong thư mục này cũng có:

- `low.graph`, `high.graph`: Dense CSR mới xuất; `pipnn.graph` không được tạo mới vì dùng graph cũ nguyên bản.
- `export_low_m3.log`, `export_high_m5.log`: BUILD tái xuất graph.
- `search_{pipnn,low,high}_{entry1,entry8}.log`: 6 log search chung.
- `gold10.rawi32`, `entries_1.rawu32`, `entries_8.rawu32`, `provenance.json`, `comparison.json`.

**Gửi cho tôi `comparison.json`**. Nếu có lỗi, gửi thông báo và tên log phát sinh. Không xóa các file hoặc kết quả trước.

## 6. Cổng quyết định nghiên cứu sau kết quả

- Nếu PiPNN xây nhanh hơn, bytes thấp hơn **và** cho Recall–QPS bằng hoặc tốt hơn Dense tại các mục tiêu chọn trước: **không tiếp tục STH dựa trên Dense hiện tại**; cần thay low-builder hoặc đổi hướng.
- Nếu Dense có lợi thế rõ về Recall–QPS tại một dải Recall nhưng BUILD đắt: mới cân nhắc H24-R1 oracle (khảo sát chọn lọc 1–10% source rows); chưa có quyền tuyên bố STH mới.
- Nếu có lợi thế nhưng chủ yếu do Dense nhiều cạnh hơn, cần kiểm chứng degree/bytes-matched trước bất kỳ kết luận khoa học nào.
- Không biến chênh BUILD hoặc QPS tại một seed thành tính mới, không dùng tốc độ của searcher độc lập để tuyên bố tốc độ native paper.

**Trạng thái trước khi chạy R0f: HOLD.**
