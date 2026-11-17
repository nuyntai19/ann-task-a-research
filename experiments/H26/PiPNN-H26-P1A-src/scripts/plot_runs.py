import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np


def _detect_format_and_find_header_line(file: str):
    """
    Returns (fmt, header_line_index) where:
      - fmt in {"new", "old"}
      - header_line_index is the 0-based line index where the data header begins
        (for new: line with "Num queries", for old: first line that looks like data).
    """
    with open(file, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    # Detect "new" format by explicit header marker.
    # The file may have quotes, so look for a substring.
    for i, line in enumerate(lines[:200]):  # scan early section only
        if "Num queries" in line:
            return "new", i

    # Otherwise treat as old (no explicit header rows).
    # Find first non-empty, non-comment-ish line that starts with a plausible data row.
    # Old rows: dataset, num_queries, target_recall, actual_recall, qps, ...
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # Heuristic: old data lines usually start with a dataset name (non-quoted)
        # and contain commas with numeric fields after.
        if "," in s and not s.startswith('"') and not s.lower().startswith("graph"):
            return "old", i

    # Fallback: old from start
    return "old", 0


def process_csv(file):
    """Read a CSV and return (recall, qps, cmps, visits) or None if unusable."""
    try:
        fmt, header_idx = _detect_format_and_find_header_line(file)

        if fmt == "new":
            # Read from the "Num queries, Target recall, ..." header line onward.
            # Use that header row as column names.
            df = pd.read_csv(
                file,
                header=0,
                skiprows=header_idx,
                engine="python",
            )

            # Normalize column names (strip quotes/whitespace)
            df.columns = [str(c).strip().strip('"') for c in df.columns]

            required = ["Actual recall", "QPS", "Average Cmps", "Average Visited"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                print(f"Skipping {file}: missing columns in new format: {missing}")
                return None

            # Coerce numeric and drop non-numeric rows (blank lines, etc.)
            for c in required:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=required)

            if df.empty:
                print(f"Skipping {file}: no numeric data rows found (new format)")
                return None

            filtered = df[df["Actual recall"] >= 0.8]
            if filtered.empty:
                print(f"Skipping {file}: no actual recall >= 0.8 (new format)")
                return None

            recall = filtered["Actual recall"].to_numpy()
            qps = filtered["QPS"].to_numpy()
            cmps = filtered["Average Cmps"].to_numpy()
            visits = filtered["Average Visited"].to_numpy()

        else:
            # Old format: no header; columns by position.
            # Start reading at first data line (header_idx) and treat all as data.
            df = pd.read_csv(
                file,
                header=None,
                skiprows=header_idx,
                engine="python",
            )

            if df.shape[1] < 8:
                print(f"Skipping {file}: less than 8 columns (old format)")
                return None

            # Coerce needed columns
            # Old indices: recall=3, qps=4, cmps=5, visits=7
            for col in [3, 4, 5, 7]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=[3, 4, 5, 7])

            if df.empty:
                print(f"Skipping {file}: no numeric data rows found (old format)")
                return None

            filtered = df[df[3] >= 0.8]  # recall >= 0.8
            if filtered.empty:
                print(f"Skipping {file}: no recall >= 0.8 (old format)")
                return None

            recall = filtered[3].to_numpy()
            qps = filtered[4].to_numpy()
            cmps = filtered[5].to_numpy()
            visits = filtered[7].to_numpy()

        order = np.argsort(recall)
        return (recall[order], qps[order], cmps[order], visits[order])

    except Exception as e:
        print(f"Error processing {file}: {e}")
        return None


def get_colors(n, scheme):
    if scheme == "redyellowgreen":
        colors = [mcolors.to_hex(c) for c in cm.get_cmap("RdYlGn")(np.linspace(0, 1, n))]
    elif scheme == "rainbow":
        colors = [mcolors.to_hex(c) for c in cm.get_cmap("rainbow")(np.linspace(1, 0, n))]
    else:
        base_colors = list(mcolors.TABLEAU_COLORS.values())
        colors = [base_colors[i % len(base_colors)] for i in range(n)]
    return colors


parser = argparse.ArgumentParser(description="Plot performance metrics from CSV files.")
parser.add_argument("-d", "--directory", type=str, required=False, default=None,
                    help="Directory containing .csv files.")
parser.add_argument("-o", "--output", type=str, required=False, default="output.png",
                    help="Output file name for the plot.")
parser.add_argument("-y", "--yaxis", type=str, required=False, choices=["qps", "cmps", "visits"], default="qps",
                    help="Y-axis metric to plot.")
parser.add_argument("-a", "--all", action="store_true",
                    help="Plot all available data series side-by-side. Overrides -y option.")
parser.add_argument("-c", "--color", type=str, required=False,
                    choices=["default", "redyellowgreen", "rainbow"], default="default",
                    help="Color scheme for the plots.")
args = parser.parse_args()

csv_data = []
if args.directory:
    dir_path = Path(args.directory)
    csv_files = sorted(dir_path.glob("*.csv"))
    for file_path in csv_files:
        csv_data.append({"path": str(file_path), "name": file_path.stem})
else:
    # Hardcode here if desired:
    # csv_data = [{"path": "path/to/file.csv", "name": "IndexName"}]
    pass

output_file = args.output
plot_type = args.yaxis.lower()

if not args.all and plot_type not in ["qps", "cmps", "visits"]:
    print("Invalid y-axis option. Use 'qps', 'cmps', or 'visits'.")
    exit(1)

series = []
for entry in csv_data:
    file = entry["path"]
    name = entry["name"]
    res = process_csv(file)
    if res is None:
        continue
    recall, qps, cmps, visits = res
    series.append({"name": name, "recall": recall, "qps": qps, "cmps": cmps, "visits": visits})

if len(series) == 0:
    print("No valid CSVs to plot.")
    exit(0)

colors = get_colors(len(series), args.color)
for s, color in zip(series, colors):
    s["color"] = color

if args.all:
    fig = plt.figure(figsize=(15, 5))
    gs = gridspec.GridSpec(2, 3, height_ratios=[0.15, 1.0], hspace=0.15, wspace=0.25)

    axes = [fig.add_subplot(gs[1, i]) for i in range(3)]
    titles = ["QPS", "Dist Comps", "Avg Visited"]
    ylabels = ["QPS (log scale)", "Dist Comps (log scale)", "Avg Visited (log scale)"]
    keys = ["qps", "cmps", "visits"]

    for ax, title, ylabel, key in zip(axes, titles, ylabels, keys):
        for s in series:
            ax.plot(s["recall"], s[key], marker='o', label=s["name"],
                    color=s["color"], linewidth=1, markersize=4)
        ax.set_xlabel("Recall")
        ax.set_ylabel(ylabel)
        ax.set_yscale("log")
        ax.set_title(title)
        ax.grid(True, which="both", linestyle="--")

    legend_ax = fig.add_subplot(gs[0, :])
    legend_ax.axis("off")

    handles, labels = axes[0].get_legend_handles_labels()
    legend = legend_ax.legend(
        handles, labels,
        loc="center",
        ncol=min(5, len(labels)),
        frameon=True,
        framealpha=0.9,
        facecolor="white",
        edgecolor="black",
        fontsize=9
    )
    legend.get_frame().set_linewidth(0.8)

    plt.savefig(output_file, dpi=300, bbox_inches="tight")
else:
    plt.figure(figsize=(10, 6))

    for s in series:
        match plot_type:
            case "qps":
                plt.plot(s["recall"], s["qps"], marker='o', label=s["name"], color=s["color"])
            case "cmps":
                plt.plot(s["recall"], s["cmps"], marker='o', label=s["name"], color=s["color"])
            case "visits":
                plt.plot(s["recall"], s["visits"], marker='o', label=s["name"], color=s["color"])

    plt.xlabel("Recall")
    match plot_type:
        case "qps":
            plt.ylabel("QPS (log scale)")
            plt.title("QPS vs Recall")
        case "cmps":
            plt.ylabel("Dist Comps (log scale)")
            plt.title("Dist Comps vs Recall")
        case "visits":
            plt.ylabel("Avg Visited (log scale)")
            plt.title("Avg Visited vs Recall")

    plt.yscale("log")
    plt.legend()
    plt.grid(True, which="both", linestyle="--")
    plt.savefig(output_file, dpi=300)