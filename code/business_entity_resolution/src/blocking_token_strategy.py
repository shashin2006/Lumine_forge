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
# NORMALIZATION
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
# CANDIDATE-SIDE TOKEN FREQUENCIES
# ------------------------------------------------------------------

print("=" * 80)
print("BUILDING TOKEN FREQUENCIES")
print("=" * 80)

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
# S1 TOKENS
# ------------------------------------------------------------------

print("=" * 80)
print("BUILDING S1 TOKENS")
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

# ------------------------------------------------------------------
# RANK TOKENS BY FREQUENCY
# ------------------------------------------------------------------

print("=" * 80)
print("RANKING TOKENS BY FREQUENCY")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE ranked_name_tokens AS
SELECT
    s.s1_id,
    s.country,
    s.token,
    f.df,
    ROW_NUMBER() OVER (
        PARTITION BY s.s1_id
        ORDER BY f.df ASC, length(s.token) DESC
    ) AS rank
FROM s1_name_tokens s
JOIN name_freq f
    ON s.country = f.country
   AND s.token = f.token
""")

con.execute("""
CREATE OR REPLACE TABLE ranked_address_tokens AS
SELECT
    s.s1_id,
    s.country,
    s.token,
    f.df,
    ROW_NUMBER() OVER (
        PARTITION BY s.s1_id
        ORDER BY f.df ASC, length(s.token) DESC
    ) AS rank
FROM s1_address_tokens s
JOIN address_freq f
    ON s.country = f.country
   AND s.token = f.token
""")

# ------------------------------------------------------------------
# DISTRIBUTION
# ------------------------------------------------------------------

print("=" * 80)
print("S1 NAME TOKEN COUNTS")
print("=" * 80)

print(
    con.execute("""
        SELECT
            AVG(cnt),
            quantile_cont(cnt, 0.50),
            quantile_cont(cnt, 0.90),
            quantile_cont(cnt, 0.95),
            quantile_cont(cnt, 0.99),
            MAX(cnt)
        FROM (
            SELECT
                s1_id,
                COUNT(*) AS cnt
            FROM s1_name_tokens
            GROUP BY s1_id
        )
    """).fetchone()
)

print("=" * 80)
print("S1 ADDRESS TOKEN COUNTS")
print("=" * 80)

print(
    con.execute("""
        SELECT
            AVG(cnt),
            quantile_cont(cnt, 0.50),
            quantile_cont(cnt, 0.90),
            quantile_cont(cnt, 0.95),
            quantile_cont(cnt, 0.99),
            MAX(cnt)
        FROM (
            SELECT
                s1_id,
                COUNT(*) AS cnt
            FROM s1_address_tokens
            GROUP BY s1_id
        )
    """).fetchone()
)

# ------------------------------------------------------------------
# TOP TOKEN FREQUENCIES FOR S1
# ------------------------------------------------------------------

print()
print("=" * 80)
print("RAREST NAME TOKEN PER S1")
print("=" * 80)

print(
    con.execute("""
        SELECT
            AVG(df),
            quantile_cont(df, 0.50),
            quantile_cont(df, 0.90),
            quantile_cont(df, 0.95),
            quantile_cont(df, 0.99),
            MAX(df)
        FROM ranked_name_tokens
        WHERE rank = 1
    """).fetchone()
)

print()
print("=" * 80)
print("RAREST ADDRESS TOKEN PER S1")
print("=" * 80)

print(
    con.execute("""
        SELECT
            AVG(df),
            quantile_cont(df, 0.50),
            quantile_cont(df, 0.90),
            quantile_cont(df, 0.95),
            quantile_cont(df, 0.99),
            MAX(df)
        FROM ranked_address_tokens
        WHERE rank = 1
    """).fetchone()
)

# ------------------------------------------------------------------
# CANDIDATE COUNT USING ONLY TOP 1 / TOP 2 / TOP 3 TOKENS
# ------------------------------------------------------------------

for k in [1, 2, 3]:

    print()
    print("=" * 80)
    print(f"TOP {k} NAME TOKENS")
    print("=" * 80)

    result = con.execute(f"""
        SELECT COUNT(*)
        FROM ranked_name_tokens s
        JOIN cand_name_tokens c
            ON s.country = c.country
           AND s.token = c.token
        WHERE s.rank <= {k}
    """).fetchone()[0]

    print(f"Raw candidate token hits: {result:,}")

for k in [1, 2, 3]:

    print()
    print("=" * 80)
    print(f"TOP {k} ADDRESS TOKENS")
    print("=" * 80)

    result = con.execute(f"""
        SELECT COUNT(*)
        FROM ranked_address_tokens s
        JOIN cand_address_tokens c
            ON s.country = c.country
           AND s.token = c.token
        WHERE s.rank <= {k}
    """).fetchone()[0]

    print(f"Raw candidate token hits: {result:,}")

print()
print("=" * 80)
print("DONE")
print("=" * 80)