"""Shared fixtures for tools/ converter tests.

These tests target ``tools/qfl_to_pyautogui.py``. The file lives outside the
``automation`` package, so we put the project root on ``sys.path`` once at
collection time. This avoids polluting global ``conftest.py`` and keeps the
import explicit for anyone reading the test files.
"""

from __future__ import annotations

import sys
from pathlib import Path

# automation/tests/unit/tools/conftest.py -> project root is four levels up.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
