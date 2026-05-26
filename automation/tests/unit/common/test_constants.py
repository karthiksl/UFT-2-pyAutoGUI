"""Unit tests for automation.common.constants."""

from __future__ import annotations

from automation.common.constants import AppConstants


class TestAppConstants:
    def test_singleton_is_frozen(self) -> None:
        try:
            AppConstants.DEFAULT_TIMEOUT = 999  # type: ignore[misc]
            assert False, "Should have raised"
        except (AttributeError, TypeError):
            pass

    def test_default_timeout_is_positive(self) -> None:
        assert AppConstants.DEFAULT_TIMEOUT > 0

    def test_epic_date_format_contains_percent(self) -> None:
        assert "%" in AppConstants.EPIC_DATE_FORMAT

    def test_coverage_types_non_empty(self) -> None:
        assert len(AppConstants.COVERAGE_TYPES) > 0
        assert "Medical" in AppConstants.COVERAGE_TYPES

    def test_plan_tiers_include_hmo(self) -> None:
        assert "HMO" in AppConstants.PLAN_TIERS

    def test_confirmation_statuses_include_accepted(self) -> None:
        assert "Accepted" in AppConstants.CONFIRMATION_STATUSES

    def test_mrn_min_less_than_max(self) -> None:
        assert AppConstants.MRN_MIN_DIGITS < AppConstants.MRN_MAX_DIGITS

    def test_ocr_min_confidence_in_range(self) -> None:
        assert 0.0 < AppConstants.OCR_MIN_CONFIDENCE <= 1.0
