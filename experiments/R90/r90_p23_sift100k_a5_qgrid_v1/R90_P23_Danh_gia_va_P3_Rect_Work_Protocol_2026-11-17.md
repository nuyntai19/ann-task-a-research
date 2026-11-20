# R90 P2.3 — đánh giá và R90 P3 rectangular work feasibility

**Ngày:** 17/11/2026. **Dữ liệu:** log terminal do người nghiên cứu cung cấp. Không truy cập artifact Ubuntu gốc; các giá trị dưới đây được đối chiếu logic theo log và script R90 P2.3 có SHA `ee2c5f607ab1155fc5cee719151b0608de1164e300d7a058689729846a25df8d`. Audit native được log báo PASS. **1 BUILD mỗi q mới, 3 Search runs cho mỗi graph (các graph baseline từ P2.1).**

## 1. Các mốc kiểm toán

- `R90_P23_INPUT_SHA_PASS` base/query/GT/evaluator/ELF, preflight PASS.
- A5 q0.5%, q2%, q5% BUILD native PASS; source A5 + cùng selector degree sau Pass1.
- Quét 18 beam cho ba q mới, tất cả đạt cả hai Recall floor 0.990 và 0.998.
- 3 Search repetitions cho 6 arms (18 processes); `R90_P23_AUDIT_PASS_BUILDS_AND_REPEATED_SEARCH_SHA`, exit code 0.
- **Không suy ra 3 BUILD** từ 3 lần Search. Chưa chứng minh lợi thế ở exact matched Recall hoặc trên heldout khác.

## 2. Dữ liệu pilot

| Arm | BUILD giây | Giảm BUILD vs N2 | Pass2 proxy W_L bỏ được | QPS @ floor .990 | Beam .990 | Recall .990 | QPS @ floor .998 | Beam .998 | Recall .998 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Stock N1 | 6.580 | 48.17% | 100% (không có Pass2) | 17684.561 | 72 | .99011999 | 9914.399 | 144 | .99851000 |
| Stock N2 | 12.695 | baseline | 0% | 17857.525 | 64 | .99207997 | 11932.263 | 104 | .99808002 |
| A5 q0.5% | 9.989 | 21.31% | 45.03% | 17086.656 | 72 | .99229997 | 10518.223 | 128 | .99838001 |
| A5 q1% | 10.893 | 14.19% | 28.53% | 18771.975 | 64 | .99006999 | 10481.400 | 128 | .99853998 |
| A5 q2% | 11.795 | 7.09% | 12.96% | 18406.648 | 64 | .99115998 | 11402.651 | 112 | .99822003 |
| A5 q5% | 12.649 | 0.36% | 1.96% | 17966.707 | 64 | .99204999 | 11979.046 | 104 | .99804997 |

Những tốc độ BUILD dưới đây là **single-build pilot**, dễ nhạy cảm với nhiễu hệ thống. QPS là các trung vị của 3 Search runs, không phải 3 graph-median. Khi so ở quality floor, Recall từng arm **không khớp đúng với nhau**. q5 nhỉnh hơn Stock N2 0.39% QPS và 0.36% BUILD tại floor .998, **không đủ** để tuyên bố cải thiện. q1 đạt .990 chỉ vượt ngưỡng 0.00006999.

## 3. Quyết định sau P2.3

- **Giữ q1%** cho nhánh target .990: pilot giảm 14.19% BUILD và tăng 5.12% QPS vs Stock N2 tại floor .990, nhưng Recall thấp hơn Stock N2.
- **Giữ q2%** làm nhánh đánh đổi ở target .998: giảm 7.09% BUILD, giảm 4.44% QPS vs Stock N2; chưa có Pareto win chắc chắn.
- **Chưa giữ q5% làm ứng viên chính:** hầu như không cắt được Pass2 leaf work. Q0.5% dùng làm đối chứng tiết kiệm BUILD và kiểm tra selector; ở floor .990 Stock N1 có cả BUILD và QPS tốt hơn q0.5%, nhưng chưa equal Recall.
- **Không mở quét q10/25%** theo leaf gating mặc định, vì P1 đã cho thấy coverage gần như 100% ở các mức đó tại SIFT10K.
- Bắt buộc thêm H17 C160 N1/N2 cùng C/K/R/N và cùng dataset/GT/evaluator, trước khi so sáu arm.

## 4. R90-P3: audit rectangular work, chưa phải RADAR mới

Script mới `r90_p3_rect_work_probe_v1.py`:

1. Chỉ dùng **bản P0 A5 staged source SHA-pinned** trong `R90/r90_p0_stock_a5_compile_gate_v1/a5_source` để copy sang thư mục kết quả mới, không chỉnh sửa P0/R85/R86/P2.
2. Thêm các atomic counters **observation only** trong vòng lặp leaf; khi `R90_A5_MODE=dryrun`, vẫn chạy `RunLeaf` đầy đủ. Graph SIFT100K bắt buộc **byte-identical** với Stock N2 graph SHA `4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1`.
3. Bốn fractions q=0.5/1/2/5%. Các thống kê cho từng lá kích thước m và số hàng Q q_B gồm:
   - `triangle_pairs = Σ m(m+1)/2` — proxy số phần tử tam giác của stock SYRK.
   - `rectangular_pairs = Σ m × q_B` — proxy số phần tử của RADAR rectangular.
   - Tổng bản sao điểm trong các lá, tổng bản sao Q; bins q_B=1..4 / 5..16 / >=17; số lá có rectangular work >= triangular.
   - Bắt buộc tái tạo chính xác coverage đã đo trong P2.3. R90_A5_LEAF_SCREEN `WL_total = Σ m²` là một **proxy khác**; không được tráo các mẫu số.
4. `preflight` kiểm tra source SHA, dependency SHA, base SHA, graph SHA và P2.3 parent manifest. `pilot` chỉ chạy khi output chưa tồn tại; `audit` kiểm tra nguồn, ELF, graph và stdout hash.

**Hạn chế lớn:** Các proxy không tính overhead memory, norm, Top2, scalar loops, cross-leaf duplication impact, và **không thể chứng minh RADAR giữ incoming reverse edges từ hàng không thuộc Q**. Với q rất ít, GEMV/rectangular GEMM có thể chậm hơn kỳ vọng dựa trên số FLOPs. Sau P3 phải có microbenchmark Eigen SYRK vs GEMM rectangular thật, và một RADAR source thực sự, trước khi đưa vào so sánh sáu arm.

## 5. Ranh giới claim

- P2.3: native build/graph/search pilot PASS, không phải thắng lợi mới ở exact-matched recall.
- P3 nếu PASS: chứng minh **cơ hội tính toán chữ nhật theo số hàng**, không chứng minh runtime speedup hay chất lượng graph.
- So sánh đủ A0, A1, A5, RADAR, H17+A5, H17+RADAR cần: pair/source/flags, build 3 independent graphs/arm, 5 native searches/graph/quality floor, Recall/QPS/BUILD/operation counters, và so sánh cùng BUILD budget. Thiết kế lựa chọn q/kernels không được dùng test GT để quyết định online.
