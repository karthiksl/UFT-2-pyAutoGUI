"""E2E dry-run test for SAMPLE_TEST_000001 (mock member-view flow).

This is the canonical "hello world" for the framework. It exercises the
sample flow at automation/tests/flows/sample/flow_sample_member_view.py
against the mock screens served by fixtures/sample_uft/screen_player.py.

Run:
    pytest -m e2e_sample -q

Prerequisites:
    python fixtures/sample_uft/screen_player.py          (Terminal 1, keep running)
    python fixtures/sample_uft/generate_mock_screens.py  (once)

Data file:
    fixtures/sample_uft/data/SAMPLE_TEST_000001.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from loguru import logger

from automation.common import Context
from automation.common.data import DataRow
from automation.common.reporting_legacy import ReporterAdapter

_CSV_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "fixtures"
    / "sample_uft"
    / "data"
    / "SAMPLE_TEST_000001.csv"
)


def _load_csv() -> list[dict[str, str]]:
    with _CSV_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_CSV_ROWS = _load_csv()


@pytest.mark.e2e_sample
@pytest.mark.parametrize(
    "csv_row",
    _CSV_ROWS,
    ids=[r["TestCaseID"] for r in _CSV_ROWS],
)
def test_sample_member_view(
    csv_row: dict[str, str],
    sample_or_repo,
    reset_screen_player,
) -> None:
    """Full member-view flow: login → MRN OCR → coverage tab → date OCR."""
    from automation.tests.flows.sample.flow_sample_member_view import (
        flow_sample_member_view,
    )

    row = DataRow(
        suite="SAMPLE_TEST_000001",
        jira=csv_row["TestCaseID"],
        payload=dict(csv_row),
    )
    reporter = ReporterAdapter()
    ctx = Context(
        or_repo=sample_or_repo,
        row=row,
        logger=logger,
        reporter=reporter,
    )

    flow_sample_member_view(ctx, row)

    assert not reporter.has_failures(), (
        f"Reporter recorded failures for {row.jira}:\n"
        + "\n".join(str(e) for e in reporter.events())
    )
