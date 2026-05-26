"""Test data I/O — Excel / CSV reader with binding-aware column resolution.

# Migration notes
# UFT counterpart: FunctionLibrary/DataReader.qfl
# Inferred functions:
#   DataRow              ← UFT DataTable row wrapper (row("ColName"))
#   iter_rows            ← For Each row In DataTable.GetSheet("SheetName")
#   load_suite_data      ← called at suite startup; loads all sheets
#   get_field            ← GetField(sBinding) — resolves data_bindings entry
# The UFT code used Excel as both test data store AND result writer; this
# module covers reading only. Writing is delegated to reporting_legacy.py.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from loguru import logger

from automation.core.config import get_config
from automation.core.exceptions import DataError

# openpyxl is an optional but expected dependency for Excel support
try:
    import openpyxl  # type: ignore[import]
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataRow:
    """A single test-data row, immutable after construction.

    Attributes:
        suite:   Name of the data source / sheet (e.g. "member_data").
        jira:    JIRA / test-case identifier for this row (e.g. "TEST_188001").
        payload: Column-name → value mapping (all values as strings).
    """

    suite: str
    jira: str
    payload: dict[str, Any]

    def get(self, column: str, default: Any = None) -> Any:
        """Return the value for *column*; return *default* when absent."""
        return self.payload.get(column, default)

    def require(self, column: str) -> Any:
        """Return the value for *column*; raise DataError when absent or blank."""
        val = self.payload.get(column)
        if val is None or str(val).strip() == "":
            raise DataError(
                f"Required column {column!r} is missing or blank in suite={self.suite!r},"
                f" jira={self.jira!r}",
            )
        return val

    def __repr__(self) -> str:
        return f"DataRow(suite={self.suite!r}, jira={self.jira!r})"


# ---------------------------------------------------------------------------
# Row iteration
# ---------------------------------------------------------------------------


def iter_rows(suite: str, jira: str | None = None) -> Iterator[DataRow]:
    """Yield DataRow objects from the data source named *suite*.

    Looks for files under ``<data_root>/<suite>/`` in this order:
      1. ``<suite>.xlsx``  (sheet "Sheet1" or first sheet)
      2. ``<suite>.csv``

    Filters to rows where the ``TestCaseID`` column matches *jira* when given.

    Args:
        suite: Data source name (matches a ``data_bindings[*].source`` value).
        jira:  Optional JIRA/test-case ID to filter rows.

    Yields:
        DataRow for each matching row.

    Raises:
        DataError: When the data file is missing or unparseable.
    """
    data_root = Path(get_config().get("data_root", "automation/data"))
    xlsx_path = data_root / suite / f"{suite}.xlsx"
    csv_path = data_root / suite / f"{suite}.csv"

    if xlsx_path.exists():
        yield from _iter_excel(xlsx_path, suite, jira)
    elif csv_path.exists():
        yield from _iter_csv(csv_path, suite, jira)
    else:
        raise DataError(
            f"No data file found for suite={suite!r}; "
            f"tried {xlsx_path} and {csv_path}",
        )


# ---------------------------------------------------------------------------
# Format readers
# ---------------------------------------------------------------------------


def _iter_excel(path: Path, suite: str, jira: str | None) -> Iterator[DataRow]:
    if not _HAS_OPENPYXL:
        raise DataError(
            "openpyxl is required to read .xlsx files — pip install openpyxl",
        )
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise DataError(f"Cannot open Excel file {path}: {exc}") from exc

    ws = wb.active
    if ws is None:
        raise DataError(f"Excel workbook {path} has no active sheet")

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        logger.warning("data: {} is empty", path)
        return

    headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
    for raw_row in rows[1:]:
        payload = {headers[i]: (raw_row[i] if i < len(raw_row) else None) for i in range(len(headers))}
        row_jira = str(payload.get("TestCaseID", "")).strip()
        if jira and row_jira != jira:
            continue
        yield DataRow(suite=suite, jira=row_jira, payload=payload)


def _iter_csv(path: Path, suite: str, jira: str | None) -> Iterator[DataRow]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for raw_row in reader:
                payload: dict[str, Any] = dict(raw_row)
                row_jira = str(payload.get("TestCaseID", "")).strip()
                if jira and row_jira != jira:
                    continue
                yield DataRow(suite=suite, jira=row_jira, payload=payload)
    except Exception as exc:  # noqa: BLE001
        raise DataError(f"Cannot read CSV {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Binding-aware field lookup
# ---------------------------------------------------------------------------


def get_field(row: DataRow, binding_name: str, or_doc: dict | None = None) -> Any:
    """Resolve *binding_name* through data_bindings; return the column value.

    When *or_doc* is None the function falls back to treating *binding_name*
    as a direct column name — allows call sites to skip the OR doc in tests.

    # inferred: needs review — or_doc loading should use load_or() result
    """
    if or_doc is not None:
        bindings: dict = or_doc.get("data_bindings", {})
        binding = bindings.get(binding_name)
        if binding is None:
            raise DataError(
                f"data_binding {binding_name!r} not defined in Visual OR",
            )
        column: str = binding.get("column", binding_name)
    else:
        column = binding_name

    return row.get(column)
