"""Unit tests for automation.common.element_utils."""

from __future__ import annotations

from automation.common.element_utils import best_match, normalize_key, similarity


class TestNormalizeKey:
    def test_lowercases_and_strips(self) -> None:
        assert normalize_key("  HELLO  ") == "hello"

    def test_spaces_and_underscores_become_underscore(self) -> None:
        assert normalize_key("save button") == "save_button"

    def test_hyphens_become_underscore(self) -> None:
        assert normalize_key("cancel-btn") == "cancel_btn"

    def test_unicode_folded(self) -> None:
        assert normalize_key("résumé") == "resume"


class TestSimilarity:
    def test_identical_strings_score_one(self) -> None:
        assert similarity("submit", "submit") == pytest.approx(1.0)

    def test_totally_different_score_zero(self) -> None:
        assert similarity("apple", "orange") == pytest.approx(0.0)

    def test_partial_overlap_between_zero_and_one(self) -> None:
        score = similarity("submit enrollment button", "enrollment submit")
        assert 0.0 < score <= 1.0

    def test_empty_strings_score_one(self) -> None:
        assert similarity("", "") == pytest.approx(1.0)

    def test_one_empty_scores_zero(self) -> None:
        assert similarity("hello", "") == pytest.approx(0.0)


class TestBestMatch:
    def test_exact_match_returns_candidate(self) -> None:
        result = best_match("save_button", ["save_button", "cancel_button"])
        assert result == "save_button"

    def test_no_candidates_returns_none(self) -> None:
        assert best_match("anything", []) is None

    def test_below_threshold_returns_none(self) -> None:
        result = best_match("xyz_abc_def", ["hello", "world"], threshold=0.9)
        assert result is None

    def test_closest_candidate_selected(self) -> None:
        candidates = ["submit_enrollment_button", "cancel_button", "save_note_button"]
        result = best_match("enrollment submit", candidates, threshold=0.3)
        assert result == "submit_enrollment_button"


import pytest  # noqa: E402 — needed for approx
