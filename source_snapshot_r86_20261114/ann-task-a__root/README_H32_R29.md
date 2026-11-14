# H32-R29 — CHARM-R0 / LOSF-R0 Offline Audit Toolkit

**Trạng thái 29/10/2026:** bộ mã kiểm toán được viết và chạy unit/synthetic tests; **chưa chạy trên SIFT1M thật** do môi trường chat không chứa `sift1m.leaves.bin`, `sift1m_base.fbin` và candidate pool/graph binary. Không được gọi kết quả mẫu là speedup BUILD hay xác nhận novelty.

## 1. Vì sao phải kiểm thử Core/Halo trước BUILD?

Theo mã `ParAlg/PiPNN` commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`:

* `assign_leaders` tính khoảng cách tới leaders và giữ fanout gần nhất (rank nội bộ, không xuất ra file). [`pipnn_utils.h#L332-L425`](https://github.com/ParAlg/PiPNN/blob/443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd/algorithms/PipNN/pipnn_utils.h#L332-L425).
* `SelectAndAssignLeaders` chỉ giữ `(leader_id, point_id)`, rồi `group_by_index` và `MergeBuckets`, `SplitDuplicates` có thể thay đổi bucket cuối. [`pipnn.h#L47-L84`](https://github.com/ParAlg/PiPNN/blob/443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd/algorithms/PipNN/pipnn.h#L47-L84).
* File H18 `sift1m.leaves.bin` chỉ có `H18LEAF1`, `n_base`, `n_leaves`, lặp `[leaf_len][IDs]`. **Không chứa nhãn Core/Halo**. Chọn ngẫu nhiên 25% Core là **control**, không phải cơ chế CHARM của Gemini.

Do đó ba chế độ CHARM trong toolkit là `random`, `centroid-proxy`, và `degree-oracle` (biết exact Top2, chỉ để kiểm tra khả năng trên lý thuyết); chế độ `flags` chấp nhận mask ngoại sinh sau khi người nghiên cứu đã chứng thực provenance từ leader assignment. Một file mask khớp cấu trúc tự nó **không** chứng minh Core đúng.

## 2. Cài đặt trên Ubuntu

Toolkit yêu cầu Python 3.9+ và NumPy; máy chạy pipeline đã cài Python có thể dùng môi trường sẵn có.

```bash
python3 -m pip install numpy  # chỉ nếu chưa có numpy trong environment
python3 ann_task_a_r29.py selftest --dir experiments/H29/toy
```

Hãy đặt `ann_task_a_r29.py` ở `~/ann-task-a/` hoặc thư mục làm việc khác. Không sửa source PiPNN hoặc rebuild.

## 3. Chạy kiểm toán dữ liệu H18 (không BUILD)

Đường dẫn leaf đã ghi trong lịch sử nhóm:

```bash
cd ~/ann-task-a
LEAVES="$PWD/experiments/H18/phase1_leaf_overlap/sift1m.leaves.bin"
mkdir -p experiments/H29
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ann_task_a_r29.py validate \
  --leaves "$LEAVES" --sample 256 --hash \
  --output experiments/H29/sift1m_leaf_validation.json
```

**Điều kiện khớp nhật ký H18** (không phải kết quả mới): `n_base=1000000`, `n_leaves=85529`, `memberships=29995085`, `pair_events=7289822248`, file size `120322480` bytes. Nếu lệch, **dừng**. Lưu SHA256 trước mọi phép thử.

## 4. CHARM-R0: Dùng `.fbin` Float32 thực, chỉ lấy mẫu leaf

Tìm file base phù hợp (tên thực tế có thể khác):

```bash
find ~/ann-task-a -type f \( -iname '*sift*base*.fbin' -o -iname '*sift*1m*.fbin' \) -print
```

Chọn đúng file có header 1.000.000 × 128 và đúng byte length `8+4×1000000×128`. Đừng dùng file queries làm base.

```bash
BASE="/DUONG_DAN_THUC_TE/sift1m_base.fbin"  # thay bằng đường dẫn tìm được
for MODE in random centroid-proxy degree-oracle; do
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ann_task_a_r29.py charm \
    --leaves "$LEAVES" --fbin "$BASE" --mode "$MODE" \
    --gamma 0.25 --sample 64 --seed 20261029 \
    --output "experiments/H29/charm_${MODE}.json" \
    > "experiments/H29/charm_${MODE}.stdout"
done
```

* `pair_savings_fraction`: tỷ lệ cặp bị bỏ **trong sample** (không phải BUILD speedup, cũng không phải ước lượng nhân quả chính thức).
* `top2_event_coverage`: tỷ lệ các proposal hướng Top-2 từ full clique còn khả năng xuất hiện khi loại Halo×Halo trên **cùng leaf**. **Không** phải global candidate coverage/Recall.
* `nearest_event_coverage`: tỷ lệ proposal láng giềng gần nhất của từng hàng còn trong tập pair.
* `degree-oracle` dùng Top-2 thật để gán Core; là heuristic đối chứng **lạc quan**, KHÔNG là upper bound toán học và **không** được coi là construction hợp lệ vì cần biết Top-2 thật từ trước.

**Lưu ý số học:** phép tính khoảng cách dùng NumPy Float32 GEMM và tie-break theo ID, không bảo đảm bitwise trùng với implementation Eigen/Top-2 của PiPNN dù công thức cùng squared-L2. Nếu có ties/sai số gần ngưỡng, cần đối chiếu source-native.

**Thiếu để kết luận CHARM:** nhãn Core/Halo theo leader gốc, global proposal dedupe/coverage, HashPrune, searcher cùng index-byte budget, và end-to-end BUILD. Phải chứng minh nguồn gốc nhãn trước khi chạy `--mode flags`. Trong mã gốc, rank leader không còn nguyên qua merge/split; chưa có patch instrument được xác minh để xuất `H29CORE1`. Không được tự tạo nhãn giả rồi gọi đó là FACT.

### Format nhãn nếu sau này instrument builder

`H29CORE1` (8 byte ASCII) + `uint64 little-endian n_leaves` + lặp `[uint32 little-endian leaf_len][leaf_len × uint8 is_core]`, với thứ tự point trong mỗi leaf **khớp byte-for-byte** file `H18LEAF1`. Metadata provenance bắt buộc: source hash, seed, fanout scheme, cluster ID/lineage, quy tắc xử lý merge/split và hash file tương ứng.

## 5. LOSF-R0: đo front-width trên membership thật (không cần vector)

```bash
OPENBLAS_NUM_THREADS=1 python3 ann_task_a_r29.py losf \
  --leaves "$LEAVES" --workers 1 2 4 8 --random-order \
  --output experiments/H29/losf_sift1m.json \
  > experiments/H29/losf_sift1m.stdout
```

Chỉ số `peak_live_fraction` là **proxy idealized scheduling** cho số reservoir sống đồng thời nếu có thể finalize ngay khi mọi membership đã hoàn tất, tính theo batch W leaf cùng chạy. Nó **không** phải peak RSS. Mô hình chưa tính completion skew, reverse updates, allocator, synchronization, graph output. Dùng nó để **bác bỏ sớm** nếu front quá lớn; không dùng một mình để tuyên bố giảm RAM.

## 6. Kill gates trước khi H33

* **CHARM**: nếu Top-2 coverage giảm nhiều, không được bù bằng cách thay ngưỡng tùy tiện sau khi nhìn GT. So độ phủ và wall time với giảm fanout ở cùng work/quality; chỉ triển khai khi có tín hiệu thực.
* **LOSF**: nếu `Fmax/n` quá lớn (gợi ý dừng >0.50 theo shortlist Claude), hoặc reservoir nén đơn giản đạt RSS gần tương đương, không làm builder mới. Phải bảo đảm không có late proposal và hash/prune tương đương trước finalize.
* **CORE-Slack**: chưa chạy trong toolkit này vì thiếu `leaf_proposals.bin`, `postprune_final.graph` và binary reader validated. Không được khẳng định kết quả.
* **PiPNN II**: source SISAP all-kNN không đại diện baseline ANN proximity-graph end-to-end; so sánh công bằng vẫn BLOCKED.

## 7. Báo cáo đã chạy trong phiên này — synthetic only

`selftest` và 3 chế độ CHARM + chế độ flags, `validate`, `losf` đều chạy được với fixture 8 điểm/4 leaf (tự động tạo). Các tỷ lệ từ fixture chỉ chứng minh mã chạy/kiểm tra phản ví dụ, không có giá trị dự báo trên SIFT1M.

Khi chạy trên Ubuntu thật, gửi lại JSON/STDOUT + SHA256 để đối chiếu với H18 trước khi quyết định GO/HOLD/NO-GO.
