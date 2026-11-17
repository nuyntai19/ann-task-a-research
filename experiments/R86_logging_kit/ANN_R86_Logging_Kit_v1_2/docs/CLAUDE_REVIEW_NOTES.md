# Đề nghị Claude kiểm tra trước khi áp patch

1. Vị trí thực của `SelectAndAssignLeaders`, `RunLeaf`, `eigen_knn`, `merge_neighbors`, `RobustPrune` trong source snapshot R86; mỗi metric có đúng ngữ nghĩa và đúng pass/depth không?
2. `active_pass` dùng atomic global có phù hợp với vòng lặp `multiple_clustertrees` tuần tự thật không? Nếu không, truyền pass_id theo task.
3. Tránh đặt counter s² trong inner loop. Xem `W_P` có bao gồm GEMM entries thực và `W_L` có bao gồm full matrix hay chỉ nửa trên.
4. Hash ID collision phải so đúng candidate ID tại nhánh hash match; có early break trước đó hay không?
5. Chọn rõ metric sum vs max (e.g. `max_depth` phải tính maximum, không cộng vào tổng).
6. Tách ON/OFF; compiler flags, GT/evaluator, source manifests và provenance đều có thể kiểm tra độc lập?
7. Việc so số cạnh/Recall trên SIFT100K phải dùng đúng fixture/query/beam, chấp nhận biến thiên do random_device; không đòi SHA graph giống tuyệt đối.
8. Tất cả columns theo Sheet v1.2 đã xuất trong CSV, nhưng actual RUN chỉ điền những gì đã đo; review cách tính `T_phase/W_phase` theo loại phase time.

Trạng thái: HEADER MẪU + LOGGING CLI, **chưa phải patch được kiểm thử trong PiPNN native**.
