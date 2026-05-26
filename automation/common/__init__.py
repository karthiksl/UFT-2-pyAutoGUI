"""Shared business helpers — migrated from FunctionLibrary/*.qfl.

# Migration notes
# UFT counterpart: FunctionLibrary/*.qfl (shared library loaded via
#   ExecuteFile / LoadFunctionLibrary at suite startup)
# Inferred public surface:
#   Context — replaces UFT's implicit global Env object + Reporter reference
#   DataRow  — wraps a single Excel row (previously accessed as row("ColName"))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loguru import Logger

    from automation.common.data import DataRow
    from automation.common.reporting_legacy import ReporterAdapter
    from automation.core.or_loader import VisualOR


@dataclass
class Context:
    """Runtime bundle passed through every test flow.

    Replaces UFT's implicit global state (Environment variables, Reporter,
    shared DataTable references).  All business code receives a Context
    instance rather than importing globals.
    """

    or_repo: "VisualOR"
    row: "DataRow | None" = field(default=None)
    logger: "Logger | None" = field(default=None)
    reporter: "ReporterAdapter | None" = field(default=None)
    extra: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Return a value from the extra bag by key."""
        return self.extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store a value in the extra bag."""
        self.extra[key] = value
