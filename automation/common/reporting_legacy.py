"""Adapter that translates UFT Reporter.ReportEvent calls to Python logging.

# Migration notes
# UFT counterpart: Implicit Reporter object (Reporter.ReportEvent)
# Inferred functions:
#   MicStatus       ← micPass / micFail / micWarning / micInfo constants
#   ReporterAdapter ← thin wrapper around Reporter.ReportEvent(eStatus, sStepName, sDetails)
#     .report_event(status, step_name, details)  ← Reporter.ReportEvent
#     .passed(step_name, details)                ← Reporter.ReportEvent micPass, ...
#     .failed(step_name, details)                ← Reporter.ReportEvent micFail, ...
#     .warning(step_name, details)               ← Reporter.ReportEvent micWarning, ...
#     .info(step_name, details)                  ← Reporter.ReportEvent micInfo, ...
# The UFT micXxx integer constants are preserved so existing callers can pass
# them directly without changing call sites.
"""

from __future__ import annotations

from enum import IntEnum

from loguru import logger as _root_logger
try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum


class MicStatus(IntEnum):
    """UFT Reporter status constants mapped to Python ints.

    Values match the UFT micPass / micFail / micWarning / micInfo constants.
    """

    PASS = 0      # micPass
    FAIL = 1      # micFail
    WARNING = 2   # micWarning
    INFO = 3      # micInfo
    DONE = 4      # micDone


class _ReportLevel(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    INFO = "INFO"
    DONE = "DONE"


_STATUS_TO_LEVEL: dict[int, _ReportLevel] = {
    MicStatus.PASS: _ReportLevel.PASS,
    MicStatus.FAIL: _ReportLevel.FAIL,
    MicStatus.WARNING: _ReportLevel.WARNING,
    MicStatus.INFO: _ReportLevel.INFO,
    MicStatus.DONE: _ReportLevel.DONE,
}


class ReporterAdapter:
    """Translates UFT Reporter.ReportEvent(...) calls to loguru log entries.

    Optionally forwards to allure (when allure-python-commons is installed).
    """

    def __init__(self, test_id: str = "", *, allure_enabled: bool = False) -> None:
        self.test_id = test_id
        self._allure_enabled = allure_enabled
        self._events: list[dict] = []

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def report_event(
        self,
        status: int | MicStatus,
        step_name: str,
        details: str = "",
    ) -> None:
        """Log one report event; mirrors UFT Reporter.ReportEvent signature."""
        level = _STATUS_TO_LEVEL.get(int(status), _ReportLevel.INFO)
        tag = f"[{self.test_id}] " if self.test_id else ""
        msg = f"{tag}{step_name}" + (f" — {details}" if details else "")
        self._events.append({"status": level, "step": step_name, "details": details})

        if level == _ReportLevel.FAIL:
            _root_logger.error("REPORT FAIL  | {}", msg)
        elif level == _ReportLevel.WARNING:
            _root_logger.warning("REPORT WARN  | {}", msg)
        elif level == _ReportLevel.PASS:
            _root_logger.success("REPORT PASS  | {}", msg)
        else:
            _root_logger.info("REPORT {}  | {}", level, msg)

        if self._allure_enabled:
            self._emit_allure(level, step_name, details)

    # ------------------------------------------------------------------
    # Convenience shortcuts matching UFT call patterns
    # ------------------------------------------------------------------

    def passed(self, step_name: str, details: str = "") -> None:
        """Log a passing step — micPass equivalent."""
        self.report_event(MicStatus.PASS, step_name, details)

    def failed(self, step_name: str, details: str = "") -> None:
        """Log a failing step — micFail equivalent."""
        self.report_event(MicStatus.FAIL, step_name, details)

    def warning(self, step_name: str, details: str = "") -> None:
        """Log a warning — micWarning equivalent."""
        self.report_event(MicStatus.WARNING, step_name, details)

    def info(self, step_name: str, details: str = "") -> None:
        """Log an info event — micInfo equivalent."""
        self.report_event(MicStatus.INFO, step_name, details)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def events(self) -> list[dict]:
        """Return a copy of all recorded events (for test assertions)."""
        return list(self._events)

    def has_failures(self) -> bool:
        """Return True when any FAIL event was recorded."""
        return any(e["status"] == _ReportLevel.FAIL for e in self._events)

    def reset(self) -> None:
        """Clear recorded events — call between test cases in a suite run."""
        self._events.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit_allure(self, level: _ReportLevel, step_name: str, details: str) -> None:
        # inferred: needs review — wire to allure-python-commons when available
        try:
            import allure  # type: ignore[import]
            allure.attach(details or step_name, name=step_name, attachment_type=allure.attachment_type.TEXT)
        except ImportError:
            pass
