import duckdb

S1 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source1.tsv"
S2 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source2.tsv"
S3 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source3.tsv"
GT = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_ground_truth.tsv"

con = duckdb.connect()

con.execute("SET memory_limit='5GB'")
con.execute("SET threads=2")
con.execute("SET preserve_insertion_order=false")

print("=" * 80)
print("LOADING")
print("=" * 80)

con.execute(f"""
CREATE OR REPLACE TABLE s1 AS
SELECT
    entity_id AS s1_id,
    business_name,
    business_address,
    country
FROM read_csv_auto(
    '{S1}',
    delim='\\t',
    header=true
)
""")

con.execute(f"""
CREATE OR REPLACE TABLE candidates AS

SELECT
    entity_id AS candidate_id,
    business_name,
    business_address,
    country
FROM read_csv_auto(
    '{S2}',
    delim='\\t',
    header=true
)

UNION ALL

SELECT
    entity_id AS candidate_id,
    business_name,
    business_address,
    country
FROM read_csv_auto(
    '{S3}',
    delim='\\t',
    header=true
)
""")

con.execute(f"""
CREATE OR REPLACE TABLE gt AS
SELECT
    source1_entity_id AS s1_id,
    matched_entity_ids
FROM read_csv_auto(
    '{GT}',
    delim='\\t',
    header=true
)
""")

# ------------------------------------------------------------------
# NORMALIZE
# ------------------------------------------------------------------

print("=" * 80)
print("NORMALIZING")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE s1_norm AS
SELECT
    s1_id,
    country,

    lower(
        regexp_replace(
            regexp_replace(
                coalesce(business_name, ''),
                '[^\\p{L}\\p{N}\\s]',
                ' ',
                'g'
            ),
            '\\s+',
            ' ',
            'g'
        )
    ) AS name_norm,

    lower(
        regexp_replace(
            regexp_replace(
                coalesce(business_address, ''),
                '[^\\p{L}\\p{N}\\s]',
                ' ',
                'g'
            ),
            '\\s+',
            ' ',
            'g'
        )
    ) AS address_norm

FROM s1
""")

con.execute("""
CREATE OR REPLACE TABLE cand_norm AS
SELECT
    candidate_id,
    country,

    lower(
        regexp_replace(
            regexp_replace(
                coalesce(business_name, ''),
                '[^\\p{L}\\p{N}\\s]',
                ' ',
                'g'
            ),
            '\\s+',
            ' ',
            'g'
        )
    ) AS name_norm,

    lower(
        regexp_replace(
            regexp_replace(
                coalesce(business_address, ''),
                '[^\\p{L}\\p{N}\\s]',
                ' ',
                'g'
            ),
            '\\s+',
            ' ',
            'g'
        )
    ) AS address_norm

FROM candidates
""")

# ------------------------------------------------------------------
# GROUND TRUTH PAIRS
# ------------------------------------------------------------------

print("=" * 80)
print("BUILDING GROUND TRUTH PAIRS")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE true_pairs AS
SELECT
    g.s1_id,
    trim(x) AS candidate_id
FROM gt g,
UNNEST(
    CASE
        WHEN matched_entity_ids IS NULL
          OR trim(matched_entity_ids) = ''
        THEN []
        ELSE string_split(matched_entity_ids, ',')
    END
) t(x)
WHERE trim(x) <> ''
""")

total_true = con.execute("""
SELECT COUNT(*)
FROM true_pairs
""").fetchone()[0]

print(f"True links: {total_true:,}")

# ------------------------------------------------------------------
# TOKEN TABLES
# ------------------------------------------------------------------

print("=" * 80)
print("CREATING TOKENS")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE s1_name_tokens AS
SELECT DISTINCT
    s1_id,
    country,
    token
FROM (
    SELECT
        s1_id,
        country,
        unnest(
            list_filter(
                string_split(name_norm, ' '),
                x -> length(x) >= 3
            )
        ) AS token
    FROM s1_norm
)
WHERE token <> ''
""")

con.execute("""
CREATE OR REPLACE TABLE cand_name_tokens AS
SELECT DISTINCT
    candidate_id,
    country,
    token
FROM (
    SELECT
        candidate_id,
        country,
        unnest(
            list_filter(
                string_split(name_norm, ' '),
                x -> length(x) >= 3
            )
        ) AS token
    FROM cand_norm
)
WHERE token <> ''
""")

con.execute("""
CREATE OR REPLACE TABLE s1_address_tokens AS
SELECT DISTINCT
    s1_id,
    country,
    token
FROM (
    SELECT
        s1_id,
        country,
        unnest(
            list_filter(
                string_split(address_norm, ' '),
                x -> length(x) >= 2
            )
        ) AS token
    FROM s1_norm
)
WHERE token <> ''
""")

con.execute("""
CREATE OR REPLACE TABLE cand_address_tokens AS
SELECT DISTINCT
    candidate_id,
    country,
    token
FROM (
    SELECT
        candidate_id,
        country,
        unnest(
            list_filter(
                string_split(address_norm, ' '),
                x -> length(x) >= 2
            )
        ) AS token
    FROM cand_norm
)
WHERE token <> ''
""")

# ------------------------------------------------------------------
# FREQUENCIES
# ------------------------------------------------------------------

con.execute("""
CREATE OR REPLACE TABLE name_freq AS
SELECT
    country,
    token,
    COUNT(*) AS df
FROM cand_name_tokens
GROUP BY country, token
""")

con.execute("""
CREATE OR REPLACE TABLE address_freq AS
SELECT
    country,
    token,
    COUNT(*) AS df
FROM cand_address_tokens
GROUP BY country, token
""")

# ------------------------------------------------------------------
# EVALUATION FUNCTION
# ------------------------------------------------------------------

def evaluate(label, condition):
    print()
    print(f"Testing: {label}")

    query = f"""
    SELECT COUNT(*)
    FROM true_pairs tp
    JOIN s1_name_tokens sn
        ON sn.s1_id = tp.s1_id
    JOIN cand_name_tokens cn
        ON cn.candidate_id = tp.candidate_id
       AND cn.country = sn.country
       AND cn.token = sn.token
    JOIN name_freq nf
        ON nf.country = cn.country
       AND nf.token = cn.token
    WHERE {condition}
    """

    # DISTINCT because a true pair can share multiple tokens.
    query = f"""
    SELECT COUNT(*)
    FROM (
        SELECT DISTINCT
            tp.s1_id,
            tp.candidate_id
        FROM true_pairs tp
        JOIN s1_name_tokens sn
            ON sn.s1_id = tp.s1_id
        JOIN cand_name_tokens cn
            ON cn.candidate_id = tp.candidate_id
           AND cn.country = sn.country
           AND cn.token = sn.token
        JOIN name_freq nf
            ON nf.country = cn.country
           AND nf.token = cn.token
        WHERE {condition}
    )
    """

    count = con.execute(query).fetchone()[0]

    recall = count / total_true

    print(f"Recovered: {count:,}")
    print(f"Recall:    {recall:.6f}")

    return count, recall


# ------------------------------------------------------------------
# NAME RARE TOKEN
# ------------------------------------------------------------------

print()
print("=" * 80)
print("RARE NAME TOKEN RECALL")
print("=" * 80)

for limit in [10, 20, 50, 100]:

    count, recall = evaluate(
        f"name token df <= {limit}",
        f"nf.df <= {limit}"
    )

# ------------------------------------------------------------------
# ADDRESS RARE TOKEN
# ------------------------------------------------------------------

def evaluate_address(label, condition):

    print()
    print(f"Testing: {label}")

    query = f"""
    SELECT COUNT(*)
    FROM (
        SELECT DISTINCT
            tp.s1_id,
            tp.candidate_id
        FROM true_pairs tp
        JOIN s1_address_tokens sa
            ON sa.s1_id = tp.s1_id
        JOIN cand_address_tokens ca
            ON ca.candidate_id = tp.candidate_id
           AND ca.country = sa.country
           AND ca.token = sa.token
        JOIN address_freq af
            ON af.country = ca.country
           AND af.token = ca.token
        WHERE {condition}
    )
    """

    count = con.execute(query).fetchone()[0]

    recall = count / total_true

    print(f"Recovered: {count:,}")
    print(f"Recall:    {recall:.6f}")

    return count, recall


print()
print("=" * 80)
print("RARE ADDRESS TOKEN RECALL")
print("=" * 80)

for limit in [10, 20, 50, 100]:

    count, recall = evaluate_address(
        f"address token df <= {limit}",
        f"af.df <= {limit}"
    )

print()
print("=" * 80)
print("DONE")
print("=" * 80)