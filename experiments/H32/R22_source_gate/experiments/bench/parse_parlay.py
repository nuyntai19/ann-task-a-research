#!/usr/bin/env python3
"""d@r from ParlayANN logs (Vamana, PiPNN, or a dumped graph graded via -graph_path).

Parses every "For 10@10 recall = r, ... average cmps = d" line, orders the
ladder by beam width Q, and interpolates linearly the distance evaluations
per query at each recall target (a dash means the ladder does not bracket
the target). Also prints build time, degree, and peak RSS when present.

    python3 bench/parse_parlay.py --targets 0.95 0.99 log1 [log2 ...]
"""
import argparse, re, sys

LINE = re.compile(r"recall = ([0-9.]+), QPS = [0-9.e+]+, Q = (\d+).*?average cmps = (\d+)")

def parse(text):
    rows = sorted((int(q), float(r), float(d)) for r, q, d in LINE.findall(text))
    ladder = [(r, d) for _, r, d in rows]
    m = re.search(r"Graph built in ([0-9.]+) seconds", text)
    deg = re.search(r"average degree ([0-9.]+) and maximum degree (\d+)", text)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    wall = re.search(r"Elapsed \(wall clock\) time.*?: ([0-9:.]+)", text)
    bd = re.search(r"BUILD_DISTANCES(?:_PIPNN.*?total=)? ?(\d+)", text)
    return dict(ladder=ladder, build_s=float(m.group(1)) if m else None,
                deg=(float(deg.group(1)), int(deg.group(2))) if deg else None,
                rss_gb=int(rss.group(1)) / 2**20 if rss else None,
                wall=wall.group(1) if wall else None,
                gdist=int(bd.group(1)) / 1e9 if bd else None)

def interp(ladder, t):
    for (r1, d1), (r2, d2) in zip(ladder, ladder[1:]):
        if r1 <= t <= r2 and r2 > r1:
            return d1 + (d2 - d1) * (t - r1) / (r2 - r1)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--targets", nargs="*", type=float, default=[0.95, 0.97, 0.99])
    a = ap.parse_args()
    head = f"{'log':<36}{'build s':>9}{'G dist':>8}{'deg':>7}{'max':>5}{'RSS GB':>8}{'max r':>7}"
    head += "".join(f"{'d@'+str(t):>9}" for t in a.targets)
    print(head); print("-" * len(head))
    for path in a.logs:
        p = parse(open(path).read())
        if not p["ladder"]:
            print(f"{path:<36} no ladder"); continue
        row = f"{path.split('/')[-1]:<36}"
        row += f"{p['build_s']:9.1f}" if p["build_s"] else f"{'—':>9}"
        row += f"{p['gdist']:8.1f}" if p["gdist"] else f"{'—':>8}"
        row += f"{p['deg'][0]:7.1f}{p['deg'][1]:5d}" if p["deg"] else f"{'—':>7}{'—':>5}"
        row += f"{p['rss_gb']:8.1f}" if p["rss_gb"] else f"{'—':>8}"
        row += f"{max(r for r, _ in p['ladder']):7.4f}"
        for t in a.targets:
            v = interp(p["ladder"], t)
            row += f"{v:9.0f}" if v else f"{'—':>9}"
        print(row)

if __name__ == "__main__":
    main()
