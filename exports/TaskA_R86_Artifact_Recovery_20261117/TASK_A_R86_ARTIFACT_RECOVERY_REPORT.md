# Báo Cáo Kiểm Kê & Thu Hồi Artifacts Lịch Sử R86 — Task A

- **Thời điểm thực hiện (UTC):** `2026-11-17T14:06:00Z` (`2026-11-17T21:06:00+07:00`)
- **Workspace lịch sử được kiểm tra:** `/home/tai/ann-task-a` (tài khoản `tai`, `uid=1000`, `gid=1000`, host `tai-linux`)
- **Thư mục evidence mới (không ghi đè dữ liệu gốc):** `/home/tai/ann-task-a/exports/TaskA_R86_Artifact_Recovery_20261117`
- **Tổng số mục trong inventory:** `338` tệp (`338 VERIFIED`, `0 HASH_MISMATCH`), `8` hạng mục thiếu/chưa ghi nhận trong `TASK_A_R86_MISSING_AND_UNVERIFIED.csv`, `428` dòng checksum trong `TASK_A_R86_CHECKSUMS.sha256`.

---

## 1. Tóm Tắt Điều Hành

**Cả 4/4 executable lịch sử bắt buộc ĐỀU VẪN CÒN NGUYÊN VẸN TRÊN ĐĨA và KHỚP SHA-256 TUYỆT ĐỐI (`4/4 VERIFIED`).** Không có executable lịch sử nào bị xóa; chúng chỉ chưa được đưa vào gói bàn giao trước đó (`exports/TaskD_R86_MST1M_Handoff_v1` chỉ đóng gói 3 datasets, 9 file `index.graph`, `formal_9graphs_raw_receipts.tar.gz` gồm 261 raw receipt của `A0/A1/A3`, và `git status` của checkout hiện tại).

Ngoài 4 executable bắt buộc, cuộc kiểm kê còn thu hồi bản sao nguyên byte (giữ nguyên timestamp và permissions, tuyệt đối **không chạy thực thi bất kỳ ELF nào**) kèm toàn bộ CMake/compiler/linker metadata, source/patch provenance, và kiểm chứng lại 3 datasets + 18/18 graph (trong đó có 9 graph ưu tiên `A0, A1, A3 × R1..R3`) + 180/180 Search runs của chiến dịch `R86_MSTURING1M_FORMAL_OFF_3X5_V1`.

Các phần thực sự **không tồn tại hoặc chưa từng được ghi nhận trong R86** là:
1. `MS_TURING_1M_REPRO_MANIFEST.json` (`MISSING` — chưa từng được tạo).
2. `seed` runtime/CLI trong receipts R86 (`NOT_RECORDED`; tuy nhiên source cứng `SEED = 555` + `parlay::hash64` đã xác minh trong `pipnn.h`).
3. Receipt cấu hình host chụp *đồng thời trong phiên R86* ngày 13–15/11/2026 cho `lscpu`/CPU model, NUMA/SMT topology, `scaling_governor`, thermal throttling, `MemTotal`, `/etc/os-release` (`NOT_RECORDED` / `HISTORICAL_UNRECOVERABLE` ở mức receipt cùng thời điểm R86; chỉ có thông số CMake kernel `Linux-7.0.0-42-generic` `x86_64`, GCC `13.3.0`, CMake `3.28.3`, `taskset`, `PARLAY_NUM_THREADS`, check `MemAvailable >= 7 GiB`, cộng thêm telemetry bối cảnh H85 ngày 11/11 trên cùng máy `tai-linux` nhưng **không được phép đồng nhất thành R86 host receipt**).
4. `.git` riêng bên trong `r86_v1_2_source` (`NOT_A_GIT_WORKTREE`, nhưng đã truy nguyên đầy đủ về commit `H70` + 2 patch SHA-pinned).
5. File `.d` compiler depfile của `eval v3` và `v4` (`NOT_VERIFIED` qua depfile do gọi `/usr/bin/c++` trực tiếp không kèm `-MD/-MF`).

---

## 2. Phạm Vi Tìm Kiếm & Quyền Truy Cập

| Phạm vi đã kiểm tra | Kết quả truy cập | Ghi chú |
|---|---|---|
| `/home/tai/ann-task-a` (bao gồm `experiments/R86`, `H70`, `H85`, `data`, `exports`) | Đọc đầy đủ (`104.039` thư mục được duyệt tổng hợp) | Phát hiện đầy đủ 4 executable, build dirs, source, datasets, 18 formal graphs, 6 pilot graphs. Chỉ **2 tệp không liên quan R86** bị `NO_READ_PERM`: `/home/tai/ann-task-a/results/perf_sift1m_8t.data` và `perf_sift1m_4t.data` (root-owned `perf` captures). |
| `/home/tai/Downloads`, `/home/tai/Documents`, `/home/tai/Desktop`, `/home/tai/.local/share/Trash`, `/home/tai/R86*`, `/home/tai/r86*` | Đọc đầy đủ (`0` lỗi quyền) | Đã đối chiếu script gốc trong `Downloads` (`R86_Highway_R85_Four_Binaries_v1_0.sh`, `r86_mst1m_fasttrack_formal_v1.py`, `r86_msturing1m_sixarm_pilot_v1.py`, `r86_msturing1m_eval_native_link_gate_v3.py`, `r86_msturing1m_highbeam_eval_search_gate_v4.py`, `TaskD_R86_MST1M_OFF_FORMAL_HandoffKit_v1.zip`). Thùng rác trống (`0` tệp). |
| `/mnt`, `/media` (`/mnt/wincheck`, `/mnt/windows`, `/media/tai`) | Đọc đầy đủ (`0` lỗi quyền) | Trống (`0` tệp). Hệ thống chạy trên `/dev/nvme0n1p5` ext4 (`393G`, trống `68G`). |
| Các file archive (`.zip`, `.tar`, `.tar.gz`) | Kiểm tra nội dung không cần giải nén | Đã kiểm tra 15 archive trong `/home/tai`, `Downloads`, `exports` (kể cả `TaskD_R86_MST1M_Data_9Graphs.tar`, `TaskD_R86_MST1M_Handoff_v1.tar.gz`, `R86_day2_source_review.tar.gz`, `R86_G1_R85_Protocol_Evidence.tar.gz`). Không archive nào chứa bản sao của 4 executable bị thiếu; tất cả đều nằm nguyên vẹn dạng unpacked trong workspace. |

---

## 3. Kiểm Chứng 4 Executable Lịch Sử Bắt Buộc (+ Companions)

Tất cả được kiểm tra bằng `hashlib` SHA-256 trên bytes thực tế, `os.stat`, `file -b`, và `LC_ALL=C readelf -h/-n/-d/-p .comment` (tĩnh, **không thực thi**).

### 3.1. Bốn executable bắt buộc

| Mã | Tên & Vai trò | Đường dẫn gốc trên máy | Bản sao thu hồi (trong thư mục này) | Size (bytes) | Mtime (UTC) | SHA-256 thực tế (= Mong đợi) | ELF BuildID (`sha1`) & Toolchain |
|---|---|---|---|---:|---|---|---|
| **A** | Builder Stock OFF (`A0`) — `neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `/home/tai/ann-task-a/experiments/R86/gates/highway_r85_four_binary_jvYREW/build_stock_off/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `recovered_artifacts/executables/A_builder_stock_off/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `2836408` | `2026-11-13T07:29:04.349406+00:00` | `aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be` (`VERIFIED`) | `7abbf2c2d610aff0e43b636fc87fd697de067db9`; GCC `(Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0` |
| **A-dup** | Builder Stock OFF (bản control trùng byte) — `neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `/home/tai/ann-task-a/experiments/R86/gates/highway_r85_stock_control_MVzZH3/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `recovered_artifacts/executables/A_builder_stock_off_MVzZH3_duplicate/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `2836408` | `2026-11-13T05:50:58.599056+00:00` | `aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be` (`VERIFIED`) | `7abbf2c2d610aff0e43b636fc87fd697de067db9` (tái lập byte-identical giữa `MVzZH3` và `jvYREW`) |
| **B** | Builder H17 OFF (`A1..A4`) — `neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `/home/tai/ann-task-a/experiments/R86/gates/highway_r85_four_binary_jvYREW/build_h17_off/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `recovered_artifacts/executables/B_builder_h17_off/neighbors-pipnn_FLOAT_T_EUCLIDEAN` | `2840040` | `2026-11-13T07:32:24.021943+00:00` | `5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297` (`VERIFIED`) | `930b31acc375459f7a02723312e1b7620ae45ba9`; GCC `13.3.0`; thêm cờ `-DR71_H17_TOP2=1` |
| **C** | Search evaluator v3 (`beam <= 512`) — `r86_msturing1m_graph_recall_v3` | `/home/tai/ann-task-a/experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v3` | `recovered_artifacts/executables/C_search_eval_v3/r86_msturing1m_graph_recall_v3` | `553840` | `2026-11-13T18:33:47.692034+00:00` | `ea6c757b47b1267b7009ff0a1a80a3fdeaaf59740c4c2036712accf9ba0d0af5` (`VERIFIED`) | `bbac7c10ab38f7063081c6c06c02c5df86680b87`; GCC `13.3.0` |
| **D** | Search evaluator v4 highbeam (`beam <= 4096`) — `r86_msturing1m_graph_recall_v4_highbeam` | `/home/tai/ann-task-a/experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam` | `recovered_artifacts/executables/D_search_eval_v4_highbeam/r86_msturing1m_graph_recall_v4_highbeam` | `553856` | `2026-11-14T05:42:39.696050+00:00` | `bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144` (`VERIFIED`) | `3edea046a21c076d27cc233f0dfeda125d7b06fa`; GCC `13.3.0` |

### 3.2. Companion executables liên quan trực tiếp (đều `VERIFIED`)

- **Builder D0 Two-Tier (`D0` arm trong cùng formal campaign):** `experiments/R86/msturing_1m_sixarm/build_d0_h17_tier_off_v2/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN` (`2851192` B, SHA `7c2aad71a97f9c2b2e6de6026085be43954a7dd0845feffb672f6782c84575ab`, BuildID `1fed297b0a8141f74aa962e78d45ce974e2fd148`, đã thu hồi bản sao).
- **Builders ON anh em trong `jvYREW`:** `build_stock_on` (`396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff`, `2549944` B) và `build_h17_on` (`ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4`, `2554272` B), đã thu hồi bản sao.
- **G11 Counter64 Search evaluator:** `experiments/R86/g11_counter64_diagnostic_v2_0/msturing_1m_eval/r86_msturing1m_graph_recall_v4_diag_counter64` (`545176` B, SHA `a98b8748b92787e6ccbf52556a8eef2c24bff4580c6275c9fa464dd82af4d3a4`, BuildID `39627f90c201820c66e94b5ec0e595b81564d47b`, đã thu hồi bản sao).
- **Pre-HW85 R86 G0 builders (tham chiếu nguồn `_deps` cho `v3/v4`):** `experiments/R86/r86_v1_2_builds/stock_off/...` (`ba8e621f...`) và `h17_off/...` (`dd3829b1...`).

---

## 4. Thu Hồi Compile / Link Metadata & Source-to-Binary Provenance

### 4.1. Builders (`A: jvYREW/build_stock_off` và `B: jvYREW/build_h17_off`)

- **Metadata thu hồi đầy đủ 100%:** `CMakeCache.txt`, `flags.make`, `link.txt`, `build.make`, `DependInfo.cmake`, `cmake_pch.hxx`, **`cmake_pch.hxx.gch.d`** (820 header paths thực sự do compiler xuất ra), `compile_commands.json`, `CMakeFiles/3.28.3/{CMakeSystem.cmake,CMakeCXXCompiler.cmake}`, `{stock_off,h17_off}.{configure,compile}.log`, `four_binary_manifest.json`, `provenance.txt`, `source_sha256.txt`, `script_sha256.txt`.
- **Toolchain & CMake flags thực tế:**
  - Compiler: `/usr/bin/c++` — GNU `13.3.0` (`Ubuntu 13.3.0-6ubuntu2~24.04.1`), CMake `3.28.3`, Unix Makefiles.
  - `CMAKE_BUILD_TYPE=Release`, `CMAKE_CXX_FLAGS=""`, `CMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG"`, root `CMakeLists.txt` cộng thêm `-march=native -ffast-math`.
  - `CXX_FLAGS = -march=native -ffast-math -O3 -DNDEBUG -std=gnu++17 -fPIE`.
  - `CXX_DEFINES`: `-DHWY_STATIC_DEFINE -DPARLAY_ELASTIC_PARALLELISM=true -DTOOLCHAIN_MISS_ASM_HWCAP_H -DUSE_DATATYPE_FLOAT_T -DUSE_DISTANCE_EUCLIDEAN`; riêng **`build_h17_off`** thêm **`-DR71_H17_TOP2=1`** (`R71_USE_H17=ON`, `R70_USE_TIER=OFF`, `R86_USE_COUNTERS=OFF`).
  - Liên kết tĩnh (`link.txt`): `-fPIE -pie`, `libabsl_*.a` (synchronization, raw_hash_set, cord, hash, strings, ...), `libhwy.a`, `libhwy_contrib.a`, `-lrt`. Thư viện động `NEEDED`: chỉ `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6`, `ld-linux-x86-64.so.2`.
- **Dependency revisions (`FETCHCONTENT_FULLY_DISCONNECTED=ON`):**
  - `highway` = **`6bc2d47793bae9c521fb4150936669647700765d`** (pin từ `experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src`, clean git status `[]`).
  - `parlaylib` = `51017699dcc421f80479cdb238d3092233ad0d26` (clean, từ `r86_v1_2_builds/stock_off/_deps/parlaylib-src`).
  - `eigen` = `3147391d946bb4b6c68edd901f2add6ac1f31f8c` (clean, từ `r86_v1_2_builds/stock_off/_deps/eigen-src`).
  - `abseil-cpp` = `bc257a88f7c1939f24e0379f14a3589e926c950c` (clean, từ `r86_v1_2_builds/stock_off/_deps/abseil-cpp-src`).
- **Chuỗi nguồn `Source -> Binary` của Builder (khép kín toàn bộ qua SHA & compiler depfile):**
  1. Git baseline `experiments/H70/pipnn-clean-443a328` tại commit **`443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`** (`dirty` trên 4 file: `CMakeLists.txt`, `algorithms/PipNN/CMakeLists.txt`, `pipnn.h`, `pipnn_utils.h`). Bản vá `experiments/R86/source_review/H70_git_diff.patch` (SHA `d6bcbe9aaae95c0916fa58599355cc93040a19ff41b89bb6109a7b3be5739121`) khớp 100% với `git diff HEAD` hiện tại của `H70`.
  2. Áp dụng patch `R86_counter_source_v1_2.patch` (SHA `70c9088092f58c16be6835cddad6710003216723164bd74fff81510c909e0a8c`, khớp `R86_STAGING_PROVENANCE.json` và `g0_manifest.json`) lên bản sạch sao chép để tạo **`experiments/R86/r86_v1_2_source`** (`NOT_A_GIT_WORKTREE`).
  3. 4 file nguồn cốt lõi được khóa SHA-256 trong `jvYREW/source_sha256.txt` (`CMakeLists.txt` `198badc6...`, `algorithms/PipNN/CMakeLists.txt` `19d5eb89...`, `pipnn.h` `77a9b97e...`, `pipnn_utils.h` `33b09c3c...`).
  4. `cmake_pch.hxx.gch.d` trong cả `build_stock_off` và `build_h17_off` chứng minh trình biên dịch đã đọc đúng `14` header từ `r86_v1_2_source` (gồm `neighbors.h`, `pipnn.h`, `pipnn_utils.h`, `graph.h`, `hash.h`, ...) cùng đúng `H85/_deps/highway-src` và `r86_v1_2_builds/stock_off/_deps/{parlaylib,eigen,abseil-cpp}-src`.
  5. `native.build.log` của các run formal in rõ banner nguồn: `A0` ghi `R70_RESERVOIR_VARIANT=STOCK_FLAT_C160` + `R71_SELECTION_VARIANT=STOCK_HIGHWAY`; `A1/A3` ghi `R71_SELECTION_VARIANT=H17_PACKED_TOP2`.
  6. Hai lần compile độc lập (`MVzZH3` lúc `05:50 UTC` và `jvYREW` lúc `07:29 UTC`) cho ra tệp Stock OFF ELF **giống nhau từng byte** (`aa2d174e...`).

### 4.2. Search Evaluators (`C: eval v3` và `D: eval v4 highbeam`)

- **Provenance có sẵn trong `experiments/R86/msturing_1m_eval/`:**
  - Nguồn `.cc` gốc của R85 `r85_a1c_graph_recall.cc` (SHA `a2b4f27e...`) -> sửa đúng 3 input-dimension guard (`128->100`, `10000->100000`, `128->100`) thành `r86_msturing1m_graph_recall.cc` (SHA `91078479eb7fdb05a6070526797c4feaf01d6e994c13f699108e497ea0609b7e`) -> sửa đúng 1 guard (`beam > 512` thành `beam > 4096`) thành `r86_msturing1m_graph_recall_v4_highbeam.cc` (SHA `6aa0e38a3b0a536ccbcd3bfe0ca690257ab963215b5135d642cbb60d259c3f89`).
  - `r86_msturing1m_eval_native_link_v3.json` và `r86_msturing1m_highbeam_v4_manifest.json` lưu nguyên vẹn `compile_command` đầy đủ gồm flags `-DHWY_STATIC_DEFINE -DPARLAY_ELASTIC_PARALLELISM=true -DTOOLCHAIN_MISS_ASM_HWCAP_H -DUSE_DATATYPE_FLOAT_T -DUSE_DISTANCE_EUCLIDEAN -march=native -ffast-math -O3 -DNDEBUG -std=gnu++17 -fPIE -pthread -fopenmp`, danh sách tĩnh các `.a` theo đúng thứ tự liên kết (`native_flags_sha256=9b034e3f...`, `native_link_sha256=ba77aec8...` khớp `r86_v1_2_builds/stock_off`), và log compile `0` byte (clean compile, SHA `e3b0c442...`).
- **Điểm kỹ thuật quan trọng cần ghi nhận cho Task D:**
  1. Hai file `.cc` `#include` đường dẫn tuyệt đối vào worktree `H70` (`.../H70/pipnn-clean-443a328/algorithms/utils/{euclidian_point.h,point_range.h,check_nn_recall.h}`), và `check_nn_recall.h` dùng include tương đối `"beamSearch.h"`, `"graph.h"`, `"stats.h"`, `"parse_results.h"`, `"types.h"`, `"csvfile.h"`. Ta đã kiểm chứng cả **11/11 file utils đó trong worktree `H70` hiện vẫn sạch nguyên vẹn 100% so với commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`**.
  2. Tuy nhiên lệnh `/usr/bin/c++` compile `v3`/`v4` trỏ `-I` và các `.a` tĩnh tới **`r86_v1_2_builds/stock_off/_deps/`** (tức dùng `highway` bản **`0e0a01dac5321dafec478d781487d1323492359e`**, còn builder dùng bản H85 `6bc2d477...` — dù Search path ở `beamSearch.h` không phụ thuộc H17/Highway top-k), và không xuất compiler `.d` depfile (`NOT_VERIFIED` ở mức `.d` depfile).

### 4.3. Randomness & Historical Host Receipts

- **Randomness:**
  - Trong receipts runtime của R86 & formal campaign (`E_PROTOCOL`, `build_command.json`, `build_result.json`, `native.build.log`): **`NOT_RECORDED`** (không có tham số `-seed` CLI hoặc bản ghi seed runtime).
  - Trong source code (`pipnn.h`): `cluster_utils` gán cứng **`size_t SEED = 555;`** (`pipnn.h:498`), truyền vào `LevelByLevelSketch`/`RecursivelySketch` (`pipnn.h:421,425`) và cập nhật sau mỗi pass bằng `SEED = parlay::hash64(SEED);` (`pipnn.h:429`), kết hợp `std::mt19937 prng(...)` (`pipnn.h:70,181`). Đoạn `std::random_device rd; std::mt19937 rng(rd()); ... parlay::random rnd(uni(rng));` ở `pipnn.h:373-376` tạo biến cục bộ `rnd` **không được sử dụng** (đã xác nhận thêm trong `SOURCE_AUDIT` dòng 20 & 75). Tuy nhiên các thao tác song song (4 luồng `PARLAY_NUM_THREADS=4`) khi ghi leaf/hash reservoir vẫn tạo biến thiên SHA giữa các graph (`r1/r2/r3` có SHA khác nhau), trong khi `Total buckets` & `# of comparisons during clustering` giữa `A0/r1` và `A1/r1` khớp nhau (`89813`/`88807`, `5104928517`/`10204781605`).
  - Trong Search (`v3`/`v4`): gọi `checkRecall(..., /*random=*/false, /*start_point=*/0u, /*k=*/10L, qp, /*verbose=*/false)` (`start_point=0`, không chọn ngẫu nhiên điểm xuất phát).
- **Historical Host Receipts (tách bạch nghiêm ngặt R86 vs H85):**
  - **Những gì có chứng cứ trực tiếp trong R86 (13–15/11):**
    - `CMakeSystem.cmake` trong cả `jvYREW`, `MVzZH3`, `D0_v2`, `G0`: `Linux-7.0.0-42-generic`, `x86_64`, non-crosscompiling. *(Lưu ý: thư mục nguồn kế thừa `external/mirage/{build,cmake-build-debug}` có chứa tệp CMake Darwin arm64 cũ từ upstream gốc — không phải máy chạy R86).*
    - `CMakeCXXCompiler.cmake` & ELF `.comment`: `GCC: (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`, `/usr/bin/ld`, GNU binutils, CMake `3.28.3`.
    - Runtime pinning: `taskset -c 0,2,4,6` + `PARLAY_NUM_THREADS=4` cho BUILD; `taskset -c 0` + `PARLAY_NUM_THREADS=1` cho Search; preflight script `r86_mst1m_fasttrack_formal_v1.py` kiểm tra `os.sched_getaffinity` chứa `{0,2,4,6}`, trống đĩa `>= 8 GiB`, `MemAvailable >= 7 GiB`.
  - **Những gì KHÔNG được ghi nhận trong R86 (`NOT_RECORDED` / `HISTORICAL_UNRECOVERABLE` ở mức R86 runtime):**
    - Không có bất kỳ file `lscpu`, CPU model name, số core/thread/SMT, NUMA topology, `MemTotal`, `/etc/os-release`, `scaling_governor`, hay thermal/frequency throttling guard nào được ghi nhận bên trong `experiments/R86/` hoặc các log `~/R86*` / `~/r86*` (chỉ có chuỗi khớp giả trong file Python `.venv` hoặc `external/mirage`).
    - *Bối cảnh tham chiếu từ chiến dịch H85 trước đó (11/11/2026) trên cùng host `tai-linux` (CHỈ mang tính bối cảnh H85, không thay thế R86 historical receipt):* `experiments/H85/r85_a4c_telemetry/session_20261111-212536_303354/preflight.json` ghi `cpus=[0,2,4,6]`, `core_id` `0,4,8,12` với `siblings` `0-1`, `2-3`, `4-5`, `6-7`, `allowed_affinity` `0..19`, `intel_pstate` + `scaling_governor=powersave`, sensor `hwmon/thermal_zone`; và `~/r85_scale_source_preflight.log` ghi `MemTotal: 32609400 kB`.

---

## 5. Đối Chiếu Với Campaign `R86_MSTURING1M_FORMAL_OFF_3X5_V1` & Google Sheet

### 5.1. Datasets & 9 Graph Ưu Tiên (`A0, A1, A3 × R1..R3`) — Tất Cả `100% VERIFIED`

- **Datasets (`data/MSTuring_1M_v1/`):**
  - `base.1M.fbin`: `400,000,008` B, shape `[1000000, 100]` float32, SHA `44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042` (`VERIFIED`).
  - `query.public.100K.fbin`: `40,000,008` B, shape `[100000, 100]` float32, SHA `48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644` (`VERIFIED`).
  - `groundtruth.public.100K.ibin`: `80,000,008` B, shape `[100000, 100]` (split int32 ID + float32 sqL2), SHA `fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344` (`VERIFIED`).
- **9 Graph ưu tiên (`A0, A1, A3 × R1..R3`) & 90 lần Search liên quan (`270` receipt + graph files kiểm tra trên đĩa):**
  - Toàn bộ `9/9` file `index.graph` khớp SHA-256 trên đĩa, khớp `build_result.json`, `expected_artifacts.csv`, `sha256sums.txt`, `TaskD_R86_MST1M_Data_9Graphs.tar`, `R86_MST1M_FORMAL_3X5`, `E_PROTOCOL`, và `RUN_INDEX`:
    - `A0/r1`: `55df31ac9b7716f779dca332ce9360c9e21a065f9298ec1c92c8ccdd37d72522` (`215,424,180` B), builder `aa2d174e...`, beams `384`/`896`, QPS med `1225.993` / `562.069`
    - `A0/r2`: `e0e0be004e6b3bd9cf55c4f620863e2d002aa5798a9e258f5330ee2f1d1ee6b9` (`215,468,020` B), QPS med `1225.238` / `561.661`
    - `A0/r3`: `a4ad500421b95700f34d1d2e267640decffbf3f54a88fdb2b3708cf33448405b` (`215,384,040` B), QPS med `1225.922` / `562.223`
    - `A1/r1`: `7da34f1c3e0ff8a67092a2c9f96bc35122b88fdbe36c59347d1f213b55c46979` (`215,506,900` B), builder `5f673586...`, beams `384`/`896`, QPS med `1226.329` / `561.574`
    - `A1/r2`: `b08ef703f162b75f6c2512d29d58113212c185030dc5b230a7488c8244c82ede` (`215,403,280` B), QPS med `1225.504` / `562.407`
    - `A1/r3`: `1b51bf7115450c208bc209d9419fd42425c8393e75f712ec1fabdd7fb69787b1` (`215,420,692` B), QPS med `1226.076` / `562.358`
    - `A3/r1`: `0fff20ec47502c675c4905787d319390e49fa5bee856ac16c814c74697c5fbb2` (`157,419,636` B), builder `5f673586...`, beams `832`/`2176`, QPS med `842.017` / `342.719`
    - `A3/r2`: `3d6113e721fa26c8a82f77d2e5bcbc60b6e55352532814694afb146c9c5f9c6c` (`157,417,780` B), QPS med `842.924` / `343.245`
    - `A3/r3`: `11f7a5059af309db0a08c4a9e0484d194c8ea5c6f17d8c8f9f67ceb299d85829` (`157,418,376` B), QPS med `841.588` / `342.350`
  - Ngoài ra `9` graph còn lại (`A2, A4, D0 × R1..R3`) cũng có mặt đủ `18/18` và `180/180` Search runs; median-of-medians tính lại từ raw JSON khớp đến 6 chữ số thập phân với `R86_MST1M_FORMAL_QPS` (`A0`: `1225.921997`/`562.069092`; `A1`: `1226.075684`/`562.358276`; `A2`: `881.385986`/`387.972748`; `A3`: `842.016785`/`342.718994`; `A4`: `776.718750`/`363.470734`; `D0`: `1224.828979`/`561.985779`).
  - Lưu ý nhận diện đã biết từ `README_FIRST.txt`: `avg_cmps` trong raw log `measure_t0998` của `v4` bị tràn 32-bit unsigned (ví dụ `4294955360`), nên không dùng `avg_cmps` từ `v4` cho phân tích distance work; hãy dùng riêng số liệu `G11_counter64` cho distance work.

### 5.2. Vì sao `TaskD_R86_MST1M_Handoff_v1` bị thiếu?

Kiểm tra script tạo gói `TaskD_R86_MST1M_OFF_FORMAL_HandoffKit_v1.zip` (`taskd_r86_handoff_audit_v1.py`) cho thấy nó chỉ xuất danh sách rsync gồm 3 datasets + 9 graph ưu tiên (`TaskD_R86_MST1M_Data_9Graphs.tar`), đóng gói 261 raw receipts bên trong `formal_mst1m_v1/{A0,A1,A3}/r1..r3`, và ghi `git status` checkout hiện tại (`provenance_current_checkout.json`). Nó **chưa bao giờ thu thập** `jvYREW`, `msturing_1m_eval`, `campaign_manifest.json`, `r86_v1_2_source`, hay `source_review/`, dẫn đến `README_HANDOFF.txt` ghi rõ *"the binary files have NOT been exported"*. Toàn bộ các tệp này hiện đã được thu hồi đầy đủ tại đây.

---

## 6. Trả Lời Trực Tiếp 7 Câu Hỏi (Mục 8) & Đề Xuất Gate Decision

1. **Đã tìm thấy bao nhiêu trong bốn executable lịch sử?**
   - Tìm thấy **4 / 4** (`100%`) ngay trong workspace `/home/tai/ann-task-a/experiments/R86/` (cộng thêm bản sao trùng của Stock OFF ở `MVzZH3`, cùng với companion `D0`, `stock_on`, `h17_on`, `G11_counter64`).
2. **Có bao nhiêu executable khớp SHA-256 tuyệt đối?**
   - **4 / 4** (`100%`) executable bắt buộc (tính cả bản trùng `MVzZH3` là **5 / 5** tệp ELF) khớp SHA-256 tuyệt đối cả trên file gốc lẫn bản sao thu hồi nguyên byte trong `recovered_artifacts/executables/`.
3. **Source-to-binary provenance đã đầy đủ đến mức nào?**
   - **Builders (`A`, `B`, `D0`):** Rất đầy đủ (~95%): chuỗi nguồn `H70 (443a328)` -> `H70_git_diff.patch (d6bcbe9a...)` -> `R86_counter_source_v1_2.patch (70c90880...)` -> `r86_v1_2_source` (khóa SHA 4 file cốt lõi) -> `cmake_pch.hxx.gch.d` (xác nhận trực tiếp `14` header của `r86_v1_2_source`, Highway `6bc2d477`, Parlay `51017699`, Eigen `3147391d`, Abseil `bc257a88`) -> cờ `-DR71_H17_TOP2=1` / OFF -> ELF + runtime banner. Thiếu duy nhất `.git` riêng bên trong `r86_v1_2_source`.
   - **Search Evaluators (`C v3`, `D v4`):** Khá đầy đủ (~85%): có `.cc` gốc (`a2b4f27e...`) -> `v3` (`91078479...`) -> `v4` (`6aa0e38a...`), đầy đủ `compile_command` nguyên văn, danh sách static `.a` libs và 0-byte clean compile logs trong JSON manifests; 11/11 header `H70/algorithms/utils/*.h` mà `v3`/`v4` `#include` đã kiểm chứng trùng byte 100% commit `443a328`. Điểm khuyết duy nhất là không có `.d` depfile của GCC và lưu ý rằng `v3`/`v4` liên kết `_deps` của `r86_v1_2_builds/stock_off` (Highway `0e0a01da`).
4. **Compile/link metadata và historical host receipt còn thiếu gì?**
   - **Compile/link metadata:** Builder `A` và `B` **không thiếu** (`CMakeCache.txt`, `flags.make`, `link.txt`, `compile_commands.json`, `build.make`, `cmake_pch.hxx.gch.d`, logs đều có đủ). Evaluator `v3` và `v4` thiếu CMake build tree và file `.d` compiler depfile (vì compile trực tiếp bằng `/usr/bin/c++`).
   - **Campaign manifest:** `MS_TURING_1M_REPRO_MANIFEST.json` không tồn tại (`MISSING`); thay vào đó có `campaign_manifest.json` đã thu hồi.
   - **Randomness:** Thiếu trường `seed` được ghi trong runtime receipts (`NOT_RECORDED`), dù source khóa `SEED = 555` + `parlay::hash64`.
   - **Historical host receipt (R86):** Thiếu bản chụp cấu hình phần cứng cùng thời điểm R86 (13–15/11/2026) gồm `lscpu`/CPU model cụ thể, core/thread/SMT topology, NUMA topology, `MemTotal`, `/etc/os-release`, `scaling_governor`, và thermal/frequency guard logs (chỉ có kernel `Linux-7.0.0-42-generic` `x86_64`, GCC `13.3.0`, `taskset` affinity, và preflight `MemAvailable >= 7 GiB` trong R86; thông số topology/governor/MemTotal ngày 11/11 thuộc chiến dịch H85).
5. **Nếu executable không còn, bằng chứng nào vẫn đủ để duy trì các kết quả lịch sử R86?**
   - Thực tế **4/4 executable đều CÒN NGUYÊN VẸN**, nên không rơi vào tình huống mất binary. Dù vậy, nếu xét trên tập evidence gốc ngoài 4 ELF, ta vẫn có: `four_binary_manifest.json`, `CMakeCache.txt`/`flags.make`/`link.txt`/`compile_commands.json`/`cmake_pch.hxx.gch.d`, `r86_msturing1m_eval_native_link_v3.json`, `r86_msturing1m_highbeam_v4_manifest.json`, `campaign_manifest.json`, 3 datasets + 18 graphs + 180 Search logs với chuỗi SHA tự nhất quán toàn phần.
6. **Có thể bàn giao những file nào cho Task D ngay bây giờ?**
   - Toàn bộ thư mục mới `/home/tai/ann-task-a/exports/TaskA_R86_Artifact_Recovery_20261117/` (chỉ `24 MB`), bao gồm:
     - 5 file báo cáo/inventory bắt buộc (`TASK_A_R86_ARTIFACT_RECOVERY_REPORT.md`, `.csv`, `.json`, `_MISSING_AND_UNVERIFIED.csv`, `_CHECKSUMS.sha256`).
     - `recovered_artifacts/executables/`: bản sao nguyên byte của cả 4 executable bắt buộc (+ bản trùng `MVzZH3`) và 4 companion (`D0`, `stock_on`, `h17_on`, `G11_counter64`).
     - `recovered_artifacts/provenance/`: toàn bộ metadata CMake/compile/link của `jvYREW`, `D0_v2`, `G0_stock_off_ref`, `msturing_1m_eval`, `campaign_manifest.json`, nguồn `r86_v1_2_source` & `H70` clean headers, 2 patch provenance, và 5 runner scripts.
   - Kết hợp với 2 gói sẵn có trước đó: `exports/TaskD_R86_MST1M_Data_9Graphs.tar` (`2,284,881,920` B) và `exports/TaskD_R86_MST1M_Handoff_v1/`.
7. **Những phần nào phải ghi `HISTORICAL_UNRECOVERABLE` hoặc `NOT_VERIFIED`?**
   - **`HISTORICAL_UNRECOVERABLE` (không có bản ghi gốc tại thời điểm R86):**
     - R86 contemporaneous host hardware/OS/governor/thermal receipt (`lscpu`/CPU model, NUMA, SMT, `MemTotal`, `/etc/os-release`, `scaling_governor`, thermal throttling log chụp ngày 13–15/11/2026).
     - `MS_TURING_1M_REPRO_MANIFEST.json` (`MISSING` — chưa từng được tạo).
     - R86 runtime `seed` receipt (`NOT_RECORDED` trong log/JSON; nguồn dùng `SEED=555` + `parlay::hash64`).
     - `.git` nội tại của `r86_v1_2_source` (chỉ có staging non-git; tuy nhiên chuỗi source-to-H70 **đã được tái lập và kiểm chứng SHA**).
   - **`NOT_VERIFIED`:**
     - Compiler `.d` depfile / CMake tree cho `eval v3` và `eval v4` (không sinh `.d` file khi compile trực tiếp bằng `g++`).
     - Tính áp dụng của telemetry host H85 (ngày 11/11) sang phiên chạy R86 (ngày 13–15/11) — **không tự suy diễn thay thế cho R86 host receipt**.
     - 2 tệp `results/perf_sift1m_{4t,8t}.data` không có quyền đọc (ngoài phạm vi R86).

### Đề Xuất Gate Decision (không tự tuyên bố PASS)

- **Phạm vi Binary & Data/Graph Integrity (4 executables + 3 datasets + 9 priority graphs + 90 Search receipts):** Đề xuất đủ bằng chứng cho **P0 Artifact Recovery / Checksum Verification PASS** sau khi bên Task D đối chiếu độc lập `sha256sum -c TASK_A_R86_CHECKSUMS.sha256`.
- **Phạm vi Build & Source Provenance (Builders A/B + Evaluators v3/v4):** Đủ điều kiện xem xét **PASS_WITH_DISCLOSED_LIMITATIONS** (chấp nhận chuỗi H70 `443a328` + 2 patch SHA + `cmake_pch.hxx.gch.d` thay cho standalone `.git` ở `r86_v1_2_source`, và chấp nhận `compile_command` + clean H70 header SHA verification cho `v3`/`v4` dù thiếu `.d` depfile).
- **Phạm vi Strict Historical Host / Seed Reproducibility:** Phải ghi nhận **CONDITIONAL / NOT_FULLY_SPECIFIED_FOR_CROSS_HOST_TIMING** (hoặc dùng giao thức build/search độc lập riêng của Task D × Task A như bạn của người dùng đã đề xuất, giữ nguyên 9 graph & raw receipts R86 kèm disclosure rõ rằng host/governor/thermal receipt và runtime seed của R86 không được lưu đầy đủ ở runtime).
