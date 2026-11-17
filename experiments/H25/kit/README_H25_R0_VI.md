# H25-R0 — Duplicate-Aware Fixed-Budget Candidate Backfill

**Ngày thiết kế:** 26/10/2026. **Trạng thái:** công cụ OFFLINE đã chạy self-test synthetic; **chưa chạy H18-SIFT1M trên laptop của người nghiên cứu**. Không phải thuật toán graph builder hoàn chỉnh, không có BUILD speedup/Recall/QPS và **không chứng minh novelty**.

## 1. Mục tiêu và bất biến

Kiểm tra giả thuyết: Khi nhiều overlapping leaves liên tiếp đề xuất cùng cạnh có hướng `(u,v)`, các occurrence thứ hai trở đi có thể được thay bằng hàng xóm thứ 3/4/… trong **chính leaf đó** mà không tăng số directed proposal events. Khoảng cách đã có thể được lấy từ dense leaf distance matrix nếu tích hợp vào PiPNN builder.

- Đơn vị kiểm toán là **directed proposal `(u,v)`**, không phải undirected pair, không phải pairwise GEMM redundancy.
- Giữ nguyên occurrence **đầu tiên** của *mỗi* directed key gốc. Chỉ các occurrence sau mới được phép thay. Vì thế `baseline_unique_keys ⊆ proposed_unique_keys` ở **proposal-union trước HashPrune**.
- Giữ đúng **một output trên mỗi proposal event**, không tự tăng `mst_deg=2` thành `mst_deg=4` ở graph builder. Việc *xem* Top-4/Top-8 là để lựa chọn thay thế, vẫn chỉ output 2 proposals/source/leaf.
- `D_GEMM_new = D_GEMM_original` là thuộc **giả thuyết thiết kế builder tương lai**: các giá trị distance vốn đã được tính cho nguyên leaf. Script offline này **tái tính** khoảng cách trên các sampled leaves, có overhead thật và không đo BUILD.
- Không có bảo đảm rằng HashPrune, RobustPrune, degree, Recall hay QPS sẽ giữ nguyên/cải thiện.

## 2. Nguồn đúng cùng lần BUILD

**Dùng file H18-R1 thật:**

- Capture: `~/ann-task-a/experiments/H18/phase2_candidate_audit/leaf_proposals.bin`
- Dataset: `~/ann-task-a/data/sift1m.fbin`
- Capture schema được xác minh trong phụ lục H23-R1.0b: 32 bytes header `H18R1P01`, `uint64 offsets[leaf_count+1]`, `uint64 keys[proposal_count]`, `key=(src<<32)|dst`.
- Theo H23 đã xác minh: SHA256 của capture là `13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95`; 1.000.000 vertices, 85.529 leaves, 59.990.170 directed proposals; unique=24.186.173. Script từ chối dữ liệu sai SHA/shape để **không** trộn BUILD khác nhau.
- **Không lấy** leaf membership từ `H18-C1` vì thuộc lượt BUILD khác. Leaf membership được khôi phục từ *các source IDs trong chính per-leaf proposal span* của H18-R1; trên mỗi leaf nguồn `u` phát đúng 2 đề xuất, đích phải nằm trong cùng leaf. Chỉ khi các kiểm tra này PASS mới chấp nhận.

## 3. Chuỗi lệnh trên Ubuntu

Tải ZIP này về thư mục `~/Downloads`, sau đó:

```bash
mkdir -p ~/ann-task-a/experiments/H25/kit
cd ~/ann-task-a/experiments/H25/kit
unzip -o ~/Downloads/H25_R0_backfill_kit.zip -d .
source ~/ann-task-a/.venv/bin/activate

python3 h25_r0_backfill_gate.py --mode selftest
python3 h25_r0_backfill_gate.py --mode plan
python3 h25_r0_backfill_gate.py --mode run --phase pilot --sample-leaves 64 --rank 4 --seed 42
```

Mặc định tool chỉ **đọc** H18 capture và SIFT1M fbin. Không sửa các tệp H17–H24, không BUILD PiPNN, không ghi đè graph. Kết quả mới:

```bash
cat ~/ann-task-a/experiments/H25/r0_candidate_backfill_sift1m_seed42/report.json
```

Nếu muốn thử rank 8 **sau** khi có báo cáo Top-4, dùng output riêng để không ghi đè R0:

```bash
python3 h25_r0_backfill_gate.py --mode run --phase pilot --sample-leaves 64 --rank 8 --seed 42 \
  --out ~/ann-task-a/experiments/H25/r0_candidate_backfill_top8_sift1m_seed42
```

Yêu cầu: Python3, NumPy trong `.venv`; máy có **MemAvailable >=5 GiB** để dựng bảng unique / first occurrence 60 triệu events. Tắt app nặng nếu script dừng vì thiếu RAM. SHA input sẽ được kiểm tra trước khi load dữ liệu. `--skip-sha` chỉ dùng để debug input khác, **không chấp nhận kết quả thiếu provenance làm bằng chứng**. Không dùng `--force` nếu không muốn ghi đè **output H25**.

## 4. Ba chính sách offline

1. `nearest`: trên một directed proposal bị lặp, chọn candidate từ rank>=3 *gần nhất* chưa được baseline emit trước event hiện tại. Đối với input R1, first occurrence của baseline key được xác định bằng oracle global sort. Khi đưa vào builder thật, phải thiết kế cấu trúc state/parallel policy mới; tool này chưa cung cấp.
2. `random`: như `nearest` nhưng chọn ngẫu nhiên trong số local rank-tail candidates hợp lệ; kiểm tra có phải nearest matters hay chỉ cần thêm candidate bất kỳ.
3. `hindsight`: chỉ chọn những tail candidates **không xuất hiện ở bất kỳ đâu** trong baseline directed union toàn bộ capture. Đây là oracle có thông tin tương lai, **không khả thi tại BUILD**; là heuristic thuận lợi để chẩn đoán, **không được gọi là cận trên tối ưu toán học**.

Để bảo toàn union baseline, tool luôn giữ occurrence đầu tiên của mọi `(u,v)`; chỉ thay subsequent occurrences. Tool xử lý sampled leaf IDs theo thứ tự tăng (canonical). Nếu rank Top2 tính lại từ fbin không khớp Top2 capture ở một source row, **bỏ qua cả row ấy**, không thay proposal, và báo tỷ lệ lệch. Nếu tỷ lệ đối chiếu Top2 toàn sample dưới 98%, tool từ chối báo pilot là oracle hợp lệ.

**Quan trọng:** `nearest` trên H25-R0 cũng là *offline replay* có thông tin occurrence global, không chứng minh bounded-memory shared-state hay parallelism khi chạy builder.

## 5. Các metric được phép kết luận từ R0

Trong `report.json`:

- `baseline_proposal_events`, `baseline_unique_directed_keys`, `baseline_duplicate_fraction`: kết quả toàn bộ H18-R1, **không phải speedup**.
- `sample_design` (sampled leaves/events, Top-2 agreement): kiểm chứng sampling/provenance.
- `duplicate_baseline_slots_in_valid_rows`: số slot lặp của **sample**, trên các row có đối chiếu Top2 thành công.
- `policies.<name>.replacements`: số slot trong sample được thay.
- `policies.<name>.novel_full_union_keys`: số **directed key thực sự mới so với union toàn bộ H18-R1** trong phần được thay. Có ích hơn số replacement thô.
- `policies.<name>.selected_in_later_baseline`: key được chọn trước nhưng vốn đã xuất hiện ở một leaf khác về sau; có thể giảm redundancy theo thời điểm nhưng **không tăng final proposal-union**.
- `fallback_duplicates`: không tìm được tail phù hợp, giữ nguyên proposal.
- `replacements_sample.csv`: tối đa 2.000 quyết định được ghi làm trace, không phải toàn bộ các thay đổi.

### R0 tuyệt đối CHƯA trả lời

- Các candidate mới có sống qua HashPrune/final prune không?
- Có cải thiện Recall@10, QPS theo same searcher, NDC, connectivity không?
- Chạy trên PiPNN BUILD thực có bao nhiêu overhead và shared synchronization?
- Graph bytes / degree có khớp baseline không?
- Có mới so với PiPNN, Three Composable Stages, ParlayANN, PAG hay không?

## 6. Kill-gate trước khi sửa C++

Đây là **ngưỡng điều hành thăm dò**, không phải tiêu chuẩn hội nghị hoặc kết quả hiện có.

- **Stop / NO-GO cho backfill Top-4 trong pilot:** Top2 provenance không khớp (sau kiểm tra nguyên nhân float tie), hoặc `hindsight` tạo thực sự mới dưới 1% của duplicated sample slots *và* `nearest` cũng gần 0; thêm rank 8 chỉ khi có giải thích rõ vì sao 4 không đủ.
- **HOLD:** Nhiều slot được thay nhưng gần như tất cả key đã nằm trong union gốc; hoặc chỉ hindsight có khả năng thêm key, còn nearest gần như không.
- **GO sang H25-R1 (chỉ là GO cho kiểm chứng):** Nearest có khả năng tạo thêm directed keys có ý nghĩa với cùng sự kiện proposal, và tốt hơn random về tính khả dụng/tập ứng viên (nếu chỉ bằng random thì giá trị của quy tắc nearest yếu). Cần đo lại trên mẫu lớn hoặc seed khác để xác định ổn định.

**H25-R1 mới được phép** thiết kế patch BUILD và replay graph để đo candidate survival, degree, Recall/QPS. Nếu không có lợi ích final graph ở matched degree/bytes thì dừng, không tối ưu code sâu. Nếu có tín hiệu đủ mạnh mới thử shared-state/scheduling bounded memory/parallelism (H25-R2), so trực tiếp PiPNN/H17/Three Stages. Việc giữ proposal set bao hàm không tạo bảo đảm monotone Recall.

## 7. Prior art bắt buộc

- PiPNN (2026): https://arxiv.org/abs/2602.21247 ; mã dùng trong nhóm: https://github.com/ParAlg/PiPNN/tree/443a328/algorithms/PipNN
- Building Navigable Graphs Without Search in Three Composable Stages (2026): https://arxiv.org/abs/2610.09041
- Batched Feedback and the Random-Access Wall (2026): https://arxiv.org/abs/2609.30493
- ParlayANN (PPoPP 2024): https://arxiv.org/abs/2305.04359

Ý tưởng duplicate backfill hiện chỉ là một **giả thuyết**, không phải claim chưa ai làm. Những primitives như Top-k, sorting/group-by-source, dedup và HashPrune đều đã có hoặc là kỹ thuật chung. Sự khác biệt cần bảo vệ sau này là **quy tắc tái phân bổ slot dưới fixed budget đi kèm work/span + bounded memory và Pareto improvement thực đo**; nếu không có đầy đủ các điều kiện ấy, không gọi là đóng góp nghiên cứu mới.
