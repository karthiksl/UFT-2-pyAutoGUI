"""Unit tests for automation.common.elements.ElementRegistry."""

from __future__ import annotations

import pytest

from automation.common.elements import ElementRegistry
from automation.core.exceptions import ConfigError


class TestRegisterAndResolve:
    def test_exact_match_resolves(self) -> None:
        reg = ElementRegistry()
        reg.register("save button", "enrollment.save_button", screen="enrollment")
        assert reg.resolve("save button", screen="enrollment") == "enrollment.save_button"

    def test_global_scope_resolves_without_screen(self) -> None:
        reg = ElementRegistry()
        reg.register("ok button", "error_dialog.ok_button")
        assert reg.resolve("ok button") == "error_dialog.ok_button"

    def test_screen_scoped_takes_priority_over_global(self) -> None:
        reg = ElementRegistry()
        reg.register("cancel", "global.cancel_button")
        reg.register("cancel", "enrollment.cancel_button", screen="enrollment")
        assert reg.resolve("cancel", screen="enrollment") == "enrollment.cancel_button"

    def test_missing_label_raises_config_error(self) -> None:
        reg = ElementRegistry()
        with pytest.raises(ConfigError, match="cannot resolve"):
            reg.resolve("nonexistent label")

    def test_len_counts_all_entries(self) -> None:
        reg = ElementRegistry()
        reg.register("a", "x.a")
        reg.register("b", "x.b")
        assert len(reg) == 2


class TestLoadPom:
    def test_load_pom_registers_upper_constants(self) -> None:
        from automation.common.poms import enrollment as pom
        reg = ElementRegistry()
        reg.load_pom(pom)
        # SUBMIT_ENROLLMENT_BTN should have been registered
        result = reg.resolve("submit_enrollment_btn", screen="enrollment")
        assert result == "enrollment.submit_enrollment_button"

    def test_non_string_attributes_ignored(self) -> None:
        class FakePom:
            VALID = "screen.some_button"
            NUMBER = 42  # not a string — must be ignored
            SCREEN = "screen"  # string but SCREEN constant is still valid

        reg = ElementRegistry()
        reg.load_pom(FakePom)
        assert reg.resolve("valid", screen="screen") == "screen.some_button"

    def test_all_for_screen_returns_registered(self) -> None:
        reg = ElementRegistry()
        reg.register("btn_a", "notes.btn_a", screen="notes")
        reg.register("btn_b", "notes.btn_b", screen="notes")
        entries = reg.all_for_screen("notes")
        assert len(entries) == 2
