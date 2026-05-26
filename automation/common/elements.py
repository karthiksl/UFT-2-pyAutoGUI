"""Semantic element registry — maps human labels to Visual OR logical names.

# Migration notes
# UFT counterpart: FunctionLibrary/ElementLibrary.qfl
# Inferred functions:
#   ElementRegistry.register  ← RegisterElement(sLabel, sOrName)
#   ElementRegistry.resolve   ← ResolveElement(sLabel, sScreen)
# UFT resolved object repository names at test-script level via string literals.
# This registry provides an optional indirection layer so tests can use
# human-readable labels (e.g. "Submit") that map to OR names like
# "enrollment.submit_enrollment_button" without hard-coding OR names everywhere.
"""

from __future__ import annotations

from automation.common.element_utils import best_match, normalize_key
from automation.core.exceptions import ConfigError


class ElementRegistry:
    """Map semantic labels to Visual OR logical names.

    Populated at suite setup by calling :meth:`register` for every known
    element, or by bulk-loading a screen's POM constants via :meth:`load_pom`.
    """

    def __init__(self) -> None:
        # {canonical_screen: {canonical_label: or_name}}
        self._map: dict[str, dict[str, str]] = {}

    def register(self, label: str, or_name: str, screen: str | None = None) -> None:
        """Map *label* → *or_name*, optionally scoped to *screen*.

        When *screen* is None the entry is registered globally (screen=``"*"``).
        """
        scope = normalize_key(screen) if screen else "*"
        bucket = self._map.setdefault(scope, {})
        bucket[normalize_key(label)] = or_name

    def load_pom(self, pom_module: object) -> None:
        """Register all ``UPPER_CASE`` string attributes from *pom_module*.

        Convention: POM modules define ``SAVE_BTN = "screen.save_button"``.
        The attribute name becomes the label, the value becomes the OR name.
        The screen scope is inferred from the OR name prefix.
        """
        for attr in dir(pom_module):
            if not attr.isupper():
                continue
            or_name = getattr(pom_module, attr)
            if not isinstance(or_name, str):
                continue
            screen = or_name.split(".")[0] if "." in or_name else None
            self.register(attr.lower(), or_name, screen=screen)

    def resolve(self, label: str, screen: str | None = None) -> str:
        """Return the OR logical name for *label* scoped to *screen*.

        Search order:
        1. Exact match in screen-scoped bucket.
        2. Fuzzy match in screen-scoped bucket (threshold 0.6).
        3. Exact match in global bucket (``"*"``).
        4. Fuzzy match in global bucket.

        Raises :class:`ConfigError` when no match is found.
        """
        key = normalize_key(label)
        scopes = []
        if screen:
            scopes.append(normalize_key(screen))
        scopes.append("*")

        for scope in scopes:
            bucket = self._map.get(scope, {})
            if key in bucket:
                return bucket[key]
            best = best_match(key, list(bucket.keys()), threshold=0.6)
            if best is not None:
                return bucket[best]

        raise ConfigError(
            f"ElementRegistry: cannot resolve label {label!r} "
            f"(screen={screen!r}); register it or load the POM module first.",
            logical_name=label,
            screen=screen or "",
        )

    def all_for_screen(self, screen: str) -> dict[str, str]:
        """Return all {label: or_name} entries for *screen*."""
        scope = normalize_key(screen)
        return dict(self._map.get(scope, {}))

    def __len__(self) -> int:
        return sum(len(b) for b in self._map.values())
