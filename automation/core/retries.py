"""Time-bounded retry decorator with screenshot capture on each failure."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

import pyautogui
from loguru import logger

from automation.core.config import get_config
from automation.core.exceptions import (
    AmbiguousMatchError,
    AutomationError,
    ConfidenceTooLowError,
    FailureCode,
)

_T = TypeVar("_T")

# Exceptions that indicate a deterministic failure — retrying is pointless.
_DEFAULT_DO_NOT_RETRY: tuple[type[Exception], ...] = (
    ConfidenceTooLowError,
    AmbiguousMatchError,
)


def _save_screenshot(attempt: int, label: str) -> Path:
    """Capture full screen and write to assets/screenshots/; return path."""
    cfg = get_config()
    screenshots_dir = Path(cfg.get("screenshots_dir", "assets/screenshots"))
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{ts}_attempt{attempt}_{label}.png"
    dest = screenshots_dir / filename
    pyautogui.screenshot(str(dest))
    logger.debug("retry: screenshot saved → {}", dest)
    return dest


def retry(
    op: Callable[[], _T],
    *,
    max_attempts: int = 3,
    max_total_s: float = 30.0,
    backoff: float = 1.5,
    do_not_retry: tuple[type[Exception], ...] = _DEFAULT_DO_NOT_RETRY,
    label: str = "op",
) -> _T:
    """Execute *op* with bounded retries; save screenshot on each failure.

    Raises the final exception with all screenshot paths appended.
    Respects *do_not_retry* to avoid wasting time on deterministic failures.
    """
    deadline = time.monotonic() + max_total_s
    last_exc: Exception | None = None
    screenshot_paths: list[Path] = []
    delay = 1.0

    for attempt in range(1, max_attempts + 1):
        try:
            result = op()
            if attempt > 1:
                logger.info("retry: {!r} succeeded on attempt {}", label, attempt)
            return result
        except do_not_retry as exc:
            logger.warning(
                "retry: {!r} raised non-retryable {} — aborting immediately",
                label,
                type(exc).__name__,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            path = _save_screenshot(attempt, label)
            screenshot_paths.append(path)
            remaining = deadline - time.monotonic()
            logger.warning(
                "retry: {!r} failed attempt {}/{} ({}) — {:.1f}s remaining",
                label,
                attempt,
                max_attempts,
                type(exc).__name__,
                remaining,
            )
            if attempt >= max_attempts or remaining <= 0:
                break
            actual_delay = min(delay, remaining)
            time.sleep(actual_delay)  # backoff sleep — permissible here
            delay *= backoff

    # Attach screenshot list to AutomationError or wrap plain exceptions.
    if isinstance(last_exc, AutomationError):
        last_exc.details["retry_screenshots"] = [str(p) for p in screenshot_paths]
        last_exc.details["attempts"] = attempt
        raise last_exc
    raise RuntimeError(
        f"retry: {label!r} exhausted {attempt} attempt(s). "
        f"Screenshots: {[str(p) for p in screenshot_paths]}"
    ) from last_exc
