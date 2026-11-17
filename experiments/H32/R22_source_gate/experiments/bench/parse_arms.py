#!/usr/bin/env python3
"""Parse fg run logs into a matched-recall table.

    python3 bench/parse_arms.py results/phase1_glove.log [--targets 0.95 0.97]

Reports, per arm: build distances (G), tree/harvest wall, completeness, and
distances per query interpolated at each recall target (a dash means the beam
sweep did not bracket it -- a statement about the sweep, not reachability).
With repeated blocks it reports the median over blocks.
"""
import argparse, re, statistics, sys
from collections import defaultdict

def parse(text):
    out = defaultdict(list)
    for chunk in re.split(r'### (?:RUN|BLOCK \d+ ARM) ', text)[1:]:
        label = chunk.split('\n', 1)[0].strip()
        m = re.search(r'trees ([\d.]+)s \(\d+ threads\), ([\d.]+)M dist', chunk)
        if not m:
            continue
        rec = {'trees_s': float(m.group(1)), 'Gdist': float(m.group(2)) / 1000}
        h = re.search(r'harvest ef=\d+ cap=\d+ rounds=\d+[^\n]*? ([\d.]+)s', chunk)
        rec['harvest_s'] = float(h.group(1)) if h else float('nan')
        c = re.search(r'local completeness \(k=10, sample\): ([\d.]+)', chunk)
        rec['compl'] = float(c.group(1)) if c else float('nan')
        rec['ladder'] = [(float(a), float(b)) for _, a, b, *_ in
                         (m2.groups() and (m2.group(0), m2.group(2), m2.group(3))
                          for m2 in re.finditer(r'^\s+(\d+)\s+([\d.]+)\s+(\d+)\s', chunk, re.M))]
        out[label].append(rec)
    return out

def interp(ladder, t):
    for (r1, d1), (r2, d2) in zip(ladder, ladder[1:]):
        if r1 <= t <= r2:
            return d1 + (d2 - d1) * (t - r1) / (r2 - r1)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log'); ap.add_argument('--targets', nargs='*', type=float,
                                            default=[0.95, 0.97])
    a = ap.parse_args()
    arms = parse(open(a.log).read())
    if not arms:
        sys.exit('no arms parsed')
    head = f"{'arm':<26}{'n':>3}{'Gdist':>8}{'build s':>9}{'compl':>7}"
    head += ''.join(f"{'d@'+str(t):>9}" for t in a.targets)
    print(head); print('-' * len(head))
    for label, recs in arms.items():
        med = lambda k: statistics.median(r[k] for r in recs)
        row = f"{label:<26}{len(recs):>3}{med('Gdist'):8.1f}"
        row += f"{med('trees_s')+med('harvest_s'):9.1f}{med('compl'):7.3f}"
        for t in a.targets:
            vals = [v for v in (interp(r['ladder'], t) for r in recs) if v]
            row += f"{statistics.median(vals):9.0f}" if vals else f"{'—':>9}"
        print(row)

if __name__ == '__main__':
    main()
