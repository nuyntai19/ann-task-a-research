# H32-R12 — Kiểm toán entry policy và tie-aware Recall (chỉ đọc)

## Vì sao cần bước này?

H32-R10 và H32-R11 phân tích **strict GT@10 ID overlap**, nhưng tại commit ParlayANN `a48c6a34e5f959190992aa531cc18454cfcc3dd3`, `check_nn_recall.h` dùng **tie-aware recall**: ngoài 10 ID GT đầu tiên, các ID trong GT[10:100] được tính là đúng nếu khoảng cách tính bởi `Euclidian_Point<float>::distance` bằng khoảng cách GT thứ 10. Vì vậy, 12 vị trí strict GT@10 unreachable của Vamana KHÔNG nhất thiết gây đúng 12 misses theo native metric.

## Bộ công cụ làm gì?

- Xác thực kết quả R10/R11 và bảng 12 query bị ảnh hưởng (hoặc số khác nếu dữ liệu khác).
- Kiểm tra source Vamana `start_point=0`, `random=false`; kiểm tra source code chính sách tie-aware, và commit Git.
- Tái dùng graph có SHA pinned và BFS của R11 để biết ID trong GT[10:100] có reachable hay không.
- So sánh hai **proxy**: (a) phép bằng nhau của `float32` distances lưu trong GT; (b) khoảng cách squared-L2 được tính lại với phép cộng tuần tự float32 giống dạng source.
- Tính structural miss floor/Recall ceiling ứng với 2 proxy, với cảnh báo **chưa xác nhận parity bit-for-bit với native binary**.
- Không xây graph, không ANN Search, không sửa graph, không sửa source, không viết vào log R10/R11.

## Cần có sẵn

`~/ann-task-a` với mã nguồn `src/ParlayANN` tại commit pinned; dữ liệu `data/sift1m*.fbin` và `sift1m_gt.ibin`; graph H31; kết quả R10/R11 đã PASS; script `experiments/H32/R11_kit/h32_r11_audit.py` nguyên trạng.

## Lệnh Ubuntu

```bash
mkdir -p ~/ann-task-a/experiments/H32/R12_kit
cd ~/ann-task-a/experiments/H32/R12_kit
unzip -o ~/Downloads/H32_R12_tie_aware_source_audit_kit.zip -d .
sha256sum -c SHA256SUMS.txt
python3 h32_r12_tie_ceiling.py --mode selftest
python3 h32_r12_tie_ceiling.py --mode audit --root ~/ann-task-a

OUT=$(ls -td ~/ann-task-a/experiments/H32/H32_R12_2* | head -n 1)
cat "$OUT/h32_r12_summary.txt"
```

## Diễn giải kết quả

- `STRICT_UNREACHABLE_GT10_M`: dữ liệu R10, không đổi.
- `STORED_GT_TIE_PROXY_MISS_FLOOR`: số vị trí bắt buộc thiếu theo phép so sánh khoảng cách được lưu trong GT (proxy, **không phải native certified**).
- `FLOAT32_SEQUENTIAL_TIE_PROXY_MISS_FLOOR`: số vị trí bắt buộc thiếu theo phép tính lại squared-L2 bằng float32 tuần tự (proxy).
- `TIE_SET_DISAGREEING_QUERIES`: số query mà hai phép nhận dạng tie có tập ID khác nhau. Nếu khác 0, phải kiểm tra số học và cách sinh ground truth, không kết luận chính xác về native.
- `SOURCE_POLICY=ZERO_NONRANDOM`: dựa trên mã nguồn gốc và HEAD Git, không khẳng định độc lập nội dung binary đã chạy.
- `NATIVE_BINARY_EXACT_PARITY=NOT_VERIFIED`: ngăn ngừa kết luận quá mức.

## Giới hạn khoa học

Giới hạn về cấu trúc chỉ có hiệu lực nếu search chỉ đi theo directed edges từ entry 0, không teleport hay fallback. Source audit không đồng nghĩa kiểm thử trace lúc chạy. Do chương trình Python và bản C++ đã biên dịch có thể dùng thứ tự cộng và lệnh vector khác nhau, không gọi proxy là native-exact. Muốn phân loại chính xác những GT reachable bị bỏ sót cần **per-query prediction IDs** từ một native diagnostic build có kiểm soát, thay vì suy từ Recall aggregate.

Nếu báo `H32R12_FAIL_CLOSED`, gửi nguyên lỗi, không tự sửa graph/source. Nếu thành công, gửi `h32_r12_summary.txt` để quyết định bước tiếp theo.
