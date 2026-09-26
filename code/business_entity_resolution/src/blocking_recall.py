from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[3]

S1 = (ROOT / "student_resource/dataset/train/train_source1.tsv").as_posix()
S2 = (ROOT / "student_resource/dataset/train/train_source2.tsv").as_posix()
S3 = (ROOT / "student_resource/dataset/train/train_source3.tsv").as_posix()
GT = (ROOT / "student_resource/dataset/train/train_ground_truth.tsv").as_posix()


def normalize_sql(column):
    """
    SQL-side normalization.

    Keep Unicode characters intact.
    Remove punctuation/symbols by replacing non-alphanumeric
    Unicode characters with spaces where supported by DuckDB.
    """
    return f"""
        lower(
            regexp_replace(
                regexp_replace(
                    trim(coalesce({column}, '')),
                    '[^[:alnum:][:space:]]',
                    ' ',
                    'g'
                ),
                '[[:space:]]+',
                ' ',
                'g'
            )
        )
    """


def main():
    con = duckdb.connect()

    con.execute("PRAGMA threads=4;")

    print("=" * 80)
    print("BUILDING TEMPORARY SOURCE TABLES")
    print("=" * 80)

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE s1 AS
        SELECT
            entity_id,
            {normalize_sql("business_name")} AS name_norm,
            {normalize_sql("business_address")} AS address_norm,
            country
        FROM read_csv(
            '{S1}',
            delim='\\t',
            header=true,
            all_varchar=true
        );
    """)

    print("Loaded S1")

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE candidates AS
        SELECT
            entity_id,
            {normalize_sql("business_name")} AS name_norm,
            {normalize_sql("business_address")} AS address_norm,
            country
        FROM read_csv(
            '{S2}',
            delim='\\t',
            header=true,
            all_varchar=true
        )

        UNION ALL

        SELECT
            entity_id,
            {normalize_sql("business_name")} AS name_norm,
            {normalize_sql("business_address")} AS address_norm,
            country
        FROM read_csv(
            '{S3}',
            delim='\\t',
            header=true,
            all_varchar=true
        );
    """)

    print("Loaded S2 + S3")

    print("=" * 80)
    print("BUILDING GROUND TRUTH")
    print("=" * 80)

    # Turn the comma-separated ground truth into individual links.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE gt AS
        SELECT
            source1_entity_id,
            trim(matched_id) AS matched_entity_id
        FROM read_csv(
            '{GT}',
            delim='\\t',
            header=true,
            all_varchar=true
        ),
        unnest(
            CASE
                WHEN trim(matched_entity_ids) = ''
                THEN []
                ELSE string_split(matched_entity_ids, ',')
            END
        ) AS t(matched_id);
    """)

    total = con.execute("""
        SELECT COUNT(*)
        FROM gt;
    """).fetchone()[0]

    print(f"Total ground-truth links: {total:,}")

    print("\n" + "=" * 80)
    print("TEST 1: EXACT NORMALIZED NAME")
    print("=" * 80)

    name_result = con.execute("""
        SELECT COUNT(*)
        FROM gt g
        JOIN s1 a
            ON a.entity_id = g.source1_entity_id
        JOIN candidates b
            ON b.entity_id = g.matched_entity_id
        WHERE
            a.country = b.country
            AND a.name_norm <> ''
            AND a.name_norm = b.name_norm;
    """).fetchone()[0]

    print(f"Recovered links: {name_result:,}")
    print(f"Recall: {name_result / total:.6f}")

    print("\n" + "=" * 80)
    print("TEST 2: EXACT NORMALIZED ADDRESS")
    print("=" * 80)

    address_result = con.execute("""
        SELECT COUNT(*)
        FROM gt g
        JOIN s1 a
            ON a.entity_id = g.source1_entity_id
        JOIN candidates b
            ON b.entity_id = g.matched_entity_id
        WHERE
            a.country = b.country
            AND a.address_norm <> ''
            AND a.address_norm = b.address_norm;
    """).fetchone()[0]

    print(f"Recovered links: {address_result:,}")
    print(f"Recall: {address_result / total:.6f}")

    print("\n" + "=" * 80)
    print("TEST 3: EXACT NAME OR EXACT ADDRESS")
    print("=" * 80)

    either_result = con.execute("""
        SELECT COUNT(*)
        FROM gt g
        JOIN s1 a
            ON a.entity_id = g.source1_entity_id
        JOIN candidates b
            ON b.entity_id = g.matched_entity_id
        WHERE
            a.country = b.country
            AND (
                (
                    a.name_norm <> ''
                    AND a.name_norm = b.name_norm
                )
                OR
                (
                    a.address_norm <> ''
                    AND a.address_norm = b.address_norm
                )
            );
    """).fetchone()[0]

    print(f"Recovered links: {either_result:,}")
    print(f"Recall: {either_result / total:.6f}")

    print("\n" + "=" * 80)
    print("TEST 4: EXACT NAME OR ADDRESS, WITHOUT COUNTRY")
    print("=" * 80)

    either_no_country = con.execute("""
        SELECT COUNT(*)
        FROM gt g
        JOIN s1 a
            ON a.entity_id = g.source1_entity_id
        JOIN candidates b
            ON b.entity_id = g.matched_entity_id
        WHERE
            (
                (
                    a.name_norm <> ''
                    AND a.name_norm = b.name_norm
                )
                OR
                (
                    a.address_norm <> ''
                    AND a.address_norm = b.address_norm
                )
            );
    """).fetchone()[0]

    print(f"Recovered links: {either_no_country:,}")
    print(f"Recall: {either_no_country / total:.6f}")

    print("\nDone.")


if __name__ == "__main__":
    main()