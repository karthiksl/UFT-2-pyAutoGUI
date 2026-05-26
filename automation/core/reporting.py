"""Test reporting integration — Allure + screenshot attachment.

# TODO(prompt-10): implement full Allure step logging, per-step screenshot
# attachment, failure category tagging, and HTML summary builder.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def step(title: str) -> Generator[None, None, None]:
    """Context manager that wraps a logical test step in a report entry.

    # TODO(prompt-10): emit Allure step start/stop events with screenshots.
    """
    yield


def attach_screenshot(path: Path, name: str = "screenshot") -> None:
    """Attach *path* to the current Allure report step.

    # TODO(prompt-10): call allure.attach.file().
    """


def set_test_metadata(test_id: str, description: str = "") -> None:
    """Annotate the current test with metadata for triage dashboards.

    # TODO(prompt-10): map to allure.dynamic.title / description.
    """
