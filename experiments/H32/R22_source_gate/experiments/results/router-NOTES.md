# Router entry points for graph search — design and gate (2026-09-21)

Idea (EC): index a sample S of the database, route the query to its nearest
point in S with a cheap greedy/small-beam search, and start the big graph's
beam there instead of at a fixed hub. Routing over a small S is cache-
resident, so its evaluations are cheaper than the ones it replaces.

## Prior art (must be topped, not rediscovered)

* HNSW's upper layers **are** this: geometric samples searched greedily to
  seed layer 0.
* SPTAG seeds a graph from a BKT forest; EFANNA from randomised KD-trees;
  LSH-APG (2023) from LSH. The construction is established.
* "Down with the Hierarchy: the H in HNSW stands for Hubs" (2024) is the
  standing refutation: flat NSW matches HNSW above d≈32, because hubs are
  already highways. Every such ablation counts **evaluations**.

What is ours, if anything: (1) evaluations are not fungible — the wall
measurements give 0.250 G/s on a 9 MB working set against 0.165 G/s on
530 MB, so a cache-resident router's evaluations cost 1/1.5 of the ones it
removes; (2) the ablations were run at recall ≥ 0.9, where the descent is a
small share of the query, and the routing case lives at the throughput end,
left of every ladder we have published; (3) the 2-bit quantiser of paper 2
finally has a job — it makes the router cache-resident at d ≈ 960/1024,
where float vectors would not fit; (4) the routing order statistics are
SOLO's certificate, which would set ef per query.

## The gate (this experiment)

A router over a uniform α-sample returns the query's nearest sample point,
whose rank in the true ordering is geometric with mean 1/α. So **"start at
the query's r-th true neighbour" is the oracle for a router over an
α ≈ 1/r sample**, and sweeping r prices router precision without building a
router. r = 50 is SOLO's α = 2%; r = 100 is 1%; r = 10,000 is 0.01%.

`bench/oracle_entries.py` writes one entry file per rank (ranks < gold width
come from the gold file, deeper ranks are brute-forced; validated against
gold, agreement 1.0000 on the first 10 columns). `fg --entry-list` replays
the whole ef ladder from each file in a single build.

Ladder extended down to ef = 10 — the published ladders start at ef = 60
(recall 0.857, 3,209 distances/query on the laptop), and the claim is about
what happens to the left of that.

**Refutes if:** the perfect oracle (r = 0) saves < 3% of d@r across the whole
ladder — then no router can pay, and the line closes.

**Alive if:** at r = 50 (α = 2%, cache-resident on GloVe at 10.6 MB) the
saving at the cheap end of the ladder exceeds the analytic router cost
(~2 log_deg(αn) · deg evaluations charged at 1/1.5), with margin.

Caveat to carry: ranks 0–10 inflate recall@10, because the entry point is
itself part of the answer. Only r ≥ 25 is a clean reading.

## Runs

| dataset | graph | log |
|---|---|---|
| GloVe-100 (1.18M, cosine) | GRAFT T32/ef600 frozen, laptop 10 threads | `router/glove_T32ef600_oracle.log` |
| wiki-1024 (200k, BGE-M3, cosine) | GRAFT T32/ef600 frozen, laptop 10 threads | `router/wiki_T32ef600_oracle.log` |

---

# Result (2026-09-21) — the line closes, with a constant

## 1. The entry point is worth a fixed toll of 4–7 hops

| | GloVe-100 (1.18M, deg 53.4) | wiki-1024 (200k, deg 40.6) |
|---|---:|---:|
| refund at recall 0.82 | 258 evaluations | 162 |
| 0.90 | 242 | 153 |
| 0.95 | 212 | 153 |
| 0.97 | 196 | 148 |
| **in hops** | **≈ 5–6.5** | **≈ 3.6–4.0** |

The refund from a *perfect, free* entry point is a **constant number of
evaluations, independent of the operating point** — the descent, and nothing
else. From a uniformly random vertex these graphs reach the query's
neighbourhood in four to six hops. There is no long descent to skip, which is
the hub effect as a number.

As a fraction it is 30% of a recall-0.60 query and 2% of a recall-0.95 query
on GloVe, purely because the denominator moves and the numerator does not.

## 2. Three mechanisms that could have been larger; all three are zero

* **A closer start does not buy a smaller beam.** At fixed ef the recall is
  identical to ±0.006 and not monotone in start quality (GloVe ef=10:
  hub 0.5947, oracle 0.5931, α=2% 0.5983). The ef needed for a given recall
  is unchanged: ratio 0.999 / 1.021 / 1.010 / 1.005 / 1.003 at recall
  0.72 → 0.97. **ef sets recall; the entry point sets an additive constant;
  they do not interact.**
* **Multi-seed buys nothing.** Seeding with the b = 4 nearest sample points
  (true ranks r, 2r, 3r, 4r) is indistinguishable from b = 1 — wiki at
  ef 10/30/40: 528/1177/1479 for both. The beam does not need help escaping
  a basin.
* **Router precision is a weak lever.** 200× more router (α 0.01% → 2%)
  buys 2–3× more refund (112 → 298 on GloVe). Most of the toll is refunded
  by *any* start inside the top 1% of the database.

Controls: on GloVe `hub`, `besthub` and `random` are indistinguishable
(within 0.4% at every recall) — GRAFT's hub entry buys nothing over a coin
flip. On wiki `besthub` is worth +2–4% and `random` −1 to −4%, so the entry
matters slightly there.

## 3. The accounting that survives: a free router, charged in time

The oracle columns **are** the free-router case, so the gross saving is the
ceiling for a router of any cost including zero. The right router is a flat
2-bit scan of a cache-resident sample (no walk, hence none of the ~200-cycle
adaptivity toll per evaluation — the quantiser of the dense paper finally has
a job):

| corpus | sample | scan cost | refund | **net at recall 0.95** | at 0.90 |
|---|---|---:|---:|---:|---:|
| GloVe-100 | 2% = 23,670 pts, 757 KB (L2) | 95 kcyc | 212 × 782 cyc | **≈ 1%** | ≈ 3% |
| wiki-1024 | 2% = 4,000 pts, 1 MB (L2) | 100 kcyc | 153 × ~4,400 cyc | **≈ 6%** | ≈ 11% |

**The regime rule: the toll is a constant, so it matters when the query is
cheap.** Queries are cheap on well-concentrated data — wiki needs 2,002
evaluations at recall 0.95 against GloVe's 9,400 — so the *same* toll is
7.6% there and 2.3% here. Not because the descent is longer at d = 1024; it
is shorter (3.8 hops vs 6.5).

## 4. Verdict

Closed as a research line, kept as a cheap option. It is worth ~5–10% of
query time on a well-concentrated embedding corpus at production recall, ~1%
on GloVe, for a 1 MB side structure and no change to the build. That is a
constant-factor engineering option, not a paper.

Prior art stands and is now quantified rather than contradicted: the
hierarchy ablations measured at recall ≥ 0.9, where a 150–250-evaluation
refund is 2–8%. They were right; the constant is four to six hops.

## 5. The one regime not tested

A **disk-resident** graph, where a hop is a page read. There the query is
~50–100 random IOs, the toll is 4–7 of them, and each costs ~100 µs — so the
same constant is 5–10% of a query whose cost is dominated by exactly the
thing the router removes, and the router itself stays in RAM. That is the
setting where this idea would be worth building, and it is DiskANN's and
SOLO's setting, not ours.
