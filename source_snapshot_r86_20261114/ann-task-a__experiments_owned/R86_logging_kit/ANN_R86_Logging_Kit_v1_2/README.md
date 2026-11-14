# ANN Task A — R86 Logging Kit v1.2

Bộ khung thực thi **không sửa nguồn PiPNN**. Hỗ trợ 4 nhóm file `.json` + `.log` A–D, và `E_manifest` cho giao thức; xuất CSV cùng thứ tự cột Google Sheet v1.2.

**Bằng chứng có sẵn:** R85 binary/provenance từ output Ubuntu người dùng gửi. **Chưa có counter chạy native R86**. `cpp/r86_counters.hpp` chỉ là mẫu hooks để Claude review trước khi gắn vào source R86 isolation. Không tự động đo Recall/NDC, phase time, allocations hoặc các chỉ số topology chưa có evaluator.

## 1. Yêu cầu

- Ubuntu, Python 3.9+; không cần thư viện Python ngoài.
- `/usr/bin/time` (thường ở package `time`) nếu dùng `capture-build`.
- C++17 nếu quyết định tích hợp `cpp/r86_counters.hpp`.

## 2. Tạo bộ file kết quả cho một experiment

Ví dụ **chỉ tạo file mẫu, không tạo số đo**:

```bash
unzip ANN_R86_Logging_Kit_v1_2.zip -d ~/ann-task-a/experiments/R86_logging_kit
cd ~/ann-task-a/experiments/R86_logging_kit/ANN_R86_Logging_Kit_v1_2
python3 scripts/r86_log.py init \
  --output ./runs --run-id R86_A3_100K_r1_ON --arm-id A3 \
  --n 100000 --dim 128 --C 64 --K 512 --N 2 --R 64 \
  --threads 1 --mode instrumented --storage-variant flat \
  --random-source 'std::random_device in recursively_sketch_wrapper' \
  --source "$HOME/ann-task-a/experiments/H85/r85_b1_controlled/isolation_v4/source"
```

Tạo: `runs/R86_A3_100K_r1_ON/{A_system.json,B_search.json,C_work.json,D_diagnostics.json,E_manifest.json,raw/,logs/,sheet_csv/}`.

**Mẫu A** không tự có `M_model` nếu chưa xác minh `sizeof(slot)`. Sau khi xác minh, thêm `--slot-bytes 8` (chỉ nếu actual sizeof thật bằng 8) khi khởi tạo hoặc dùng `set --group A --field slot_bytes ...`, sau đó tính lại model theo công thức.

## 3. Xuất nội dung một nhóm (không in cả log)

```bash
RUN=./runs/R86_A3_100K_r1_ON
python3 scripts/r86_log.py show --run "$RUN" --group C
python3 scripts/r86_log.py show --run "$RUN" --group C --metric W_L
python3 scripts/r86_log.py render-logs --run "$RUN"
cat "$RUN/logs/C_work.log"
```

## 4. Khi source PiPNN ON đã được review/instrument đúng

C++ gọi `r86::dump_jsonl("/path/counter_events.jsonl")` sau khi tất cả worker đã kết thúc. Từ file đó:

```bash
python3 scripts/r86_log.py import-counters --run "$RUN" \
  --events /path/counter_events.jsonl
python3 scripts/r86_log.py validate --run "$RUN"
```

Sự kiện JSONL phải có `pass_id` (0 = final), `depth` (null hoặc số >= 0), `metric_code`, `observed` **integer >= 0**. File định dạng trong `examples/counter_events.format.jsonl` chỉ để đọc schema: null chưa phải observation nên không import trực tiếp.

## 5. Chạy BUILD thực tế và lưu thời gian/RSS

Tạo một run **khác** với `--mode timed` và cùng dataset/protocol, nhưng executable `R86_COUNTERS=OFF`:

```bash
python3 scripts/r86_log.py init \
  --output ./runs --run-id R86_A3_100K_r1_OFF --arm-id A3 \
  --n 100000 --dim 128 --C 64 --K 512 --N 2 --threads 1 \
  --mode timed --source /actual/R86/source --binary /actual/R86/OFF/binary

# Replace the example command below with the ACTUAL PiPNN invocation,
# and run it ONLY after Day2 provenance/equivalence gates pass:
python3 scripts/r86_log.py capture-build \
  --run ./runs/R86_A3_100K_r1_OFF \
  --output-graph /path/to/real/graph.index \
  -- /path/to/real/R86_OFF/binary -some-verified-cli-args
```

`raw/stdout.log`, `raw/stderr.log`, `raw/gnu_time.txt` được lưu nguyên; `A_system.json` nhận T_build và peak RSS (không ghi phase time giả). Bản instrumented không được dùng làm clean timed benchmark.

## 6. Sau khi evaluator có kết quả thật

Chuyển đầu ra native evaluator sang `examples/search_results.template.json` với **số đo thật** và phương pháp `direct`/`interpolated`, sau đó:

```bash
python3 scripts/r86_log.py import-search --run ./runs/R86_A3_100K_r1_OFF \
  --results /path/to/evaluator_normalized_results.json
```

**Không** tự động suy diễn NDC từ `COMPARISONS` của PiPNN construction.

## 7. Xuất dữ liệu theo cột Google Sheet

```bash
python3 scripts/r86_log.py export-csv --run ./runs/R86_A3_100K_r1_OFF
ls ./runs/R86_A3_100K_r1_OFF/sheet_csv
```

Tạo 6 CSV: `RUN_INDEX`, `A_SYSTEM`, `B_SEARCH`, `C_WORK`, `D_DIAGNOSTICS`, `E_PROTOCOL`. CSV để **review trước khi nhập vào Google Sheet**; package không có quyền tự kết nối/sửa Sheets trên Ubuntu. Các giá trị chưa đo để ô trống.

## 8. Ý nghĩa của `.log` / `.json`

- `.json` = nguồn dữ liệu máy đọc được; từng nhóm A–E độc lập.
- `.log` = bản diễn giải đầy đủ tên chỉ số, hiển thị cả `NOT_MEASURED`.
- `raw/` = stdout, stderr, GNU time và counter JSONL gốc.
- `E_manifest` = bắt buộc, khóa liên kết `run_id`,`graph_id`, source, binary, data, threads, random source, rep.

## 9. Tiếp theo

Đọc `docs/R86_DAY2_INTEGRATION.md`, kiểm chứng source snapshot / cờ / binary, sau đó gửi patch C++ sang Claude kiểm tra **trước khi build**. Khi R86 counter gate PASS trên 10K, mới thực hiện quét n.

## 10. Cảnh báo khi trình bày thầy

- `W(n)` và `W(n)/n` là empirical cost; fit không phải chứng minh Big-O.
- N1/N2 không có nghĩa vùng nào cũng nên xử lý giống nhau.
- Số lượng proposal vào pruning bị chặn bởi C là giới hạn danh sách, nhưng không chứng minh số distance calls thực tế giảm với tỉ số đúng 160/64.
- `T_phase/W_phase` cần phase timer có phạm vi rõ; nested worker timings không phải additive wall time.

## 11. Kiểm tra độc lập histogram và số phép đếm leaf

Nếu binary ON xuất **mỗi leaf một dòng** `{"pass_id":1,"depth":3,"size":512}` (không dùng file `examples/leaf_sizes.format.jsonl` vì đó là schema null):

```bash
python3 scripts/r86_log.py import-leaf-sizes --run "$RUN" --events /path/actual_leaf_sizes.jsonl
```

Lệnh tính độc lập `leaf_count`, `Σsize`, `Σsize²`, `Σsize*(size−1)/2`, histogram theo pass/depth. Nếu số tính lại khác counter C++, lệnh trả `FAIL` và đặt trạng thái `INVALID`. Đây là cổng chứng cứ quan trọng cho Ngày 2.

## 12. Thời gian từng phase và median qua các lần chạy

Chỉ sau khi source gắn timer có ngữ nghĩa rõ, nhập phase timings từ JSON theo `examples/phase_times.template.json`:

```bash
python3 scripts/r86_log.py import-phases --run ./runs/REAL_TIMED_RUN \
  --events /path/real_phase_timings.json
```

`method` bắt buộc là `exclusive_wall`, `inclusive_wall`, `worker_seconds` hoặc `external_profile`. `worker_seconds` cần bật `--allow-worker-seconds` và **không coi là wall phase time**.

Sau khi có nhiều run/arm (mỗi lần có `graph_id` riêng):

```bash
python3 scripts/r86_log.py summarize --root ./runs --output ./R86_summary.json
```

Trả median, min, max, IQR (nếu >=4 observations), số unique graph hash và các metric SEARCH. Các summary này là **descriptive**; phải kiểm tra protocol/data/source trước khi tuyên bố khác biệt có ý nghĩa.

## 13. Nhập model dự đoán và chỉ số D/graph

Để có cột `predicted` và `observed/predicted`, dùng dữ liệu tính **độc lập** theo `examples/predictions.template.json` rồi:

```bash
python3 scripts/r86_log.py import-predictions --run "$RUN" --results /path/actual_predictions.json
```

Nếu có report graph từ analyzer/validator độc lập, dùng `import-graph-stats`; nếu có thí nghiệm D với `hypothesis_id` được xác định trước, dùng `import-diagnostics`. Ba file `examples/*.template.json` chỉ là mô tả định dạng, **không nhập nguyên xi khi trường value còn null**.

## 14. Tiếp tục provenance audit trên Ubuntu (không sửa dữ liệu)

```bash
bash scripts/day2_provenance_audit.sh > /tmp/R86_day2_provenance_audit.txt
```

Đọc `/tmp/R86_day2_provenance_audit.txt`; tập trung SHA `pipnn_utils.h` tại `isolation_v4/source` so với H70 và CMakeCache/executable của R85. Gửi file text để kiểm tra trước khi viết patch. Không chỉnh quyền kernel hay sửa source cũ.
