# H32-R13 — Chẩn đoán query-by-query native-source, không chỉnh graph

## Vấn đề
H32-R12 tìm 10 GT vị trí không thể lấy được từ entry 0 sau khi cho phép bổ sung láng giềng đồng hạng. Nhưng H31 chưa có predicted IDs từng query. R13 dùng qsearchAll gốc từ commit ParlayANN `a48c6a34e5f959190992aa531cc18454cfcc3dd3` trong một executable mới, để thu 10 ID/query cho SIFT1M, Q=100, k=10, entry=0, random=false.

**Đây là ANN SEARCH MỚI (3 × 10.000 query). Không có BUILD graph, không thay original binary hay graph, không có trace giải thích nhánh tìm kiếm.** Script thất bại an toàn nếu SHA graph, commit nguồn, source key, hình dạng dữ liệu sai; chỉ tạo tệp dưới `experiments/H32/H32_R13_*`.

## Cách dùng

```bash
mkdir -p ~/ann-task-a/experiments/H32/R13_kit
cd ~/ann-task-a/experiments/H32/R13_kit
unzip -o ~/Downloads/H32_R13_native_query_diagnostic_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r13_run.py --mode selftest
python3 h32_r13_run.py --mode compile --root ~/ann-task-a
python3 h32_r13_run.py --mode audit --root ~/ann-task-a
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R13_2* | head -n 1)
cat "$OUT/h32_r13_summary.txt"
```

*Compile mode* chỉ build executable riêng, không tìm query. *Audit mode* sẽ compile một executable mới và chạy 3 graph ở 1 search thread. Nó xác minh score tie-aware do executable mới tính so với giá trị Recall H31 đã ghi: Vamana 0.983140, Stock/Top2 0.990870, dung sai 0.00002. Nếu không khớp, **không coi phân loại per-query là phép tái lập H31**.

Do các graph khác nhau về cạnh và bytes, mọi kết luận về topology superiority vẫn bị chặn. `qsearchAll` lấy từ source pinned nhưng khác binary / build flags H31; aggregate parity nếu PASS là kiểm tra tương thích, không chứng minh bit-exact parity. GT 100 đã có chỉ được kiểm tra header/kích thước và dữ liệu H31 trước đó; chưa recompute chính xác. Reachability lấy từ CSV của H32-R11.

### File kết quả
- `h32_r13_summary.txt` (gửi phần này cho trợ lý)
- `h32_r13_report.json`
- `{vamana,stock,top2}_q100_predictions.csv` (mỗi tệp 10.000 query, 10 ID, strict/tie counts)
- `{vamana,stock,top2}_native_stdout.txt`
- `compile_command.json`

### Nếu compile thất bại
Gửi dòng `H32R13_FAIL_CLOSED` và đường dẫn `compile_failure.txt` (nếu có). **Không** tự động sửa ParlayANN hoặc biên dịch lại index.

Không upload graph, dữ liệu SIFT1M hoặc GT file. Không mở H33 khi chưa có bằng chứng và sàng lọc prior art.
