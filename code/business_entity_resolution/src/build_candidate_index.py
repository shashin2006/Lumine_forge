import csv
import sqlite3
import re
import os
from itertools import combinations

from normalization import normalize_name, normalize_address


ROOT = r"C:\Lumine_Forge_Submission\student_resource"

S2 = os.path.join(ROOT, "dataset", "train", "train_source2.tsv")
S3 = os.path.join(ROOT, "dataset", "train", "train_source3.tsv")

INDEX_DB = os.path.join(ROOT, "candidate_index.sqlite")


# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------

BATCH_SIZE = 50_000

MIN_NAME_TOKEN_LEN = 3
MIN_ADDRESS_TOKEN_LEN = 2

# Do not index extremely common token pairs.
# Pair signatures are already much more selective than
# individual tokens.
MAX_NAME_PAIR_DF = 500
MAX_ADDRESS_PAIR_DF = 500


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def tokens(text, minimum_length):
    if not text:
        return []

    return sorted(
        set(
            t for t in text.split()
            if len(t) >= minimum_length
        )
    )


def make_pairs(values):
    if len(values) < 2:
        return []

    return [
        "|".join(pair)
        for pair in combinations(values, 2)
    ]


def normalize_for_db(text):
    return str(text).strip()


# ------------------------------------------------------------
# REMOVE OLD INDEX
# ------------------------------------------------------------

if os.path.exists(INDEX_DB):
    print("Removing existing index...")
    os.remove(INDEX_DB)


# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

print("=" * 80)
print("CREATING SQLITE INDEX")
print("=" * 80)

conn = sqlite3.connect(INDEX_DB)

conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA temp_store=FILE")
conn.execute("PRAGMA cache_size=-500000")


conn.execute("""
CREATE TABLE candidates (
    candidate_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    country TEXT,
    name_norm TEXT,
    address_norm TEXT
)
""")


conn.execute("""
CREATE TABLE name_exact (
    country TEXT,
    name_norm TEXT,
    candidate_id TEXT
)
""")


conn.execute("""
CREATE TABLE address_exact (
    country TEXT,
    address_norm TEXT,
    candidate_id TEXT
)
""")


conn.execute("""
CREATE TABLE name_pairs (
    country TEXT,
    pair_key TEXT,
    candidate_id TEXT
)
""")


conn.execute("""
CREATE TABLE address_pairs (
    country TEXT,
    pair_key TEXT,
    candidate_id TEXT
)
""")


# ------------------------------------------------------------
# LOAD ONE SOURCE
# ------------------------------------------------------------

def process_source(path, source_name):

    print()
    print("=" * 80)
    print(f"PROCESSING {source_name}")
    print("=" * 80)

    candidates_batch = []
    name_exact_batch = []
    address_exact_batch = []
    name_pair_batch = []
    address_pair_batch = []

    count = 0

    with open(
        path,
        "r",
        encoding="utf-8",
        errors="replace",
        newline=""
    ) as f:

        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:

            candidate_id = normalize_for_db(row["entity_id"])
            country = normalize_for_db(row.get("country", ""))

            name = normalize_name(
                row.get("business_name", "")
            )

            address = normalize_address(
                row.get("business_address", "")
            )

            candidates_batch.append(
                (
                    candidate_id,
                    source_name,
                    country,
                    name,
                    address
                )
            )

            if name:
                name_exact_batch.append(
                    (
                        country,
                        name,
                        candidate_id
                    )
                )

            if address:
                address_exact_batch.append(
                    (
                        country,
                        address,
                        candidate_id
                    )
                )

            # ------------------------------------------------
            # NAME TOKEN PAIRS
            # ------------------------------------------------

            name_tokens = tokens(
                name,
                MIN_NAME_TOKEN_LEN
            )

            for pair_key in make_pairs(name_tokens):

                name_pair_batch.append(
                    (
                        country,
                        pair_key,
                        candidate_id
                    )
                )

            # ------------------------------------------------
            # ADDRESS TOKEN PAIRS
            # ------------------------------------------------

            address_tokens = tokens(
                address,
                MIN_ADDRESS_TOKEN_LEN
            )

            for pair_key in make_pairs(address_tokens):

                address_pair_batch.append(
                    (
                        country,
                        pair_key,
                        candidate_id
                    )
                )

            count += 1

            # ------------------------------------------------
            # BATCH INSERT
            # ------------------------------------------------

            if count % BATCH_SIZE == 0:

                conn.executemany(
                    """
                    INSERT OR IGNORE INTO candidates
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    candidates_batch
                )

                conn.executemany(
                    """
                    INSERT INTO name_exact
                    VALUES (?, ?, ?)
                    """,
                    name_exact_batch
                )

                conn.executemany(
                    """
                    INSERT INTO address_exact
                    VALUES (?, ?, ?)
                    """,
                    address_exact_batch
                )

                conn.executemany(
                    """
                    INSERT INTO name_pairs
                    VALUES (?, ?, ?)
                    """,
                    name_pair_batch
                )

                conn.executemany(
                    """
                    INSERT INTO address_pairs
                    VALUES (?, ?, ?)
                    """,
                    address_pair_batch
                )

                conn.commit()

                candidates_batch.clear()
                name_exact_batch.clear()
                address_exact_batch.clear()
                name_pair_batch.clear()
                address_pair_batch.clear()

                print(
                    f"{count:,} records processed",
                    flush=True
                )

    # --------------------------------------------------------
    # FINAL BATCH
    # --------------------------------------------------------

    if candidates_batch:

        conn.executemany(
            """
            INSERT OR IGNORE INTO candidates
            VALUES (?, ?, ?, ?, ?)
            """,
            candidates_batch
        )

        conn.executemany(
            """
            INSERT INTO name_exact
            VALUES (?, ?, ?)
            """,
            name_exact_batch
        )

        conn.executemany(
            """
            INSERT INTO address_exact
            VALUES (?, ?, ?)
            """,
            address_exact_batch
        )

        conn.executemany(
            """
            INSERT INTO name_pairs
            VALUES (?, ?, ?)
            """,
            name_pair_batch
        )

        conn.executemany(
            """
            INSERT INTO address_pairs
            VALUES (?, ?, ?)
            """,
            address_pair_batch
        )

        conn.commit()

    print(
        f"{source_name}: {count:,} records"
    )


# ------------------------------------------------------------
# BUILD INDEX
# ------------------------------------------------------------

process_source(S2, "S2")
process_source(S3, "S3")


# ------------------------------------------------------------
# INDEXES
# ------------------------------------------------------------

print()
print("=" * 80)
print("CREATING DATABASE INDEXES")
print("=" * 80)

indexes = [

    """
    CREATE INDEX idx_name_exact
    ON name_exact(country, name_norm)
    """,

    """
    CREATE INDEX idx_address_exact
    ON address_exact(country, address_norm)
    """,

    """
    CREATE INDEX idx_name_pairs
    ON name_pairs(country, pair_key)
    """,

    """
    CREATE INDEX idx_address_pairs
    ON address_pairs(country, pair_key)
    """,

    """
    CREATE INDEX idx_candidates_id
    ON candidates(candidate_id)
    """
]

for sql in indexes:
    conn.execute(sql)
    conn.commit()


# ------------------------------------------------------------
# STATISTICS
# ------------------------------------------------------------

print()
print("=" * 80)
print("INDEX STATISTICS")
print("=" * 80)

for table in [
    "candidates",
    "name_exact",
    "address_exact",
    "name_pairs",
    "address_pairs"
]:

    count = conn.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]

    print(
        f"{table:20} {count:,}"
    )


conn.execute("VACUUM")
conn.close()

print()
print("=" * 80)
print("INDEX BUILD COMPLETE")
print("=" * 80)

print(f"Index: {INDEX_DB}")