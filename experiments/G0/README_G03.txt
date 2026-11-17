G0.3 — Edge-Refinement Feasibility Pilot (exploratory)
======================================================

Purpose
-------
Take an already-built SIFT1M PiPNN f30 graph and create 4 alternative graphs
through exactly B=100,000 outgoing-edge swaps per alternative. Every f30
vertex's out-degree remains unchanged, every graph has the same file size and
number of directed edges as f30. BFS reachability from vertex 0 is audited.
Evaluate every result through the same existing native ParlayANN Vamana SEARCH.

Policies
--------
- random_2hop: genuinely non-oracle. Sample an edge (v,w) from f30's 2-hop
  neighborhood (v -> a -> w), not originally an outgoing edge of v; evict a
  random edge from v. Requires no f60 graph for candidate generation (the
  source vertex pool is shared across methods for convenience).
- oracle_random: pick an f60-only candidate and an f30-only victim, both random.
- oracle_lowdegree: prioritize low-outdegree source vertices, then make random
  f60-only-for-f30 edge replacements.
- oracle_geometry: same selected source vertices as oracle_random, replace
  longest f30-only edge with shortest f60-only edge (squared L2 distance).

Oracle methods are DIAGNOSTICS ONLY: f60 must already exist and its build
cost must be charged. These methods are NOT feedback-based BUILD algorithms.
Different candidate-generation costs are NOT matched; only edge replacement
budget, all f30 source degrees, and graph bytes are equal. f60 is a qualitative
reference and has a different graph size.

Environment
-----------
cd ~/ann-task-a
source .venv/bin/activate
set +e
set +u
set +o pipefail

IMPORTANT: Verify frozen graphs before proceeding:
sha256sum -c experiments/G0/metadata/baseline_graphs.sha256

1. Expand this zip directly into experiments/G0/.
   It should create: experiments/G0/g03_construct.py and g03_evaluate.py

2. Construct graph variants:
python -u experiments/G0/g03_construct.py --budget 100000 --pool-size 250000 --seed 20261023 \
  2>&1 | tee experiments/G0/logs/g03_construct.log

3. Native-search evaluation:
python -u experiments/G0/g03_evaluate.py --budget 100000 --seed 20261023 --q 120 135 160 \
  2>&1 | tee experiments/G0/logs/g03_evaluate.log

4. Show resulting measurements:
cat experiments/G0/results/g03/search_b100000_s20261023.csv

Output files
------------
experiments/G0/results/g03/manifest_b100000_s20261023.json
experiments/G0/results/g03/random_2hop_b100000_s20261023.graph
experiments/G0/results/g03/oracle_random_b100000_s20261023.graph
experiments/G0/results/g03/oracle_lowdegree_b100000_s20261023.graph
experiments/G0/results/g03/oracle_geometry_b100000_s20261023.graph
experiments/G0/results/g03/search_b100000_s20261023.csv
experiments/G0/results/g03/search_b100000_s20261023.json
experiments/G0/logs/g03/*.log

Failures: logs and python errors should remain in the terminal if 'set +e' is
executed first. The script DOES NOT overwrite output graphs from prior runs;
change --seed and/or --budget to repeat. It will not alter source graphs.

Interpretation
--------------
Same-Q comparisons can tell whether replacing a small fraction of edges
changes recall and/or search performance. This does NOT constitute an
honest build-time speedup claim, proven predictive feedback, or novelty.
After this screening step, use multiple seeds, an untouched independent
validation dataset/query set, matched candidate-generation distance evaluations,
and a true end-to-end construction budget before considering a GO decision.

Both scripts were tested on a synthetic graph; real-data outcome is UNKNOWN
until run on the user's existing SIFT1M files.
