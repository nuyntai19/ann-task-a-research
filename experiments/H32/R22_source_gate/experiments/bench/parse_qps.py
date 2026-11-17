#!/usr/bin/env python3
"""QPS and distance evaluations at fixed recall from ParlayANN logs.

Reads every "For k@k recall = r, QPS = q, Q = ..., average cmps = d" line
(k = 10 or 100), orders the ladder by beam width, and interpolates at each
target recall: d linearly, QPS log-linearly. QPS is ParlayANN's batch
throughput with all threads of the machine that ran the log (d0: 64), so
compare QPS only between logs from the same machine and session.

    python3 bench/parse_qps.py --targets 0.90 0.95 0.99 log1 [log2 ...]
"""
import argparse, math, re

LINE = re.compile(r"For (\d+)@\d+ recall = ([0-9.]+), QPS = ([0-9.e+]+), Q = (\d+).*?average cmps = (\d+)")

def ladder(text):
    rows = sorted((int(q), float(r), float(qps), float(d)) for k, r, qps, q, d in LINE.findall(text))
    k = LINE.search(text).group(1) if LINE.search(text) else "?"
    return k, [(r, qps, d) for _, r, qps, d in rows]

def at(lad, t):
    for (r0, q0, d0), (r1, q1, d1) in zip(lad, lad[1:]):
        if r0 <= t <= r1 and r1 > r0:
            w = (t - r0) / (r1 - r0)
            return math.exp(math.log(q0) + w * (math.log(q1) - math.log(q0))), d0 + w * (d1 - d0)
    return None

ap = argparse.ArgumentParser()
ap.add_argument("--targets", nargs="*", type=float, default=[0.90, 0.95, 0.99])
ap.add_argument("logs", nargs="+")
a = ap.parse_args()
hdr = "".join(f"  {'QPS@'+str(t):>10} {'d@'+str(t):>8}" for t in a.targets)
print(f"{'log':<44} {'k':>3}{hdr}")
for f in a.logs:
    k, lad = ladder(open(f, errors="replace").read())
    cells = []
    for t in a.targets:
        v = at(lad, t)
        cells.append(f"  {v[0]:>10.0f} {v[1]:>8.0f}" if v else f"  {'—':>10} {'—':>8}")
    print(f"{f.split('/')[-1][:44]:<44} {k:>3}{''.join(cells)}")
