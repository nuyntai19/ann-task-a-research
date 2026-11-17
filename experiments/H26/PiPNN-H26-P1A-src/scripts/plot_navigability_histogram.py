import csv

import matplotlib.pyplot as plt

# Path to the CSV file
csv_file = "../../output/beam_width_hist.csv"

bucket_edges = []
counts = []

# Read the histogram data from the CSV file
with open(csv_file, newline='') as f:
    reader = csv.reader(f)
    for row in reader:
        if len(row) != 2:
            continue
        bucket_edges.append(float(row[0]))
        counts.append(int(row[1]))

# Plot the histogram
plt.bar(bucket_edges, counts, width=bucket_edges[1] - bucket_edges[0], align='edge', edgecolor='black')
plt.xlabel('Beam Width')
plt.ylabel('Count')
plt.title('Beam Width Histogram')
plt.grid(axis='y', linestyle='--', alpha=0.7)

plt.tight_layout()
plt.savefig("../../output/beam_width_hist.png")

plt.yscale('log')
plt.savefig("../../output/beam_width_hist_log.png")