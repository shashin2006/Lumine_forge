from pathlib import Path
from collections import Counter
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

FILES = {
    "train_source1": ROOT / "student_resource/dataset/train/train_source1.tsv",
    "train_source2": ROOT / "student_resource/dataset/train/train_source2.tsv",
    "train_source3": ROOT / "student_resource/dataset/train/train_source3.tsv",
    "ground_truth": ROOT / "student_resource/dataset/train/train_ground_truth.tsv",
    "test_source1": ROOT / "student_resource/dataset/test/test_source1.tsv",
    "test_source2": ROOT / "student_resource/dataset/test/test_source2.tsv",
    "test_source3": ROOT / "student_resource/dataset/test/test_source3.tsv",
}


def count_rows(path, chunk_size=100_000):
    total = 0

    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        chunksize=chunk_size,
    ):
        total += len(chunk)

    return total


def ground_truth_stats(path):
    total = 0
    singleton = 0
    matched = 0
    match_counts = Counter()

    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        chunksize=100_000,
    ):
        total += len(chunk)

        for value in chunk["matched_entity_ids"]:
            if not value.strip():
                singleton += 1
                match_counts[0] += 1
            else:
                ids = [x for x in value.split(",") if x]
                n = len(set(ids))
                matched += n
                match_counts[n] += 1

    return total, singleton, matched, match_counts


def main():
    print("=" * 80)
    print("DATASET ROW COUNTS")
    print("=" * 80)

    counts = {}

    for name, path in FILES.items():
        print(f"\nCounting {name} ...")
        counts[name] = count_rows(path)
        print(f"{name}: {counts[name]:,}")

    print("\n" + "=" * 80)
    print("GROUND TRUTH STATISTICS")
    print("=" * 80)

    total, singleton, total_matches, match_counts = ground_truth_stats(
        FILES["ground_truth"]
    )

    print(f"\nTotal S1 ground-truth rows : {total:,}")
    print(f"Singleton S1 entities      : {singleton:,}")
    print(f"Matched S1 entities        : {total - singleton:,}")
    print(f"Total positive links       : {total_matches:,}")

    if total:
        print(f"Singleton percentage       : {singleton / total * 100:.2f}%")

    print("\nNumber of matches per S1:")
    for n in sorted(match_counts):
        print(f"  {n:>4} matches : {match_counts[n]:,} S1 entities")

    print("\n" + "=" * 80)
    print("SOURCE SIZE RATIOS")
    print("=" * 80)

    s1 = counts["train_source1"]
    s2 = counts["train_source2"]
    s3 = counts["train_source3"]

    print(f"\nTrain S1 : {s1:,}")
    print(f"Train S2 : {s2:,}")
    print(f"Train S3 : {s3:,}")

    print(f"\nS2 / S1 : {s2 / s1:.2f}")
    print(f"S3 / S1 : {s3 / s1:.2f}")
    print(f"(S2+S3) / S1 : {(s2+s3) / s1:.2f}")


if __name__ == "__main__":
    main()