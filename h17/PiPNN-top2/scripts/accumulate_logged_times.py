import argparse
import re

def main():
    parser = argparse.ArgumentParser(description="Sum logged time values from the last detected run in a log file.")
    parser.add_argument("logfile", help="Path to the log file")
    args = parser.parse_args()

    last_detected_index = -1
    lines = []

    with open(args.logfile, "r") as f:
        for i, line in enumerate(f):
            lines.append(line)
            if line.startswith("Data: detected"):
                last_detected_index = i
    if last_detected_index == -1:
        print("No logged run detected.")
        return

    first_level_pattern = re.compile(r"Parlay time: first level assign time:\s*([0-9.]+)")
    buckets_pattern = re.compile(r"Parlay time: buckets time:\s*([0-9.]+)")
    leaf_pattern = re.compile(r"Parlay time: build leaf time:\s*([0-9.]+)")
    prune_pattern = re.compile(r"Parlay time: Final prune time:\s*([0-9.]+)")

    simhash_construct_pattern = re.compile(r"Parlay time: SimHash constructed time:\s*([0-9.]+)")
    hashed_points_pattern = re.compile(r"Parlay time: Hashed points time:\s*([0-9.]+)")
    sorted_hash_values_pattern = re.compile(r"Parlay time: Sorted hash values time:\s*([0-9.]+)")
    created_buckets_pattern = re.compile(r"Parlay time: Created buckets time:\s*([0-9.]+)")

    total_buckets = 0.0
    total_leaf = 0.0
    total_prune = 0.0
    for line in lines[last_detected_index+1:]:
        match = first_level_pattern.search(line)
        if match:
            total_buckets += float(match.group(1))
        match = buckets_pattern.search(line)
        if match:
            total_buckets += float(match.group(1))
        match = leaf_pattern.search(line)
        if match:
            total_leaf += float(match.group(1))
        match = prune_pattern.search(line)
        if match:
            total_prune += float(match.group(1))
        match = simhash_construct_pattern.search(line)
        if match:
            total_buckets += float(match.group(1))
        match = hashed_points_pattern.search(line)
        if match:
            total_buckets += float(match.group(1))
        match = sorted_hash_values_pattern.search(line)
        if match:
            total_buckets += float(match.group(1))
        match = created_buckets_pattern.search(line)
        if match:
            total_buckets += float(match.group(1))

    print(f"Total buckets time: {total_buckets}")
    print(f"Total leaf time: {total_leaf}")
    print(f"Final prune time: {total_prune}")

if __name__ == "__main__":
    main()
