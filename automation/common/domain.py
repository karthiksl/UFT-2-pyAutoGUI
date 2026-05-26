"""Epic domain helpers — member ID validation, date coercion, plan lookups.

# Migration notes
# UFT counterpart: FunctionLibrary/DomainHelpers.qfl
# Inferred functions:
#   parse_member_id        ← ValidateMRN(sValue)       — strip/validate MRN
#   format_date_for_epic   ← FormatEpicDate(sDate)     — coerce to MM/DD/YYYY
#   normalize_coverage_type← NormalizeCovType(sType)   — canonical coverage type
#   normalize_plan_tier    ← GetPlanTier(sPlanName)    — extract HMO/PPO/etc.
#   normalize_change_reason← NormChangeReason(sReason) — dropdown-value lookup
#   plan_tier_from_name    ← PlanTierFromName(sPlan)   — regex extract tier
"""

from __future__ import annotations

import re
from datetime import date

from automation.common.constants import AppConstants
from automation.common.utils import normalize_key, parse_date
from automation.core.exceptions import DataError

# ---------------------------------------------------------------------------
# Member ID / MRN
# ---------------------------------------------------------------------------

_MRN_STRIP_RE = re.compile(r"[^0-9]")


def parse_member_id(value: str) -> str:
    """Strip non-numeric chars and validate MRN digit count.

    Returns the cleaned numeric MRN string.

    Raises DataError when length is outside [MRN_MIN_DIGITS, MRN_MAX_DIGITS].
    """
    clean = _MRN_STRIP_RE.sub("", str(value).strip())
    lo, hi = AppConstants.MRN_MIN_DIGITS, AppConstants.MRN_MAX_DIGITS
    if not (lo <= len(clean) <= hi):
        raise DataError(
            f"Invalid member ID {value!r}: expected {lo}–{hi} digits, got {len(clean)}",
        )
    return clean


def is_valid_member_id(value: str) -> bool:
    """Return True when *value* is a valid MRN (non-raising wrapper)."""
    try:
        parse_member_id(value)
        return True
    except DataError:
        return False


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------


def format_date_for_epic(value: str | date) -> str:
    """Return *value* as the MM/DD/YYYY string that Epic date fields expect.

    Accepts: date objects, ISO strings (YYYY-MM-DD), or MM/DD/YYYY strings.
    """
    if isinstance(value, date):
        return value.strftime(AppConstants.EPIC_DATE_FORMAT)
    return parse_date(str(value)).strftime(AppConstants.EPIC_DATE_FORMAT)


# ---------------------------------------------------------------------------
# Coverage type
# ---------------------------------------------------------------------------


def normalize_coverage_type(value: str) -> str:
    """Return the canonical coverage type matching Epic's dropdown text.

    Raises DataError when *value* does not match any known type.
    """
    key = normalize_key(value)
    for ct in AppConstants.COVERAGE_TYPES:
        if normalize_key(ct) == key:
            return ct
    raise DataError(
        f"Unknown coverage type {value!r}; "
        f"expected one of {AppConstants.COVERAGE_TYPES}",
    )


# ---------------------------------------------------------------------------
# Plan tier
# ---------------------------------------------------------------------------

_TIER_RE = re.compile(r"\b(HMO|PPO|HDHP|EPO)\b", re.IGNORECASE)


def plan_tier_from_name(plan_name: str) -> str | None:
    """Extract the plan tier acronym (HMO/PPO/HDHP/EPO) from *plan_name*.

    Returns None when no tier acronym is found.
    """
    m = _TIER_RE.search(plan_name)
    return m.group(1).upper() if m else None


def normalize_plan_tier(value: str) -> str:
    """Return the canonical plan tier; raises DataError when unknown."""
    upper = value.strip().upper()
    if upper in AppConstants.PLAN_TIERS:
        return upper
    raise DataError(
        f"Unknown plan tier {value!r}; expected one of {AppConstants.PLAN_TIERS}",
    )


# ---------------------------------------------------------------------------
# Change reason
# ---------------------------------------------------------------------------


def normalize_change_reason(value: str) -> str:
    """Return the canonical change reason matching Epic's dropdown text.

    Case-insensitive lookup; raises DataError on no match.
    """
    key = normalize_key(value)
    for reason in AppConstants.CHANGE_REASONS:
        if normalize_key(reason) == key:
            return reason
    raise DataError(
        f"Unknown change reason {value!r}; "
        f"expected one of {AppConstants.CHANGE_REASONS}",
    )


# ---------------------------------------------------------------------------
# Confirmation status
# ---------------------------------------------------------------------------


def normalize_confirmation_status(value: str) -> str:
    """Return the canonical confirmation status; raises DataError on no match."""
    key = normalize_key(value)
    for status in AppConstants.CONFIRMATION_STATUSES:
        if normalize_key(status) == key:
            return status
    raise DataError(
        f"Unknown confirmation status {value!r}; "
        f"expected one of {AppConstants.CONFIRMATION_STATUSES}",
    )
