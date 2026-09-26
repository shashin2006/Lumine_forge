from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[3]

S1 = (ROOT / "student_resource/dataset/train/train_source1.tsv").as_posix()
S2 = (ROOT / "student_resource/dataset/train/train_source2.tsv").as_posix()
S3 = (ROOT / "student_resource/dataset/train/train_source3.tsv").as_posix()
GT = (ROOT / "student_resource/dataset/train/train_ground_truth.tsv").as_posix()


def norm(column):
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

    # ---------------------------------------------------------------
    # S1
    # ---------------------------------------------------------------

    print("=" * 80)
    print("LOADING S1")
    print("=" * 80)

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE s1 AS
        SELECT
            entity_id,
            country,
            {norm("business_name")} AS name_norm,
            {norm("business_address")} AS address_norm
        FROM read_csv(
            '{S1}',
            delim='\\t',
            header=true,
            all_varchar=true
        );
    """)

    print("S1 loaded.")

    # ---------------------------------------------------------------
    # S2 + S3
    # ---------------------------------------------------------------

    print("=" * 80)
    print("LOADING S2 + S3")
    print("=" * 80)

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE candidates AS

        SELECT
            entity_id,
            country,
            {norm("business_name")} AS name_norm,
            {norm("business_address")} AS address_norm
        FROM read_csv(
            '{S2}',
            delim='\\t',
            header=true,
            all_varchar=true
        )

        UNION ALL

        SELECT
            entity_id,
            country,
            {norm("business_name")} AS name_norm,
            {norm("business_address")} AS address_norm
        FROM read_csv(
            '{S3}',
            delim='\\t',
            header=true,
            all_varchar=true
        );
    """)

    print("S2 + S3 loaded.")

    # ---------------------------------------------------------------
    # Ground truth
    # ---------------------------------------------------------------

    print("=" * 80)
    print("LOADING GROUND TRUTH")
    print("=" * 80)

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

    print(f"Ground-truth links: {total:,}")

    # ---------------------------------------------------------------
    # Join true pairs.
    # ---------------------------------------------------------------

    print("=" * 80)
    print("BUILDING TRUE PAIRS")
    print("=" * 80)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE true_pairs AS

        SELECT
            g.source1_entity_id,
            g.matched_entity_id,

            a.country AS s1_country,
            b.country AS candidate_country,

            a.name_norm AS s1_name,
            b.name_norm AS candidate_name,

            a.address_norm AS s1_address,
            b.address_norm AS candidate_address

        FROM gt g

        JOIN s1 a
            ON a.entity_id = g.source1_entity_id

        JOIN candidates b
            ON b.entity_id = g.matched_entity_id;
    """)

    # ---------------------------------------------------------------
    # Create token lists.
    #
    # We remove very short tokens for the token experiment.
    # ---------------------------------------------------------------

    print("=" * 80)
    print("CREATING TOKEN LISTS")
    print("=" * 80)

    con.execute("""
        ALTER TABLE true_pairs ADD COLUMN s1_name_tokens VARCHAR[];
        ALTER TABLE true_pairs ADD COLUMN candidate_name_tokens VARCHAR[];
        ALTER TABLE true_pairs ADD COLUMN s1_address_tokens VARCHAR[];
        ALTER TABLE true_pairs ADD COLUMN candidate_address_tokens VARCHAR[];
    """)

    con.execute("""
        UPDATE true_pairs
        SET
            s1_name_tokens =
                list_filter(
                    string_split(s1_name, ' '),
                    lambda x: length(x) >= 3
                ),

            candidate_name_tokens =
                list_filter(
                    string_split(candidate_name, ' '),
                    lambda x: length(x) >= 3
                ),

            s1_address_tokens =
                list_filter(
                    string_split(s1_address, ' '),
                    lambda x: length(x) >= 2
                ),

            candidate_address_tokens =
                list_filter(
                    string_split(candidate_address, ' '),
                    lambda x: length(x) >= 2
                );
    """)

    # ---------------------------------------------------------------
    # Measure overlap.
    # ---------------------------------------------------------------

    print("=" * 80)
    print("CALCULATING TOKEN OVERLAP")
    print("=" * 80)

    con.execute("""
        ALTER TABLE true_pairs ADD COLUMN common_name_tokens INTEGER;
        ALTER TABLE true_pairs ADD COLUMN common_address_tokens INTEGER;
    """)

    con.execute("""
        UPDATE true_pairs
        SET
            common_name_tokens =
                length(
                    list_intersect(
                        s1_name_tokens,
                        candidate_name_tokens
                    )
                ),

            common_address_tokens =
                length(
                    list_intersect(
                        s1_address_tokens,
                        candidate_address_tokens
                    )
                );
    """)

    # ---------------------------------------------------------------
    # Evaluate basic token rules.
    # ---------------------------------------------------------------

    rules = {

        ">=1 common name token":
            "common_name_tokens >= 1",

        ">=2 common name tokens":
            "common_name_tokens >= 2",

        ">=3 common name tokens":
            "common_name_tokens >= 3",

        ">=1 common address token":
            "common_address_tokens >= 1",

        ">=2 common address tokens":
            "common_address_tokens >= 2",

        ">=3 common address tokens":
            "common_address_tokens >= 3",

        "name OR address token":
            """
            common_name_tokens >= 1
            OR common_address_tokens >= 1
            """,

        "2 name OR 2 address tokens":
            """
            common_name_tokens >= 2
            OR common_address_tokens >= 2
            """,

        "name >=1 AND address >=1":
            """
            common_name_tokens >= 1
            AND common_address_tokens >= 1
            """,

        "name >=2 AND address >=1":
            """
            common_name_tokens >= 2
            AND common_address_tokens >= 1
            """,
    }

    print("\n" + "=" * 80)
    print("TOKEN BLOCKING RECALL")
    print("=" * 80)

    for description, condition in rules.items():

        recovered = con.execute(f"""
            SELECT COUNT(*)
            FROM true_pairs
            WHERE {condition};
        """).fetchone()[0]

        recall = recovered / total

        print(
            f"{description:<40}"
            f"{recovered:>12,} "
            f"{recall:.6f}"
        )

    # ---------------------------------------------------------------
    # Combined with prefix.
    # ---------------------------------------------------------------

    combined = {

        "prefix2 OR name token":
            """
            (
                length(s1_name) >= 2
                AND substr(s1_name, 1, 2)
                    = substr(candidate_name, 1, 2)
            )
            OR common_name_tokens >= 1
            """,

        "prefix3 OR name token":
            """
            (
                length(s1_name) >= 3
                AND substr(s1_name, 1, 3)
                    = substr(candidate_name, 1, 3)
            )
            OR common_name_tokens >= 1
            """,

        "prefix2 OR name/address token":
            """
            (
                length(s1_name) >= 2
                AND substr(s1_name, 1, 2)
                    = substr(candidate_name, 1, 2)
            )
            OR common_name_tokens >= 1
            OR common_address_tokens >= 1
            """,

        "prefix3 OR name/address token":
            """
            (
                length(s1_name) >= 3
                AND substr(s1_name, 1, 3)
                    = substr(candidate_name, 1, 3)
            )
            OR common_name_tokens >= 1
            OR common_address_tokens >= 1
            """,

        "prefix2 OR 2 name tokens OR address":
            """
            (
                length(s1_name) >= 2
                AND substr(s1_name, 1, 2)
                    = substr(candidate_name, 1, 2)
            )
            OR common_name_tokens >= 2
            OR common_address_tokens >= 1
            """,
    }

    print("\n" + "=" * 80)
    print("COMBINED TOKEN + PREFIX RECALL")
    print("=" * 80)

    for description, condition in combined.items():

        recovered = con.execute(f"""
            SELECT COUNT(*)
            FROM true_pairs
            WHERE {condition};
        """).fetchone()[0]

        recall = recovered / total

        print(
            f"{description:<45}"
            f"{recovered:>12,} "
            f"{recall:.6f}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()