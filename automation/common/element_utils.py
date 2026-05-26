"""Fuzzy element-name matching utilities.

# Migration notes
# UFT counterpart: FunctionLibrary/ElementUtils.qfl
# Inferred functions:
#   normalize_key   ← NormalizeKey(sName)         — canonical form for comparison
#   similarity      ← Similarity(sA, sB)           — 0..1 string similarity score
#   best_match      ← BestMatch(sName, aNames)     — closest logical name lookup
# UFT used exact match only; fuzzy matching is added to handle minor label
# drift between Epic Hyperdrive versions without needing full OR re-capture.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_key(value: str) -> str:
    """Return *value* lowercased, stripped, and with collapsed whitespace."""
    nfkd = unicodedata.normalize("NFKD", value)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\s_\-]+", "_", ascii_str.strip().lower())


def similarity(a: str, b: str) -> float:
    """Return a 0.0..1.0 Jaccard token-overlap similarity between *a* and *b*.

    Uses word-level tokens so "submit enrollment" ≈ "enrollment submit" → 1.0.
    Sufficient for UI label matching; no external dependencies.
    """
    tokens_a = set(normalize_key(a).split("_"))
    tokens_b = set(normalize_key(b).split("_"))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def best_match(
    query: str,
    candidates: list[str],
    *,
    threshold: float = 0.5,
) -> str | None:
    """Return the candidate from *candidates* most similar to *query*.

    Returns None when the best score falls below *threshold*.
    """
    if not candidates:
        return None
    scored = [(c, similarity(query, c)) for c in candidates]
    best_name, best_score = max(scored, key=lambda x: x[1])
    return best_name if best_score >= threshold else None
