# H32-R8 — Kiểm toán H31 tại Ubuntu, chỉ đọc

**Mục tiêu:** kiểm toán những graph, dữ liệu và log **đã có** để biết có thể tái sử dụng H31 đến đâu. Không chạy BUILD, không chạy SEARCH, không sửa graph, không cài gói hay dùng `sudo`.

Bộ công cụ chứa:
- `h32_r8_audit.py`: chỉ dùng Python 3 standard library; đọc các input H31 và sinh đúng hai file báo cáo trong **thư mục mới** dưới `~/ann-task-a/experiments/H32/H32_R8_<timestamp>/`.
- `README_H32_R8_VI.md`: hướng dẫn này.
- `SHA256SUMS.txt`: checksum của bộ công cụ.

## Lệnh chạy trên Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H32/R8_kit
cd ~/ann-task-a/experiments/H32/R8_kit
unzip -o ~/Downloads/H32_R8_readonly_kit.zip -d .

# Xem mã trước khi chạy nếu muốn
less h32_r8_audit.py

# Chỉ kiểm tra code trên fixture tổng hợp, chưa xác minh file máy thật
python3 h32_r8_audit.py --mode selftest

# Đọc các file H31 hiện hữu và sinh báo cáo mới; KHÔNG gọi BUILD/SEARCH
python3 h32_r8_audit.py --mode audit --root ~/ann-task-a
```

Kết quả sẽ in `H32R8_DONE=...`; mở hai file ở đường dẫn đó:

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R8_2* | head -n 1)
cat "$OUT/h32_r8_summary.txt"
```

**Gửi lại nội dung `h32_r8_summary.txt`**, tốt nhất đính kèm thêm `h32_r8_report.json` (file nhỏ). Không cần gửi graph, dataset SIFT1M hay binary hàng trăm MB.

## Những gì script xác minh

1. `h31_r0_inventory.json` đã lưu từ 28/10 và SHA256 **pinned** của VAMANA, STOCK, TOP2; kiểm tra bytes/header/degrees/edge counts của graph.
2. Dataset `sift1m.fbin`, queries và ParlayANN GT hai khối **ID uint32 + distance float32**, kiểm tra đúng header và kích thước. Lấy mẫu 100 hàng GT để kiểm tra ID hợp lệ và giá trị hữu hạn không âm. **Không chứng minh exact GT**.
3. SHA256 của executable `src/ParlayANN/algorithms/vamana/neighbors` và Git HEAD ở repository nếu tìm được; KHÔNG thực thi binary.
4. Bốn phiên ghi log: H31-R2 ban đầu Q100/120/160 và ba đợt H31-R2b Q120 đã cân bằng thứ tự. Đối chiếu JSON, 5 lượt lặp nội bộ/log, median QPS, provenance graph và binary, không coi các lần lặp nội bộ là BUILD độc lập.

## Cách diễn giải

- `PASS_LOCAL_AUDIT`: các bằng chứng đang có khớp dấu vết R0/R2 và self-consistency của files; **không có nghĩa matched Recall/graph budget**.
- `PARTIAL_LOCAL_AUDIT`: có file/đợt log bị thiếu; phần còn đủ có thể giữ làm evidence nhưng không claim đã kiểm toán toàn bộ.
- `FAIL_INPUT_INTEGRITY`: phát hiện sai SHA, kích thước, log/JSON hoặc provenance; **dừng diễn giải khoa học**, kiểm tra chính xác đường dẫn và version, **không rebuild để che lỗi**.
- `PARLAYANN_HEAD=UNVERIFIED`: source checkout thay đổi, dù binary SHA có thể còn đúng; cần kiểm toán provenance riêng, không tự suy source=binary.
- Q01 có khác ngân sách graph (Vamana ~114,57 MB, PiPNN ~95,17 MB). Q02 chưa có code đo intra-query; R8 không sửa hai hạn chế này.

### Lưu ý

- **Không dùng** script này để chạy các số liệu của H17 hay kiểm tra tỉ lệ tăng tốc BUILD: đó là kết quả cũ, không đo lại.
- Script có đọc hàng trăm MB để băm graph nhưng không ghi/đổi file input; chỉ ghi `h32_r8_report.json` và `h32_r8_summary.txt` vào thư mục `H32_R8_...` mới.
- Lệnh `--mode audit` có thể kết thúc với trạng thái PARTIAL/FAIL được **in trong báo cáo** nhưng exit code vẫn bằng 0 để giữ lại bằng chứng kiểm toán; **phải xem `OVERALL`**.
- Môi trường CPU không được benchmark; thông tin affinity chỉ phục vụ audit context.
