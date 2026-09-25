from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

FILES = [
    ROOT / "student_resource/dataset/train/train_source1.tsv",
    ROOT / "student_resource/dataset/train/train_source2.tsv",
    ROOT / "student_resource/dataset/train/train_source3.tsv",
    ROOT / "student_resource/dataset/train/train_ground_truth.tsv",
    ROOT / "student_resource/dataset/test/test_source1.tsv",
    ROOT / "student_resource/dataset/test/test_source2.tsv",
    ROOT / "student_resource/dataset/test/test_source3.tsv",
]


def inspect_file(path):
    print("\n" + "=" * 80)
    print(path)
    print("=" * 80)

    # Read only a small sample.
    df = pd.read_csv(
        path,
        sep="\t",
        nrows=10_000,
        dtype=str,
        keep_default_na=False,
    )

    print("Columns:")
    for column in df.columns:
        print(f"  - {column}")

    print("\nShape of sample:", df.shape)

    print("\nFirst 3 rows:")
    print(df.head(3).to_string(index=False))

    print("\nMissing/empty values:")
    for column in df.columns:
        empty = (df[column].str.strip() == "").sum()
        print(f"  {column}: {empty:,} / {len(df):,}")

    if "country" in df.columns:
        print("\nCountry distribution in sample:")
        print(df["country"].value_counts().head(20).to_string())

    if "business_name" in df.columns:
        print("\nBusiness name length:")
        lengths = df["business_name"].str.len()
        print(lengths.describe().to_string())

    if "business_address" in df.columns:
        print("\nBusiness address length:")
        lengths = df["business_address"].str.len()
        print(lengths.describe().to_string())


def main():
    for path in FILES:
        if not path.exists():
            print(f"WARNING: File does not exist: {path}")
            continue

        inspect_file(path)


if __name__ == "__main__":
    main()