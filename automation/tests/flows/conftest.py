"""pytest fixtures for the flows/ layer — sample OR, screen player guard, AST checker."""

from __future__ import annotations

import ast
import subprocess
import time as _time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# AST-based self-check: no raw pyautogui.click or time.sleep in task/flow code
# ---------------------------------------------------------------------------

_TASKS_SAMPLE_DIR = Path(__file__).parent.parent / "tasks" / "sample"
_FLOWS_SAMPLE_DIR = Path(__file__).parent / "sample"

_FORBIDDEN: list[tuple[str, str]] = [
    ("pyautogui", "click"),   # use actions.click() instead
    ("time", "sleep"),        # use waits.* instead
]


def _scan_for_forbidden(directory: Path) -> list[str]:
    violations: list[str] = []
    if not directory.exists():
        return violations
    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
            ):
                continue
            for module, attr in _FORBIDDEN:
                if func.value.id == module and func.attr == attr:
                    violations.append(
                        f"{py_file.name}:{node.lineno}: "
                        f"{module}.{attr}() — forbidden in task/flow code"
                    )
    return violations


@pytest.fixture(scope="session", autouse=True)
def _ast_forbidden_call_check() -> None:
    """Scan task and flow source files for raw pyautogui.click / time.sleep calls."""
    violations: list[str] = []
    for d in (_TASKS_SAMPLE_DIR, _FLOWS_SAMPLE_DIR):
        violations.extend(_scan_for_forbidden(d))

    print("\n[self-check] Forbidden-call scan:")
    if violations:
        for v in violations:
            print(f"  FAIL  {v}")
        pytest.fail(
            "Forbidden calls found in task/flow files:\n" + "\n".join(violations),
            pytrace=False,
        )
    else:
        print("  PASS  no pyautogui.click or time.sleep in tasks/sample/ or flows/sample/")


# ---------------------------------------------------------------------------
# Sample OR — loads sample_or.yaml once per session and injects into actions
# and OCR cache so all sample tests use the right object repository.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_or_repo():
    """Load sample_or.yaml, wire it into actions + OCR cache, return VisualOR."""
    from automation.core import ocr as _ocr
    from automation.core.actions import set_or_repo
    from automation.core.config import get_config
    from automation.core.or_loader import load_or

    or_path = (
        Path(__file__).parent.parent.parent  # automation/
        / "or"
        / "sample_or.yaml"
    )
    repo = load_or(or_path)
    set_or_repo(repo)

    # Point the OCR target cache at sample_or.yaml so assert_text("sample_home.mrn_text", ...)
    # resolves correctly.
    cfg = get_config()
    cfg._data["or_path"] = str(or_path)
    _ocr._invalidate_ocr_target_cache()

    return repo


# ---------------------------------------------------------------------------
# Screen player — skip tests when screen_player.py is not running
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _screen_player_pid() -> bool:
    """Return True if screen_player.py process is running."""
    result = subprocess.run(
        ["pgrep", "-f", "screen_player.py"],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.fixture()
def screen_player_running(_screen_player_pid: bool) -> None:  # type: ignore[return]
    """Skip the test immediately if screen_player.py is not running."""
    if not _screen_player_pid:
        pytest.skip(
            "screen_player.py is not running — start it with:\n"
            "    python fixtures/sample_uft/screen_player.py"
        )


# ---------------------------------------------------------------------------
# Screen reset — after each test, return screen_player to the login screen
# ---------------------------------------------------------------------------

@pytest.fixture()
def reset_screen_player(screen_player_running: None) -> None:  # type: ignore[return]
    """Yield; press F8 × 3 after the test to full-cycle screen_player back to login.

    Three F8 presses advance through any position in the 3-screen cycle
    (0→1→2→0), guaranteeing login is showing before the next test starts.
    """
    yield
    try:
        import pyautogui

        # Click centre of screen_player window to ensure it has keyboard focus.
        pyautogui.click(640, 400)
        _time.sleep(0.15)
        for _ in range(3):
            pyautogui.press("f8")
            _time.sleep(0.10)
    except Exception:  # noqa: BLE001 — reset is best-effort
        pass
