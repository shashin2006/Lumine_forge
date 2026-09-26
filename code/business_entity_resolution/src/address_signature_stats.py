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
CREATE OR REPLACE TABLE candidates AS

SELECT
    entity_id AS candidate_id,
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
    business_address,
    country
FROM read_csv_auto(
    '{S3}',
    delim='\\t',
    header=true
)
""")

print("Loaded.")

# ------------------------------------------------------------
# Extract digit signatures
# ------------------------------------------------------------

print("=" * 80)
print("EXTRACTING ADDRESS DIGITS")
print("=" * 80)

con.execute("""
CREATE OR REPLACE TABLE address_numbers AS
SELECT
    candidate_id,
    country,
    regexp_extract_all(
        coalesce(business_address, ''),
        '[0-9]+'
    ) AS numbers
FROM candidates
""")

# ------------------------------------------------------------
# Basic statistics
# ------------------------------------------------------------

print("=" * 80)
print("NUMBER COUNTS")
print("=" * 80)

print(
    con.execute("""
        SELECT
            AVG(n),
            quantile_cont(n, 0.50),
            quantile_cont(n, 0.90),
            quantile_cont(n, 0.95),
            quantile_cont(n, 0.99),
            MAX(n)
        FROM (
            SELECT
                candidate_id,
                len(numbers) AS n
            FROM address_numbers
        )
    """).fetchone()
)

# ------------------------------------------------------------
# Flatten numbers
# ------------------------------------------------------------

con.execute("""
CREATE OR REPLACE TABLE number_tokens AS
SELECT DISTINCT
    candidate_id,
    country,
    number
FROM (
    SELECT
        candidate_id,
        country,
        unnest(numbers) AS number
    FROM address_numbers
)
WHERE number <> ''
""")

# ------------------------------------------------------------
# Number frequency
# ------------------------------------------------------------

con.execute("""
CREATE OR REPLACE TABLE number_freq AS
SELECT
    country,
    number,
    COUNT(*) AS df
FROM number_tokens
GROUP BY country, number
""")

print()
print("=" * 80)
print("NUMBER FREQUENCY")
print("=" * 80)

for limit in [1, 5, 10, 50, 100, 500, 1000]:

    count = con.execute(f"""
        SELECT COUNT(*)
        FROM number_freq
        WHERE df <= {limit}
    """).fetchone()[0]

    print(
        f"numbers with df <= {limit:4}: {count:,}"
    )

# ------------------------------------------------------------
# Frequency distribution
# ------------------------------------------------------------

print()
print("=" * 80)
print("NUMBER DF DISTRIBUTION")
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
        FROM number_freq
    """).fetchone()
)

# ------------------------------------------------------------
# Sample common numbers
# ------------------------------------------------------------

print()
print("=" * 80)
print("COMMON NUMBERS")
print("=" * 80)

rows = con.execute("""
    SELECT
        number,
        df
    FROM number_freq
    ORDER BY df DESC
    LIMIT 30
""").fetchall()

for number, df in rows:
    print(f"{number:20} {df:,}")

print()
print("=" * 80)
print("DONE")
print("=" * 80)