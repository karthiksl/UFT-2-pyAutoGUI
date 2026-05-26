"""Step registry — BDD-style step pattern matching for UFT script migration.

# Migration notes
# UFT counterpart: FunctionLibrary/StepDefinitions.qfl
# Inferred functions:
#   @step(pattern)     ← Sub-style function registration (no direct UFT analog)
#   STEP_REGISTRY      ← global dictionary of pattern → callable
#   execute_step       ← UFT called shared functions by name string; this maps
#                        natural-language step text to the registered handler.
# Pattern matching uses Python re so UFT's positional parameter convention
# (passing values inline in a descriptor string) is preserved.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

if TYPE_CHECKING:
    from automation.common import Context

# {compiled_regex: handler_callable}
STEP_REGISTRY: dict[re.Pattern[str], Callable[..., Any]] = {}


def step(pattern: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register a function as the handler for *pattern*.

    *pattern* is a Python regex string.  Named groups ``(?P<name>...)`` become
    keyword arguments to the decorated function.

    Example::

        @step(r"I click the (?P<label>.+) button")
        def click_button(ctx: Context, label: str) -> None:
            actions.click(f"*.{label.lower().replace(' ', '_')}_button")
    """
    compiled = re.compile(pattern, re.IGNORECASE)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if any(p.pattern == compiled.pattern for p in STEP_REGISTRY):
            logger.warning("steps: duplicate pattern registered: {!r}", pattern)
        STEP_REGISTRY[compiled] = fn
        return fn

    return decorator


def execute_step(ctx: "Context", text: str) -> Any:
    """Find the registered handler for *text* and call it with *ctx*.

    Raises :class:`KeyError` when no registered pattern matches *text*.
    """
    for pattern, handler in STEP_REGISTRY.items():
        m = pattern.fullmatch(text.strip())
        if m is not None:
            kwargs = m.groupdict()
            logger.debug("steps: executing {!r} → {}", text, handler.__name__)
            return handler(ctx, **kwargs)
    raise KeyError(f"No step registered for: {text!r}")


def clear_registry() -> None:
    """Remove all registered steps — useful between test suites."""
    STEP_REGISTRY.clear()


def list_steps() -> list[str]:
    """Return all registered pattern strings for debugging / documentation."""
    return [p.pattern for p in STEP_REGISTRY]
