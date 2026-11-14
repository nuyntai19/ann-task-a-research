#!/usr/bin/env python3
"""Parse an `fg --entry-list` log and price the router.

For each entry source it interpolates d@r (distance evaluations per query to
reach recall r) and the QPS at that recall, and reports the saving against
the baseline entry. A rank-r entry models a router over an alpha ~ 1/r
sample; the saving is an upper bound because the oracle entry is free, so we
also subtract an analytic router cost:

    router evaluations ~ hops * degree over alpha*n points,
    charged at the in-cache beam rate (1.5x the DRAM-resident rate, measured
    in wall-FINDINGS.md: 0.250 G/s at 9 MB vs 0.165 G/s at 530 MB).
"""
import argparse, math, re, sys

def parse(path):
    blocks, cur, label = {}, None, None
    for line in open(path):
        m = re.match(r"\s*entry=(\S+)", line)
        if m:
            label = m.group(1); cur = []; blocks[label] = cur; continue
        m = re.match(r"\s*(\d+)\s+([0-9.]+)\s+(\d+)\s+(\d+)\s*$", line)
        if m and cur is not None:
            cur.append((int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))))
    return blocks

def at_recall(rows, r):
    """(dist/query, QPS) interpolated at recall r; None if the ladder misses it."""
    for (e0, r0, d0, q0), (e1, r1, d1, q1) in zip(rows, rows[1:]):
        if r0 <= r <= r1 and r1 > r0:
            t = (r - r0) / (r1 - r0)
            return d0 + t * (d1 - d0), q0 + t * (q1 - q0)
    return None

def rank_of(label):
    m = re.search(r"_r(\d+)\.i32$", label)
    return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log"); ap.add_argument("--base", default="hub")
    ap.add_argument("--recalls", type=float, nargs="+", default=[0.85, 0.90, 0.95, 0.97])
    ap.add_argument("--n", type=int, required=True, help="database size")
    ap.add_argument("--degree", type=float, required=True, help="mean out-degree of the graph")
    ap.add_argument("--cache-speedup", type=float, default=1.52,
                    help="in-cache beam rate / DRAM-resident beam rate")
    a = ap.parse_args()
    B = parse(a.log)
    if a.base not in B: sys.exit(f"baseline '{a.base}' not in {list(B)}")

    print(f"\n{'entry':>28}{'alpha':>9}" + "".join(f"{('d@%.2f' % r):>12}" for r in a.recalls))
    print(f"{'':>28}{'':>9}" + "".join(f"{'(saving)':>12}" for r in a.recalls))
    base = {r: at_recall(B[a.base], r) for r in a.recalls}
    rows = []
    for label, tab in B.items():
        rk = rank_of(label)
        alpha = "" if rk is None else (f"{100.0/max(rk,1):.3f}%" if rk else "oracle")
        cells, save = [], {}
        for r in a.recalls:
            v = at_recall(tab, r); b = base[r]
            if v is None or b is None: cells.append(f"{'--':>12}"); continue
            s = 1.0 - v[0] / b[0]; save[r] = (v[0], b[0], s)
            cells.append(f"{v[0]:8.0f}{s*100:+4.0f}%")
        rows.append((label, rk, save))
        print(f"{label.replace('file:','').split('/')[-1]:>28}{alpha:>9}" + "".join(cells))

    print(f"\n  net of an analytic router cost (greedy over alpha*n, degree {a.degree:.0f},"
          f" charged at 1/{a.cache_speedup:.2f} the beam's cost per evaluation):")
    print(f"{'alpha':>10}{'rank':>8}{'router evals':>14}" +
          "".join(f"{('net@%.2f' % r):>12}" for r in a.recalls))
    for label, rk, save in rows:
        if not rk: continue
        ns = a.n / rk                                  # sample size for alpha ~ 1/rank
        if ns < 2: continue
        hops = math.log(ns) / math.log(max(a.degree, 2.0)) * 2.0   # ~2 log_deg(ns) greedy hops
        cost = hops * a.degree / a.cache_speedup       # in baseline-evaluation equivalents
        cells = []
        for r in a.recalls:
            if r not in save: cells.append(f"{'--':>12}"); continue
            v, b, _ = save[r]
            cells.append(f"{(1.0-(v+cost)/b)*100:+11.1f}%")
        print(f"{100.0/rk:9.3f}%{rk:>8}{cost:14.0f}" + "".join(cells))

if __name__ == "__main__":
    main()
