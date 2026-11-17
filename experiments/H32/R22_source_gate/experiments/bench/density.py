#!/usr/bin/env python3
"""Density of a coherent-block harvest: how much of a dense (block x union)
GEMM would be wasted if the beams of a block of points ran in lockstep.

    density.py groups  <parents0.i32> <out_prefix> [--cap 512] [--min 128] [--nblocks 64] [--seed 1]
        Coherent blocks = maximal tree-0 SAT subtrees of size <= cap (a node
        is a block root when its subtree fits and its parent's does not);
        sample nblocks of them with size >= min.  Control = nblocks random
        blocks of the median coherent size.  Writes <out_prefix>.mask (n
        bytes, for fg --log-visited) and <out_prefix>.blocks.npz.
    density.py analyze <log.bin> <out_prefix>.blocks.npz
        For each block: B, mean |V_i| (ids whose distance to point i was
        evaluated), |union V_i|, density = sum|V_i| / (B * |union|), and the
        lockstep profile (new-to-the-block ids per expansion step, m_s).
"""
import sys, argparse, numpy as np

def groups(a):
    par = np.fromfile(a.parents, dtype=np.int32); n = len(par)
    rng = np.random.default_rng(a.seed)
    # subtree sizes: process in an order where children precede parents (BFS from root, reversed)
    children = [[] for _ in range(n)]
    root = -1
    for v in range(n):
        p = par[v]
        if p < 0 or p == v: root = v
        else: children[p].append(v)
    order = [root]; i = 0
    while i < len(order):
        order.extend(children[order[i]]); i += 1
    size = np.ones(n, dtype=np.int64)
    for v in reversed(order):
        p = par[v]
        if p >= 0 and p != v: size[p] += size[v]
    is_root = np.zeros(n, dtype=bool)
    for v in range(n):
        p = par[v]
        if size[v] <= a.cap and (p < 0 or p == v or size[p] > a.cap): is_root[v] = True
    roots = np.nonzero(is_root)[0]
    big = roots[size[roots] >= a.min]
    print(f"n={n} block roots={len(roots)} with size in [{a.min},{a.cap}]: {len(big)}; "
          f"coverage of all roots: {size[roots].sum()/n:.3f}")
    pick = rng.choice(big, size=min(a.nblocks, len(big)), replace=False)
    def members(r):
        out = [r]; st = [r]
        while st:
            v = st.pop(); out.extend(children[v]); st.extend(children[v])
        return np.array(out, dtype=np.int32)
    coh = [members(r) for r in pick]
    med = int(np.median([len(c) for c in coh]))
    rnd = [rng.choice(n, size=med, replace=False).astype(np.int32) for _ in range(a.nblocks)]
    mask = np.zeros(n, dtype=np.uint8)
    for c in coh + rnd: mask[c] = 1
    mask.tofile(a.out + ".mask")
    np.savez(a.out + ".blocks.npz", coherent=np.array(coh, dtype=object), random=np.array(rnd, dtype=object), allow_pickle=True)
    print(f"coherent sizes: median {med}, min {min(len(c) for c in coh)}, max {max(len(c) for c in coh)}; "
          f"random blocks: {a.nblocks} x {med}; masked points {int(mask.sum())} -> {a.out}.mask")

def read_log(path):
    raw = np.fromfile(path, dtype=np.int32); logs = {}; i = 0
    while i < len(raw):
        p, ln = int(raw[i]), int(raw[i + 1]); logs[p] = raw[i + 2:i + 2 + ln]; i += 2 + ln
    return logs

def analyze(a):
    logs = read_log(a.log); z = np.load(a.blocks, allow_pickle=True)
    for kind in ("coherent", "random"):
        blocks = z[kind]; dens = []; rows = []
        for blk in blocks:
            seqs = [logs[int(p)] for p in blk if int(p) in logs]
            if len(seqs) != len(blk): continue
            B = len(seqs)
            sets = [np.unique(s[s >= 0]) for s in seqs]             # evaluated ids (markers have the high bit set -> negative)
            sizes = np.array([len(s) for s in sets]); union = np.unique(np.concatenate(sets))
            dens.append(sizes.sum() / (B * len(union)))
            # lockstep: step s = the s-th expansion of each query. An id is "new to the
            # block" at the first step any query evaluates it; m_s = count per step.
            ids_all, steps_all = [], []
            for s_ in seqs:
                mark = (s_ < 0); step = np.cumsum(mark)          # 0 before the first expansion (entries)
                keep = ~mark; ids_all.append(s_[keep]); steps_all.append(step[keep])
            ids_all = np.concatenate(ids_all); steps_all = np.concatenate(steps_all)
            order = np.lexsort((steps_all, ids_all)); ids_s = ids_all[order]; st_s = steps_all[order]
            first = np.ones(len(ids_s), dtype=bool); first[1:] = ids_s[1:] != ids_s[:-1]
            nsteps = int(steps_all.max()) + 1
            m = np.bincount(st_s[first], minlength=nsteps)
            rows.append((B, sizes.mean(), len(union), dens[-1], nsteps, m.mean(), np.median(m), (m < 32).mean(), len(union) * 448 / 1e6))
        r = np.array(rows)
        print(f"\n== {kind} blocks: {len(rows)}")
        print(f"{'':>10}{'B':>7}{'|V_i|':>9}{'|union|':>9}{'density':>9}{'steps':>7}{'m_s mean':>9}{'m_s med':>8}{'frac<32':>8}{'union MB':>9}")
        for lab, f in (("median", np.median), ("mean", np.mean), ("min", np.min), ("max", np.max)):
            v = f(r, axis=0)
            print(f"{lab:>10}{v[0]:7.0f}{v[1]:9.0f}{v[2]:9.0f}{v[3]:9.3f}{v[4]:7.0f}{v[5]:9.1f}{v[6]:8.0f}{v[7]:8.2f}{v[8]:9.2f}")
        print(f"  density (pooled) = {sum(x[0]*x[1] for x in rows)/sum(x[0]*x[2] for x in rows):.3f}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("groups"); g.add_argument("parents"); g.add_argument("out")
    g.add_argument("--cap", type=int, default=512); g.add_argument("--min", type=int, default=128)
    g.add_argument("--nblocks", type=int, default=64); g.add_argument("--seed", type=int, default=1)
    an = sub.add_parser("analyze"); an.add_argument("log"); an.add_argument("blocks")
    a = ap.parse_args(); groups(a) if a.cmd == "groups" else analyze(a)
