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
file trước khi đọc. GT local có header `(n_queries, 100)`, tiếp theo là IDs
uint32 rồi khoảng cách bình phương float32, theo định dạng native của PiPNN.

Chỉ chuẩn bị dữ liệu, chưa cần binary:

```bash
python3 local_setup/khoa-linux/run.py --dataset sift --prepare-only
```

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
| `runs/` | Graph, log build/search, counters và `summary.json` của từng lần chạy |

`deps/`, `build/`, `logs/`, `data/`, `runs/` được bỏ qua bởi Git nhưng vẫn lưu
trên ổ đĩa. Mỗi run ghi lệnh, binary/source SHA256, số thread, dataset, graph
audit và Recall@10/QPS trong `summary.json`. H17 ON kiểm tra các file counters
có nội dung và JSON hợp lệ; không thay thế bài kiểm toán counter của R86.

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
