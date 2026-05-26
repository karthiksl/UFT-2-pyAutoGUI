"""Unit tests for automation.common.steps."""

from __future__ import annotations

import pytest

import automation.common.steps as steps_mod
from automation.common.steps import STEP_REGISTRY, clear_registry, execute_step, list_steps, step


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Clear the global step registry before each test."""
    clear_registry()


class TestStepDecorator:
    def test_registers_pattern(self) -> None:
        @step(r"I click (?P<label>.+)")
        def do_click(ctx, label: str) -> str:
            return f"clicked:{label}"

        assert len(STEP_REGISTRY) == 1

    def test_execute_matches_and_calls(self) -> None:
        @step(r"I type (?P<text>.+) into (?P<field>.+)")
        def do_type(ctx, text: str, field: str) -> str:
            return f"{text}→{field}"

        result = execute_step(None, "I type hello into username")
        assert result == "hello→username"

    def test_execute_no_match_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="No step registered"):
            execute_step(None, "this step does not exist")

    def test_case_insensitive_matching(self) -> None:
        @step(r"open the (?P<screen>\w+) screen")
        def open_screen(ctx, screen: str) -> str:
            return screen

        result = execute_step(None, "OPEN THE enrollment SCREEN")
        assert result == "enrollment"

    def test_list_steps_returns_pattern_strings(self) -> None:
        @step(r"dummy step")
        def dummy(ctx) -> None:
            pass

        patterns = list_steps()
        assert any("dummy step" in p for p in patterns)

    def test_clear_registry_empties(self) -> None:
        @step(r"some step")
        def some(ctx) -> None:
            pass

        clear_registry()
        assert len(STEP_REGISTRY) == 0
