import duckdb

S1 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source1.tsv"
S2 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source2.tsv"
S3 = r"C:\Lumine_Forge_Submission\student_resource\dataset\train\train_source3.tsv"

con = duckdb.connect()

# VERY IMPORTANT for your 7.7 GB machine
con.execute("SET memory_limit='5GB'")
con.execute("SET threads=2")
con.execute("SET preserve_insertion_order=false")

print("=" * 80)
print("LOADING DATA")
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
    country,
    'S2' AS source
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
    country,
    'S3' AS source
FROM read_csv_auto(
    '{S3}',
    delim='\\t',
    header=true
)
""")

print("Loaded.")

# ------------------------------------------------------------------
# NORMALIZATION
# ------------------------------------------------------------------

print("=" * 80)
print("NORMALIZING")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE s1_blocks AS
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
CREATE OR REPLACE TABLE cand_blocks AS
SELECT
    candidate_id,
    source,
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

print("Normalized.")

# ------------------------------------------------------------------
# PREFIX
# ------------------------------------------------------------------

print("=" * 80)
print("PREFIX-2 CANDIDATE COUNT")
print("=" * 80)

prefix_count = con.execute("""
SELECT COUNT(*)
FROM s1_blocks s
JOIN cand_blocks c
    ON substr(s.name_norm, 1, 2) = substr(c.name_norm, 1, 2)
   AND s.country = c.country
WHERE substr(s.name_norm, 1, 2) <> ''
""").fetchone()[0]

print(f"Prefix-2 pairs: {prefix_count:,}")

# ------------------------------------------------------------------
# EXACT NAME
# ------------------------------------------------------------------

print("=" * 80)
print("EXACT NAME CANDIDATE COUNT")
print("=" * 80)

exact_name = con.execute("""
SELECT COUNT(*)
FROM s1_blocks s
JOIN cand_blocks c
    ON s.name_norm = c.name_norm
   AND s.country = c.country
WHERE s.name_norm <> ''
""").fetchone()[0]

print(f"Exact-name pairs: {exact_name:,}")

# ------------------------------------------------------------------
# EXACT ADDRESS
# ------------------------------------------------------------------

print("=" * 80)
print("EXACT ADDRESS CANDIDATE COUNT")
print("=" * 80)

exact_address = con.execute("""
SELECT COUNT(*)
FROM s1_blocks s
JOIN cand_blocks c
    ON s.address_norm = c.address_norm
   AND s.country = c.country
WHERE s.address_norm <> ''
""").fetchone()[0]

print(f"Exact-address pairs: {exact_address:,}")

# ------------------------------------------------------------------
# TOKEN FREQUENCY
# ------------------------------------------------------------------

print("=" * 80)
print("BUILDING TOKEN FREQUENCIES")
print("=" * 80)

# We DON'T create all S1 x candidate token pairs.
# Instead, calculate candidate-side token frequencies.

con.execute("""
CREATE OR REPLACE TABLE candidate_name_tokens AS
SELECT DISTINCT
    candidate_id,
    country,
    unnest(
        list_filter(
            string_split(name_norm, ' '),
            x -> length(x) >= 3
        )
    ) AS token
FROM cand_blocks
WHERE name_norm <> ''
""")

con.execute("""
CREATE OR REPLACE TABLE candidate_address_tokens AS
SELECT DISTINCT
    candidate_id,
    country,
    unnest(
        list_filter(
            string_split(address_norm, ' '),
            x -> length(x) >= 2
        )
    ) AS token
FROM cand_blocks
WHERE address_norm <> ''
""")

print("Calculating frequencies...")

con.execute("""
CREATE OR REPLACE TABLE name_token_freq AS
SELECT
    country,
    token,
    COUNT(*) AS df
FROM candidate_name_tokens
GROUP BY country, token
""")

con.execute("""
CREATE OR REPLACE TABLE address_token_freq AS
SELECT
    country,
    token,
    COUNT(*) AS df
FROM candidate_address_tokens
GROUP BY country, token
""")

# ------------------------------------------------------------------
# TOKEN FREQUENCY DISTRIBUTION
# ------------------------------------------------------------------

print("=" * 80)
print("NAME TOKEN FREQUENCY")
print("=" * 80)

for limit in [10, 50, 100, 500, 1000, 5000]:
    count = con.execute(f"""
        SELECT COUNT(*)
        FROM name_token_freq
        WHERE df <= {limit}
    """).fetchone()[0]

    print(f"tokens with df <= {limit:5}: {count:,}")

print()

print("=" * 80)
print("ADDRESS TOKEN FREQUENCY")
print("=" * 80)

for limit in [10, 50, 100, 500, 1000, 5000]:
    count = con.execute(f"""
        SELECT COUNT(*)
        FROM address_token_freq
        WHERE df <= {limit}
    """).fetchone()[0]

    print(f"tokens with df <= {limit:5}: {count:,}")

# ------------------------------------------------------------------
# ESTIMATE RARE TOKEN BLOCK SIZES
# ------------------------------------------------------------------

print()
print("=" * 80)
print("ESTIMATING RARE TOKEN BLOCK SIZE")
print("=" * 80)

# We estimate candidates by joining S1 tokens against candidate tokens,
# but only for rare tokens.

con.execute("""
CREATE OR REPLACE TABLE s1_name_tokens AS
SELECT DISTINCT
    s1_id,
    country,
    unnest(
        list_filter(
            string_split(name_norm, ' '),
            x -> length(x) >= 3
        )
    ) AS token
FROM s1_blocks
WHERE name_norm <> ''
""")

con.execute("""
CREATE OR REPLACE TABLE s1_address_tokens AS
SELECT DISTINCT
    s1_id,
    country,
    unnest(
        list_filter(
            string_split(address_norm, ' '),
            x -> length(x) >= 2
        )
    ) AS token
FROM s1_blocks
WHERE address_norm <> ''
""")

# Name tokens

for limit in [50, 100, 500, 1000]:

    print()
    print(f"NAME TOKENS df <= {limit}")

    result = con.execute(f"""
        SELECT COUNT(*)
        FROM s1_name_tokens s
        JOIN candidate_name_tokens c
            ON s.country = c.country
           AND s.token = c.token
        JOIN name_token_freq f
            ON f.country = c.country
           AND f.token = c.token
        WHERE f.df <= {limit}
    """).fetchone()[0]

    print(f"Estimated raw token pairs: {result:,}")

# Address tokens

for limit in [50, 100, 500, 1000]:

    print()
    print(f"ADDRESS TOKENS df <= {limit}")

    result = con.execute(f"""
        SELECT COUNT(*)
        FROM s1_address_tokens s
        JOIN candidate_address_tokens c
            ON s.country = c.country
           AND s.token = c.token
        JOIN address_token_freq f
            ON f.country = c.country
           AND f.token = c.token
        WHERE f.df <= {limit}
    """).fetchone()[0]

    print(f"Estimated raw token pairs: {result:,}")

print()
print("=" * 80)
print("DONE")
print("=" * 80)