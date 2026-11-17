# H19-G0 — Same-run offline cross-block proxy audit

**Status:** NO_GO_SCORE_DOES_NOT_BEAT_SIMPLE_BASELINES

- H18-R1 leaf proposals: 59,990,170 events / 85,529 leaves.
- Holdout pair probes: 168 pairs; eligible: 168.
- Sampled surrogate positive pair occurrences: 159.
- Pilot/holdout split prevents using heldout distances when constructing the directional score.

| Ranking | Sampled hit rate | Blocks | Rectangular pair budget used |
|---|---:|---:|---:|
| directional_score | 0.00061 | 22 | 1,664,149 |
| nearest_score | 0.00090 | 21 | 1,674,023 |
| overlap_high_score | 0.00077 | 13 | 1,662,106 |
| overlap_low_score | 0.00000 | 15 | 1,662,781 |
| radius_score | 0.00040 | 18 | 1,666,276 |

Random-30 median sampled hit rate: 0.00023.

**IMPORTANT:** These hits are only a pilot-second-nearest *surrogate*. They cannot establish navigation utility, build speedup, recall preservation, or novelty. Budget replacement was NOT implemented. H19-C1 remains unselected.

Review summary.json + pair_candidates.csv before any G1; this result does not warrant running 10M BUILD.
