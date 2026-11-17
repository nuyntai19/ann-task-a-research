import numpy as np, sys, time
sys.path.insert(0, "bench")
exec(open("bench/kmeans_init_diag.py").read().split("W0 = Q[:L].copy()")[0])   # reuse data, assign, lloyd_step, evaluate, hsp_smooth
W = Q[:L].copy(); print(f"{'HSP-smoothing rounds':<24}{'no Lloyd':<32}{'+3 Lloyd':<32}{'spread'}")
for r in range(0, 7):
    if r > 0: W, dg = hsp_smooth(W, 1)
    rec0, p0, g0, m0 = evaluate(W); C = W.copy()
    for _ in range(3): C = lloyd_step(C)
    rec3, p3, g3, m3 = evaluate(C)
    spread = np.sqrt(((W - W.mean(0))**2).sum(1)).mean()
    print(f"{r:<24}{rec0:.3f}@{p0:.0f}k|{g0:.1f}G|{m0//1000}k{'':<8}{rec3:.3f}@{p3:.0f}k|{g3:.1f}G|{m3//1000}k{'':<8}{spread:.2f}", flush=True)
