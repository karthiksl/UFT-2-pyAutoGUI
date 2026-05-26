"""End-to-end flow: Login → assert MRN → open Coverage → assert Effective Date.

Migrated from SAMPLE_TEST_000001.qfl.md.

SAMPLE_FORCE_FAIL=1
    Substitute an obviously wrong MRN ("0000000") so the OCR assertion raises
    OcrTextMismatchError deterministically — useful for verifying that the
    failure path (screenshot capture, reporter.failed, exception propagation)
    works correctly without requiring a real broken application.
"""

from __future__ import annotations

import os

from automation.common import Context
from automation.common.data import DataRow
from automation.core import retries
from automation.core.exceptions import OcrTextMismatchError
from automation.tests.tasks.sample import task_coverage, task_home, task_login


def flow_sample_member_view(ctx: Context, row: DataRow) -> None:
    """Execute the full member-view sample flow against screen_player.py."""
    force_fail = os.environ.get("SAMPLE_FORCE_FAIL", "0") == "1"

    username = str(row.require("MemberID"))
    password = "sample_pass"
    expected_mrn = str(row.require("MemberID"))
    expected_date = str(row.require("CoverageEffectiveDate"))

    if force_fail:
        expected_mrn = "0000000"

    # ── Step 1: Login ────────────────────────────────────────────────────────
    task_login.enter_username(ctx, username)
    task_login.enter_password(ctx, password)
    task_login.click_login(ctx)

    # ── Step 2: Verify patient MRN on Home screen ────────────────────────────
    # OcrTextMismatchError is retryable — transient screen transitions may
    # produce a partial frame.  ConfidenceTooLowError is not retried.
    retries.retry(
        lambda: task_home.assert_mrn_via_ocr(ctx, expected_mrn),
        label="assert_mrn",
        max_attempts=2,
        max_total_s=10.0,
    )

    # ── Step 3: Navigate to Coverage tab ────────────────────────────────────
    task_home.open_coverage_tab(ctx)

    # ── Step 4: Verify Effective Date on Coverage screen ────────────────────
    retries.retry(
        lambda: task_coverage.assert_effective_date_via_ocr(ctx, expected_date),
        label="assert_coverage_date",
        max_attempts=2,
        max_total_s=10.0,
    )

    # ── Step 5: Report pass ──────────────────────────────────────────────────
    if ctx.reporter is not None:
        ctx.reporter.passed(
            "flow_sample_member_view",
            f"TestCaseID={row.get('TestCaseID')} MRN={row.get('MemberID')} "
            f"CoverageEffectiveDate={expected_date}",
        )
