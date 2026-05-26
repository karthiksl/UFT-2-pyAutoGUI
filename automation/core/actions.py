"""Two-phase click, type_text, and hotkey actions.

All input actions go through this module. Raw pixel coordinates are never
accepted here — only logical names resolved via or_loader + finder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyautogui
from loguru import logger

from automation.core.citrix import ensure_citrix_focused
from automation.core.config import get_config
from automation.core.exceptions import PostActionStateNotReachedError, UiNotFoundError
from automation.core.finder import locate
from automation.core.waits import wait_for_object_exists, wait_for_object_gone

if TYPE_CHECKING:
    from automation.core.or_loader import VisualOR

# Module-level OR reference — injected once at test session start.
_or_repo: "VisualOR | None" = None


def set_or_repo(or_repo: "VisualOR") -> None:
    """Inject the global OR repository used by all action helpers."""
    global _or_repo
    _or_repo = or_repo


def _get_spec(logical_name: str):
    """Resolve *logical_name* to ObjectSpec; raise if OR is not loaded."""
    if _or_repo is None:
        raise RuntimeError(
            "actions: OR repository is not loaded. Call set_or_repo() in conftest.py."
        )
    return _or_repo.get(logical_name)


def click(
    logical_name: str,
    *,
    expect_after: str | None = None,
    timeout: float | None = None,
    double: bool = False,
    button: str = "left",
) -> None:
    """Two-phase locate-then-click with optional post-action state assertion.

    Phase 1 — locate the target.
    Phase 2 — re-locate immediately before committing the click (guards against
               stale coordinates when the UI animated between phases).
    If *expect_after* is set, waits for that anchor to appear; otherwise waits
    for the clicked anchor to disappear or for any screen change.
    """
    cfg = get_config()
    t = timeout if timeout is not None else cfg.get("default_timeout", 30.0)
    spec = _get_spec(logical_name)

    ensure_citrix_focused()

    # Phase 1: locate
    match1 = locate(spec)
    if match1 is None:
        raise UiNotFoundError(
            f"click: Phase 1 — {logical_name!r} not found.",
            logical_name=logical_name,
            screen=spec.screen,
        )

    # Phase 2: re-locate to confirm position is stable
    match2 = locate(spec)
    if match2 is None:
        raise UiNotFoundError(
            f"click: Phase 2 — {logical_name!r} disappeared between locate calls.",
            logical_name=logical_name,
            screen=spec.screen,
        )

    x, y = match2.center_x, match2.center_y
    logger.info(
        "click: {!r} @ ({},{}) conf={:.3f} button={}{}",
        logical_name,
        x,
        y,
        match2.confidence,
        button,
        " [double]" if double else "",
    )

    click_fn = pyautogui.doubleClick if double else pyautogui.click
    click_fn(x, y, button=button)

    # Post-action state assertion.
    if expect_after is not None:
        after_spec = _get_spec(expect_after)
        try:
            wait_for_object_exists(after_spec, timeout=t)
        except Exception as exc:
            raise PostActionStateNotReachedError(
                f"After clicking {logical_name!r}, expected {expect_after!r} "
                f"did not appear within {t}s.",
                logical_name=expect_after,
                screen=after_spec.screen,
            ) from exc
    else:
        # Best-effort: wait for the clicked element to disappear (button depresses),
        # but do not fail the action if it remains (e.g. checkbox stays visible).
        try:
            wait_for_object_gone(spec, timeout=min(t, 3.0))
        except Exception:  # noqa: BLE001
            logger.debug(
                "click: {!r} still visible after click — treating as toggle/non-dismissing element",
                logical_name,
            )


def type_text(logical_name: str, value: str, interval: float = 0.05) -> None:
    """Click *logical_name* to focus it, then type *value* with *interval* delay."""
    ensure_citrix_focused()
    click(logical_name)
    logger.info("type_text: {!r} ← {!r}", logical_name, value)
    pyautogui.typewrite(value, interval=interval)


def hotkey(*keys: str) -> None:
    """Send a keyboard shortcut; keys are passed directly to pyautogui.hotkey."""
    ensure_citrix_focused()
    logger.info("hotkey: {}", " + ".join(keys))
    pyautogui.hotkey(*keys)


def press(key: str, presses: int = 1, interval: float = 0.1) -> None:
    """Press a single key *presses* times."""
    ensure_citrix_focused()
    logger.info("press: key={!r} presses={}", key, presses)
    pyautogui.press(key, presses=presses, interval=interval)
