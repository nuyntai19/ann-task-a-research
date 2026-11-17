# R26b — Chỉ phục hồi số liệu SEARCH

R26b đầu tiên đã BUILD hai graph hợp lệ và hoàn thành tám lượt native SEARCH nhưng không in thống kê vì lệnh thiếu `-verbose`. `h32_r26b_report.py` cũ dùng regex `For 10@10 recall = ...` không đúng với mã `cmuparlay/ParlayANN` phiên bản `a48c6a3` ở chế độ fixed `-Q`; bản chính xác là dòng `search: Q=..., k=10, limit=..., recall=..., visited=..., comparisons=..., QPS=...`.

Chạy `bash h32_r26b_search_recovery.sh` trong thư mục giải nén. Chỉ SEARCH lại 8 tổ hợp Q={80,100,120,160} × {PiPNN, FGraft}, mỗi tổ hợp có 5 lượt chạy **nội bộ** của binary. Không build, prune, chuyển dữ liệu, thay source, ghi đè tệp graph/pool hoặc thay log cũ. File mới có hậu tố `.verbose.log`, `.verbose.time.log`. Parser kiểm tra từng log có đúng 5 dòng hợp lệ trước khi tiếp tục. Nếu lỗi giữa chừng, giữ nguyên log và thông báo để tiếp tục có điều kiện, KHÔNG chạy lại toàn bộ và KHÔNG xóa đồ thị.

Kết quả: `r26b_search_recovered_summary.txt`, `r26b_search_recovered_report.json`, và `r26b_search_recovered.stdout.txt` nằm **trong thư mục kết quả R26b cũ**. Code không tự suy ra matched Recall hoặc strict recall; native ParlayANN sử dụng tie-aware recall. FGraft 28.368.175 cạnh, PiPNN 22.797.630 cạnh: graph budgets **khác 24,435%**; không được kết luận lợi thế chất lượng từ dữ liệu này. SOURCE pin và checksum graph được xác minh trước khi SEARCH.

### Ví dụ

```bash
mkdir -p ~/ann-task-a/experiments/H32/R26b_recovery_kit
cd ~/ann-task-a/experiments/H32/R26b_recovery_kit
unzip -o ~/Downloads/H32_R26b_search_recovery_kit.zip
sha256sum -c SHA256SUMS.txt
bash h32_r26b_search_recovery.sh
```
