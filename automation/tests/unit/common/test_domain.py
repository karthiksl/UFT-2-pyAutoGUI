"""Unit tests for automation.common.domain."""

from __future__ import annotations

from datetime import date

import pytest

from automation.common.domain import (
    format_date_for_epic,
    is_valid_member_id,
    normalize_change_reason,
    normalize_confirmation_status,
    normalize_coverage_type,
    normalize_plan_tier,
    parse_member_id,
    plan_tier_from_name,
)
from automation.core.exceptions import DataError


class TestParseMemberId:
    def test_valid_7_digit_mrn(self) -> None:
        assert parse_member_id("1234567") == "1234567"

    def test_strips_dashes(self) -> None:
        assert parse_member_id("123-456-7890") == "1234567890"

    def test_strips_spaces(self) -> None:
        assert parse_member_id("12 34 56") == "123456"

    def test_too_short_raises(self) -> None:
        with pytest.raises(DataError, match="Invalid member ID"):
            parse_member_id("123")

    def test_too_long_raises(self) -> None:
        with pytest.raises(DataError, match="Invalid member ID"):
            parse_member_id("12345678901")  # 11 digits

    def test_is_valid_wrapper_true(self) -> None:
        assert is_valid_member_id("1234567") is True

    def test_is_valid_wrapper_false(self) -> None:
        assert is_valid_member_id("abc") is False


class TestFormatDateForEpic:
    def test_string_input(self) -> None:
        assert format_date_for_epic("2024-01-15") == "01/15/2024"

    def test_date_object_input(self) -> None:
        assert format_date_for_epic(date(2024, 12, 31)) == "12/31/2024"

    def test_already_correct_format(self) -> None:
        assert format_date_for_epic("03/07/2025") == "03/07/2025"


class TestNormalizeCoverageType:
    def test_known_type_returns_canonical(self) -> None:
        assert normalize_coverage_type("medical") == "Medical"

    def test_mixed_case_accepted(self) -> None:
        assert normalize_coverage_type("DENTAL") == "Dental"

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(DataError, match="Unknown coverage type"):
            normalize_coverage_type("Imaginary")


class TestPlanTier:
    def test_extract_hmo_from_name(self) -> None:
        assert plan_tier_from_name("TEST Gold HMO Plus") == "HMO"

    def test_extract_ppo(self) -> None:
        assert plan_tier_from_name("TEST Silver PPO") == "PPO"

    def test_no_tier_returns_none(self) -> None:
        assert plan_tier_from_name("Unknown Plan") is None

    def test_normalize_ppo(self) -> None:
        assert normalize_plan_tier("ppo") == "PPO"

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(DataError, match="Unknown plan tier"):
            normalize_plan_tier("XYZ")


class TestNormalizeChangeReason:
    def test_exact_match(self) -> None:
        assert normalize_change_reason("New Hire") == "New Hire"

    def test_case_insensitive(self) -> None:
        assert normalize_change_reason("new hire") == "New Hire"

    def test_unknown_raises(self) -> None:
        with pytest.raises(DataError, match="Unknown change reason"):
            normalize_change_reason("Unknown Reason")


class TestNormalizeConfirmationStatus:
    def test_accepted(self) -> None:
        assert normalize_confirmation_status("accepted") == "Accepted"

    def test_pending(self) -> None:
        assert normalize_confirmation_status("PENDING") == "Pending"

    def test_unknown_raises(self) -> None:
        with pytest.raises(DataError):
            normalize_confirmation_status("maybe")
