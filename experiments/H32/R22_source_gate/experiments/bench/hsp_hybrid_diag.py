import numpy as np, sys
sys.path.insert(0, "bench")
src_code = open("bench/hsp_lloyd_diag.py").read().split("\nW0 = Q[:L].copy()\nprint(")[0]
exec(src_code)
W0 = Q[:L].copy()
# hybrid: r enlarged rounds (directed) then k plain Lloyd rounds
print(f"{'enlarged r':<12}{'then Lloyd 0':<30}{'then Lloyd 2':<30}{'then Lloyd 5':<30}")
for r in (1, 2, 3, 5):
    C = W0.copy()
    for _ in range(r): C, _ = enlarged_step(C, False)
    out = []
    Ck = C.copy(); k_done = 0
    for k in (0, 2, 5):
        while k_done < k: Ck = lloyd_step(Ck); k_done += 1
        out.append(evaluate(Ck))
    print(f"{r:<12}" + "".join(f"{rec:.3f}@{p:.0f}k|{g:.1f}G|{mx//1000}k{'':<10}" for rec, p, g, mx in out), flush=True)
    if r == 5: C.astype(np.float32).tofile(sys.argv[1] + "_enl5_L700.f32")
    if r == 2: C.astype(np.float32).tofile(sys.argv[1] + "_enl2_L700.f32")
print("wrote enlarged-Lloyd leader files (r=2, r=5)")
