"""Unit tests for automation.common.Context."""

from __future__ import annotations

from unittest.mock import MagicMock

from automation.common import Context
from automation.common.data import DataRow


class TestContext:
    def _make_ctx(self) -> Context:
        return Context(or_repo=MagicMock())

    def test_default_row_is_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.row is None

    def test_set_and_get_extra(self) -> None:
        ctx = self._make_ctx()
        ctx.set("key", "value")
        assert ctx.get("key") == "value"

    def test_get_missing_returns_default(self) -> None:
        ctx = self._make_ctx()
        assert ctx.get("missing", "fallback") == "fallback"

    def test_row_can_be_assigned(self) -> None:
        ctx = self._make_ctx()
        row = DataRow(suite="s", jira="j", payload={})
        ctx.row = row
        assert ctx.row is row

    def test_extra_defaults_to_empty_dict(self) -> None:
        ctx = self._make_ctx()
        assert ctx.extra == {}
