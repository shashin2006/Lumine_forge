from pathlib import Path
from collections import Counter
import pandas as pd

from normalization import normalize_name, normalize_address


ROOT = Path(__file__).resolve().parents[3]

FILES = [
    ROOT / "student_resource/dataset/train/train_source2.tsv",
    ROOT / "student_resource/dataset/train/train_source3.tsv",
]


def process_file(path, name_counter, address_counter, country_counter):
    print(f"\nProcessing: {path.name}")

    rows = 0

    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        chunksize=50_000,
    ):
        rows += len(chunk)

        # Normalize names.
        names = chunk["business_name"].map(normalize_name)

        # Normalize addresses.
        addresses = chunk["business_address"].map(normalize_address)

        name_counter.update(names)
        address_counter.update(addresses)
        country_counter.update(chunk["country"])

        if rows % 500_000 == 0:
            print(f"  processed: {rows:,}")

    print(f"  finished: {rows:,} rows")


def summarize(counter, title):
    total = sum(counter.values())
    unique = len(counter)

    duplicate_records = sum(
        count
        for count in counter.values()
        if count > 1
    )

    duplicate_keys = sum(
        1
        for count in counter.values()
        if count > 1
    )

    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

    print(f"Total records       : {total:,}")
    print(f"Unique keys         : {unique:,}")
    print(f"Duplicate keys      : {duplicate_keys:,}")
    print(f"Records in duplicate groups : {duplicate_records:,}")

    if total:
        print(
            f"Unique-key ratio    : {unique / total * 100:.2f}%"
        )

    print("\nTop 30 most frequent keys:")

    for key, count in counter.most_common(30):
        display_key = key if key else "<EMPTY>"
        print(f"{count:>8,}  {display_key[:100]}")


def main():
    name_counter = Counter()
    address_counter = Counter()
    country_counter = Counter()

    for path in FILES:
        process_file(
            path,
            name_counter,
            address_counter,
            country_counter,
        )

    summarize(
        name_counter,
        "NORMALIZED BUSINESS NAME STATISTICS",
    )

    summarize(
        address_counter,
        "NORMALIZED ADDRESS STATISTICS",
    )

    print("\n" + "=" * 80)
    print("COUNTRY STATISTICS")
    print("=" * 80)

    total_countries = sum(country_counter.values())

    for country, count in country_counter.most_common():
        print(
            f"{country:20} {count:>10,} "
            f"({count / total_countries * 100:.2f}%)"
        )


if __name__ == "__main__":
    main()