# R86 Day 2 — thực hiện theo cổng xác minh, chưa patch H70

## Bằng chứng provenance đã có từ người dùng

- R85-SCALE1 A2/A3/A4 (+C64 K1024 N1) cùng SHA executable H17 Flat `8757b9be9fa3ae1f90febe082001fa60ba22c71ba6b6cdd899e013f6c0bcd500`.
- H17 Flat: `R71_USE_H17=ON`, `R70_USE_TIER=OFF`; Stock `OFF/OFF`; D0 `ON/ON`.
- H70 repo HEAD `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd` nhưng **DIRTY**; source snapshot lúc build chưa được chứng minh hoàn toàn bởi SHA executable.
- B1 `isolation_v4` có snapshot riêng và xử lý symlink hỏng. Không sửa vào `H70` hoặc `H85` gốc.
- A1/B160 ở chiến dịch SIFT1M **không được ghép wall-time** với SCALE1/BIGANN1M. R86 phải chạy A0–A4 với cùng input/protocol khi đưa ra ablation mới.

## Làm trước khi chạy BUILD

1. Đọc các manifest và đối chiếu SHA của **binary, source files, cache flags**. `cmake-build` khác path có thể tạo binary SHA khác dù thuật toán tương đương; dùng test hành vi, không so SHA làm tiêu chí duy nhất.
2. Sao chép nguồn từ **một** snapshot đã xác nhận sang R86 isolation, giữ nguyên H70, R85.
3. Từ source snapshot đó tạo 4 target nếu có thời gian: Stock OFF, Stock ON, H17 Flat OFF, H17 Flat ON. Tất cả chỉ khác định nghĩa `R86_COUNTERS` giữa ON/OFF, ngoài cờ H17.
4. Test bản OFF trên SIFT100K theo giao thức đã pin, so graph validator, edge count và Recall ở cùng beam so với R85-B1. Do random_device, không kỳ vọng mọi node/edge hash byte-identical. Cần phạm vi sai số/biến thiên giữa build độc lập trước khi đặt gate.
5. Chỉ thêm instrumentation khi đã chọn đúng source, và gửi patch Claude review **trước khi build**.
6. Với bản ON, chạy 10K, một luồng, kiểm tra tổng W_L/W_pairs/leaf_count độc lập từ leaf-size dump; kiểm tra số membership; kiểm tra event placement same/diff hash; kiểm tra graph validity. Chưa chạy sweep 1M khi gate chưa PASS.

## Nơi gắn hooks (C++ skeleton `cpp/r86_counters.hpp`)

Đây là hướng dẫn **chưa áp dụng patch**. Vị trí và thông số phải đối chiếu mã nguồn R86 thật:

```cpp
#include "r86_counters.hpp"

// Trong multiple_clustertrees, trước mỗi lượt sketch (các lượt chạy tuần tự):
r86::set_active_pass(static_cast<int>(i+1));
// recursively_sketch_wrapper(...)
// Sau khi hoàn tất mọi sketch, trước final prune:
r86::set_active_pass(0);  // global final prune; not N2 pass

// Trong SelectAndAssignLeaders, khi đã biết |ids|, số leader, fanout:
r86::add(r86::Metric::W_P, static_cast<uint64_t>(ids.size())*num_leaders, depth);
r86::add(r86::Metric::W_A, static_cast<uint64_t>(ids.size())*fanout, depth);

// Trong RunLeaf, khi biết s = leaf size:
r86::add(r86::Metric::leaf_count, 1, depth);
r86::add(r86::Metric::leaf_size_sum, s, depth);
r86::add(r86::Metric::W_L, static_cast<uint64_t>(s)*s, depth);
r86::add(r86::Metric::W_pairs, static_cast<uint64_t>(s)*(s-1)/2, depth);

// Pick emits proposals; before HashPrune/merge stage
// r86::add(r86::Metric::proposals, n_directed_edges, depth);
// r86::add(r86::Metric::merge_attempts, n_forward_plus_reverse, depth);

// Trên nhánh code thực sự xử lý hash collision:
// r86::add(r86::Metric::collision_same_id, 1); // if candidate IDs equal
// r86::add(r86::Metric::collision_diff_id, 1); // otherwise
// Đừng đếm hash collision như duplicate proposal toàn cục.

// Trong final RobustPrune, ngay trước distance function thực sự được gọi:
// r86::add(r86::Metric::prune_distance_calls);

// Sau khi mọi worker đã join; đường dẫn file do runner truyền vào:
r86::dump_jsonl("/absolute/path/to/counter_events.jsonl");
```

### Chú ý ngữ nghĩa

- `active_pass` là biến atomic toàn cục. Chỉ đúng nếu từng vòng `recursively_sketch_wrapper` chạy xong toàn bộ worker trước khi chuyển sang pass khác. Nếu có async kéo dài, **truyền pass_id theo task** thay vì dùng global.
- `depth = -1` là metrics không gắn độ sâu. Trong C_WORK, tránh cộng lại cả bản tổng hợp và từng depth (double count). `max_depth` tốt hơn lấy `max` từ dump, không được tăng dồn như số lượng.
- `W_L=s²` chỉ là matrix-entry logical proxy; trong code có thể tính cả upper/lower triangular; không suy ra số instructions/FLOP nếu chưa xét GEMM.
- W_P đã có counter `COMPARISONS` trong upstream SelectAndAssignLeaders; KHÔNG phải NDC search.
- Đếm 1 `swap=3 assignments` là quy ước mô hình, không là máy thực thi ba store instruction.
- `collision_same_id` là **cận dưới số duplicate proposal phát hiện khi va chạm trong reservoir hiện tại**, không đếm ID đã bị evict rồi được đề xuất lại.
- `T_partition`, `T_leaf`, `T_prune` là **phase wall-time** nếu stage thực sự được ngăn cách; nếu leaf lồng trong partition, đừng cộng thời gian các worker để gọi là wall-time stage. Đặt `T_phase_method`/notes trong A.
- `T_phase/W_phase` là hiệu năng trung bình có điều kiện, không đủ chứng minh cache hoặc GEMM efficiency khi thiếu hardware counters.
- Header chỉ cung cấp hooks, không thể tự instrument một chương trình chưa xác minh source. `R86_COUNTERS=OFF` khiến các lệnh đếm không làm gì.

## Hình thức đầu ra & nhập vào Sheet

1. Mỗi test tạo `E_manifest.json` và `A/B/C/D` files cùng run_id, graph_id.
2. ON xuất `raw/counter_events.jsonl`; chạy `import-counters` để đưa vào `C_work.json`.
3. OFF runner được bọc `capture-build` để tạo `A_system.json`; không lấy elapsed của ON để claim BUILD speedup.
4. E ghi mode ON/OFF, SHA nguồn, binary, input, GT, cờ, threads, seed/random_device, rep.
5. `export-csv` xuất đúng header từng tab Google Sheet, các ô chưa đo để trống. Không tự động upload/sửa Sheets; hãy review trước khi copy vào tab.

## PASS/FAIL

- PASS provenance, compiler, independent counter assertions, graph structure và measurement separation.
- Nếu FAIL: dừng sweep, lưu nguyên raw output để có thể phân tích lại.
