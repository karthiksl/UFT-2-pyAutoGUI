"""Explicit wait predicates — the only place time.sleep is permitted."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pyautogui
from loguru import logger

from automation.core.exceptions import TimeoutError, UiNotFoundError
from automation.core.finder import Match, locate

if TYPE_CHECKING:
    from automation.core.or_loader import ObjectSpec, VisualOR


def _now() -> float:
    return time.monotonic()


def wait_for_object_exists(
    spec: "ObjectSpec",
    timeout: float,
    poll: float = 0.5,
) -> Match:
    """Poll until *spec* is visible; raise TimeoutError when deadline passes."""
    deadline = _now() + timeout
    logger.debug("wait_for_object_exists: {!r} timeout={}s", spec.name, timeout)
    while _now() < deadline:
        match = locate(spec)
        if match is not None:
            logger.debug("wait_for_object_exists: found {!r}", spec.name)
            return match
        time.sleep(poll)  # only sleep inside waits.py
    raise TimeoutError(
        f"Object {spec.name!r} did not appear within {timeout}s.",
        logical_name=spec.name,
        screen=spec.screen,
    )


def wait_for_object_gone(
    spec: "ObjectSpec",
    timeout: float,
    poll: float = 0.5,
) -> None:
    """Poll until *spec* is no longer visible; raise TimeoutError otherwise."""
    deadline = _now() + timeout
    logger.debug("wait_for_object_gone: {!r} timeout={}s", spec.name, timeout)
    while _now() < deadline:
        if locate(spec) is None:
            logger.debug("wait_for_object_gone: {!r} has disappeared", spec.name)
            return
        time.sleep(poll)  # only sleep inside waits.py
    raise TimeoutError(
        f"Object {spec.name!r} was still visible after {timeout}s.",
        logical_name=spec.name,
        screen=spec.screen,
    )


def wait_for_screen_stable(
    region: tuple[int, int, int, int],
    *,
    stable_count: int = 3,
    timeout: float = 15.0,
    poll: float = 0.5,
    diff_threshold: float = 0.005,
) -> None:
    """Wait until *region* pixel content stops changing.

    Compares successive screenshots; declares stable once *stable_count*
    consecutive frames differ by less than *diff_threshold* (fraction of pixels).
    """
    logger.debug("wait_for_screen_stable: region={} stable_count={}", region, stable_count)
    deadline = _now() + timeout
    prev_frame: np.ndarray | None = None
    stable_streak = 0

    while _now() < deadline:
        screenshot = pyautogui.screenshot(region=region)
        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

        if prev_frame is not None:
            diff = cv2.absdiff(prev_frame, frame)
            changed_fraction = np.count_nonzero(diff) / diff.size
            if changed_fraction < diff_threshold:
                stable_streak += 1
                if stable_streak >= stable_count:
                    logger.debug("wait_for_screen_stable: stable after {} checks", stable_streak)
                    return
            else:
                stable_streak = 0
                logger.debug(
                    "wait_for_screen_stable: frame changed {:.3%} — resetting streak",
                    changed_fraction,
                )

        prev_frame = frame
        time.sleep(poll)  # only sleep inside waits.py

    raise TimeoutError(
        f"Screen region {region} did not stabilise within {timeout}s.",
    )


def wait_while_busy(
    busy_spec: "ObjectSpec",
    timeout: float = 60.0,
    poll: float = 0.5,
) -> None:
    """Block until the busy/spinner anchor is gone from the screen."""
    logger.debug("wait_while_busy: spinner={!r} timeout={}s", busy_spec.name, timeout)
    wait_for_object_gone(busy_spec, timeout=timeout, poll=poll)
