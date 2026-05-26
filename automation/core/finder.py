"""Image-anchor location within a bounded region.

This is the ONLY module permitted to translate logical object names into pixel
coordinates. All callers must pass an ObjectSpec; raw coordinates are forbidden
outside this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pyautogui
from loguru import logger
from PIL import Image

from automation.core.exceptions import (
    AmbiguousMatchError,
    ConfidenceTooLowError,
    ConfigError,
    UiNotFoundError,
)

if TYPE_CHECKING:
    from automation.core.or_loader import ObjectSpec, Region


@dataclass
class Match:
    """Successful image-anchor match result."""

    logical_name: str
    screen: str
    center_x: int
    center_y: int
    confidence: float
    region_x: int
    region_y: int
    region_w: int
    region_h: int


def _capture_region(region: "Region") -> np.ndarray:
    """Screenshot the bounded region and return as BGR numpy array."""
    screenshot = pyautogui.screenshot(
        region=(region.x, region.y, region.width, region.height)
    )
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def _load_template(image_path: Path) -> np.ndarray:
    """Load reference PNG as BGR numpy array."""
    if not image_path.exists():
        raise ConfigError(
            f"Reference image not found: {image_path}",
            logical_name=str(image_path),
        )
    template = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if template is None:
        raise ConfigError(
            f"cv2 could not read reference image: {image_path}",
            logical_name=str(image_path),
        )
    return template


def _find_all_matches(
    haystack: np.ndarray, template: np.ndarray, threshold: float
) -> list[tuple[float, int, int, int, int]]:
    """Return list of (confidence, left, top, w, h) for every match over threshold."""
    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    th, tw = template.shape[:2]

    locations = np.where(result >= threshold)
    matches: list[tuple[float, int, int, int, int]] = []
    for pt in zip(*locations[::-1]):  # x, y
        conf = float(result[pt[1], pt[0]])
        matches.append((conf, int(pt[0]), int(pt[1]), tw, th))

    # Non-maximum suppression: merge overlapping boxes (keep highest confidence)
    matches = _nms(matches, iou_threshold=0.5)
    return matches


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Compute intersection-over-union for two (x, y, w, h) boxes."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _nms(
    matches: list[tuple[float, int, int, int, int]], iou_threshold: float = 0.5
) -> list[tuple[float, int, int, int, int]]:
    """Non-maximum suppression over (conf, x, y, w, h) list."""
    matches.sort(key=lambda m: m[0], reverse=True)
    kept: list[tuple[float, int, int, int, int]] = []
    for cand in matches:
        _, cx, cy, cw, ch = cand
        dominated = any(
            _iou((cx, cy, cw, ch), (kx, ky, kw, kh)) > iou_threshold
            for _, kx, ky, kw, kh in kept
        )
        if not dominated:
            kept.append(cand)
    return kept


def locate(spec: "ObjectSpec") -> Match | None:
    """Search for *spec*'s image inside its bounded region.

    Returns None when the best score is below spec.min_confidence.
    Raises AmbiguousMatchError when ≥ 2 independent matches exceed the threshold.
    """
    logger.debug(
        "locate: name={!r} screen={!r} region=({},{},{},{}) min_conf={}",
        spec.name,
        spec.screen,
        spec.region.x,
        spec.region.y,
        spec.region.width,
        spec.region.height,
        spec.min_confidence,
    )

    haystack = _capture_region(spec.region)
    template = _load_template(spec.image)

    # Template must be smaller than or equal to the region.
    th, tw = template.shape[:2]
    hh, hw = haystack.shape[:2]
    if th > hh or tw > hw:
        raise ConfigError(
            f"Template {spec.image.name} ({tw}×{th}) is larger than "
            f"region {hw}×{hh} for object {spec.name!r}.",
            logical_name=spec.name,
            screen=spec.screen,
        )

    matches = _find_all_matches(haystack, template, spec.min_confidence)

    if not matches:
        logger.debug("locate: no match found for {!r}", spec.name)
        return None

    if len(matches) >= 2:
        raise AmbiguousMatchError(
            f"Found {len(matches)} matches for {spec.name!r} — "
            f"tighten region or raise min_confidence.",
            logical_name=spec.name,
            screen=spec.screen,
            details={"match_count": len(matches), "confidences": [m[0] for m in matches]},
        )

    conf, rel_x, rel_y, mw, mh = matches[0]
    # Convert region-relative coordinates to absolute screen coordinates.
    abs_cx = spec.region.x + rel_x + mw // 2
    abs_cy = spec.region.y + rel_y + mh // 2

    logger.debug(
        "locate: found {!r} @ ({},{}) conf={:.3f}",
        spec.name,
        abs_cx,
        abs_cy,
        conf,
    )
    return Match(
        logical_name=spec.name,
        screen=spec.screen,
        center_x=abs_cx,
        center_y=abs_cy,
        confidence=conf,
        region_x=spec.region.x,
        region_y=spec.region.y,
        region_w=spec.region.width,
        region_h=spec.region.height,
    )
