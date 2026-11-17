#!/usr/bin/env python3
"""Figure: build distance throughput vs working set (results/wall/cache_sweep/cache_sweep.json).
    python3 bench/plot_sweep.py results/wall/cache_sweep/cache_sweep.json ../FGRAFTPaper/fig_sweep.pdf"""
import json, sys, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
res = json.load(open(sys.argv[1])); rows = res["rows"]
mb = np.array([r["working_set_MB"] for r in rows])
fg = np.array([r["fg"]["gdist"] / r["fg"]["build_s"] for r in rows])
vam = np.array([r["vamana"]["gdist"] / r["vamana"]["build_s"] for r in rows])
gemm = np.array([r["gemm"]["rate"] / 1e9 for r in rows])
C = {"gemm": "#2a78d6", "vamana": "#eb6834", "fg": "#1baf7a"}   # validated categorical slots 1-3
plt.rcParams.update({"font.size": 9, "font.family": "serif", "axes.edgecolor": "#888", "axes.linewidth": 0.6,
                     "xtick.color": "#444", "ytick.color": "#444", "axes.labelcolor": "#0b0b0b"})
fig, ax = plt.subplots(figsize=(5.2, 3.2))
ax.set_xscale("log"); ax.set_yscale("log")
ax.axvspan(20, 80, color="#000", alpha=0.05, lw=0)
ax.text(40, 0.06, "L3: one socket → all four", ha="center", va="bottom", fontsize=7.5, color="#52514e")
ax.axhline(0.335, color="#52514e", lw=0.8, ls=":")
ax.text(9, 0.36, "dependent-read bandwidth ceiling, 150 GB/s ÷ 448 B", fontsize=7.5, color="#52514e", va="bottom")
ax.plot(mb, gemm, "-o", color=C["gemm"], lw=2, ms=5, mec="white", mew=0.8)
ax.plot(mb, vam, "-s", color=C["vamana"], lw=2, ms=5, mec="white", mew=0.8)
ax.plot(mb, fg, "-^", color=C["fg"], lw=2, ms=5.5, mec="white", mew=0.8)
ax.text(mb[-1] * 1.12, gemm[-1], "dense GEMM", color=C["gemm"], va="center", fontsize=8.5, fontweight="bold")
ax.text(mb[-1] * 1.12, vam[-1] * 1.12, "Vamana", color=C["vamana"], va="center", fontsize=8.5, fontweight="bold")
ax.text(mb[-1] * 1.12, fg[-1] * 0.88, "GRAFT T16", color=C["fg"], va="center", fontsize=8.5, fontweight="bold")
ax.annotate("", xy=(mb[-1] * 0.93, gemm[-1]), xytext=(mb[-1] * 0.93, vam[-1]), arrowprops=dict(arrowstyle="<->", color="#52514e", lw=0.8))
ax.text(mb[-1] * 0.86, np.sqrt(gemm[-1] * vam[-1]), f"{gemm[-1]/vam[-1]:.0f}×", ha="right", va="center", fontsize=8.5, color="#0b0b0b")
ax.annotate("", xy=(mb[0] * 0.93, gemm[0]), xytext=(mb[0] * 0.93, vam[0]), arrowprops=dict(arrowstyle="<->", color="#52514e", lw=0.8))
ax.text(mb[0] * 0.86, np.sqrt(gemm[0] * vam[0]), f"{gemm[0]/vam[0]:.0f}×", ha="right", va="center", fontsize=8.5, color="#0b0b0b")
ax.set_xlim(5.5, 1400); ax.set_ylim(0.05, 8)
ax.set_xlabel("working set (MB), GloVe-100 prefixes, 448 B per vector")
ax.set_ylabel("build throughput (10$^9$ distances / s)")
ax.set_yticks([0.1, 0.2, 0.5, 1, 2, 5]); ax.set_yticklabels(["0.1", "0.2", "0.5", "1", "2", "5"])
ax.set_xticks([10, 20, 50, 100, 200, 500, 1000]); ax.set_xticklabels(["10", "20", "50", "100", "200", "500", "1000"])
ax.grid(True, which="major", color="#ddd", lw=0.5); ax.grid(False, which="minor")
ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
fig.tight_layout(); fig.savefig(sys.argv[2]); print("wrote", sys.argv[2])
