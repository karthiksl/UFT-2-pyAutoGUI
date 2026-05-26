"""Home-screen atomic tasks for the SAMPLE_TEST_000001 dry-run flow."""

from __future__ import annotations

from automation.common import Context
from automation.common.poms import sample_coverage as coverage_pom
from automation.common.poms import sample_home as home_pom
from automation.core import actions, ocr


def assert_mrn_via_ocr(ctx: Context, expected_mrn: str) -> None:
    ocr.assert_text("sample_home.mrn_text", expected_mrn, mode="contains")


def open_coverage_tab(ctx: Context) -> None:
    actions.click(home_pom.COVERAGE_TAB, expect_after=coverage_pom.HEADER_LABEL)
