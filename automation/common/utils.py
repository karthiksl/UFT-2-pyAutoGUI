"""General-purpose utilities for business-layer code.

# Migration notes
# UFT counterpart: FunctionLibrary/Utilities.qfl
# Inferred functions:
#   normalize_name       ← NormalizeName(sValue)        — strips/folds whitespace
#   format_date          ← FormatDate(sDate, sFormat)    — date coercion helper
#   parse_date           ← ParseDate(sDate)              — flexible date parser
#   safe_int             ← SafeInt(sValue, nDefault)     — cast with fallback
#   safe_float           ← SafeFloat(sValue, nDefault)   — cast with fallback
#   mask_sensitive       ← MaskSensitive(sValue)         — log-safe masking
#   retry_with_jitter    ← (inferred) RetryOp wrapper    — bounded retry + sleep
"""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import date, datetime
from typing import Any, Callable, TypeVar

from loguru import logger

from automation.common.constants import AppConstants

T = TypeVar("T")

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


def normalize_name(value: str) -> str:
    """Fold Unicode, strip whitespace, collapse internal spaces.

    Equivalent to UFT's NormalizeName() — maps é→e, trims, collapses runs.
    """
    nfkd = unicodedata.normalize("NFKD", value)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_str).strip()


def mask_sensitive(value: str, *, visible_tail: int = 4) -> str:
    """Return *value* with all but the last *visible_tail* chars replaced by *.

    Safe for logging SSNs, passwords, and member IDs.
    """
    if len(value) < visible_tail:
        return "*" * len(value)
    return "*" * (len(value) - visible_tail) + value[-visible_tail:]


def normalize_key(value: str) -> str:
    """Lowercase, strip, collapse whitespace — canonical comparison key."""
    return re.sub(r"\s+", " ", value.strip().lower())


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def format_date_epic(d: date | datetime | str) -> str:
    """Return *d* as MM/DD/YYYY string required by Epic date fields."""
    if isinstance(d, str):
        d = parse_date(d)
    return d.strftime(AppConstants.EPIC_DATE_FORMAT)


def parse_date(value: str) -> date:
    """Parse common date string formats; raises ValueError on failure.

    Tries: MM/DD/YYYY, YYYY-MM-DD, MM-DD-YYYY, M/D/YYYY, YYYYMMDD.
    """
    # inferred: needs review — add any additional formats seen in test data
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y%m%d", "%-m/%-d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date {value!r}; expected MM/DD/YYYY or YYYY-MM-DD")


def today_epic() -> str:
    """Return today's date formatted for Epic."""
    return format_date_epic(date.today())


# ---------------------------------------------------------------------------
# Safe casts
# ---------------------------------------------------------------------------


def safe_int(value: Any, default: int = 0) -> int:
    """Cast *value* to int; return *default* on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Cast *value* to float; return *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """Cast *value* to str, stripping whitespace; return *default* on failure."""
    if value is None:
        return default
    try:
        return str(value).strip()
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------------------
# Retry with jitter
# ---------------------------------------------------------------------------


def retry_with_jitter(
    op: Callable[[], T],
    *,
    max_attempts: int = AppConstants.BUSINESS_MAX_ATTEMPTS,
    backoff_s: float = AppConstants.BUSINESS_BACKOFF_S,
    jitter_s: float = 0.25,
    label: str = "op",
) -> T:
    """Call *op()* up to *max_attempts* times with exponential backoff + jitter.

    Unlike core/retries.retry(), this helper is for business-layer I/O
    (file reads, data lookups) where screenshot capture is inappropriate.
    """
    import random

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return op()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == max_attempts:
                break
            sleep_s = backoff_s * (2 ** (attempt - 1)) + random.uniform(0, jitter_s)
            logger.warning(
                "retry_with_jitter: {} attempt {}/{} failed ({}); retrying in {:.2f}s",
                label,
                attempt,
                max_attempts,
                type(exc).__name__,
                sleep_s,
            )
            time.sleep(sleep_s)
    raise RuntimeError(f"{label} failed after {max_attempts} attempts") from last_exc
