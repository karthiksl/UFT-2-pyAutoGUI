"""Suite data source loader and validator.

# Migration notes
# UFT counterpart: FunctionLibrary/SuiteSource.qfl
# Inferred functions:
#   load_suite_data    ← LoadSuiteData(sSuiteName)     — open sheet, return rows
#   validate_suite_data← ValidateSuiteData(aSuiteRows) — required-column check
# UFT validated test data by asserting column existence before iterating rows.
# This module mirrors that pattern and adds DataError with column diagnostics.
"""

from __future__ import annotations

from typing import Iterator

from automation.common.data import DataRow, iter_rows
from automation.core.exceptions import DataError

# Columns that every suite sheet must contain regardless of source type.
_UNIVERSAL_REQUIRED = {"TestCaseID"}

# Per-source required columns — inferred from UFT script parameter references
_SOURCE_REQUIRED: dict[str, set[str]] = {
    "member_data": {"TestCaseID", "MemberID", "LastName", "FirstName", "DateOfBirth"},
    "coverage_data": {"TestCaseID", "EffectiveDate", "CoverageType", "PlanName"},
    "dependent_data": {"TestCaseID", "DependentFirstName", "DependentLastName", "RelationshipType"},
}


def load_suite_data(suite: str, jira: str | None = None) -> list[DataRow]:
    """Load all rows for *suite*, optionally filtered to *jira*.

    Validates that required columns are present before returning.

    Raises DataError when required columns are missing or the file is absent.
    """
    rows = list(iter_rows(suite, jira=jira))
    if rows:
        validate_suite_data(suite, rows)
    return rows


def validate_suite_data(suite: str, rows: list[DataRow]) -> None:
    """Assert that *rows* contain all required columns for *suite*.

    Raises DataError listing every missing column.
    """
    if not rows:
        return
    present = set(rows[0].payload.keys())
    required = _UNIVERSAL_REQUIRED | _SOURCE_REQUIRED.get(suite, set())
    missing = required - present
    if missing:
        raise DataError(
            f"Suite {suite!r} data is missing required columns: {sorted(missing)}; "
            f"found: {sorted(present)}",
        )


def iter_suite_rows(suite: str, jira: str | None = None) -> Iterator[DataRow]:
    """Yield validated DataRow objects from *suite* data source.

    Like :func:`load_suite_data` but streams rows instead of building a list.
    """
    first = True
    for row in iter_rows(suite, jira=jira):
        if first:
            validate_suite_data(suite, [row])
            first = False
        yield row
