# H26-P2 — Kiểm toán số phép tính khoảng cách cặp điểm bị lặp giữa các overlapping leaves (OFFLINE)

## Vì sao làm bước này?

P1a/P1b trên SIFT1M cho biết Eigen `rankUpdate(P)` là thành phần đắt nhất của distance matrix, và chi phí theo kích thước leaf bám khá sát số lượng cặp có tính đến chiều dữ liệu. P2 **chưa đưa ra thuật toán mới**. Thay vào đó, kiểm toán một giả thuyết có thể bác bỏ trước khi viết C++: *overlap giữa các leaf có làm nhiều cặp điểm `(u,v)` bị tính đi tính lại hay không?*

Đừng nhầm với H18: **59,68% directed proposal events bị trùng** KHÔNG suy ra tỷ lệ trùng phép tính cặp khoảng cách. P2 đo một đại lượng khác hoàn toàn.

## Nguồn và phương pháp

Chỉ đọc capture chính xác ở:

`~/ann-task-a/experiments/H18/phase2_candidate_audit/leaf_proposals.bin`

Khóa SHA256 bắt buộc: `13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95`. Định dạng: 32-byte header `H18R1P01`; `uint64` offset; `uint64` proposal `(u<<32)|v`. Mỗi source ID của mỗi leaf tạo ra 2 directed proposals, cho phép phục hồi **tất cả vertex IDs thuộc leaf** từ các source IDs. Script kiểm tra cấu trúc mọi leaf; từ chối dữ liệu không khớp.

Không tạo danh sách hàng tỷ cặp. Thay vào đó:

1. Một leaf có `n` điểm chứa `C(n,2)` cặp không hướng, không tính `(u,u)`.
2. Chọn ngẫu nhiên một **pair occurrence** với xác suất đều: chọn leaf tỷ lệ `C(n,2)`, rồi chọn 2 vertex phân biệt trong leaf. Lặp có hoàn lại (`--samples=30000`). Điều này **không** phải uniform-over-leaves.
3. Tạo inverted membership index *chỉ cho những vertex là endpoint của các pair được lấy mẫu*. Quét 85.529 leaf, xây danh sách leaf chứa mỗi endpoint của sample.
4. Với mỗi cặp mẫu `(u,v)`, tính `m(u,v)` = số leaf chứa cả u và v. Vì mỗi lần xuất hiện ở leaf ứng với một phép cập nhật inner product hình học, `m>=1`.
5. Ước lượng fraction of avoidable duplicate mathematical pair computations theo **oracle toàn cục**, bằng `E[1 - 1/m]`. Với tổng số pair occurrences `T`, ước lượng số distinct pair keys là `T * E[1/m]`.

Đây là ước lượng về **công việc toán học lặp**, không phải tỷ lệ BUILD time có thể tiết kiệm. Tái sử dụng ở mức cặp riêng lẻ có thể phá tính hiệu quả của Eigen rank-k update/BLAS, tốn bộ nhớ, contention, communication và khiến BUILD chậm hơn. Trị số cao KHÔNG đủ điều kiện GO sang một thuật toán ANN mới.

Tính khoảng tin cậy 95% Hoeffding bảo thủ cho tỷ lệ trên; chỉ bao gồm độ bất định của lấy mẫu trong **một capture cố định**, không bao gồm nondeterminism giữa những lần BUILD.

## Thao tác Ubuntu

Tải ZIP `H26_P2_pair_reuse_audit_kit.zip` vào `~/Downloads`. Sau đó:

```bash
mkdir -p ~/ann-task-a/experiments/H26/P2_kit
cd ~/ann-task-a/experiments/H26/P2_kit
unzip -o ~/Downloads/H26_P2_pair_reuse_audit_kit.zip -d .

python3 h26_p2_pair_reuse_audit.py --mode selftest
```

Self-test mong đợi:

```
H26P2_SYNTHETIC_PASS theoretical_redundancy=0.444444 observed=...
```

Nếu PASS, chạy **không cần BUILD hay CMake**:

```bash
python3 h26_p2_pair_reuse_audit.py --mode run --samples 30000 --seed 42
```

Script dùng NumPy đã cài trong `.venv`, bắt buộc check SHA và hình dạng file H18; không viết lại dữ liệu gốc, không sửa H25/H26. Với khoảng 60 triệu proposals, cần đọc capture lớn từ SSD và quét toàn bộ leaf; RAM tăng theo số endpoint mẫu (không xây hàng tỷ pair keys). Đừng ngắt nếu đang hiện `INDEX_PROGRESS ...`.

Khi có `H26P2_DONE`, chạy:

```bash
OUT=~/ann-task-a/experiments/H26/H26_P2_pair_audit_H18_seed42_n30000
cat "$OUT/h26_p2_pair_audit.txt"
cat "$OUT/h26_p2_pair_audit.json"
```

Gửi hai kết quả để phân tích. Nếu muốn kiểm thử ổn định lấy mẫu với seed khác, chạy `--seed 1729` (output folder khác).

## Tiêu chí quyết định

- **Thấp**, chẳng hạn dưới 10% duplicate work theo cặp: không nên đầu tư vào global pair reuse/cache trên nhánh này.
- **Đáng kể**, chẳng hạn trên 20% duplicate work: chỉ GO tới *cost model + lower bound memory/communication*, không GO thẳng sang builder. Hệ thống phải tiếp tục tận dụng matrix kernel; caching random pair lookup có thể chậm.
- **Trung gian hoặc CI rộng**: kiểm toán lại theo bucket size; có thể tăng sample mà không sửa source.

Các ngưỡng 10%/20% chỉ là **heuristic để ưu tiên nghiên cứu**, không phải thước đo scientific novelty hay chỉ tiêu hội nghị. Chưa kiểm tra prior art về distance reuse/blocked GEMM, chưa có performance, recall, index byte, Pareto, span hoặc bounded-memory proof.

## Phòng ngừa lỗi

- Không dùng dữ liệu đề xuất Top-2 duplicates của H18 làm tỷ lệ duplicate pairs. Một cặp có thể trùng ở leaf khác dù không bao giờ được chọn Top-2.
- Dataset được đo là **một lần BUILD H18-R1**, chưa đo trên H26-P1b. Các con số `n,leaves,rows,pair count` được kiểm tra để giảm nguy cơ trộn dữ liệu, nhưng không chứng minh hai lần BUILD có leaf membership giống hệt.
- `pair_occurrence_with_multiplicity_gt_1` khác với `redundant_pair_occurrence_fraction`. Fraction sau dùng `1-1/m` để tránh đếm trùng quá mức.
- Script sẽ FAIL CLOSED nếu SHA, schema, membership hay output directory không đúng. Không tự gỡ những kiểm tra này để chạy cho bằng được.
