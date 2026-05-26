"""Unit tests for automation.common.poms — verify all POM constants are strings.

These tests do not touch the Visual OR or any UI; they just assert the module
structure matches the expected convention.
"""

from __future__ import annotations

import importlib
import re

import pytest

_POM_MODULES = [
    "automation.common.poms.epic_login",
    "automation.common.poms.epic_home",
    "automation.common.poms.member_search",
    "automation.common.poms.member_chart",
    "automation.common.poms.member_demographics",
    "automation.common.poms.enrollment",
    "automation.common.poms.coverage_change",
    "automation.common.poms.plan_selection",
    "automation.common.poms.dependent_management",
    "automation.common.poms.confirmation",
    "automation.common.poms.notes",
    "automation.common.poms.error_dialog",
]

_OR_NAME_RE = re.compile(r"^[a-z_0-9]+\.[a-z_0-9]+$")


@pytest.mark.parametrize("module_path", _POM_MODULES)
class TestPomModule:
    def test_module_imports(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        assert mod is not None

    def test_screen_constant_is_string(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "SCREEN"), f"{module_path} must define SCREEN"
        assert isinstance(mod.SCREEN, str)
        assert "_" in mod.SCREEN or mod.SCREEN.islower()

    def test_or_names_follow_convention(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        for attr in dir(mod):
            if not attr.isupper() or attr == "SCREEN":
                continue
            value = getattr(mod, attr)
            if not isinstance(value, str):
                continue
            assert _OR_NAME_RE.match(value), (
                f"{module_path}.{attr} = {value!r} does not match '<screen>.<object>' convention"
            )

    def test_screen_prefix_matches_screen_constant(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        screen = getattr(mod, "SCREEN", None)
        if screen is None:
            return
        for attr in dir(mod):
            if not attr.isupper() or attr == "SCREEN":
                continue
            value = getattr(mod, attr)
            if isinstance(value, str) and "." in value:
                prefix = value.split(".")[0]
                assert prefix == screen, (
                    f"{module_path}.{attr} prefix {prefix!r} != SCREEN {screen!r}"
                )
