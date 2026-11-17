# H26-P3b triage: phân biệt Fused speedup và regression của đối chứng Top-2

## Vì sao cần kiểm tra

H26-P0 Top2 selection worker khoảng 38.758 s; H26-P3b TOP2 *control* là 59.055 s, Fused 38.469 s. Đối chứng chạy trong binary P3b có vẻ chậm hơn nguồn H26-P0. Vì vậy mức cải thiện -13.33% wall của Fused so P3b Top2 có thể là hậu quả control bị chậm hơn, không phải Fused nhanh hơn một baseline tối ưu đã chứng minh.

## Phương pháp

Dùng ba arm: `p0_top2` với binary H26-P0, `p3b_top2` và `p3b_fused` với binary P3b. Mỗi arm chạy 3 vòng, luân phiên một lần ở mỗi vị trí thứ tự. Tất cả đều chạy SIFT1M, 4 threads, CPUSET 0,2,4,6, không ghi graph. Kiểm `85,529` leaf; `29,995,085` rows; `59,990,170` proposals; preflight fused/Highway sampled trước lúc đo.

Lưu ý ba phép đo không cùng binary tuyệt đối nên không quy kết nhân quả tuyệt đối được. Cần sử dụng same-source recompile/uninstrumented or source disassembly nếu cần đào sâu sau.

## Chạy

```bash
mkdir -p ~/ann-task-a/experiments/H26/P3B_triage_kit
cd ~/ann-task-a/experiments/H26/P3B_triage_kit
unzip -o ~/Downloads/H26_P3B_control_triage_kit.zip -d .
bash h26_p3b_triage.sh
```

## Kết quả

```bash
OUT=$(ls -td ~/ann-task-a/experiments/H26/H26_P3B_TRIAGE_* | head -n 1)
cat "$OUT/triage_summary.txt"
```

Nếu `H26TRIAGE_FAIL_CLOSED`, gửi phần log cuối trước khi làm việc khác. Không sửa/ghi đè mã hay graph H26-P0/P3b. Script preflight và 9 lượt BUILD sẽ chạy tuần tự đồng bộ trong terminal.

## Cách đánh giá

- Nếu `p3b_top2` chậm hơn đáng kể so `p0_top2` còn `p3b_fused` ngang `p0_top2`, NO-GO cho tuyên bố Fused tạo speedup hơn H26-P0.
- Nếu `p3b_fused` nhanh hơn cả `p0_top2` ở nhiều vòng và chênh đáng kể, tiếp tục gate kiểm tra graph + Recall.
- Cả hai trường hợp đây đều chỉ là *implementation optimization*, không phải đóng góp ANN mới.
