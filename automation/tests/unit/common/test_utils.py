"""Unit tests for automation.common.utils."""

from __future__ import annotations

import pytest

from automation.common.utils import (
    format_date_epic,
    mask_sensitive,
    normalize_key,
    normalize_name,
    parse_date,
    retry_with_jitter,
    safe_float,
    safe_int,
    safe_str,
)


class TestNormalizeName:
    def test_strips_leading_trailing_whitespace(self) -> None:
        assert normalize_name("  hello  ") == "hello"

    def test_collapses_internal_spaces(self) -> None:
        assert normalize_name("John   Doe") == "John Doe"

    def test_folds_unicode_to_ascii(self) -> None:
        assert normalize_name("José") == "Jose"

    def test_empty_string(self) -> None:
        assert normalize_name("") == ""


class TestMaskSensitive:
    def test_masks_all_but_last_four(self) -> None:
        assert mask_sensitive("123456789") == "*****6789"

    def test_short_value_fully_masked(self) -> None:
        result = mask_sensitive("abc")
        assert result == "***"

    def test_custom_visible_tail(self) -> None:
        assert mask_sensitive("secretvalue", visible_tail=2) == "*********ue"

    def test_exact_length_value(self) -> None:
        assert mask_sensitive("1234", visible_tail=4) == "1234"


class TestNormalizeKey:
    def test_lowercases(self) -> None:
        assert normalize_key("HELLO") == "hello"

    def test_strips_whitespace(self) -> None:
        assert normalize_key("  hi  ") == "hi"

    def test_collapses_spaces(self) -> None:
        assert normalize_key("a  b") == "a b"


class TestParseDate:
    def test_mm_dd_yyyy(self) -> None:
        d = parse_date("01/15/2024")
        assert d.year == 2024 and d.month == 1 and d.day == 15

    def test_iso_format(self) -> None:
        d = parse_date("2024-06-30")
        assert d.year == 2024 and d.month == 6

    def test_yyyymmdd(self) -> None:
        d = parse_date("20241231")
        assert d.year == 2024 and d.day == 31

    def test_invalid_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestFormatDateEpic:
    def test_formats_as_mm_dd_yyyy(self) -> None:
        result = format_date_epic("2024-03-15")
        assert result == "03/15/2024"

    def test_accepts_date_object(self) -> None:
        from datetime import date
        result = format_date_epic(date(2024, 1, 1))
        assert result == "01/01/2024"


class TestSafeCasts:
    def test_safe_int_valid(self) -> None:
        assert safe_int("42") == 42

    def test_safe_int_invalid_returns_default(self) -> None:
        assert safe_int("abc", default=7) == 7

    def test_safe_float_valid(self) -> None:
        assert safe_float("3.14") == pytest.approx(3.14)

    def test_safe_float_invalid_returns_default(self) -> None:
        assert safe_float("nope", default=1.5) == pytest.approx(1.5)

    def test_safe_str_strips(self) -> None:
        assert safe_str("  hi  ") == "hi"

    def test_safe_str_none_returns_default(self) -> None:
        assert safe_str(None, default="x") == "x"


class TestRetryWithJitter:
    def test_succeeds_on_first_attempt(self) -> None:
        calls = []

        def op() -> int:
            calls.append(1)
            return 42

        result = retry_with_jitter(op, label="test")
        assert result == 42
        assert len(calls) == 1

    def test_retries_and_succeeds(self) -> None:
        attempts = {"n": 0}

        def op() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("not yet")
            return "ok"

        result = retry_with_jitter(op, max_attempts=3, backoff_s=0.0, label="retry_test")
        assert result == "ok"
        assert attempts["n"] == 3

    def test_raises_after_max_attempts(self) -> None:
        def op() -> None:
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="always fails|failed after"):
            retry_with_jitter(op, max_attempts=2, backoff_s=0.0)
