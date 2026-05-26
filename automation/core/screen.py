"""Screen anchor helpers and stability waits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from automation.core.config import get_config
from automation.core.exceptions import UnexpectedScreenError
from automation.core.finder import locate
from automation.core.waits import wait_for_object_exists, wait_for_screen_stable

if TYPE_CHECKING:
    from automation.core.or_loader import ObjectSpec, VisualOR


class ScreenAnchor:
    """Wraps a logical screen name and its identifying OR objects."""

    def __init__(self, name: str, anchors: list["ObjectSpec"]) -> None:
        self.name = name
        self._anchors = anchors

    def is_active(self) -> bool:
        """Return True when all identifying anchors are visible."""
        for spec in self._anchors:
            if locate(spec) is None:
                logger.debug(
                    "screen.is_active: {!r} missing anchor {!r}",
                    self.name,
                    spec.name,
                )
                return False
        return True

    def assert_active(self) -> None:
        """Raise UnexpectedScreenError when this screen is not visible."""
        if not self.is_active():
            raise UnexpectedScreenError(
                f"Expected screen {self.name!r} is not active.",
                screen=self.name,
            )

    def wait_until_active(self, timeout: float | None = None) -> None:
        """Block until all identifying anchors are present."""
        cfg = get_config()
        t = timeout if timeout is not None else cfg.get("default_timeout", 30.0)
        for spec in self._anchors:
            wait_for_object_exists(spec, timeout=t)
        logger.info("screen: {!r} is now active", self.name)

    def wait_until_stable(
        self,
        region: tuple[int, int, int, int] | None = None,
        timeout: float = 15.0,
    ) -> None:
        """Wait until the screen's pixel content stops changing."""
        if region is None and self._anchors:
            # Default to the bounding box of the first anchor's region.
            r = self._anchors[0].region
            region = (r.x, r.y, r.width, r.height)
        if region is None:
            raise ValueError("wait_until_stable requires a region when no anchors are defined")
        cfg = get_config()
        stable_count = cfg.get("screen_stable_frames", 3)
        wait_for_screen_stable(region, stable_count=stable_count, timeout=timeout)


def build_screen_anchor(screen_name: str, or_repo: "VisualOR") -> ScreenAnchor:
    """Create a ScreenAnchor from all OR objects belonging to *screen_name*."""
    objects = or_repo.all_for_screen(screen_name)
    if not objects:
        raise ValueError(f"No OR objects found for screen {screen_name!r}")
    return ScreenAnchor(screen_name, objects)
