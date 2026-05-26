"""pytest fixtures: OR repository, Citrix session guard, failure screenshot hook."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from loguru import logger

from automation.core.actions import set_or_repo
from automation.core.citrix import assert_session_healthy, ensure_citrix_focused
from automation.core.config import get_config, load_config, set_config
from automation.core.logging_setup import configure_logging
from automation.core.or_loader import VisualOR, load_or


# ---------------------------------------------------------------------------
# Session-scoped: configure logging + load OR once per pytest run.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _framework_init(tmp_path_factory) -> None:
    """Bootstrap logging and config before any test runs."""
    cfg = load_config()
    set_config(cfg)
    configure_logging(
        level=cfg.get("log_level", "INFO"),
        log_file=Path("assets") / "logs" / "test_run.log",
    )
    logger.info("framework: initialised (log_level={})", cfg.get("log_level"))


@pytest.fixture(scope="session")
def or_repo() -> VisualOR:
    """Load and validate the Visual OR YAML exactly once per test session."""
    cfg = get_config()
    or_path = Path(cfg.get("or_path", "or/epic_or.yaml"))
    if not or_path.is_absolute():
        # Resolve relative to the automation package root.
        package_root = Path(__file__).parent.parent
        or_path = package_root / or_path
    repo = load_or(or_path)
    set_or_repo(repo)  # inject into actions module
    logger.info("or_repo: loaded {} objects from {}", len(repo), or_path)
    return repo


# ---------------------------------------------------------------------------
# Function-scoped: Citrix guard wraps every individual test.
# ---------------------------------------------------------------------------


@pytest.fixture()
def citrix(or_repo: VisualOR) -> None:
    """Ensure Citrix is focused and the session is healthy before each test."""
    cfg = get_config()
    focus_timeout = cfg.get("citrix_focus_timeout", 5.0)
    ensure_citrix_focused(timeout=focus_timeout)
    assert_session_healthy()
    logger.info("citrix: session is healthy — proceeding with test")


# ---------------------------------------------------------------------------
# Autouse: capture a screenshot + last-anchor info on every test failure.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _failure_screenshot(request, tmp_path: Path) -> None:
    """On test failure: write a screenshot and attach it to the report."""
    yield  # test runs here

    if request.node.rep_call is not None and request.node.rep_call.failed:
        cfg = get_config()
        screenshots_dir = Path(cfg.get("screenshots_dir", "assets/screenshots"))
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        test_name = request.node.name.replace("/", "_").replace(":", "_")
        dest = screenshots_dir / f"{ts}_FAIL_{test_name}.png"
        try:
            import pyautogui
            pyautogui.screenshot(str(dest))
            logger.error("failure screenshot → {}", dest)
            # TODO(prompt-10): attach to Allure via allure.attach.file(dest, ...)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_failure_screenshot: could not capture screenshot: {}", exc)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach the call report to the request node so _failure_screenshot can read it."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
