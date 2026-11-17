#!/usr/bin/env python3
"""Paper 2, Table 3 from one paired run: every arm against Vamana.

Reads the d0_phase1.py manifest (results.rows: {block, system, build_s, ...}),
reports per-arm median build, the Hodges-Lehmann ratio to Vamana with its
exact 95% CI and the exact Wilcoxon p (same estimators as
graft-ann/bench/paired_stats.py), G dist and completeness medians, and the
d@r medians of the ParlayANN-graded arms (PiPNN) interpolated per block.

    python3 bench/table3_stats.py results/table3/phase1-table3-glove-d0-s1.json
"""
import json, statistics, sys
sys.path.insert(0, "/Users/elchavez/code/claude/graft-ann/bench")
import numpy as np
from scipy import stats
from paired_stats import walsh_hl

def interp(ladder, t):
    lad = sorted((r, d) for _, r, d in ladder)
    for (r1, d1), (r2, d2) in zip(lad, lad[1:]):
        if r1 <= t <= r2 and r2 > r1: return d1 + (d2 - d1) * (t - r1) / (r2 - r1)
    return None

def main(path, ref="vamana-R100-L200-a1.0-2pass", targets=(0.95, 0.97)):
    m = json.load(open(path)); rows = [r for r in m["results"]["rows"] if "build_s" in r]
    by = {}
    for r in rows: by.setdefault(r["system"], {})[r["block"]] = r
    print(f"{path}: {m['config']['blocks_done']} blocks done")
    head = f"{'arm':<30}{'n':>3}{'build med':>11}{'IQR%':>6}{'HL vs Vamana [95% CI]':>26}{'p':>8}{'G dist':>8}{'compl':>7}" + "".join(f"{'d@'+str(t):>9}" for t in targets)
    print(head); print("-" * len(head))
    for a, recs in by.items():
        blocks = sorted(set(recs) & set(by[ref]))
        b = np.array([recs[k]["build_s"] for k in blocks]); v = np.array([by[ref][k]["build_s"] for k in blocks])
        med = np.median(b); iqr = (np.percentile(b, 75) - np.percentile(b, 25)) / med * 100
        line = f"{a:<30}{len(blocks):>3}{med:11.1f}{iqr:6.1f}"
        if a != ref and len(blocks) >= 2:
            lr = np.log(b / v); hl, lo, hi = walsh_hl(lr)
            p = stats.wilcoxon(lr, alternative="two-sided", method="exact").pvalue if len(blocks) >= 5 else float("nan")
            line += f"{np.exp(hl):9.3f} [{np.exp(lo):.3f}, {np.exp(hi):.3f}]{p:8.3g}"
        else: line += f"{'1':>26}{'':>8}"
        g = [recs[k]["gdist"] for k in blocks if "gdist" in recs[k]]; c = [recs[k]["completeness"] for k in blocks if "completeness" in recs[k]]
        line += f"{statistics.median(g):8.1f}" if g else f"{'—':>8}"; line += f"{statistics.median(c):7.3f}" if c else f"{'—':>7}"
        for t in targets:
            vals = [x for x in (interp(recs[k]["ladder"], t) for k in blocks if recs[k].get("ladder")) if x]
            line += f"{statistics.median(vals):9.0f}" if vals else f"{'—':>9}"
        print(line)

if __name__ == "__main__":
    main(sys.argv[1])
