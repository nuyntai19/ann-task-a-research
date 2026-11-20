# R90-P4 — MS-Turing1M: Stock vs H17 vs H17+Fast v2, 4 CPU

**Trạng thái (2026-11-18):** Runner mới chỉ PASS `py_compile` và `selftest` cục bộ; chưa chạy native Ubuntu, chưa có kết quả BUILD hay Search mới trên MS-Turing1M.

## 1. Tại sao thực hiện P4?

- Kết quả SIFT đã đóng băng: 1CPU SIFT1M Fast v2 so H17 giảm 7,8544% BUILD và graph SHA trùng; 4CPU SIFT1M Fast v2 giảm ~7,6655% BUILD, 3/3 cặp thắng, Peak RSS gần như không đổi. D7 native trên sáu graph SIFT1M: cả sáu đạt Recall@10 ≥0,99 ở beam76 và ≥0,998 ở beam140; QPS Fast/H17 1,003110 và 0,997656.
- D6 native một CPU SIFT10K, SIFT100K, SIFT1M đo các phép toán nguồn trong Top-2 (MST_DEG=2); tại 1M giảm 97,3087% Pack và 47,9551% tổng so sánh giá trị Top-2.
- Gemini đưa ra giá trị Stock→H17→Fast tổng ~24–28% trên SIFT100K, nhưng Stock và Fast có thể lấy từ các campaign khác nhau; **không gọi đây là benchmark paired cùng campaign**. Với MS-Turing1M, P4 cố gắng đo cả ba nhánh trong cùng một chiến dịch, đồng thời kiểm tra tính tổng quát ngoài SIFT.
- Stock OFF binary R86 và H17/Fast ELF R90 đến từ **hai nhánh source/build vintage khác nhau**; đây là hạn chế phương pháp cần nêu trong bài. ELF SHA và cùng máy/dữ liệu/cờ giúp tăng độ tin cậy nhưng không tự động loại trừ mọi khác biệt toolchain.

## 2. Nguồn đã khóa

| Thành phần | Đường dẫn tương đối dưới `~/ann-task-a` | SHA256 |
| --- | --- | --- |
| Base MS-Turing 1M, d=100 | `data/MSTuring_1M_v1/base.1M.fbin` | `44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042` |
| Query công khai 100K, d=100 | `data/MSTuring_1M_v1/query.public.100K.fbin` | `48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644` |
| GT 100K ×100 | `data/MSTuring_1M_v1/groundtruth.public.100K.ibin` | `fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344` |
| Stock OFF R86 | `experiments/R86/gates/highway_r85_four_binary_jvYREW/build_stock_off/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be` |
| H17 CTRL R90 | `experiments/R90/r90_p38_h17_top2_prefilter_native_v2/build/ctrl/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `92c22ad5d9d9022860725329ff097784e7c8a649460d03dd343cdb6adb90363e` |
| H17 + Fast v2 R90 | `experiments/R90/r90_p38_h17_top2_prefilter_native_v2/build/fast/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `ab4a0c678b3a71b2896d6f4d4339131705a1758b0c5398ed8ac32dd656cd7e91` |
| H17 `pipnn_utils.h` | `experiments/H17/phase3_top2_e2e/PiPNN-top2/algorithms/PipNN/pipnn_utils.h` | `b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520` |

R86 data sources and stock ELF are confirmed from previous `R86_MSTURING1M_FORMAL_OFF_3X5_V1` campaign manifest and handoff artifact list (connected GitHub); Ubuntu preflight rechecks the actual files and hashes.

**Cấu hình BUILD:** `-num_clusters 2 -cluster_size 1024 -table_size 160 -top_level_leaders 100 -fanout_scheme 10,3,1 -mst_deg 2 -prune 1 -prune_all 1 -prune_degree 64 -hash_bits 12 -alpha 1.1 -k 0`; `taskset -c 0,2,4,6`, `PARLAY_NUM_THREADS=4`, `OMP_NUM_THREADS=4`. Preflight xác minh bốn lõi vật lý riêng biệt.

## 3. Thiết kế BUILD, báo cáo và cổng kiểm toán

Ba vòng chạy, mỗi vòng ba arms, đảo thứ tự dạng Latin square:

- Vòng 1: Stock → H17 → Fast.
- Vòng 2: Fast → Stock → H17.
- Vòng 3: H17 → Fast → Stock.

Tổng 9 BUILD MS-Turing1M. **Không có điều kiện bắt buộc graph SHA giống nhau** giữa ba arms vì H17 song song vốn có biến động graph. Mỗi graph được lưu riêng SHA, số cung, Peak RSS, wall, CPU%, native stdout và `/usr/bin/time -v`. Cổng audit kiểm tra source ELF/inputs, đủ 9 cặp arm-rep, mọi graph header và số cung; so sánh adjacency multisets Stock↔H17, H17↔Fast, Stock↔Fast cho từng rep; báo cáo speedup Stock→H17, H17→Fast và Stock→Fast theo *paired rep* cũng như tỷ số trung bình thời gian. Cổng audit phải **PASS kể cả khi Fast không nhanh hơn**, vì đây là kiểm tra khoa học, không phải bộ lọc thiên vị.

**Tài nguyên:** Dữ liệu base 400 MB, 9 graph khoảng 2 GB (phụ thuộc cung), RAM available yêu cầu ít nhất 5 GiB, disk free ít nhất 4 GiB. Nếu thiếu, STOP tại preflight; không xóa log/campaign cũ.

## 4. Lệnh Ubuntu an toàn

Sau khi tải `r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1.py` vào `~/Downloads`:

```bash
F="$HOME/Downloads/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1.py"
EXPECTED="c28ffbb20f729ce4d88f06da3c2be54d8d8b87c0e8ebef379528c93d22b30e43"
OUT="$HOME/ann-task-a/experiments/R90/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1"
LOG="$HOME/R90_P4_MSTURING1M_3ARM_4CPU.log"

if [ ! -f "$F" ] || [ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]; then
  echo "R90_P4_SCRIPT_SHA_HOLD"
elif [ -e "$OUT" ] || [ -L "$OUT" ] || [ -e "$LOG" ] || [ -L "$LOG" ]; then
  echo "R90_P4_OUTPUT_EXISTS_HOLD"
else
  ( set -euo pipefail
    python3 "$F" selftest
    python3 "$F" preflight
    python3 "$F" pilot
    python3 "$F" audit
    echo "R90_P4_SEQUENCE_COMPLETE"
  ) 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
  echo "R90_P4_EXIT_CODE=$RC"
fi

echo TERMINAL_SAFE_END
```

Nếu RUN nhận HOLD sau khi đã BUILD dở, **không xóa thư mục đầu ra để chạy lại**. Gửi log cùng `OUT/build_manifest.json` và `OUT/build_summary.json` để xử lý fail-closed / chẩn đoán riêng.

## 5. Tiếp theo: Search chuẩn MS-Turing

**Dừng sau P4 BUILD và kiểm toán các manifest trước khi làm Search.** Query MS-Turing gồm **100.000 query, dimension 100**, không phải 10.000 query / d128 như SIFT. Cần evaluator native riêng của R86 MS-Turing, khóa SHA, đo Recall@10/QPS trên cùng GT, beam sweep đủ rộng, đặc biệt tại Recall≥0,99 và ≥0,998. Các đồ thị MS-Turing R86 từng cần beam lớn (ví dụ 384/896 ở A0/A1), vì vậy evaluator H85 cũ giới hạn beam ≤512 **không thích hợp** cho mốc 0,998 trên dataset này. Sẽ thiết kế phase Search riêng sau khi nhận graph/manifest P4, không suy diễn graph bằng nhau hoặc Recall không đổi từ kết quả SIFT.

## 6. Scope giới hạn

- Causal claim phải giới hạn: so trên cùng CPU/flags/data với frozen ELF khác vintage; chưa loại hoàn toàn khác biệt compiler flags/counters.
- `Wall` của P4 là benchmark BUILD không instrumentation; khác D6 diagnostic.
- So chất lượng Search ở matched Recall mới cho phép kết luận toàn diện, P4 chỉ xác nhận BUILD.
- Chưa push GitHub `main`; đề xuất Gemini không phải lệnh của người dùng.
- Bất kỳ dự đoán tốc độ so Stock/ H17/Fast hay MS-Turing phải gắn nhãn dự đoán cho đến khi có log native.
