"""Deterministic failure hierarchy for the automation framework."""

from __future__ import annotations

from enum import auto
from pathlib import Path
from typing import Any

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum


class FailureCode(StrEnum):
    UI_NOT_FOUND = auto()
    TIMEOUT = auto()
    APP_HANG = auto()
    UNEXPECTED_SCREEN = auto()
    CONFIDENCE_TOO_LOW = auto()
    AMBIGUOUS_MATCH = auto()
    POST_ACTION_STATE_NOT_REACHED = auto()
    CITRIX_NOT_FOCUSED = auto()
    CITRIX_SESSION_ERROR = auto()
    OCR_LOW_CONFIDENCE = auto()
    OCR_TEXT_MISMATCH = auto()
    DATA_ERROR = auto()
    CONFIG_ERROR = auto()


class AutomationError(Exception):
    """Base exception; all framework errors are a subclass of this."""

    code: FailureCode
    logical_name: str | None
    screen: str | None
    screenshot_path: str | None
    details: dict[str, Any]

    def __init__(
        self,
        message: str,
        *,
        code: FailureCode,
        logical_name: str | None = None,
        screen: str | None = None,
        screenshot_path: str | Path | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.logical_name = logical_name
        self.screen = screen
        self.screenshot_path = str(screenshot_path) if screenshot_path else None
        self.details = details or {}

    def __str__(self) -> str:
        parts = [f"[{self.code}] {super().__str__()}"]
        if self.logical_name:
            parts.append(f"  logical_name={self.logical_name!r}")
        if self.screen:
            parts.append(f"  screen={self.screen!r}")
        if self.screenshot_path:
            parts.append(f"  screenshot={self.screenshot_path}")
        if self.details:
            parts.append(f"  details={self.details}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# One subclass per FailureCode — callers may catch specific types.
# ---------------------------------------------------------------------------


class UiNotFoundError(AutomationError):
    """Image anchor was not located within the bounded region."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.UI_NOT_FOUND, **kwargs)


class TimeoutError(AutomationError):  # noqa: A001 — intentional shadow
    """A wait predicate did not succeed within the allowed time."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.TIMEOUT, **kwargs)


class AppHangError(AutomationError):
    """The target application stopped responding."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.APP_HANG, **kwargs)


class UnexpectedScreenError(AutomationError):
    """A screen appeared that the flow did not anticipate."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.UNEXPECTED_SCREEN, **kwargs)


class ConfidenceTooLowError(AutomationError):
    """Best image-match score is below the minimum acceptable threshold."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.CONFIDENCE_TOO_LOW, **kwargs)


class AmbiguousMatchError(AutomationError):
    """Two or more matches exceeded the confidence threshold simultaneously."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.AMBIGUOUS_MATCH, **kwargs)


class PostActionStateNotReachedError(AutomationError):
    """Expected post-click state anchor was not seen within the timeout."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.POST_ACTION_STATE_NOT_REACHED, **kwargs)


class CitrixNotFocusedError(AutomationError):
    """The Citrix ICA window is not the active foreground window."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.CITRIX_NOT_FOCUSED, **kwargs)


class CitrixSessionError(AutomationError):
    """Citrix session is disconnected, reconnecting, or locked."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.CITRIX_SESSION_ERROR, **kwargs)


class OcrLowConfidenceError(AutomationError):
    """OCR extraction confidence is below the required minimum."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.OCR_LOW_CONFIDENCE, **kwargs)


class OcrTextMismatchError(AutomationError):
    """OCR-extracted text did not match the expected value."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.OCR_TEXT_MISMATCH, **kwargs)


class DataError(AutomationError):
    """Test data is missing, malformed, or fails validation."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.DATA_ERROR, **kwargs)


class ConfigError(AutomationError):
    """Framework or OR configuration is invalid."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, code=FailureCode.CONFIG_ERROR, **kwargs)
