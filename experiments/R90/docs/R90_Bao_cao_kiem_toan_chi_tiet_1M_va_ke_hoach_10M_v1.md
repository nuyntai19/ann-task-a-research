# R90 — Kiểm toán bằng chứng 1M, giải thích Stock → H17 → Fast v2 và điều kiện mở MS-Turing10M

**Ngày:** 19/11/2026. **Trạng thái:** Bản phân tích đã đối chiếu nguồn hiện có; **KHÔNG PHẢI báo cáo luận văn đã hoàn tất mọi chỉ số**. Không kết luận 10M trước khi chạy native.

## A. Định nghĩa bài toán và phạm vi so sánh

Mục tiêu của nhánh R90: **giảm công việc/thời gian dựng graph PiPNN (BUILD)**, với chất lượng graph được kiểm soát bằng Recall@10 và throughput của **cùng bộ Search**. Điều kiện chính của chiến dịch là `C=160`, `cluster_size=1024`, `MST_DEG=2`, `prune_degree=64`, hai lần cluster, bốn CPU vật lý `0,2,4,6` đối với BUILD và CPU0/1 thread khi SEARCH. Phải kiểm tra nguồn/binary/flags/seed/dataset ở *từng* chiến dịch trước khi so sánh.

- **SIFT1M:** 1.000.000 vector chiều 128. BUILD P3.11 H17/Fast 4 CPU; Search D7 trên **10.000 query** (không gọi là 100K).
- **MS-Turing1M:** 1.000.000 vector chiều 100. BUILD P4 Stock/H17/Fast 4 CPU; Search P4Q/P4M/P4R trên **100.000 query** và exact GT tương ứng.
- Hai dataset không có cùng phân bố dữ liệu/cùng kích thước chiều; không so QPS tuyệt đối của chúng để suy ra thuật toán nào hiệu quả hơn.

**Nguồn chính:** [Google Sheet canonical](https://docs.google.com/spreadsheets/d/12ApqgMV8YykflyFXUT2VMbUhgyiGirtoOmRWCXCz3Ek/edit), [GitHub commit khóa 1dca8b1](https://github.com/nuyntai19/ann-task-a-research/tree/1dca8b14820f7f1d934255f16819376e4511924c), PiPNN.pdf và PiPNN-II.pdf người dùng cung cấp, `summary.json` P4R gốc có SHA256 `52a395edd9b9b822ba909a8631e6bf4aace75397261035187323113f7ccb0cfe` (đã kiểm tra trực tiếp).

## B. Stock, H17 và Fast v2 thực sự khác nhau như thế nào?

**Stock PiPNN (Stage 2 Pick, đối với MST_DEG=2):** sau `eigen_build_distmat`, mỗi hàng i của leaf quét các j khác i, tính packed key `packFloatAndInt(dist_ij,j)`, `Q.push_back` đủ `s-1` ứng viên và gọi `VQPartialSort(Q,2)` rồi xuất hai cạnh có hướng. Những công việc khác như Partition, `dist_mat`, directed-edge output, Merge/HashPrune, Final robustPrune vẫn thực hiện. Cần phân biệt **VQPartialSort bên trong leaf Pick** với một VQPartialSort *khác* trong AssignLeaders (Partition).

**H17:** chỉ thay phần chọn Top-2 trong `MST_DEG==2` thành hai giá trị packed-double `first`/`second` cập nhật trực tiếp trong lúc quét. Mọi ứng viên và `packFloatAndInt` vẫn được xử lý. Bỏ mảng Q chứa s−1 ứng viên *mỗi hàng*, các `Q.push_back` và `VQPartialSort` ở leaf (nhánh không phải `MST_DEG==2` vẫn giữ giải pháp gốc). `dist_mat` và số cặp quét leaf không tự giảm. H17 không phải thay đổi quy tắc chọn hai hàng xóm; packed-distance và tie-breaking ID được giữ theo source.

**H17 + Fast v2:** giữ chính xác logic H17 và thêm cutoff float `r90_second_cutoff` sau khi đã có hai phần tử. Nếu `dist_ij > cutoff`, bỏ qua pack và so sánh packed-double; nếu bằng ngưỡng hoặc trường hợp đặc biệt thì đi nhánh fallback packed để bảo toàn tie-breaking. Không bỏ tính `dist_mat`, không bỏ quét ứng viên leaf. Việc cập nhật cutoff làm **tăng** một loại phép gán `float`, dù giảm mạnh Pack và so sánh packed-double.

### Mức độ chứng minh từ mã nguồn

| Khía cạnh | Stock | H17 | Fast v2 | Trạng thái số đo |
|---|---|---|---|---|
| Đọc cặp `dist_mat` của leaf | Có | Có | Có | `candidate_scans` H17/Fast bằng nhau đã đo D6 |
| `Q.push_back` Top-2 | Có, một lần / cặp ứng viên | Không ở nhánh N2 | Không ở nhánh N2 | Stock A0 SIFT1M có `top2_q_writes=28.123.433.514` ở R86 WN, nhưng chưa phải so phép gán đầy đủ có kiểm soát cùng binary/vintage |
| `VQPartialSort` trong Pick | Có, 1 lần / hàng leaf nếu có ứng viên | Không với N2 | Không với N2 | Gọi sort suy ra trực tiếp từ source; chưa đo **nội bộ comparator/moves/swaps Highway** |
| `packFloatAndInt` | Mỗi cặp | Mỗi cặp | Chỉ ứng viên qua cutoff | D6 đếm chính xác H17↔Fast |
| `first`/`second` assignment | Không cùng cách biểu diễn | Có | Bằng H17 | D6 đếm chính xác H17↔Fast |
| `cutoff` assignment | Không | Không | Thêm một float local | D6 đếm chính xác |
| `dist_mat`, Partition, HashPrune | Giữ | Giữ | Giữ | Toàn BUILD counter 3-arm cùng nguồn/cùng dataset **chưa đầy đủ** |

**Lưu ý phương pháp đo:** một “swap” ở thuật toán scalar thường có thể được mô tả thành 3 lệnh gán, nhưng trong Highway SIMD `VQPartialSort`, lane shuffles/moves có thể không ánh xạ thành `std::swap`. Không thể viết “bỏ X swap” khi chưa instrument đúng code và thống nhất định nghĩa. `Q.push_back` là writes theo counter source, không được tự đồng nhất với toàn bộ memory writes hoặc tất cả phép gán máy.

## C. Kết quả BUILD 1M — so sánh thực đo

### C1. MS-Turing1M, 4 CPU, ba graph độc lập mỗi arm (P4)

| Chỉ số | Stock | H17 | H17+Fast v2 |
|---|---:|---:|---:|
| BUILD mean wall (s) | 42,051131 | 36,478232 | **33,796617** |
| Δ so Stock | – | **−13,253%** | **−19,630%** |
| Δ Fast so H17 | | | **−7,351%** |
| Peak RSS mean (MiB) | 3.052,70 | 3.057,37 | 3.048,83 |
| CPU utilization mean | 396% | 395,67% | 396% |
| Directed arcs mean | ~52,856 triệu | ~52,855 triệu | ~52,855 triệu |

Dữ liệu gốc P4 `build_manifest.json` **còn chứa** `user_s`, `sys_s`, `involuntary_context_switches` theo từng BUILD; các trường này đã được bổ sung vào `R90_BUILD!U118:V126, X118:X126`. Không suy từ CPU% thành user/system time. Số cung graph không bằng số phép thử cặp và không bằng chi phí chọn Top-2.

**Giới hạn quan trọng:** Stock ELF lấy từ R86, còn H17/Fast từ R90. Chênh 19,630% là chênh thời gian thực đo giữa ba nhánh P4, **chưa được quy hoàn toàn cho thay đổi H17+Fast** khi source/toolchain vintage không khóa đồng nhất. Để khẳng định tác động riêng H17 ở MS-Turing1M, nên có 3-arm build đối chứng cùng snapshot/toolchain/flags.

### C2. SIFT1M — phải tách hai protocol

- **P3.11 4 CPU, cùng H17 control vs Fast:** H17 35,4368465 s; Fast 32,7204212 s; Fast giảm **7,665%**, ba graph độc lập mỗi nhánh. Peak RSS trung bình H17 2.795.152 KiB, Fast 2.799.000 KiB (không phải bằng chứng tiết kiệm RAM). Graph khác nhau ở khoảng 1,00–1,56% số đỉnh trên 4CPU; không được gọi byte-identical.
- **P3.8-v2 1 CPU:** H17 135,494 s → Fast 124,852 s, giảm ~7,854%; graph SHA trùng hoàn toàn khi chạy 1CPU trong protocol đó.
- **H17 lịch sử:** một đối chứng PiPNN Stock → H17 trong nhật ký f30 báo khoảng 50,28 → 44,95 s (~10,60%). Đây là **protocol lịch sử khác** với P3.11; chưa nên nối số trực tiếp thành chuỗi 3-arm ở cùng phiên bản.

`R90_BUILD` hiện đã bổ sung user/system CPU time, context switches, arcs từ **manifest gốc P3.11** cho cả 6 graph.

## D. Đếm số phép toán nội bộ — D6 chứng minh gì?

D6 là chạy diagnostic tách biệt 1CPU, đo **executed source-level counters** trong Pick Top-2 (`MST_DEG=2`) trên prefix SIFT 10K, 100K, 1M; thời gian trên binary instrumented không dùng làm số BUILD wall-time. Mã/graph kiểm toán SHA và kết quả gốc nằm trong `work_summary_1m.json` + `manifest_1m.json` ở commit GitHub đã khóa.

| SIFT n | Candidate scans H17=Fast | H17 Pack → Fast Pack | Giảm Pack | H17 total value compares → Fast | Giảm compares ròng |
|---|---:|---:|---:|---:|---:|
| 10K | 274.608.788 | 274.608.788 → 5.955.297 | 97,831% | 545.150.665 → 281.545.877 | 48,354% |
| 100K | 2.972.620.700 | 2.972.620.700 → 77.482.551 | 97,393% | 5.892.945.778 → 3.063.291.694 | 48,018% |
| 1M | 28.123.433.514 | 28.123.433.514 → 756.889.237 | **97,309%** | 55.738.900.272 → 29.009.246.128 | **47,955%** |

Tại SIFT1M, Fast có **28.003.434.410** FP32 cutoff checks (chi phí **mới**), và chỉ **1.005.811.718** packed-double compares thay vì H17 **55.738.900.272**. Tổng so sánh mới = FP32 checks + packed-double compares, vẫn giảm ròng **26.729.654.144**. Nhưng **candidates=28,123 tỷ không thay đổi**, vì Fast vẫn lấy khoảng cách đã có từ `dist_mat`.

**Gán Top-2 đo thật trên SIFT1M:** H17 và Fast đều có `first_assignments=417.870.131`, `second_assignments=753.408.807`. H17 tổng **1.171.278.938** gán; Fast bổ sung `cutoff_assignments=753.408.807` nên tổng **1.924.687.745** gán. **Số gán được đếm tăng**, không giảm; đây là trade-off đổi một gán float nhỏ để tránh rất nhiều Pack và so sánh packed-double. 100K lần lượt tổng 120.773.942 → 198.250.814; 10K tổng 9.350.976 → 15.305.953.

Các chỉ số khác trong D6: leaf calls 991 / 16.664 / 180.064; leaf point visits 453.297 / 5.999.243 / 59.999.552 tại 10K/100K/1M. Các giá trị được bổ sung `R90_D6_SCALING!A20:S29` và `C_WORK!A644:S679`.

### Điều chưa được đếm trực tiếp theo chuẩn thầy

**Stock Highway VQPartialSort nội bộ**: comparator executions, SIMD lane shuffles, element moves, swaps và toàn bộ memory traffic; chưa có một cuộc đối chứng 3-arm Stock/H17/Fast 1M cùng source snapshot dùng bộ counter thống nhất. **MS-Turing1M D6** chưa có native counters Pack/check/assignments cho ba arm. R86 công việc toàn BUILD nhiều công đoạn **có** các giá trị như `W_P`, `W_L`, merge/hash/prune trong cấu hình cũ, nhưng phải đối chiếu cấu hình A0/A1/A3/A4; A3/A4 thay cả C/K/N nên không là thí nghiệm chỉ thay H17.

## E. SEARCH không bị đánh đổi lớn ở hai tested quality floors

### SIFT1M D7 (10.000 query)

- Recall ≥ 0,990: H17 và Fast đều đạt đầu tiên trong lưới thử ở **beam 76**, Recall mean ~0,990140; QPS mean 8.784,78 → 8.812,10 (**+0,311%** Fast).
- Recall ≥ 0,998: cả hai đạt ở **beam 140**, Recall mean H17 0,9980133 và Fast 0,9980100; QPS 5.216,62 → 5.204,39 (**−0,234%** Fast).
- Counters Search do evaluator công bố tại hai beam này: avg_cmps 2.182/3.322; avg_visited 83/140 theo 3 graph mỗi arm trong D7. Không phải P4 / MS-Turing counters.

### MS-Turing1M P4M + P4R (100.000 query)

- P4M đã tìm thấy **đầu tiên trên lưới 8 beam**: Recall ≥0,990 tại **beam 368** (beam 352 không đạt); ≥0,998 tại **beam 880** (beam 848 không đạt), trên cả **9/9 graph**. Chưa chứng minh là beam nguyên nhỏ nhất toàn cục.
- P4R đo mới **27/27 Search**, tức 3 repeat mới × 9 graph, 2 beam / Search, native audit PASS. `summary.json` SHA256 đã xác minh: `52a395edd9b9b822ba909a8631e6bf4aace75397261035187323113f7ccb0cfe`.

| P4R: mean của 3 graph median | Stock | H17 | Fast | Fast/H17 |
|---|---:|---:|---:|---:|
| QPS beam 368 | 1273,392253 | 1273,673787 | 1271,822144 | **−0,145378%** |
| QPS beam 880 | 570,509725 | 571,168254 | 570,115784 | **−0,184266%** |

P4R xác nhận Recall của mỗi graph không đổi qua 3 Search trên cùng graph; các giá trị Recall gốc có trong `summary.json`. Chênh QPS nhỏ không đủ để chứng minh *tương đương thống kê* hoặc giải thích **nguyên nhân** sai khác. Đặc biệt có một lượt Stock r1 đầu b368 chỉ 1228,4889 QPS, trong khi hai lượt sau 1274,6578 và 1275,5049; việc lấy median làm phép đo bền hơn nhưng không chứng minh nguyên nhân là cache/turbo.

**Lỗi còn tồn tại:** `avg_cmps` của R86 v4 ở beam cao bị tràn 32 bit. Không được sử dụng giá trị b880/b896 đó. R86 G11 Counter64 là thí nghiệm trên các graph khác; muốn so 9 graph P4 phải chạy evaluator Counter64 parity trên **chính 9 graph ấy**. Không có per-query p95/p99 từ phép đo QPS trung bình.

## F. Độ phức tạp và câu hỏi 10M / 50M / 100M / bão hòa

Gọi `s_b` là số điểm trong leaf b, `L` là số lượt tham gia leaf (tính cả lặp), `W_leaf = Σ_b s_b(s_b-1)` là số cặp ứng viên chọn Top-2 có hướng. **H17 và Fast không giảm `W_leaf`**, chúng thay cách xử lý *mỗi* cặp. H17 giữ 2 packed-key O(1) theo hàng i, thay vì vật chứa Q có độ lớn O(s_b). Fast thêm một cutoff check O(1) mỗi ứng viên, bỏ nhiều Pack; vì thế cải thiện hệ số công việc thực thi chứ **chưa chứng minh giảm bậc Big-O của toàn PiPNN**. Việc phân lớp K cố định không chứng minh toàn thuật toán O(n) nếu số lượt partition/leaf và công việc point–leader tăng theo n.

**Bằng chứng trên prefix SIFT10K→SIFT1M:** D6 `candidate_scans` tăng ~102,41× khi n tăng 100×; số mũ khớp hai đầu xấp xỉ **1,00518**. Nhưng counter **Partition `W_P` của R86 Stock A0** tăng từ **3.751.489** (10K) lên **9.667.904.774** (1M), hệ số xấp xỉ **n^1,706** theo *hai đầu* cùng thử nghiệm. `W_L` Stock A0 tăng từ 275.062.085 tới 28.183.433.066 (~`n^1,005`). Đây là lý do phải đánh giá Stage 1 riêng: nếu Partition càng chiếm tỷ trọng lớn thì giảm Pack ở Stage 2 có thể **bão hòa về % wall-time** khi n tăng. Ngược lại, cải thiện cache/SIMD và cấu trúc leaf có thể làm tỷ lệ thay đổi hướng khác. **Không có kết luận nào được phép dự đoán chính xác 10M chỉ từ 1M.**

### Footprint định hướng — không phải peak RSS đo thật

Với đồ thị C160, nếu dùng mô hình `n×(C+1)×8 byte` cho một candidate reservoir và base FP32 100D, cùng số cung mỗi điểm ~52,85 theo graph MS-Turing1M P4:

| Quy mô | Candidate C160, GB thập phân | Base 100D FP32, GB | Graph cung × 4B, GB (nội suy) |
|---|---:|---:|---:|
| 1M | 1,288 | 0,4 | 0,211 |
| 10M | **12,88** | **4,0** | **2,114** |
| 50M | **64,4** | **20,0** | **10,57** |
| 100M | **128,8** | **40,0** | **21,14** |

Tất cả là **sizing model**: graph degree thực và build workspace có thể thay đổi; tổng chưa tính các temporary/copies, Eigen matrices, Parlay/HashPrune, allocator và peak đồng thời. Trên 10M, phải kiểm tra `MemAvailable`, disk free, format input, SHA, GT chính xác, 4CPU pinning; không tự khởi động BUILD gây swap/OOM. 50M/100M chỉ xem như cổng mở rộng phụ thuộc thành công 10M và hạ tầng.

## G. Checklist thí nghiệm còn thiếu trước báo cáo hoàn chỉnh

**P0 — cần để trả lời thầy trực tiếp:**

1. Đối chứng **Stock vs H17 vs Fast** trên 1M với **đúng source/compiler/flags/seed**, đo cả BUILD OFF timed (≥3 graph/arm) lẫn ON diagnostic; không trộn wall-time ON và OFF. Trên SIFT1M cần kiểm tra xem H17 lịch sử f30 có protocol tương thích trước khi quyết định rebuild.
2. Bộ đếm source-defined tại `MST_DEG=2`: Stock `Q writes`, `sort_calls`, Highway comparator/swap/move (định nghĩa SIMD kỹ), H17/Fast Pack, FP32 checks, packed compares, first/second/cutoff assigns; cả ứng viên/quy mô leaf `Σ s(s−1)`; hoàn tất cho **SIFT1M và MS-Turing1M**. Đồng thời toàn BUILD W_P, W_L, merge attempts/hash moves/prune calls nếu muốn giải thích bottleneck toàn hệ thống.
3. Trích profile P4 từ đúng stdout SHA đã khóa và phản biện diễn giải `selection_sum_s`, `matrix_sum_s`, `merge_sum_s` (thời gian **cộng dồn các worker** không đồng nghĩa wall-time tuần tự).
4. Sửa bộ đếm Search 64-bit của evaluator trên **cùng graph P4** và đối chiếu Recall/QPS native parity; không sửa evaluator cũ và không gán giá trị overflow bằng 0.
5. Kiểm toán 10M đầu vào: base 10M fbin shape/dim/endian/file size/SHA, query/GT **thuộc 10M**, nguồn dữ liệu, memory/disk gate trước BUILD.

**P1 — hữu ích cho phần đánh giá hệ thống/thầy:** đo p50/p95/p99 **per-query** với instrumentation tách khỏi benchmark QPS; topology degree/isolated-components/entry-point reachability với graph có SHA; multi-core Search throughput là benchmark *riêng*, không thay thế CPU0; fine-beam sweep nếu mục tiêu là beam sát ngưỡng.

**P2 — tùy định hướng luận văn:** perf PMU LLC/memory bandwidth (nếu hệ điều hành cấp quyền), cache misses, total memory bytes/copy, energy, source-level novelty audit trước đề xuất phương pháp mới.

## H. Quyết định theo cổng (đề xuất)

- **Gate A — R90 1M Audit:** cập nhật sheet từ nguồn hiện có, chuyển `NOT_MEASURED`/`INVALID_COUNTER` thành thí nghiệm riêng, **không tạo số ước lượng**. Bảng các trạng thái: `R90_1M_EVIDENCE_GAPS`.
- **Gate B — 1M Missing Native:** thực hiện riêng các phép đo P0 thực sự chưa có. Nếu bộ đếm Highway comparator/lane move không thể instrument tin cậy, ghi rõ không đo được và mô tả Q writes + sort calls theo source; tránh kết luận vượt khả năng đo.
- **Gate C — 1M Final Report:** bảng Stock/H17/Fast cùng protocol, liệt kê số đếm, đồ thị W_P/W_L, cấp tính toán, graph/Recall/QPS, và các giới hạn. Chỉ xuất bản báo cáo cuối khi không còn mục P0 âm thầm treo.
- **Gate D — MS-Turing10M:** preflight read-only / resource + exact GT, thử pilot, sau đó ≥3 BUILD per arm và SEARCH đúng quality floor, profiling và counters so với 1M để xác định speedup có bão hòa hay không.
- **Gate E — new BUILD algorithm:** chỉ chọn nút thắt mới (dist_mat/Partition/Merge/Prune) dựa trên 10M profile và đối chiếu PiPNN II/prior art; không nhầm tối ưu code với sáng tạo thuật toán mới.

**Kết luận hiện tại:** H17 giảm công việc cấp phát/ghi Q và bỏ leaf partial sort trong N2; Fast v2 giảm pack + packed comparisons bằng float cutoff dù tăng phép gán cutoff. Thời gian BUILD 1M giảm thực tế, Search tại tested quality floor không bị đánh đổi lớn trong thí nghiệm, **nhưng chưa đủ counter nội bộ Stock Highway và MS-Turing D6 để kết luận toàn bộ định lượng theo yêu cầu thầy**. Đây là các việc cần đo thêm trước báo cáo đóng sổ và trước khi BUILD 10M.
