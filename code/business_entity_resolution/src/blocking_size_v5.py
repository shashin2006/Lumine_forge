import duckdb

S1 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source1.tsv"
S2 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source2.tsv"
S3 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source3.tsv"

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
# TOKENS
# ------------------------------------------------------------------

print("=" * 80)
print("CREATING TOKEN TABLES")
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
# TWO NAME TOKEN BLOCK
# ------------------------------------------------------------------

print("=" * 80)
print("TWO COMMON NAME TOKENS")
print("=" * 80)

name_two_count = con.execute("""
SELECT COUNT(*)
FROM (
    SELECT
        s.s1_id,
        c.candidate_id
    FROM s1_name_tokens s
    JOIN cand_name_tokens c
        ON s.country = c.country
       AND s.token = c.token
    GROUP BY
        s.s1_id,
        c.candidate_id
    HAVING COUNT(*) >= 2
)
""").fetchone()[0]

print(f"2-name-token candidates: {name_two_count:,}")

# ------------------------------------------------------------------
# TWO ADDRESS TOKEN BLOCK
# ------------------------------------------------------------------

print("=" * 80)
print("TWO COMMON ADDRESS TOKENS")
print("=" * 80)

address_two_count = con.execute("""
SELECT COUNT(*)
FROM (
    SELECT
        s.s1_id,
        c.candidate_id
    FROM s1_address_tokens s
    JOIN cand_address_tokens c
        ON s.country = c.country
       AND s.token = c.token
    GROUP BY
        s.s1_id,
        c.candidate_id
    HAVING COUNT(*) >= 2
)
""").fetchone()[0]

print(f"2-address-token candidates: {address_two_count:,}")

# ------------------------------------------------------------------
# NAME + ADDRESS TOKEN
# ------------------------------------------------------------------

print("=" * 80)
print("NAME TOKEN + ADDRESS TOKEN")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE name_pairs AS
SELECT
    s.s1_id,
    c.candidate_id
FROM s1_name_tokens s
JOIN cand_name_tokens c
    ON s.country = c.country
   AND s.token = c.token
GROUP BY
    s.s1_id,
    c.candidate_id
HAVING COUNT(*) >= 1
""")

con.execute("""
CREATE OR REPLACE TABLE address_pairs AS
SELECT
    s.s1_id,
    c.candidate_id
FROM s1_address_tokens s
JOIN cand_address_tokens c
    ON s.country = c.country
   AND s.token = c.token
GROUP BY
    s.s1_id,
    c.candidate_id
HAVING COUNT(*) >= 1
""")

name_address_count = con.execute("""
SELECT COUNT(*)
FROM name_pairs n
JOIN address_pairs a
    ON n.s1_id = a.s1_id
   AND n.candidate_id = a.candidate_id
""").fetchone()[0]

print(f"name+address candidates: {name_address_count:,}")

# ------------------------------------------------------------------
# EXACT NAME
# ------------------------------------------------------------------

print("=" * 80)
print("EXACT NAME")
print("=" * 80)

exact_name = con.execute("""
SELECT COUNT(*)
FROM s1_norm s
JOIN cand_norm c
    ON s.name_norm = c.name_norm
   AND s.country = c.country
WHERE s.name_norm <> ''
""").fetchone()[0]

print(f"Exact name candidates: {exact_name:,}")

# ------------------------------------------------------------------
# EXACT ADDRESS
# ------------------------------------------------------------------

print("=" * 80)
print("EXACT ADDRESS")
print("=" * 80)

exact_address = con.execute("""
SELECT COUNT(*)
FROM s1_norm s
JOIN cand_norm c
    ON s.address_norm = c.address_norm
   AND s.country = c.country
WHERE s.address_norm <> ''
""").fetchone()[0]

print(f"Exact address candidates: {exact_address:,}")

print()
print("=" * 80)
print("DONE")
print("=" * 80)