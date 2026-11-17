# H26-P2b — Kiểm toán locality của các cặp điểm trùng giữa overlapping leaves

## Bối cảnh và câu hỏi

P2 (SIFT1M, một H18 capture, 30.000 pair-occurrence samples) ước lượng **30,261% lượt xuất hiện cặp điểm toán học là dư thừa** nếu sử dụng oracle chỉ tính mỗi cặp một lần trên toàn bộ các leaf. Tuy nhiên, đây **không phải tỷ lệ wall time tiết kiệm**, vì Eigen `rankUpdate` sử dụng kernel cập nhật ma trận tối ưu. Toàn bộ cặp phân biệt ước tính hơn 5 tỷ: một bảng tra toàn cục lưu `(uint32 u,uint32 v,float distance)` thô tối thiểu khoảng 61 GB (chưa có hash table, synchronization và metadata). Một cache toàn cục thực tế khó phù hợp cấu hình thí nghiệm ~2 GB RSS BUILD.

P2b tìm lời giải cho hai câu hỏi **trước khi viết builder/cache**:

1. Nếu coi leaf IDs trong capture là một *thứ tự xử lý tuần tự giả định*, bao nhiêu pair occurrences có cùng cặp trong **W leaf ID trước đó**? Đây là metric *idealized leaf-ID locality*, KHÔNG phải temporal reuse distance thật hoặc cache hit trong `parlay::parallel_for`. Bởi PiPNN chạy song song, leaf có ID gần nhau có thể chạy chồng hoặc không theo thứ tự; không được tuyên bố cache nhanh hơn dựa trên số này.
2. Nếu chỉ có oracle cache những cặp có multiplicity toàn cục `m >= k`, tỷ lệ duplicate pair work tối đa về mặt toán học sẽ là bao nhiêu? Đây là **oracle có hindsight**, không phải chính sách khả thi vì online không biết trước `m`.

## Dữ liệu và công thức

Đọc và xác thực SHA256 của H18 `leaf_proposals.bin` (pin `13e78697...8d428ccc95`). File có 85.529 leaf và hơn 7,289 tỷ **unordered offdiagonal pair occurrences**. Không tính các cặp diagonal và không lập danh sách hàng tỷ cặp.

Lấy mẫu **uniform over pair occurrences**, bằng chọn leaf tỷ lệ `C(n,2)` rồi chọn ngẫu nhiên 2 vertex khác nhau trong leaf. Chỉ tạo inverted leaf-membership index cho những endpoint xuất hiện trong mẫu. Với từng mẫu `(u,v, leaf_id)`:

- `m`: số leaf chứa cả `u` và `v`.
- `prior_leaf_gap`: chênh lệch `leaf_id` đến leaf gần nhất trước nó (theo ID) cũng chứa cặp.
- Oracle toàn cục: `mean(1 - 1/m)`.
- Metric window W: `mean(prior leaf exists AND prior_leaf_gap <= W)`.
- Oracle chỉ cache multiplicity >= k: `mean((1 - 1/m) * [m>=k])`.

Các phép thống kê này là ước lượng có sai số lấy mẫu cho **một capture cố định**. Kiểm tra lại với seed khác nếu gần ngưỡng GO/HOLD/NO-GO, nhưng seed lấy mẫu khác **không thay cho BUILD khác**.

**Lưu ý về kết quả window:** cửa sổ W đếm *số thứ tự leaf ID*, không phải số pair keys trong cache, không phải số giây, và không phải memory footprint của cache. Các metric có thể dùng để bác bỏ một hướng kém triển vọng nhưng chưa đủ để chứng minh cache khả thi. Chỉ phép đo thứ tự thực tế dưới scheduler, bộ nhớ và runtime so với `rankUpdate` mới chứng minh hiệu quả.

## Hướng dẫn Ubuntu

Giả định bạn đã có dữ liệu H18 và môi trường Python/NumPy như ở H26-P2. Tải ZIP `H26_P2B_locality_kit.zip` về `~/Downloads` rồi chạy:

```bash
mkdir -p ~/ann-task-a/experiments/H26/P2B_kit
cd ~/ann-task-a/experiments/H26/P2B_kit
unzip -o ~/Downloads/H26_P2B_locality_kit.zip -d .
python3 h26_p2b_locality.py --mode selftest
```

Kỳ vọng dòng `H26P2B_SYNTHETIC_PASS`. Sau đó:

```bash
python3 h26_p2b_locality.py --mode run --samples 30000 --seed 42
```

Tool in `H26P2B_SAMPLE`, `H26P2B_INDEX_PROGRESS` và cuối cùng `H26P2B_DONE`. Không cần CMake hay BUILD, không viết/sửa PiPNN/H25/H26, và không ghi đè output cũ. Nếu máy đã có thư mục output cùng seed, đổi `--seed 1729` hoặc cung cấp `--out` **trỏ tới thư mục mới**.

Lấy kết quả:

```bash
OUT=~/ann-task-a/experiments/H26/H26_P2B_locality_H18_seed42_n30000
cat "$OUT/h26_p2b_locality.txt"
cat "$OUT/h26_p2b_locality.json"
```

Gửi báo cáo `txt` để quyết định có đáng làm online locality instrument hoặc microbenchmark caching hay không. Không cần gửi toàn bộ JSON nếu TXT đã đủ.

## Tiêu chí đánh giá khoa học

- Nếu window W nhỏ chỉ bao phủ tỷ lệ nhỏ so với oracle 30,26% → **NO-GO cho hướng naive local pair cache**; không thử code builder.
- Nếu phần lớn cơ hội cần W rất lớn hoặc chỉ xuất hiện ở những cặp rất nhiều lần → cần tính chi phí bộ nhớ/cache và nhận diện key; thường NO-GO nếu cache vượt memory budget.
- Nếu locality theo leaf IDs có vẻ khả quan → chỉ **HOLD/GO cho thực nghiệm** ghi nhận **thời gian bắt đầu/kết thúc leaf thật, tương quan giữa các worker, miss rate và microbenchmark trên cùng hardware**, không GO cho thuật toán mới.
- Nếu policy thực nghiệm có thể vượt Eigen GEMM mà giữ recall và graph bytes thì mới xem xét prior-art audit và cơ chế ANN-specific để kiểm tra novelty.

## Giới hạn và an toàn

- **Không dùng** con số `30,26%` để suy luận `30,26%` tăng tốc BUILD; không lấy lượng proposal trùng từ H18 làm proxy của repeated matrix dot products.
- **Không ghi đè** các artifacts H25, H26-P0/P1a/P1b/P2.
- Không mặc định floating-point distances tính tại các leaf giống bit-by-bit nếu thứ tự tính toán khác.
- 12 bytes/pair là giới hạn lý tưởng *dữ liệu thô*, không phải kích thước triển khai hashmap hoặc RAM trong BUILD.
- Số liệu 30.000 mẫu là từ **một H18 capture**, chưa có kiểm chứng liên dữ liệu/seed.
