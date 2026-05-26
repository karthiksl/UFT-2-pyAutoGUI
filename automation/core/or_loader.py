"""Visual Object Repository loader and validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from automation.core.exceptions import ConfigError


@dataclass(frozen=True)
class Region:
    """Bounding box relative to the Citrix session window (pixels)."""

    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_dict(cls, d: "dict[str, int] | list[int] | tuple[int, ...]") -> "Region":
        """Construct from a YAML-sourced dict OR a 4-element list/tuple [x,y,w,h]."""
        try:
            if isinstance(d, (list, tuple)):
                if len(d) != 4:
                    raise ValueError(f"Expected 4 elements, got {len(d)}")
                return cls(x=int(d[0]), y=int(d[1]), width=int(d[2]), height=int(d[3]))
            return cls(
                x=int(d["x"]),
                y=int(d["y"]),
                width=int(d["width"]),
                height=int(d["height"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(
                f"Invalid region definition {d!r}: {exc}"
            ) from exc


@dataclass(frozen=True)
class ObjectSpec:
    """Single logical object entry from the Visual OR."""

    name: str
    screen: str
    image: Path          # path to reference PNG, relative to assets/images/
    region: Region
    min_confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 < self.min_confidence <= 1.0):
            raise ConfigError(
                f"Object {self.name!r}: min_confidence must be (0, 1], "
                f"got {self.min_confidence}",
                logical_name=self.name,
                screen=self.screen,
            )


class VisualOR:
    """In-memory repository of all ObjectSpec entries."""

    def __init__(self, objects: list[ObjectSpec]) -> None:
        self._index: dict[str, ObjectSpec] = {}
        for obj in objects:
            if obj.name in self._index:
                raise ConfigError(
                    f"Duplicate object name {obj.name!r} in Visual OR",
                    logical_name=obj.name,
                )
            self._index[obj.name] = obj

    def get(self, name: str) -> ObjectSpec:
        """Return ObjectSpec for *name*; raise ConfigError when absent."""
        try:
            return self._index[name]
        except KeyError as exc:
            raise ConfigError(
                f"Object {name!r} not found in Visual OR",
                logical_name=name,
            ) from exc

    def all_for_screen(self, screen: str) -> list[ObjectSpec]:
        """Return all objects belonging to *screen*."""
        return [obj for obj in self._index.values() if obj.screen == screen]

    def __len__(self) -> int:
        return len(self._index)

    def __repr__(self) -> str:
        return f"VisualOR({len(self)} objects)"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"name", "screen", "image", "region", "min_confidence"}


def _parse_object(raw: dict[str, Any], assets_root: Path) -> ObjectSpec:
    """Validate and parse a single object entry dict into ObjectSpec."""
    missing = _REQUIRED_KEYS - raw.keys()
    if missing:
        raise ConfigError(
            f"Object entry missing required keys {missing!r}: {raw}",
        )
    name: str = raw["name"]
    screen: str = raw["screen"]
    image_path = assets_root / raw["image"]
    region = Region.from_dict(raw["region"])
    try:
        min_confidence = float(raw["min_confidence"])
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Object {name!r}: min_confidence must be a float, got {raw['min_confidence']!r}",
            logical_name=name,
        ) from exc
    metadata = {k: v for k, v in raw.items() if k not in _REQUIRED_KEYS}
    return ObjectSpec(
        name=name,
        screen=screen,
        image=image_path,
        region=region,
        min_confidence=min_confidence,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_or(path: Path | str, *, assets_root: Path | str | None = None) -> VisualOR:
    """Load and validate the Visual OR YAML at *path*."""
    or_path = Path(path)
    if not or_path.exists():
        raise ConfigError(
            f"Visual OR file not found: {or_path}",
            logical_name=str(or_path),
        )
    try:
        with or_path.open() as fh:
            raw_doc = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"YAML parse error in {or_path}: {exc}",
            logical_name=str(or_path),
        ) from exc

    if "objects" not in raw_doc:
        raise ConfigError(
            f"Visual OR {or_path} must have a top-level 'objects' list",
            logical_name=str(or_path),
        )

    _assets_root = Path(assets_root) if assets_root else or_path.parent.parent / "assets" / "images"

    objects: list[ObjectSpec] = []
    for idx, entry in enumerate(raw_doc["objects"]):
        try:
            objects.append(_parse_object(entry, _assets_root))
        except ConfigError as exc:
            raise ConfigError(
                f"Error in Visual OR entry #{idx}: {exc}",
            ) from exc

    return VisualOR(objects)
