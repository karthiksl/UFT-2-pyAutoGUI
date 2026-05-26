"""Coverage-screen atomic tasks for the SAMPLE_TEST_000001 dry-run flow."""

from __future__ import annotations

from automation.common import Context
from automation.core import ocr


def assert_effective_date_via_ocr(ctx: Context, expected_date: str) -> None:
    ocr.assert_text("sample_coverage.effective_date_value", expected_date, mode="contains")
