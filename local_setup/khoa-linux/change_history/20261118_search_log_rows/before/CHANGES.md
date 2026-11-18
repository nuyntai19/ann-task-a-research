# Nhật ký điều chỉnh cho khoa-linux

Ngày thiết lập: 2026-11-18. Thư mục lưu mọi thay đổi: `local_setup/khoa-linux/`.

## Vấn đề của bản clone

- Script R86 cũ dùng `$HOME/ann-task-a` và các build/dependency/artifact trên
  máy tác giả; những file đó bị loại khỏi source-only mirror.
- CMake R86 gốc gọi `external/mirage`, nhưng thư mục đó không có trong cây
  source R86. PiPNN không cần Mirage/Faiss để build.
- Các evaluator lưu trữ R70/R72 yêu cầu cố định SIFT100K/300 queries hoặc
  SIFT1M/10K queries, không phù hợp với một bài kiểm tra nhỏ ban đầu.
- Dataset SIFT đã có trên máy này trong project PipeANN bên cạnh, nhưng
  graph/GT của một subset không thể dùng chung với GT toàn bộ SIFT1M.

## File mới và mục đích

- `CMakeLists.txt`: điểm vào build riêng, chỉ thêm PiPNN cùng dependency;
  tái sử dụng nguyên target CMake R86, C++17, Release, `-march=native`,
  `-ffast-math`, các cờ H17/counters gốc. Không cấu hình Mirage/Faiss.
- `deps.lock.json`: pin bốn commit ParlayLib/Eigen/Abseil/Highway từ script
  `R86_Highway_R85_Four_Binaries_v1_0.sh` đã lưu trong bản tham chiếu.
- `fetch_deps.py`: shallow-fetch đúng commit; kiểm tra HEAD và local changes;
  có chế độ offline; không tự ghi đè thư viện có sửa đổi.
- `setup.sh`: configure/build riêng hai biến thể stock OFF và H17 ON;
  mặc định hai job để phù hợp RAM; chạy primitive tests và smoke cả hai;
  giữ log và dừng ngay khi có lỗi.
- `evaluate.cc`: adapter dùng reader và `checkRecall` R86 gốc, cho phép
  kích thước dữ liệu biến đổi. Không thay đổi thuật toán tìm kiếm.
- `run.py`: đường dẫn theo vị trí file, tự phát hiện dữ liệu SIFT cục bộ,
  chuẩn bị synthetic hoặc subset SIFT, tính exact GT mới, chạy build/search
  trong thư mục riêng; kiểm tra graph/counter output và lưu provenance.
- `.gitignore`: chỉ bỏ qua dependency, build, data và kết quả phát sinh trong
  thư mục cục bộ này; các script/cấu hình/nhật ký vẫn được Git nhận diện.
- `README.md`: các lệnh chạy và giới hạn kiểm tra trên máy người dùng.
- `machine.json`, `original_files.sha256.json`, `reference_originals/`:
  thông tin máy/commit và bản sao trước khi làm để đối chiếu.
- `validation.json`: ghi đúng các kiểm tra đã thực hiện và blocker còn lại.

## File gốc đã thay đổi

Không có file nào bên ngoài `local_setup/khoa-linux/` được chỉnh sửa.
Các bản trong `reference_originals/` là bản tham chiếu trước khi làm, không
phải source đang được build. Không có thay đổi cấu hình hệ điều hành/sudo.

## Ghi chú dependency và kiểm chứng

Pin dependency giữ nguyên định danh từ tài liệu thí nghiệm. Bản build mới
vẫn cần kiểm chứng trên compiler/CPU hiện tại; không tái sử dụng binary SHA
của máy tác giả. `LOCAL_FUNCTIONAL_CHECK_PASS` chỉ xác nhận pipeline cục bộ
đã hoàn thành; không công nhận gate/benchmark lịch sử hay counter identities.

Phiên Codex ban đầu không phân giải được `github.com`, vì thế lần tải
ParlayLib đầu tiên dừng trước compile. Xem `validation.json` cho trạng thái
kiểm tra cụ thể và log. Khi mạng sẵn sàng, chạy lại `setup.sh` để tiếp tục.

## Bổ sung log latency tìm kiếm — 2026-11-18

- Bản sao các file cục bộ trước khi sửa nằm ở
  `change_history/20261118_latency/before/`, kèm SHA256 và kết quả search baseline.
- `instrument_latency.py` tạo bản sao header native trong build và chỉ chèn
  timer vào hai callback query của `qsearchAll` (start cố định và random).
  Script dừng với lỗi nếu source gốc đổi cấu trúc không khớp điểm chèn.
- `latency_probe.h` dùng steady clock để đo thời gian từng query; mỗi worker
  ghi vào ô riêng; CSV được ghi sau khi mọi query hoàn tất.
- `evaluate.cc` dùng header được instrument, ghi raw CSV cho cả năm beam;
  có tham số cuối tùy chọn `[LATENCY.csv]`, mặc định `query_latency.csv`,
  từ chối ghi đè file đã có.
- `run.py` giữ lệnh CLI cũ, truyền đường dẫn CSV riêng mỗi run, xác minh đủ
  query/beam và tính mean/p50/p95/p99/min/max bằng NumPy; lưu vào
  `summary.json` và `search.log`. Manifest ghi thêm SHA256 của mã cục bộ.
- `test_latency.py` kiểm tra percentile trên tập biết trước, dữ liệu sai/thiếu,
  và xác nhận instrumentation không đổi mã native ngoài hai timer.
- Mọi chỉnh sửa vẫn nằm trong `local_setup/khoa-linux/`; mã R86 gốc giữ nguyên.
- Chi tiết compile, so sánh baseline và chạy SIFT nằm trong
  `change_history/20261118_latency/validation.json` khi kiểm tra hoàn tất.
