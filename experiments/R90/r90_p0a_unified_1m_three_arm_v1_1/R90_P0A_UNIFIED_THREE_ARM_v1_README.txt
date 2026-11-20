R90 P0-A — Unified Stock/H17/Fast v1 (EXPERIMENTAL, GATED)
Ngày: 2026-11-19

MỤC TIÊU
* So sánh Stock, H17, Fast từ cùng R86 v1_2 source snapshot.
* OFF: 4 CPU, 3 lần BUILD / phương pháp / dataset, dùng để đo BUILD, RSS, graph SHA.
* ON: 1 CPU, 1 BUILD / phương pháp / dataset; R86 counters toàn cục ở Stock,
  D6 Top-2 source counters cho H17/Fast, cộng R86 counters toàn cục.
* Dataset: SIFT1M & MS-Turing1M, C160/K1024/N2.
* ON time là diagnostic; không sử dụng làm BUILD benchmark. Graph OFF mới vẫn cần
  Search Recall/QPS độc lập, KHÔNG mặc nhiên kế thừa matched Recall từ P4.

SỰ THẬT VỀ TRẠNG THÁI
- Syntax và selftest giả lập của script PASS trong môi trường ChatGPT.
- Chưa biên dịch/kiểm graph SHA trên Ubuntu. Native STATUS = PENDING.
- Source cùng snapshot, compiler SHA được kiểm riêng khi bước compile chạy.
- Có thể HOLD trong preflight do source/dependency drift. Giữ file và gửi log, KHÔNG sửa
  source gốc, binary gốc hay manifest lịch sử để vượt HOLD.

LỆNH AN TOÀN BẮT ĐẦU (KHÔNG BUILD / COMPILE)
  bash "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_Ubuntu_PREPARE_ONLY.sh"

CHỈ SAU KHI GỬI source_manifest.json VÀ LOG PREPARE THÀNH CÔNG, xác nhận tiếp:
  python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1.py" compile
  python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1.py" pilot10k
  python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1.py" auditpilot

Chỉ sau 6 graph pilot10k cùng SHA và source/ELF audit đầy đủ:
  python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1.py" full1m
  python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1.py" audit1m

LƯU Ý KỸ THUẬT
- Fast OFF chỉ thêm FP32 second cutoff trong nhánh H17 MST_DEG=2.
- H17 ON và Fast ON dùng D6 exact instrumentation source snapshot từ R90-D6,
  được chuyển vào cùng baseline R86. 1CPU graph parity pilot10k được yêu cầu.
- Counter Highway VQPartialSort chỉ đếm call và Q-writes theo R86_COUNTERS;
  KHÔNG đếm scalar swaps/SIMD shuffle bên trong thư viện.
- ON graph output trong R90_P0A mới, không thể thay graph native P4 cũ.
- Full 1M chưa được chứng nhận native; không chạy nếu pilot HOLD.
