import csv
import sqlite3
import os
from itertools import combinations

from normalization import normalize_name, normalize_address


# ============================================================
# PATHS
# ============================================================

ROOT = r"C:\Lumine_Forge_Submission\student_resource"

INDEX_DB = os.path.join(
    ROOT,
    "candidate_index.sqlite"
)

TRAIN_S1 = os.path.join(
    ROOT,
    "dataset",
    "train",
    "train_source1.tsv"
)

OUTPUT_DIR = os.path.join(
    ROOT,
    "output"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "candidate_pairs_train.tsv"
)


# ============================================================
# SETTINGS
# ============================================================

MIN_NAME_TOKEN_LEN = 3

PROGRESS_EVERY = 25_000


# ============================================================
# HELPERS
# ============================================================

def get_tokens(text, minimum_length):

    if not text:
        return []

    return sorted(
        set(
            token
            for token in text.split()
            if len(token) >= minimum_length
        )
    )


def get_token_pairs(tokens):

    if len(tokens) < 2:
        return []

    return [
        "|".join(pair)
        for pair in combinations(tokens, 2)
    ]


# ============================================================
# OPEN DATABASE
# ============================================================

print("=" * 80)
print("OPENING INDEX")
print("=" * 80)

conn = sqlite3.connect(
    INDEX_DB
)

conn.execute(
    "PRAGMA query_only=TRUE"
)

conn.execute(
    "PRAGMA cache_size=-500000"
)


# ============================================================
# PREPARED QUERIES
# ============================================================

exact_name_query = """
SELECT candidate_id
FROM name_exact
WHERE country = ?
  AND name_norm = ?
"""

exact_address_query = """
SELECT candidate_id
FROM address_exact
WHERE country = ?
  AND address_norm = ?
"""

name_pair_query = """
SELECT candidate_id
FROM name_pairs
WHERE country = ?
  AND pair_key = ?
"""

source_query = """
SELECT source
FROM candidates
WHERE candidate_id = ?
"""


# ============================================================
# OUTPUT
# ============================================================

out = open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
    newline=""
)

writer = csv.writer(
    out,
    delimiter="\t",
    lineterminator="\n"
)

writer.writerow([
    "source1_entity_id",
    "candidate_entity_id",
    "candidate_source",
    "block_type"
])


# ============================================================
# STATISTICS
# ============================================================

total_s1 = 0
total_pairs = 0

exact_name_hits = 0
exact_address_hits = 0
name_pair_hits = 0


# ============================================================
# PROCESS S1
# ============================================================

print("=" * 80)
print("GENERATING CANDIDATES")
print("=" * 80)

with open(
    TRAIN_S1,
    "r",
    encoding="utf-8",
    errors="replace",
    newline=""
) as f:

    reader = csv.DictReader(
        f,
        delimiter="\t"
    )

    for row in reader:

        s1_id = row["entity_id"]

        country = (
            row.get("country") or ""
        ).strip()

        name_norm = normalize_name(
            row.get("business_name", "")
        )

        address_norm = normalize_address(
            row.get("business_address", "")
        )

        # ----------------------------------------------------
        # Candidate dictionary
        # ----------------------------------------------------

        candidates = {}

        def add_candidate(
            candidate_id,
            block_type
        ):

            if candidate_id not in candidates:
                candidates[candidate_id] = set()

            candidates[candidate_id].add(
                block_type
            )

        # ----------------------------------------------------
        # 1. EXACT NAME
        # ----------------------------------------------------

        if name_norm:

            for (
                candidate_id,
            ) in conn.execute(
                exact_name_query,
                (
                    country,
                    name_norm
                )
            ):

                add_candidate(
                    candidate_id,
                    "exact_name"
                )

                exact_name_hits += 1

        # ----------------------------------------------------
        # 2. EXACT ADDRESS
        # ----------------------------------------------------

        if address_norm:

            for (
                candidate_id,
            ) in conn.execute(
                exact_address_query,
                (
                    country,
                    address_norm
                )
            ):

                add_candidate(
                    candidate_id,
                    "exact_address"
                )

                exact_address_hits += 1

        # ----------------------------------------------------
        # 3. NAME TOKEN PAIRS
        # ----------------------------------------------------

        name_tokens = get_tokens(
            name_norm,
            MIN_NAME_TOKEN_LEN
        )

        name_pairs = get_token_pairs(
            name_tokens
        )

        for pair_key in name_pairs:

            for (
                candidate_id,
            ) in conn.execute(
                name_pair_query,
                (
                    country,
                    pair_key
                )
            ):

                add_candidate(
                    candidate_id,
                    "name_pair"
                )

                name_pair_hits += 1

        # ----------------------------------------------------
        # WRITE
        # ----------------------------------------------------

        for (
            candidate_id,
            block_types
        ) in candidates.items():

            result = conn.execute(
                source_query,
                (candidate_id,)
            ).fetchone()

            if result is None:
                continue

            candidate_source = result[0]

            writer.writerow([
                s1_id,
                candidate_id,
                candidate_source,
                ",".join(
                    sorted(block_types)
                )
            ])

            total_pairs += 1

        total_s1 += 1

        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        if (
            total_s1 % PROGRESS_EVERY
            == 0
        ):

            out.flush()

            print(
                f"S1 processed: "
                f"{total_s1:,} | "
                f"candidate pairs: "
                f"{total_pairs:,}",
                flush=True
            )


# ============================================================
# CLOSE
# ============================================================

out.close()
conn.close()


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 80)
print("CANDIDATE GENERATION COMPLETE")
print("=" * 80)

print(
    f"S1 entities processed : "
    f"{total_s1:,}"
)

print(
    f"Candidate pairs       : "
    f"{total_pairs:,}"
)

print()
print(
    f"Exact name hits       : "
    f"{exact_name_hits:,}"
)

print(
    f"Exact address hits    : "
    f"{exact_address_hits:,}"
)

print(
    f"Name-pair hits        : "
    f"{name_pair_hits:,}"
)

print()
print(
    f"Output: {OUTPUT_FILE}"
)