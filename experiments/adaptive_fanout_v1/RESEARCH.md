# Adaptive fanout: giả thuyết và thiết kế kiểm tra

## Cơ sở

Mỗi điểm trong một bucket hiện được gán vào số leader cố định theo độ sâu,
thường là fanout 10 ở root, 3 ở tầng sau và 1 ở các tầng sâu hơn. Khi điểm nằm
rõ ràng gần một leader, các bản sao sang leader xa hơn có thể tăng công việc
leaf mà ít bổ sung cạnh hữu ích. Điểm gần ranh giới cần nhiều bản sao hơn.

SPANN (NeurIPS 2021), mục 3.2.2, dùng closure multi-cluster assignment:
chỉ nhân bản sang tâm có khoảng cách không quá `(1+epsilon)` lần khoảng cách
tới tâm gần nhất. Đây là tiền lệ cho heuristic, không phải bằng chứng đảm bảo
chất lượng của graph PiPNN: SPANN có cấu trúc inverted index và mục tiêu khác.

Nguồn chính: https://proceedings.neurips.cc/paper_files/paper/2021/file/299dc35e747eb77177d9cea10a802da2-Paper.pdf

## Quy tắc thử nghiệm

Trong một bucket, sắp leader theo khoảng cách L2: `d1 <= d2 <= ... <= dF`.
Giữ số leader:

```
f(x, bucket) = max(f_min, số i <= F thỏa di <= (1+epsilon)*d1)
```

Luôn giới hạn bởi F; trong code dùng bình phương khoảng cách nên điều kiện
thực tế là `Di <= (1+epsilon)^2*D1`, có dung sai float nhỏ cho tie. Giữ tất
cả tie đủ điều kiện trong cap, kể cả nhiều leader có khoảng cách bằng zero.
`f_min=1` hoặc 2; mặc định chỉ áp dụng từ depth=1, giữ nguyên root fanout 10.
Fanout được quyết định cho từng điểm trong từng bucket; các bucket khác nhau
có phân bố fanout khác nhau, được ghi vào `buckets.jsonl`.

## Vì sao chưa thể bảo đảm không giảm chất lượng

Khoảng cách tới leader không cho biết đầy đủ mật độ dữ liệu, bán kính láng
giềng thật, hoặc cạnh nào quan trọng cho điều hướng graph. Trong một metric,
nếu `d2-d1 > 2r`, mọi điểm trong bán kính r quanh x đều có cùng leader gần nhất
với x (theo bất đẳng thức tam giác). Tuy nhiên ratio heuristic không có upper
bound được chứng minh cho bán kính kNN r; các lần chia tiếp và final pruning
cũng ảnh hưởng graph. Vì vậy không có đảm bảo Recall bằng nhau trên mọi tập.

Chúng ta kiểm tra noninferiority thực nghiệm với dung sai đã định trước, không
gọi dung sai đó là bảo toàn Recall tuyệt đối.

## Dữ liệu, biến kiểm soát và quyết định

- SIFT1M base, toàn bộ 10.000 query và GT top-100 có sẵn, cùng một snapshot
  dữ liệu cho mọi arm. GT không được dùng để xây graph hay chọn fanout.
- Cùng compiler/dependency, H17 ON, R86 counters OFF, C160, leaf cap256,
  prune degree64, alpha1.1, fanout cap10,3,1, root leader100, một lượt cây.
- Cùng bốn thread; fixed và adaptive dùng chung một binary và telemetry.
- Calibration: query IDs 0..999. Chọn epsilon/floor bằng phần này.
- Holdout: query IDs 1000..9999. Phân tích sau khi lưu lựa chọn vào selection.json.
- Pilot seed555: fixed, epsilon 0/.01/.03/.05/.10 với floor1, epsilon .03 floor2.
- Điều kiện pilot: giảm ít nhất 5% directed proposals và mất Recall@10 không
  quá 0.002 tuyệt đối tại mọi beam 80/100/120/140/160. Trong các ứng viên đạt,
  chọn số proposals nhỏ nhất; không chọn theo lần đo thời gian nhanh nhất.
- Xác nhận fixed/ứng viên đã chọn trên thêm seed556 và557; đổi thứ tự chạy để
  giảm lệch do nhiệt/cache. Tổng ba seed cho hai arm được so sánh chính.
- Holdout dùng paired bootstrap cả build seed và query, 2.000 mẫu. Bound
  một phía Bonferroni cho các beam bảo vệ với family alpha=.05. Kiểm tra bound
  thấp không dưới -0.002. Ba seed và một dataset vẫn là giới hạn quan trọng.
- Nếu không arm nào đạt, report ghi rõ thất bại; vẫn giữ công cụ để thử tiếp.

Refinement được ghi trong `refinement_protocol.json` sau khi đọc calibration
pilot và trước khi phân tích holdout adaptive. Nó thử epsilon .10 floor2,
.15 floor1/2 và .20 floor1/2, giữ cùng split và tiêu chí; chỉ một cấu hình
được chọn bằng calibration để xác nhận trên ba seed. Không dùng kết quả
holdout của pilot để chọn tham số. Baseline được tái sử dụng sau khi kiểm tra
binary/dataset/config khớp, nên timing refinement không được counterbalance
với baseline ngay tại cùng thời điểm; phải xem đây là phép đo chẩn đoán.

## Số đo

Nominal/actual assignments, histogram fanout theo bucket/depth, leaf visits,
sum(leaf_size^2), directed proposals thực sự sinh ra trước online pruning,
occupied reservoir slots, số cạnh cuối, graph reachable từ node0, native build
wall time/RSS, Recall/QPS, latency và Recall từng query. Báo thêm beam nhỏ nhất
đạt Recall .95/.99 trên lưới đã thử và hiệu năng tại beam đó.

Chú ý: fewer proposals khác với fewer final edges. Pool C160 vẫn cấp phát như
cũ; flat buffer cũng reserve theo fanout tối đa rồi compact logical size tại
chỗ. Không khẳng định bộ nhớ giảm tỷ lệ với số assignment; phải đọc peak RSS.
Telemetry tạo ít overhead ở cả fixed/adaptive; CPU không được độc chiếm.

## Kiểm chứng triển khai

- Test ngưỡng trên L2 bình phương, floor, monotonicity và các tie/zero.
- Fixed mode trên SIFT10K, một thread, seed555 phải cho graph byte-identical
  với binary gốc; proposals/W_A/W_L khớp counters gốc. Xem control_validation.json.
- Kiểm tra histogram không có fanout zero, root không đổi và tổng counts.
- SHA256 của 232 file source/config/binary cũ được kiểm tra trước/sau; không
  sửa chúng. Snapshot source và patch nằm trong thư mục thử nghiệm này.
