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

    # Don't use all CPU threads because you only have ~8 GB RAM.
    con.execute("PRAGMA threads=4;")

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

    # ------------------------------------------------------------------
    # Build derived blocking keys.
    # ------------------------------------------------------------------

    print("=" * 80)
    print("BUILDING BLOCKING KEYS")
    print("=" * 80)

    con.execute("""
        ALTER TABLE s1 ADD COLUMN name_first_token VARCHAR;
        ALTER TABLE s1 ADD COLUMN name_first2 VARCHAR;
        ALTER TABLE s1 ADD COLUMN name_first3 VARCHAR;
        ALTER TABLE s1 ADD COLUMN name_first4 VARCHAR;
        ALTER TABLE s1 ADD COLUMN name_last_token VARCHAR;
        ALTER TABLE s1 ADD COLUMN name_first_last VARCHAR;

        ALTER TABLE candidates ADD COLUMN name_first_token VARCHAR;
        ALTER TABLE candidates ADD COLUMN name_first2 VARCHAR;
        ALTER TABLE candidates ADD COLUMN name_first3 VARCHAR;
        ALTER TABLE candidates ADD COLUMN name_first4 VARCHAR;
        ALTER TABLE candidates ADD COLUMN name_last_token VARCHAR;
        ALTER TABLE candidates ADD COLUMN name_first_last VARCHAR;
    """)

    for table in ["s1", "candidates"]:

        con.execute(f"""
            UPDATE {table}
            SET
                name_first_token =
                    CASE
                        WHEN name_norm = '' THEN ''
                        ELSE split_part(name_norm, ' ', 1)
                    END,

                name_first2 =
                    CASE
                        WHEN length(name_norm) >= 2
                        THEN substr(name_norm, 1, 2)
                        ELSE name_norm
                    END,

                name_first3 =
                    CASE
                        WHEN length(name_norm) >= 3
                        THEN substr(name_norm, 1, 3)
                        ELSE name_norm
                    END,

                name_first4 =
                    CASE
                        WHEN length(name_norm) >= 4
                        THEN substr(name_norm, 1, 4)
                        ELSE name_norm
                    END,

                name_last_token =
                    CASE
                        WHEN name_norm = '' THEN ''
                        ELSE regexp_extract(
                            name_norm,
                            '([^ ]+)$',
                            1
                        )
                    END,

                name_first_last =
                    CASE
                        WHEN name_norm = '' THEN ''
                        WHEN strpos(name_norm, ' ') = 0
                        THEN name_norm
                        ELSE
                            split_part(name_norm, ' ', 1)
                            || ' '
                            || regexp_extract(
                                name_norm,
                                '([^ ]+)$',
                                1
                            )
                    END;
        """)

    # ------------------------------------------------------------------
    # Ground truth joined to actual records.
    #
    # This gives us ONE row per true link, not a huge candidate join.
    # ------------------------------------------------------------------

    print("=" * 80)
    print("JOINING TRUE LINKS")
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
            b.address_norm AS candidate_address,

            a.name_first_token AS s1_first_token,
            b.name_first_token AS candidate_first_token,

            a.name_first2 AS s1_first2,
            b.name_first2 AS candidate_first2,

            a.name_first3 AS s1_first3,
            b.name_first3 AS candidate_first3,

            a.name_first4 AS s1_first4,
            b.name_first4 AS candidate_first4,

            a.name_last_token AS s1_last_token,
            b.name_last_token AS candidate_last_token,

            a.name_first_last AS s1_first_last,
            b.name_first_last AS candidate_first_last

        FROM gt g

        JOIN s1 a
            ON a.entity_id = g.source1_entity_id

        JOIN candidates b
            ON b.entity_id = g.matched_entity_id;
    """)

    # ------------------------------------------------------------------
    # Evaluate a blocking rule.
    # ------------------------------------------------------------------

    rules = {
        "first 2 name characters":
            """
            s1_first2 <> ''
            AND s1_first2 = candidate_first2
            """,

        "first 3 name characters":
            """
            s1_first3 <> ''
            AND s1_first3 = candidate_first3
            """,

        "first 4 name characters":
            """
            s1_first4 <> ''
            AND s1_first4 = candidate_first4
            """,

        "first name token":
            """
            s1_first_token <> ''
            AND s1_first_token = candidate_first_token
            """,

        "last name token":
            """
            s1_last_token <> ''
            AND s1_last_token = candidate_last_token
            """,

        "first + last name token":
            """
            s1_first_last <> ''
            AND s1_first_last = candidate_first_last
            """,

        "first 3 name chars + country":
            """
            s1_country = candidate_country
            AND s1_first3 <> ''
            AND s1_first3 = candidate_first3
            """,

        "first 4 name chars + country":
            """
            s1_country = candidate_country
            AND s1_first4 <> ''
            AND s1_first4 = candidate_first4
            """,

        "first token + country":
            """
            s1_country = candidate_country
            AND s1_first_token <> ''
            AND s1_first_token = candidate_first_token
            """,

        "first+last token + country":
            """
            s1_country = candidate_country
            AND s1_first_last <> ''
            AND s1_first_last = candidate_first_last
            """,

        "exact name + country":
            """
            s1_country = candidate_country
            AND s1_name <> ''
            AND s1_name = candidate_name
            """,

        "exact address + country":
            """
            s1_country = candidate_country
            AND s1_address <> ''
            AND s1_address = candidate_address
            """,

        "exact name OR address":
            """
            (
                s1_name <> ''
                AND s1_name = candidate_name
            )
            OR
            (
                s1_address <> ''
                AND s1_address = candidate_address
            )
            """,

        "exact name OR address + country":
            """
            s1_country = candidate_country
            AND
            (
                (
                    s1_name <> ''
                    AND s1_name = candidate_name
                )
                OR
                (
                    s1_address <> ''
                    AND s1_address = candidate_address
                )
            )
            """,
    }

    print("\n" + "=" * 80)
    print("BLOCKING RECALL RESULTS")
    print("=" * 80)

    for description, condition in rules.items():

        query = f"""
            SELECT COUNT(*)
            FROM true_pairs
            WHERE {condition};
        """

        recovered = con.execute(query).fetchone()[0]

        recall = recovered / total

        print(
            f"{description:<40} "
            f"{recovered:>12,} "
            f"{recall:.6f}"
        )

    # ------------------------------------------------------------------
    # Combined rules.
    # ------------------------------------------------------------------

    combined_rules = {

        "first3 OR first_token":
            """
            (
                s1_first3 <> ''
                AND s1_first3 = candidate_first3
            )
            OR
            (
                s1_first_token <> ''
                AND s1_first_token = candidate_first_token
            )
            """,

        "first4 OR first_token":
            """
            (
                s1_first4 <> ''
                AND s1_first4 = candidate_first4
            )
            OR
            (
                s1_first_token <> ''
                AND s1_first_token = candidate_first_token
            )
            """,

        "first4 OR first_last":
            """
            (
                s1_first4 <> ''
                AND s1_first4 = candidate_first4
            )
            OR
            (
                s1_first_last <> ''
                AND s1_first_last = candidate_first_last
            )
            """,

        "first3 OR first_token OR exact address":
            """
            (
                s1_first3 <> ''
                AND s1_first3 = candidate_first3
            )
            OR
            (
                s1_first_token <> ''
                AND s1_first_token = candidate_first_token
            )
            OR
            (
                s1_address <> ''
                AND s1_address = candidate_address
            )
            """,

        "first4 OR first_token OR exact address":
            """
            (
                s1_first4 <> ''
                AND s1_first4 = candidate_first4
            )
            OR
            (
                s1_first_token <> ''
                AND s1_first_token = candidate_first_token
            )
            OR
            (
                s1_address <> ''
                AND s1_address = candidate_address
            )
            """,
    }

    print("\n" + "=" * 80)
    print("COMBINED BLOCKING RECALL")
    print("=" * 80)

    for description, condition in combined_rules.items():

        query = f"""
            SELECT COUNT(*)
            FROM true_pairs
            WHERE {condition};
        """

        recovered = con.execute(query).fetchone()[0]

        recall = recovered / total

        print(
            f"{description:<45} "
            f"{recovered:>12,} "
            f"{recall:.6f}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()