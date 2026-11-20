# R90 — Kiểm toán PiPNN gốc và thiết kế thử nghiệm A5/RADAR (source-only)

**Ngày:** 2026-11-17  
**Trạng thái:** Kiểm toán mã nguồn tĩnh; **chưa triển khai A5/RADAR native**, chưa công bố BUILD/Search win.  
**GitHub nghiên cứu:** `nuyntai19/ann-task-a-research`, `main` commit `f0c33362b622fb768b5533aa6fd9ebdf7cd2781a` (snapshot lúc kiểm tra).  
**PiPNN gốc:** `ParAlg/PiPNN` commit `443a328`.  
**Nguồn kế hoạch:** Google Sheet `WEEK_PLAN` dòng 29 (A5), 50–51 (RADAR), 55–56 (hướng song song), 63 (R90); Google Doc “Đề Xuất Cải Tiến PiPNN” (HARP, ORTHO-LANE, VBT); bản chép ASR 08:19 do người dùng cung cấp.

## 1. Phân biệt các loại vòng lặp

Paper PiPNN Algorithm 4 tách **BUILD** thành (1) RBC phân hoạch chồng lấn, (2) xử lý lá, tạo ứng viên bằng khoảng cách + Top-k, (3) HashPrune tích lũy ứng viên trực tuyến, (4) final RobustPrune rồi xuất graph. Search là công việc sau BUILD; Google Doc gọi nó là giai đoạn 5.

**`N=2` không phải “giai đoạn 2”.** Theo `pipnn.h`, `multiple_clustertrees(G, ..., num_clusters)` cấp phát HashPrune graph một lần, lặp `recursively_sketch_wrapper(G, ...)` N lần; sau N pass mới `ExportToGraph` + final RobustPrune. Một lần wrapper gồm cả xây bucket, xử lý từng lá và merge vào cùng `G`. Do đó A5/RADAR can thiệp **giữa Pass 1 và Pass 2 của chu trình 1→2→3**, không đơn giản giữa hai stage có số thứ tự 1 và 2.

## 2. Những điểm code đã đối chiếu

| Source/anchor | Hiện trạng trong source | Hệ quả cho A5/RADAR |
| --- | --- | --- |
| `R86/pipnn.h` `SelectAndAssignLeaders` khoảng L53–94 | Chọn leader với `std::mt19937 prng(seed)`, `std::sample`, `assign_leaders`, `group_by_index`, rồi `leaders.clear()` | Cần thu GT-free features trước khi xóa danh sách leaders; `leaders` không tồn tại như một lịch sử P1 lưu sẵn |
| `R86/pipnn.h` `recursively_sketch_wrapper` khoảng L370–459 | Chạy RBC & `RunLeaf` trong một pass; `SEED = parlay::hash64(SEED)` cuối wrapper | P2 không chỉ là HashPrune và có seed/partition riêng |
| `R86/pipnn.h` `multiple_clustertrees` khoảng L461–474 | `G.allocate_graph()` **trước** vòng `num_clusters` và cùng G cho cả N passes | Không gọi `multiple_clustertrees` lần hai để "append P2": sẽ cấp phát lại, làm mất/đổi reservoir |
| `R86/pipnn_utils.h` `eigen_knn` khoảng L438–529 | `eigen_build_distmat`: ma trận đối xứng; chọn `MST_DEG` láng giềng cho **mỗi** hàng; merge cả `u→v` và `v→u` | RADAR chữ nhật phải thay kernel tính khoảng cách, xử lý semantics cạnh ngược và giữ ràng buộc hash/prune |
| `R86/pipnn_utils.h`, `R71_H17_TOP2` | Chỉ bật fast Top-2 khi `MST_DEG==2` | H17 có thể giữ cho các lá nguyên vẹn; với hàng chọn lọc Q×B cần kernel mới, không tính ma trận vuông rồi lọc hậu kỳ |
| `R86/pipnn.h` `ExportToGraph` khoảng L531–559 | `graph.finalize()` và `utils::robustPrune` **sau mọi pass**, điều khiển bởi `prune_all`/degree | Không gọi post-prune giữa hai pass khi so với baseline. P1-only graph phải xuất từ bản sao/đối chứng riêng hoặc snapshot bảo toàn trạng thái |
| `algorithms/utils/graph.h` `LSHGraph` khoảng L658–960 của upstream | Per-node reservoir `table_size`, bf16 norm, `hash` 16-bit, khóa khi merge | Occupancy snapshot chưa cho biết ID, hash, norm của candidate; cần audit chính xác, tránh lẫn N2 edge delta với công dụng nhân quả |
| `algorithms/utils/hash.h` `Hash_Family` | Hyperplanes tạo bằng Gaussian random vectors, `SketchHash.relative_hash(p,q)` dùng sign các projection residual | Không có bất biến *orthogonal* cho các planes; ORTHO-LANE tài liệu mới phải kiểm tra lại tên/giả định |
| `R86/algorithms/PipNN/CMakeLists.txt` | `R71_USE_H17`, `R86_USE_COUNTERS`, `R70_USE_TIER` là cờ riêng | Pin cùng source, flags, deps, CPU, graph SHA; phân biệt stock OFF, H17 OFF, H17 ON; counters ON không được đem làm BUILD timing |
| `src/PiPNN/algorithms/PipNN/pipnn.h` trong mirror | Có `RunLeaf(...,i)` và `h25_r1::verify()` khác upstream gốc | Thư mục tên `src/PiPNN` không nhất thiết là stock nguyên trạng: dùng upstream pinned 443a328 và R86 provenance để đối chứng |

**Nguồn GitHub mã gốc:**
- https://github.com/ParAlg/PiPNN/blob/443a328/algorithms/PipNN/pipnn.h
- https://github.com/ParAlg/PiPNN/blob/443a328/algorithms/PipNN/pipnn_utils.h
- https://github.com/ParAlg/PiPNN/blob/443a328/algorithms/utils/graph.h
- https://github.com/ParAlg/PiPNN/blob/443a328/algorithms/utils/hash.h

**Nguồn mirror R86:**
- https://github.com/nuyntai19/ann-task-a-research/blob/f0c33362b622fb768b5533aa6fd9ebdf7cd2781a/experiments/R86/r86_v1_2_source/algorithms/PipNN/pipnn.h
- https://github.com/nuyntai19/ann-task-a-research/blob/f0c33362b622fb768b5533aa6fd9ebdf7cd2781a/experiments/R86/r86_v1_2_source/algorithms/PipNN/pipnn_utils.h
- https://github.com/nuyntai19/ann-task-a-research/blob/f0c33362b622fb768b5533aa6fd9ebdf7cd2781a/experiments/R86/gates/highway_r85_four_binary_jvYREW/source_sha256.txt

Frozen R86 source SHA256 đã ghi trong manifest: `pipnn.h = 77a9b97e593e82037b6f801fb23b5f5bbeab5a5e0c8e112b6386f55488ca9f7d`, `pipnn_utils.h = 33b09c3cb85d70f0a11d86c481dc2a6e398b9e162fe1d42b2b1bd1314a0bd3db`. Mã và nguồn được kiểm tra tĩnh; chưa có bản patch R90 native nào để xác minh ON/OFF.

## 3. A5 vs RADAR: thứ gì được thay và phần nào được giữ

**A5 giả thuyết tổng quát** (WEEK_PLAN dòng 29): Chọn một phần công việc P2 theo tín hiệu GT-free phát sinh từ P1, so với N1 và full N2. Không thay final RobustPrune, trừ thí nghiệm tách riêng. A5 nguyên bản prereg trên H17 C64 K512 N1/N2; nếu thử C160 phải định nghĩa *arm và ngưỡng mới*, không âm thầm thay protocol.

**A5 leaf-gate (thử trước):** Sau P1, tính selector cho node Q. P2 vẫn chạy RBC để tạo buckets toàn bộ, nhưng chỉ gọi `RunLeaf` cho bucket có node thuộc Q. Với bucket được giữ lại, `RunLeaf` nguyên vẹn, chọn Top2 và merge 2 chiều nguyên vẹn; không giảm W_P của P2, chỉ giảm W_L của những bucket bị bỏ qua. Nếu với Q=25% hầu như mọi bucket đều chứa Q, leaf-gate có thể **không tiết kiệm W_L**. Vì vậy trước khi patch, đo **tỷ lệ lá P2 được giữ theo Q** bằng read-only bucket coverage trên P2 control.

**RADAR rectangular Pass 1.5 (khó hơn):** P1 bình thường, tính selector Q. P2 tạo các context buckets B, với `Q∩B` chỉ định hàng cần cập nhật. Tính **thật sự** khoảng cách |Q∩B| × |B| bằng GEMM chữ nhật thay vì |B|², chọn Top2 cho các hàng Q, merge candidate vào G; cần quyết định ghi cạnh ngược vào node ngoài Q hay không (cả hai là biến thể cần thí nghiệm một-yếu-tố). Phần tiền xử lý RBC/leader và `W_P` vẫn phải tính đủ; không tuyên bố giảm toàn BUILD chỉ từ tỷ lệ giảm phép tính của một lá. H17 chỉ tái dùng thủ tục chọn Top-2 cho các hàng tính; không đủ để tạo GEMM chữ nhật tự động.

**A5 restricted-tree (chưa ưu tiên):** Chỉ đưa Q vào P2 RBC; có thể giảm W_P nhưng làm thay đổi leader, buckets và phân bố ứng viên, không còn cùng first-P2 partition với full N2. Là một thuật toán mạnh hơn và phải đánh giá độc lập; không lấy kết quả trước làm cận nhân quả full P2.

## 4. Hệ quả từ ghi âm thầy

Đoạn chép được người dùng cung cấp (không đồng nhất với nguyên văn đã thẩm định) nhấn mạnh: sử dụng bounding region/bbox/radius và ý tưởng closest pair để giảm chi phí xét thuộc vùng; định lượng số phép so sánh và phép gán thay vì chỉ thời gian/RAM; đo W(n) khi n tăng và đối chứng cùng chất lượng Search. **Không thấy câu lệnh rõ ràng giao A5 hoặc RADAR.** Hướng geometric bound trong WEEK_PLAN D5.1/D5.4 liên quan trực tiếp hơn; D5.1 triangle bound kiểm tra trước đó 0/65536 cặp được bỏ trong mẫu, không chứng minh mọi kiểu bound thất bại.

## 5. Google Doc khác với A5/RADAR

Doc native “Đề Xuất Cải Tiến PiPNN” trình bày: HARP (định tuyến lá GPU/CPU giữa Stage1→2, target-sharded HashPrune Stage2→3); ORTHO-LANE (thay đổi final pruning Stage4 và thêm Search song song Stage5, giữ H17); VBT (thay RBC Stage1 và tính cặp Stage2 bằng Voronoi seam, có thể dùng H17). Doc **ưu tiên ORTHO-LANE cho CPU của nhóm**, không phải RADAR. Các đề xuất này là giả thuyết kiến trúc, không phải kết quả native đã chứng minh. Source audit chỉ ra ORTHO: Gaussian planes không bảo đảm trực giao và graph cuối chỉ lưu neighbor IDs, muốn giữ lane offsets/hash cần chi phí metadata; không được khẳng định "0 byte overhead" khi chưa có codec/format đo thật. VBT: `fanout=1` trong PiPNN **không** tương đương phân hoạch Voronoi 1-pass; phải viết mới RBC assignment/tiling. HARP: chứng minh merge algebra với bf16/tie/insertion ordering và tính tổng I/O GPU+SSD trước khi tuyên bố tương đương.

## 6. Cổng triển khai an toàn, thứ tự khuyến nghị

1. **R90-P0 source/provenance OFF:** pin stock PiPNN (443a328), R86 H17 OFF/ON exact sources; `R71_USE_H17` theo MST_DEG2; sao chép vào thư mục nghiên cứu độc lập, không chỉnh `main` hoặc dữ liệu đã khóa. Lập build graph OFF deterministic control.
2. **P1 matched-Pass1:** chạy N1 và N2 source+seed+flags giống hệt; *trong một vòng lặp đúng nghĩa* chụp P1 leader/bucket identifiers, hash/ID/dist per reservoir node, tổng W_P/W_L và bin/counter sau pass1 trước pass2; so SHA P1, không suy từ graph cuối. Xác minh seed initial=555 và `parlay::hash64` transition; random_device local `rnd` của wrapper hiện không được dùng cho chọn leader nhưng không miễn chứng minh định tính ổn định. Chạy nhiều seed độc lập, cùng seed ở cặp N1/N2.
3. **P2 read-only coverage scan:** trên các bucket P2 full control, đánh giá top10/20/25/40% GT-free node selector và tỷ lệ *lá có Q* cùng lượng W_L tiết kiệm tiềm năng; đo hậu-RobustPrune P1/P1+P2 paired final graph, mức cải thiện Recall và W_P/W_L không gán nguyên nhân từ unpaired graph A3/A4.
4. **P3 A5 leaf-gate pilot:** chỉ khi P2 scan cho thấy có thể bỏ đủ lá; tắt patch phải cho exact graph+counter parity với H17 N2 OFF (không làm mới code thay đổi baseline). Rerun 10K→100K trước; all-equal N2 when selector all nodes; N1 when selector none, nếu điều kiện hợp lệ (cần kiểm thử thứ tự seed/export/prune).
5. **P4 RADAR rectangular kernel:** chỉ mở khi leaf-gate ít lợi hoặc oracle budget cho thấy có đủ Q nghèo ứng viên; test full square vs rectangle when Q=B (parity) and Q=∅ (zero extra work), test reverse edges semantics, counters count real GEMM/MACs, native Recall and graph outputs.
6. **P5 formal:** cùng dataset/protocol 3 independent paired graph builds ×5 native Search mỗi graph/target ở matched Recall, đo build wall/CPU, RAM/RSS, graph bytes, W_P/W_L, merge/hash/prune, top2 comparisons+assignments, sector coverage/connectivity/Recall–QPS/p95; scaling W(n) ít nhất 10K→100K→1M và 3M/5M tùy resource gate. Baselines A0 stock C160, A1 H17 C160 N2, A1 H17 C160 N1, A5, RADAR; C64 chỉ phụ trợ RAM. Đo 1-factor: không đồng thời thay C/K/N/alpha/hardware rồi gán win cho RADAR.

**Nhắc lại:** Thí nghiệm RADAR-R0-P0 trên sáu graph A3/A4 chỉ mô tả khác biệt graph, chưa có matched P1. Không có evidence A5/RADAR native PASS; mọi khẳng định về tỷ lệ giảm work phải chờ phép đo.
