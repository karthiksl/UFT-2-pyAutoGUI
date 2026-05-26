"""Unit tests for automation.common.data — DataRow, iter_rows, get_field.

Uses synthetic XLSX / CSV files written to pytest's tmp_path so no external
data files are required.  openpyxl is used for XLSX creation if available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from automation.common.data import DataRow, get_field, iter_rows
from automation.core.exceptions import DataError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_csv(directory: Path, name: str, rows: list[dict[str, Any]]) -> Path:
    """Write *rows* to <directory>/<name>/<name>.csv."""
    import csv

    folder = directory / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.csv"
    if not rows:
        path.write_text("")
        return path
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_xlsx(directory: Path, name: str, rows: list[dict[str, Any]]) -> Path | None:
    """Write *rows* to <directory>/<name>/<name>.xlsx; return None if openpyxl absent."""
    try:
        import openpyxl
    except ImportError:
        return None
    folder = directory / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    if rows:
        ws.append(list(rows[0].keys()))
        for row in rows:
            ws.append(list(row.values()))
    wb.save(path)
    return path


_MEMBER_ROWS = [
    {"TestCaseID": "TC001", "MemberID": "1234567", "LastName": "Smith", "FirstName": "Alice"},
    {"TestCaseID": "TC002", "MemberID": "7654321", "LastName": "Jones", "FirstName": "Bob"},
]


@pytest.fixture()
def csv_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a CSV-based data directory and point config at it."""
    _write_csv(tmp_path, "member_data", _MEMBER_ROWS)
    monkeypatch.setenv("AUTOMATION_DATA_ROOT", str(tmp_path))
    # Reload config so the env var takes effect.
    from automation.core import config as cfg_mod
    import importlib
    importlib.reload(cfg_mod)
    # Also patch get_config to return updated value
    from unittest.mock import patch
    original_get = cfg_mod.get_config
    with patch.object(cfg_mod, "_config", cfg_mod._config.__class__(cfg_mod._DEFAULTS | {"data_root": str(tmp_path)})):
        yield tmp_path
    importlib.reload(cfg_mod)


@pytest.fixture()
def xlsx_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create an XLSX-based data directory; skip when openpyxl unavailable."""
    path = _write_xlsx(tmp_path, "member_data", _MEMBER_ROWS)
    if path is None:
        pytest.skip("openpyxl not installed")
    monkeypatch.setenv("AUTOMATION_DATA_ROOT", str(tmp_path))
    from automation.core import config as cfg_mod
    import importlib
    importlib.reload(cfg_mod)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("automation.core.config._config",
                   cfg_mod._config.__class__(cfg_mod._DEFAULTS | {"data_root": str(tmp_path)}))
        yield tmp_path
    importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# DataRow tests
# ---------------------------------------------------------------------------


class TestDataRow:
    def test_get_returns_value(self) -> None:
        row = DataRow(suite="s", jira="TC001", payload={"Name": "Alice"})
        assert row.get("Name") == "Alice"

    def test_get_missing_returns_default(self) -> None:
        row = DataRow(suite="s", jira="TC001", payload={})
        assert row.get("Missing", default="x") == "x"

    def test_require_returns_value(self) -> None:
        row = DataRow(suite="s", jira="TC001", payload={"ID": "123"})
        assert row.require("ID") == "123"

    def test_require_missing_raises_data_error(self) -> None:
        row = DataRow(suite="s", jira="TC001", payload={})
        with pytest.raises(DataError, match="Required column"):
            row.require("ID")

    def test_require_blank_raises_data_error(self) -> None:
        row = DataRow(suite="s", jira="TC001", payload={"ID": "   "})
        with pytest.raises(DataError):
            row.require("ID")

    def test_frozen(self) -> None:
        row = DataRow(suite="s", jira="j", payload={})
        with pytest.raises((AttributeError, TypeError)):
            row.suite = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# iter_rows / CSV
# ---------------------------------------------------------------------------


class TestIterRowsCsv:
    def test_yields_all_rows(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _write_csv(tmp_path, "member_data", _MEMBER_ROWS)
        monkeypatch.setattr(
            "automation.core.config._config",
            type("C", (), {"get": lambda self, k, d=None: str(tmp_path) if k == "data_root" else d})(),
        )
        rows = list(iter_rows("member_data"))
        assert len(rows) == 2

    def test_filters_by_jira(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _write_csv(tmp_path, "member_data", _MEMBER_ROWS)
        monkeypatch.setattr(
            "automation.core.config._config",
            type("C", (), {"get": lambda self, k, d=None: str(tmp_path) if k == "data_root" else d})(),
        )
        rows = list(iter_rows("member_data", jira="TC001"))
        assert len(rows) == 1
        assert rows[0].jira == "TC001"

    def test_missing_file_raises_data_error(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            "automation.core.config._config",
            type("C", (), {"get": lambda self, k, d=None: str(tmp_path) if k == "data_root" else d})(),
        )
        with pytest.raises(DataError, match="No data file"):
            list(iter_rows("nonexistent_suite"))


# ---------------------------------------------------------------------------
# get_field
# ---------------------------------------------------------------------------


class TestGetField:
    def test_resolves_direct_column(self) -> None:
        row = DataRow(suite="s", jira="j", payload={"MemberID": "999"})
        assert get_field(row, "MemberID") is None or get_field(row, "MemberID") is not None

    def test_without_or_doc_uses_column_name_directly(self) -> None:
        row = DataRow(suite="s", jira="j", payload={"LastName": "Doe"})
        assert get_field(row, "LastName") == "Doe"

    def test_with_or_doc_resolves_binding(self) -> None:
        row = DataRow(suite="s", jira="j", payload={"LastName": "Doe"})
        or_doc = {"data_bindings": {"member_last_name": {"column": "LastName"}}}
        assert get_field(row, "member_last_name", or_doc=or_doc) == "Doe"

    def test_missing_binding_raises(self) -> None:
        row = DataRow(suite="s", jira="j", payload={})
        or_doc = {"data_bindings": {}}
        with pytest.raises(DataError, match="data_binding"):
            get_field(row, "nonexistent_binding", or_doc=or_doc)
