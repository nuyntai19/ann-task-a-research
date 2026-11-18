# Chạy PiPNN R86 trên máy khoa-linux

Toàn bộ cấu hình cục bộ nằm trong `local_setup/khoa-linux/`. Đường dẫn project
được tìm từ vị trí script, nên có thể chuyển cả repository sang thư mục khác.
Mã thuật toán R86 và các script thí nghiệm lịch sử được giữ nguyên.

## Bắt đầu

Từ thư mục repository:

```bash
cd /home/khoa/research/PiPNN/ann-task-a-research
bash local_setup/khoa-linux/setup.sh
```

Lần đầu cần internet đến GitHub và GitLab để tải thư viện. Script không dùng
sudo và không cài package toàn hệ thống. Máy này đã có GCC 13.3, CMake 3.28,
Make, Git, Python 3.12 và NumPy. Nếu chạy trên máy khác mà thiếu NumPy, cài
`python3-numpy` hoặc NumPy trong môi trường Python đang dùng.

Script lần lượt:

1. Tải và xác minh bốn dependency theo commit trong `deps.lock.json`.
2. Build bản `stock_off` (H17 OFF, counters OFF) và `h17_on` (H17 ON, counters ON).
3. Chạy bài kiểm tra primitive `r70_native_tests correctness` có sẵn.
4. Với mỗi bản, tạo dữ liệu synthetic 2.048 vectors × 128 chiều, 32 queries;
   tính exact ground truth mới; build graph thật, kiểm tra cấu trúc và chạy
   tìm kiếm bằng evaluator gốc với beam 10/20/40/80/160.

Chỉ khi hoàn thành tất cả bước mới in `LOCAL_SETUP_AND_SMOKE_PASS`.
Mỗi lần chạy tạo thư mục dữ liệu/kết quả và log riêng, không ghi đè lần trước.
Nếu có lỗi build/chạy, script trả exit code khác 0; đọc log tương ứng để sửa tiếp.

Máy có khoảng 15 GiB RAM; mặc định chỉ compile song song hai job:

```bash
BUILD_JOBS=2 bash local_setup/khoa-linux/setup.sh
```

Sau khi đã tải đủ dependency, có thể build lại không cần mạng:

```bash
bash local_setup/khoa-linux/setup.sh --offline
```

## Chạy dữ liệu SIFT có sẵn trên máy

Đã tìm thấy dữ liệu tại project PipeANN bên cạnh:
`/home/khoa/research/PipeANN/data/sift1m_run/converted/`.
Runner tự tìm đường dẫn tương đối này hoặc `data/` trong repository.
Nó chỉ đọc dữ liệu gốc và ghi bản subset mới trong thư mục cục bộ này.

Sau khi setup thành công:

```bash
python3 local_setup/khoa-linux/run.py --dataset sift
python3 local_setup/khoa-linux/run.py --dataset sift --variant h17_on
```

Mặc định dùng 10.000 base vectors đầu, 32 queries đầu, tối đa bốn thread.
Ground truth được tính lại chính xác trên subset, không dùng GT của SIFT1M.
Đây là kiểm tra hoạt động với SIFT10K, chưa phải benchmark toàn bộ SIFT1M.

Chọn dữ liệu hoặc kích thước khác:

```bash
python3 local_setup/khoa-linux/run.py --dataset sift \
  --sift-dir /home/khoa/research/PipeANN/data/sift1m_run/converted \
  --rows 100000 --queries 100 --threads 4
```

`--sift-dir` cần có `sift_base.fbin` và `sift_query.fbin`: header hai số uint32
little-endian `(n, d)`, tiếp theo là `n*d` float32. Runner kiểm tra kích thước
file trước khi đọc. GT local có header `(n_queries, k)` (thường k=100), tiếp
theo là IDs uint32 rồi khoảng cách bình phương float32 theo định dạng native.

### Ground truth đã có trong data

Khi dùng **toàn bộ base** trong `sift_base.fbin`, runner tự tìm
`sift_groundtruth.ivecs` hoặc `sift_groundtruth.ibin` trong `--sift-dir` để
tái sử dụng. Có thể chạy toàn bộ query hoặc một prefix (`--queries 100`):
GT sẽ lấy đúng các hàng query đó. Trên máy này, `data/sift_groundtruth.ivecs`
có 10.000 hàng × 100 neighbor IDs cho base SIFT1M.

Script kiểm tra kích thước, số query, phạm vi/độ trùng ID, thứ tự khoảng cách,
và đối chiếu exact top-k trên ba query mẫu (đầu/giữa/cuối phần được chọn).
Đây là kiểm chứng mẫu, không chứng nhận lại toàn bộ GT. Với `.ivecs`, script
chuyển IDs sang định dạng PiPNN và tính khoảng cách tới các ID đã có để ghi
payload native; không tìm lại top-100 trên một triệu base cho mọi query.

Log in `GT_MODE=REUSE_EXISTING` khi dùng GT có sẵn. Khi chạy tập con base như
SIFT10K/100K từ file base SIFT1M, GT của SIFT1M không còn đúng và script sẽ
tính lại, in `GT_MODE=EXACT_RECOMPUTE`. Synthetic hoặc thiếu GT tương thích
cũng dùng nhánh tính lại. `data/.../manifest.json` ghi mode, nguồn GT, SHA256
và phạm vi kiểm chứng; metadata này cũng nằm trong summary của run.

`sift_groundtruth.ibin` chấp nhận dạng IDs-only hoặc IDs + distances. Runner
tính lại khoảng cách của các ID được cung cấp thay vì tin payload distance
cũ. GT không hợp lệ sẽ báo lỗi, không âm thầm dùng dữ liệu sai.

Nếu một tiến trình cũ vẫn đang tính GT, mã mới chỉ có tác dụng khi khởi chạy
lại script; việc sửa file Python không thay đổi tiến trình đã chạy.

Chỉ chuẩn bị dữ liệu, chưa cần binary:

```bash
python3 local_setup/khoa-linux/run.py --dataset sift --prepare-only
```

## Đặt tên thư mục kết quả

Thêm `--run-name` để đặt chính xác tên thư mục ngay dưới `runs/`, không có
đuôi ngẫu nhiên. Ví dụ SIFT1M, H17 ON, 100 queries, 4 thread, lần lặp thứ nhất:

```bash
python3 -u local_setup/khoa-linux/run.py \
  --dataset sift --sift-dir "$PWD/data" \
  --rows 1000000 --queries 100 --threads 4 \
  --variant h17_on --timeout 3600 \
  --run-name sift1m_h17_on_q100_t4_r1
```

Kết quả lưu đúng tại `local_setup/khoa-linux/runs/sift1m_h17_on_q100_t4_r1/`,
gồm graph, build/search log, latency CSV, counters và summary.
`summary.json` cũng ghi `run_name`. Khi chạy lần hai, đổi tên thành
`sift1m_h17_on_q100_t4_r2`.

Tên được phép dài 1-128 ký tự, bắt đầu bằng chữ/số, dùng chữ ASCII, số,
`_`, `-`, `.`; không nhận đường dẫn. Nếu thư mục/file/symlink cùng tên đã tồn
tại, script báo lỗi trước khi chuẩn bị dữ liệu và giữ kết quả cũ. Không dùng
`--run-name` cùng `--prepare-only`. Bỏ tùy chọn này thì giữ cách đặt tên
ngẫu nhiên như trước. Thư mục dữ liệu/GT trong `data/` vẫn được tạo riêng.

## Nơi lưu mọi thứ

| Đường dẫn trong thư mục này | Nội dung |
|---|---|
| `CHANGES.md` | Giải thích từng thay đổi và khác biệt với pipeline lịch sử |
| `reference_originals/` | Bản sao README, cấu hình build và script gốc để đối chiếu |
| `original_files.sha256.json` | SHA256 của các file tham chiếu trước khi làm |
| `machine.json` | Thông tin máy, compiler, commit repository ban đầu |
| `validation.json` | Kết quả kiểm tra đã thực hiện trong phiên thiết lập |
| `deps.lock.json` | URL và commit của từng thư viện |
| `deps/` | Source thư viện được tải về |
| `build/stock_off/`, `build/h17_on/` | Build độc lập; có `compile_commands.json` |
| `logs/setup-*.log` | Log tải thư viện, configure, compile và smoke |
| `data/` | Dữ liệu kiểm tra cùng GT và manifest có SHA256 |
| `runs/` | Graph, log build/search, `query_latency.csv`, counters và `summary.json` của từng lần chạy |

`deps/`, `build/`, `logs/`, `data/`, `runs/` được bỏ qua bởi Git nhưng vẫn lưu
trên ổ đĩa. Mỗi run ghi lệnh, binary/source SHA256, số thread, dataset, graph
audit và Recall@10/QPS trong `summary.json`. H17 ON kiểm tra các file counters
có nội dung và JSON hợp lệ; không thay thế bài kiểm toán counter của R86.

## Latency tìm kiếm

Từ lần cập nhật latency, vẫn dùng lệnh chạy cũ:

```bash
python3 local_setup/khoa-linux/run.py --dataset sift
```

Mỗi run lưu thêm:

- `query_latency.csv`: cột `beam,query_id,latency_us`; một số đo cho mỗi query
  tại mỗi beam. Đơn vị microsecond (1.000 microsecond = 1 millisecond).
- `summary.json`: mỗi phần tử `search` có `latency_us` gồm `query_count`,
  `mean`, `p50`, `p95`, `p99`, `min`, `max`.
- `search.log`: mỗi dòng `LOCAL_RECALL_ROW` ghi cùng lúc `beam`, `recall`,
  `qps`, `avg_cmps`, `latency_mean_us`, `latency_p50_us`, `latency_p95_us`,
  `latency_p99_us`. Nhờ đó có thể đọc đầy đủ kết quả của một beam trên một dòng.

Thời gian được đo bằng `std::chrono::steady_clock` ngay trong callback xử lý
query của `qsearchAll` native, gồm tìm kiếm và tạo kết quả cho query đó.
Nó không gồm chờ scheduler, tải graph/dataset, tính Recall/ground truth hoặc
ghi CSV. Các query vẫn chạy song song theo `--threads`, nên đây là thời gian
xử lý từng query dưới mức đồng thời đó. QPS vẫn đo cả batch và có thêm chi phí
nhỏ của bộ đếm giờ; không được suy latency từng query từ `1/QPS`.

Percentile dùng nội suy tuyến tính của NumPy trên các số đo thực tế. Mặc định
chỉ 32 queries, mỗi query chạy một lần cho mỗi beam, chưa có warmup/repetition;
p95/p99 của bài kiểm tra nhỏ này chưa phải benchmark latency ổn định. Có thể
tăng `--queries` khi cần tập mẫu lớn hơn.

### Chọn danh sách beam

Thêm `--beams` để chọn beam cần đo theo đúng thứ tự, ví dụ:

```bash
python3 -u local_setup/khoa-linux/run.py \
  --dataset sift --sift-dir "$PWD/data" \
  --rows 1000000 --queries 10000 --threads 4 --variant h17_on \
  --timeout 3600 --beams 10,20,40,80,100,120,140,160 \
  --run-name sift1m_h17_on_q10000_t4_beams8_r1
```

Nếu chỉ muốn từ 80 đến 160, dùng `--beams 80,100,120,140,160`.
Đây là danh sách thay thế toàn bộ danh sách mặc định; mỗi giá trị chỉ xuất
hiện một lần và phải >= 10 (vì evaluator tìm top-10). Không truyền tùy chọn
thì vẫn dùng `10,20,40,80,160`. Log/CSV/summary có kết quả và latency cho mọi
beam được chọn; `summary.json` ghi thêm danh sách `beams`. Chỉ build graph
một lần, sau đó search cùng graph lần lượt theo các beam.

Tùy chọn này cần evaluator mới; hai biến thể trên máy hiện tại đã được build
lại. Trên bản checkout khác, chạy `setup.sh --offline` nếu đã có dependency.

Mã gốc không bị sửa: CMake tạo bản header có timer trong
`build/<variant>/generated/local_latency/` dành riêng cho evaluator. Cần build
lại evaluator một lần sau cập nhật này; hai bản trên máy hiện tại đã được
kiểm tra theo hồ sơ trong `change_history/20261118_latency/`.

Kiểm tra aggregation và instrumentation:

```bash
python3 local_setup/khoa-linux/test_latency.py
python3 local_setup/khoa-linux/test_ground_truth.py
```

## Phạm vi kiểm tra

Bộ build cục bộ bỏ bước cấu hình Mirage/Faiss vốn không dùng bởi PiPNN và
không có trong cây source R86 được clone. Nó dùng trực tiếp target CMake
`algorithms/PipNN` và source thuật toán gốc. `local_graph_recall` là adapter
cục bộ cho evaluator native để nhận kích thước dữ liệu nhỏ; các evaluator
R70/R72 lưu trữ chỉ chấp nhận kích thước cố định 100K/1M.

Các commit thư viện lấy từ script R86 HW85 gốc. Kết quả trên CPU/compiler của
máy này không được coi là tái hiện các graph SHA, thời gian hay gate lịch sử.
Các script chiến dịch cũ vẫn cần artifact/dataset lịch sử riêng; chúng không
phải điểm vào của cấu hình cục bộ này.

Xem `validation.json` để biết bước nào đã chạy thật. Chỉ có dữ liệu hoặc
kiểm tra cú pháp PASS không đồng nghĩa với compile hoặc tìm kiếm PASS.
