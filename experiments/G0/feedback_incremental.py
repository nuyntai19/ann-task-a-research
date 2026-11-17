import csv
import json
import runpy
from pathlib import Path

import numpy as np

ROOT = Path.home() / "ann-task-a"
SOURCE = ROOT / "experiments/G0/probe_feedback.py"
OUT = ROOT / "experiments/G0/results"

if not SOURCE.is_file():
    raise SystemExit(f"Missing file: {SOURCE}")

print("===== REPLAY G0.2A =====", flush=True)

state = runpy.run_path(str(SOURCE))

X = state["X"]
y = np.asarray(state["y"], dtype=np.int32)
indices = np.asarray(state["indices"])
recalls = np.asarray(state["recalls"])

n_dev = int(state["N_DEV"])
n_val = int(state["N_VAL"])

assert len(X) == len(y) == len(indices)
assert len(y) == n_dev + n_val

feature_names = [
    "best_distance",
    "frontier_gap",
    "stall_fraction",
    "degree_deficit",
    "late_progress",
]

raw = np.asarray(
    [
        [row[name] for name in feature_names]
        for row in X
    ],
    dtype=np.float64,
)

if not np.isfinite(raw).all():
    raise ValueError("Non-finite feature values")

OUT.mkdir(parents=True, exist_ok=True)

# Save per-query measurements for future analysis.
csv_path = OUT / "feedback_per_query.csv"

with csv_path.open(
    "w", newline="", encoding="utf-8"
) as file:

    writer = csv.writer(file)

    writer.writerow([
        "split",
        "query_id",
        "failure",
        "recall",
        *feature_names,
    ])

    for i in range(len(X)):
        writer.writerow([
            "DEV" if i < n_dev else "VALIDATION",
            int(indices[i]),
            int(y[i]),
            float(recalls[i]),
            *raw[i].tolist(),
        ])

# Normalize using DEV statistics only.
mu = raw[:n_dev].mean(axis=0)
sigma = raw[:n_dev].std(axis=0)

sigma = np.where(sigma > 1e-12, sigma, 1.0)

z = np.clip((raw - mu) / sigma, -10.0, 10.0)


def auc(scores, labels):
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int32)

    positive = scores[labels == 1]
    negative = np.sort(scores[labels == 0])

    if not len(positive) or not len(negative):
        return float("nan")

    left = np.searchsorted(
        negative, positive, side="left"
    )
    right = np.searchsorted(
        negative, positive, side="right"
    )

    return float(
        np.mean(
            (left + 0.5 * (right - left))
            / len(negative)
        )
    )


def fit_logistic(features, labels):
    a = np.column_stack([
        np.ones(len(features)),
        features,
    ])

    beta = np.zeros(a.shape[1], dtype=np.float64)

    # L2 penalty; do not penalize intercept.
    penalty = np.eye(len(beta))
    penalty[0, 0] = 0.0

    for _ in range(35):
        logits = np.clip(a @ beta, -30, 30)
        probabilities = 1 / (1 + np.exp(-logits))

        weights = probabilities * (1 - probabilities)

        gradient = (
            a.T @ (probabilities - labels)
            + penalty @ beta
        )

        hessian = (
            (a.T * weights) @ a
            + penalty
        )

        delta = np.linalg.solve(
            hessian, gradient
        )

        beta -= delta

        if np.max(np.abs(delta)) < 1e-7:
            break

    return beta


def predict(features, columns, beta):
    a = np.column_stack([
        np.ones(len(features)),
        features[:, columns],
    ])

    # Logits preserve AUROC ranking.
    return a @ beta


models = {
    "distance_only": [0],
    "frontier_only": [1],
    "distance_plus_frontier": [0, 1],
    "distance_plus_frontier_stall": [0, 1, 2],
    "all_five": [0, 1, 2, 3, 4],
}

scores = {}
results = {}

print("\n===== G0.2B VALIDATION AUROC =====")

for name, columns in models.items():
    beta = fit_logistic(
        z[:n_dev, columns],
        y[:n_dev],
    )

    score = predict(
        z[n_dev:],
        columns,
        beta,
    )

    scores[name] = score
    results[name] = auc(
        score,
        y[n_dev:],
    )

    print(f"{name:34s} {results[name]:.5f}")

# Bootstrap the paired difference in validation AUROC.
rng = np.random.default_rng(20261023)

deltas = []

for _ in range(2000):
    selection = rng.integers(
        0, n_val, size=n_val
    )

    labels = y[n_dev:][selection]

    if labels.min() == labels.max():
        continue

    baseline_auc = auc(
        scores["distance_only"][selection],
        labels,
    )

    combined_auc = auc(
        scores["distance_plus_frontier"][selection],
        labels,
    )

    deltas.append(combined_auc - baseline_auc)

delta = (
    results["distance_plus_frontier"]
    - results["distance_only"]
)

ci = np.percentile(
    deltas, [2.5, 97.5]
).tolist()

summary = {
    "experiment": "G0.2B incremental prediction",
    "n_dev": n_dev,
    "n_validation": n_val,
    "validation_failures": int(y[n_dev:].sum()),
    "validation_auc": results,
    "delta_auc_frontier_over_distance": delta,
    "delta_auc_bootstrap_95pct_ci": ci,
    "bootstrap_samples": len(deltas),
    "note": "Surrogate query-level analysis, not block-level refinement evidence",
}

output = OUT / "feedback_incremental.json"

output.write_text(
    json.dumps(summary, indent=2),
    encoding="utf-8",
)

print("\n===== PRIMARY COMPARISON =====")

print(f"Delta AUROC (+frontier): {delta:+.5f}")
print(f"Bootstrap 95% CI: [{ci[0]:+.5f}, {ci[1]:+.5f}]")

print("\nSaved:", output)
print("Per-query data:", csv_path)
print("G0.2B COMPLETE")
