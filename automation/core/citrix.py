"""Citrix session focus and health probes.

On non-Windows platforms (macOS / Linux dev boxes) all functions degrade to
no-ops with a logged warning so the package imports cleanly for unit tests.
"""

from __future__ import annotations

import platform
import time
from enum import auto
from typing import TYPE_CHECKING

from loguru import logger
try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from automation.core.config import get_config
from automation.core.exceptions import CitrixNotFocusedError, CitrixSessionError

if TYPE_CHECKING:
    pass

_IS_WINDOWS = platform.system() == "Windows"

# Lazy-import pygetwindow / pywinauto only on Windows.
if _IS_WINDOWS:
    try:
        import pygetwindow as gw  # type: ignore[import]
    except ImportError:  # pragma: no cover
        gw = None  # type: ignore[assignment]
    try:
        import pywinauto  # type: ignore[import]
    except ImportError:  # pragma: no cover
        pywinauto = None  # type: ignore[assignment]
else:
    gw = None  # type: ignore[assignment]
    pywinauto = None  # type: ignore[assignment]


class SessionState(StrEnum):
    ACTIVE = auto()
    RECONNECTING = auto()
    DISCONNECTED = auto()
    LOCKED = auto()
    UNKNOWN = auto()


def _warn_non_windows(fn_name: str) -> None:
    logger.warning(
        "citrix.{}: non-Windows platform — skipping Citrix focus check", fn_name
    )


def _get_citrix_window_title() -> str:
    return get_config().get("citrix_window_title", "Citrix Viewer")


def _find_citrix_window():
    """Return the Citrix window object, or None if not found."""
    if gw is None:
        return None
    title = _get_citrix_window_title()
    windows = gw.getWindowsWithTitle(title)
    return windows[0] if windows else None


def ensure_citrix_focused(timeout: float = 5.0) -> None:
    """Assert the Citrix ICA window is the active foreground window.

    Raises CitrixNotFocusedError after *timeout* seconds if focus cannot be
    obtained. No-op on non-Windows with a warning.
    """
    if not _IS_WINDOWS:
        _warn_non_windows("ensure_citrix_focused")
        return

    deadline = time.monotonic() + timeout
    title = _get_citrix_window_title()

    while time.monotonic() < deadline:
        win = _find_citrix_window()
        if win is not None:
            try:
                win.activate()
                time.sleep(0.2)  # allow OS to complete focus switch
                active = gw.getActiveWindow()
                if active and title in (active.title or ""):
                    logger.debug("citrix: window {!r} is focused", title)
                    return
            except Exception as exc:  # noqa: BLE001
                logger.debug("citrix: activate raised {} — retrying", type(exc).__name__)
        time.sleep(0.3)

    raise CitrixNotFocusedError(
        f"Could not focus Citrix window {title!r} within {timeout}s.",
        details={"citrix_window_title": title},
    )


def get_session_state() -> SessionState:
    """Return the current Citrix session state.

    Returns SessionState.ACTIVE on non-Windows (safe default for dev).
    """
    if not _IS_WINDOWS:
        _warn_non_windows("get_session_state")
        return SessionState.ACTIVE

    win = _find_citrix_window()
    if win is None:
        return SessionState.DISCONNECTED

    # Heuristic: minimised window often signals a dropped/locked session.
    try:
        if win.isMinimized:
            return SessionState.RECONNECTING
    except Exception:  # noqa: BLE001
        pass

    # TODO(prompt-NN): add image-anchor checks for disconnected / locked overlays
    # defined in epic_or.yaml under screen="citrix_system".
    return SessionState.ACTIVE


def assert_session_healthy() -> None:
    """Raise CitrixSessionError when the session is not ACTIVE.

    No-op on non-Windows with a warning.
    """
    if not _IS_WINDOWS:
        _warn_non_windows("assert_session_healthy")
        return

    state = get_session_state()
    if state != SessionState.ACTIVE:
        raise CitrixSessionError(
            f"Citrix session is not healthy: state={state}",
            details={"session_state": str(state)},
        )
    logger.debug("citrix: session is healthy ({})", state)


def get_session_rect() -> tuple[int, int, int, int]:
    """Return (x, y, width, height) of the Citrix session window in screen pixels.

    On non-Windows returns (0, 0, screen_w, screen_h) so region offsets are
    identity transforms — safe for macOS/Linux dev boxes.
    """
    if not _IS_WINDOWS:
        _warn_non_windows("get_session_rect")
        try:
            import pyautogui  # type: ignore[import]
            w, h = pyautogui.size()
        except Exception:  # noqa: BLE001
            w, h = 1920, 1080
        return (0, 0, w, h)

    win = _find_citrix_window()
    if win is None:
        raise CitrixNotFocusedError(
            f"Citrix window {_get_citrix_window_title()!r} not found — "
            "cannot determine session rect.",
            details={"citrix_window_title": _get_citrix_window_title()},
        )
    try:
        return (int(win.left), int(win.top), int(win.width), int(win.height))
    except Exception as exc:  # noqa: BLE001
        raise CitrixSessionError(
            f"Cannot read Citrix window rect: {exc}",
            details={"error": str(exc)},
        ) from exc
