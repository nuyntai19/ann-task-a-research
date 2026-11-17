# H24-R0d — Bắt đầu đối chứng Dense LOW/HIGH (26/10/2026)

**Trạng thái:** Bộ công cụ đã chuẩn bị và tự kiểm thử thành công. **Chưa chạy BUILD thực tế** trên Ryzen 7 3750H của bạn vì môi trường ChatGPT không gắn vào laptop Ubuntu và không có vector dataset/binary. Không tự diễn giải kết quả synthetic test thành BUILD speedup. STH vẫn **HOLD**.

## 1. Phạm vi và bảo toàn dữ liệu

Thử nghiệm này chỉ trả lời câu hỏi: Với cùng một Dense builder, tăng memberships từ **m=3** lên **m=5** tạo ra khác biệt về BUILD và native ANN query quality thế nào? Tại mục tiêu STH speedup 1,15×, còn bao nhiêu thời gian cho scoring + adaptive beam + reverse repair?

Bản chính đối chiếu: mã nguồn công khai `https://github.com/zevahcle/graft-ann`, nhánh **fgraft**. Tham số giữ cố định L=240, C=200, `dense-prune=1`, HSP `dense-spine=3`, `dense-spine-s=0`, `dense-spine-cap=16`, `dense-spine-repair=1`, R=64, alpha=1, metric L2 cho SIFT, BUILD 4 worker, search 1 worker, seed=42, `ef=[60,100,140,200,300,400,600]`. **Không thay đổi H17–H23**; mọi output mới nằm trong `~/ann-task-a/experiments/H24/`.

**Đối chứng m=3/m=5 là một cặp feasibility triage; nó không thay thế high-budget tuned baseline**. Chỉ thay membership. Vì final spine được union sau prune, hai graph có thể khác edges, degree và bytes dù chung cap. Log phải được đọc cùng graph bytes và Recall/QPS; không được dùng thời gian của cả CLI làm BUILD.

## 2. Dùng trên Ubuntu của bạn

Tải và giải nén `H24_R0d_dense_pair_kit.zip` vào một thư mục mới, ví dụ `~/ann-task-a/experiments/H24/kit/` (chỉ thêm file mới). Yêu cầu `python3` + NumPy, `git`, `g++`, `make` và kết nối mạng nếu cần clone source public. Dùng 2 file nguồn SIFT1M thực (`sift_base.fvecs`, `sift_query.fvecs`). Có thể tìm đường dẫn bằng lệnh:

```bash
find ~/ann-task-a -type f \( -iname '*base*.fvecs' -o -iname '*query*.fvecs' \) -print
```

Sau khi thay **2 đường dẫn thực** mà lệnh `find` trả về:

```bash
cd ~/ann-task-a/experiments/H24/kit
bash h24_run_dense_pair_ubuntu.sh \
  --base '/duong/dan/sift_base.fvecs' \
  --query '/duong/dan/sift_query.fvecs' \
  --nbase 50000 --nquery 200 --seed 42 --metric l2 \
  --mode run
```

Script tự tạo tập con ngẫu nhiên base 50k (seed=42) và lấy 200 **external queries** đầu tiên. **Ground truth sẽ được tính lại chính xác trên tập con 50k** bằng thuật toán exhaustive batched; tuyệt đối không dùng GT Top-10 của full SIFT1M cho subset. Script tự clone `fgraft` vào `~/ann-task-a/experiments/H24/vendor/graft-ann` nếu chưa có, build **duy nhất** `src/fg` bằng `make -C src fg -j2`, ghi SHA Git, sau đó chạy 2 BUILD với tham số như nhau trừ `m=3`/`m=5`. Không sửa source gốc hoặc thư mục H17–H23. Mỗi log được lưu riêng, từ chối ghi đè khi chạy lại.

Nếu đã có `graft-ann` bản fgraft, thêm `--graft-dir '/path/to/graft-ann'`. Với GloVe metric cosine, thêm `--metric cos` và dữ liệu phù hợp. Trước khi chạy, `--mode plan` chỉ in kế hoạch mà không clone/build.

**Giới hạn:** 50k là pilot xác nhận cơ chế đối chứng và time-headroom sơ bộ; không đại diện điều kiện 1M/100M và không đủ để chấp nhận một paper. Nếu kết quả không có quality gap, đó là NO-GO của *cặp cấu hình thăm dò*, không phải của mọi biến thể STH.

## 3. Đọc kết quả sau chạy

Gửi file mới:

`~/ann-task-a/experiments/H24/dense_pair_n50000_q200_seed42_L240_m3v5_HSP3/gate_results.json`

Nên gửi cả `dense_low_m3_seed42.log`, `dense_high_m5_seed42.log` và `run_manifest.json` để kiểm toán BUILD source logs, graph edge bytes và query ladder. Parser lấy `leaders + candidates + prune`, trong đó nhãn `prune` của source bao gồm ending/spine; nó không cộng thêm pha spine hai lần. Dùng native QPS/Recall trong cùng searcher và đọc cả độ lớn graph.

**Giới hạn thời gian được đăng ký:**

\[
T_{\mathrm{extra,max}} = T_{\mathrm{HIGH}}/1.15 - T_{\mathrm{LOW}}.
\]

- Nếu `<=0`, mục tiêu tăng tốc ít nhất 1,15× là **bất khả thi với chính cặp LOW/HIGH** ngay cả giả sử scoring/beam/repair miễn phí. Dừng ở cặp đó, không code rescue.
- Nếu `>0`, đây chỉ là còn ngân sách; **không** xác minh được hard-tail nhỏ, beam cứu được hay cơ chế mới.
- Nếu HIGH không cải thiện đáng kể đường cong quality, không cần rescue về mặt mục tiêu chất lượng; kiểm tra lại có đủ quality gap hay không, không kết luận STH có gain.
- Muốn nâng GO còn phải qua: phân biệt prior art FastKCNA/Graft/NGFix/PIGR, causal intervention cho hard vertices, measured wall cost rescue trên CPU, matched Recall–QPS/bytes, nhiều seed và dataset.

**Chú ý về độ đo:** So Recall ở cùng `ef` chỉ để thăm dò, **không phải** so QPS ở matched Recall; không được gọi 1 seed là kết luận khoa học. Có thể đo 200k sau khi 50k pass preliminary gate, nhưng cần chọn thêm một corpus khó có GT đúng.

## 4. Kiểm thử đã hoàn tất trong phiên ChatGPT

- `h24_prepare_real_subset.py --selftest`: **PASS**, bao gồm kiểm tra tie-breaking của 10 láng giềng.
- Fixture `.fvecs` nhân tạo 1.400 base ×16D, lấy 1.200 vector base và 100 queries: **PASS**, GT đối chiếu với NumPy exhaustive cho 5 queries.
- `h24_r0d_dense_pair_gate.py --mode selftest`: **PASS** parse log mô phỏng và negative-headroom precedence.
- `bash -n h24_run_dense_pair_ubuntu.sh`: **PASS**.
- `h24_run_dense_pair_ubuntu.sh --mode plan` trên fixture: **PASS**; **không clone, không BUILD**.

Không có `.npy` dữ liệu SIFT1M, binary Graft/fgraft, hay log native BUILD trên Ubuntu trong phiên này; vì vậy chưa có số liệu `T_LOW`, `T_HIGH` hoặc speedup nào được đo.

## 5. Nguồn kiểm chứng

- Builder CLI: https://github.com/zevahcle/graft-ann/blob/fgraft/src/main.cpp
- Dense builder phase/timings/prune/spine: https://github.com/zevahcle/graft-ann/blob/fgraft/src/build.cpp
- Build flags: https://github.com/zevahcle/graft-ann/blob/fgraft/src/fg.hpp
- Build `Makefile`: https://github.com/zevahcle/graft-ann/blob/fgraft/src/Makefile
- Dự án H17–H23: https://docs.google.com/document/d/185pgBkUudDkF-HvqxM2xPgV3f1Q7hwjbIuusq6AnIbc/edit
