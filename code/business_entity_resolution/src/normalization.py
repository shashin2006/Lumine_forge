import re
import unicodedata


LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "llc",
    "llp",
    "plc",
    "pvt",
    "private",
    "proprietary",
    "sa",
    "sas",
    "sarl",
}


def normalize_unicode(text: str) -> str:
    """Unicode normalization while preserving non-Latin scripts."""
    if not text:
        return ""

    text = str(text)

    # Compatibility normalization.
    text = unicodedata.normalize("NFKC", text)

    # Case folding works for Latin and many other scripts.
    text = text.casefold()

    return text


def remove_punctuation(text: str) -> str:
    """
    Remove punctuation and symbols while preserving:
    - letters from all scripts
    - numbers
    - Unicode combining marks
    - whitespace
    """
    result = []

    for char in text:
        category = unicodedata.category(char)

        # Preserve letters: L*
        # Preserve numbers: N*
        # Preserve combining marks: M*
        # Preserve whitespace.
        if (
            category.startswith(("L", "N", "M"))
            or char.isspace()
        ):
            result.append(char)
        else:
            result.append(" ")

    return "".join(result)


def normalize_name(text: str) -> str:
    """
    Normalize business names while preserving Unicode words/scripts.

    Examples:

        ABC Pvt. Ltd. -> abc

        A.B.C. Corporation -> a b c

        Orelee's Barbershop -> orelee s barbershop

        Hindi text remains readable and is NOT split into characters.
    """
    text = normalize_unicode(text)

    if not text:
        return ""

    text = re.sub(r"(?<=\w)[\'’](?=\w)", "", text)
    # Remove Unicode punctuation.
    text = remove_punctuation(text)

    # Collapse whitespace.
    tokens = text.split()

    # Remove common legal suffixes.
    filtered = [
        token
        for token in tokens
        if token not in LEGAL_SUFFIXES
    ]

    return " ".join(filtered)


def normalize_name_compact(text: str) -> str:
    """
    Compact representation useful for exact blocking.

    Spaces and punctuation are removed.
    """
    normalized = normalize_name(text)

    return "".join(normalized.split())


def name_tokens(text: str) -> list[str]:
    normalized = normalize_name(text)

    if not normalized:
        return []

    return normalized.split()


def normalize_address(text: str) -> str:
    """
    Normalize addresses while preserving Unicode scripts.
    """
    text = normalize_unicode(text)

    if not text:
        return ""

    # Treat ampersand as a word separator.
    text = text.replace("&", " and ")

    text = re.sub(r"(?<=\w)[\'’](?=\w)", "", text)
    # Remove Unicode punctuation.
    text = remove_punctuation(text)

    # Collapse whitespace.
    text = " ".join(text.split())

    return text


def normalize_address_compact(text: str) -> str:
    return "".join(normalize_address(text).split())


def address_tokens(text: str) -> list[str]:
    normalized = normalize_address(text)

    if not normalized:
        return []

    return normalized.split()


def character_ngrams(text: str, n: int = 3) -> set[str]:
    """
    Generate character n-grams.

    Intended for fuzzy blocking/features after normalization.
    """
    text = text.strip()

    if not text:
        return set()

    if len(text) < n:
        return {text}

    return {
        text[i:i + n]
        for i in range(len(text) - n + 1)
    }