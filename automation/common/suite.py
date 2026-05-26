"""Suite lifecycle helpers — setup, teardown, and data refresh.

# Migration notes
# UFT counterpart: FunctionLibrary/SuiteHelpers.qfl
# Inferred functions:
#   SuiteConfig        ← Suite-level configuration bundle (no direct UFT analog)
#   setup_suite        ← SuiteSetup(sTestID)    — OR load, citrix focus, log init
#   teardown_suite     ← SuiteTeardown()        — reporter flush, citrix release
#   refresh_test_data  ← RefreshTestData()      — re-read data rows mid-run
# UFT ran SuiteSetup as a single procedure called from the main Action.
# This module decomposes that into typed, testable pieces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from automation.common.reporting_legacy import ReporterAdapter
from automation.common.suite_source import load_suite_data
from automation.core.config import get_config, load_config

if TYPE_CHECKING:
    from automation.common import Context
    from automation.common.data import DataRow
    from automation.core.or_loader import VisualOR


@dataclass
class SuiteConfig:
    """Bundle of suite-level configuration resolved at startup."""

    test_id: str
    suite_name: str
    or_path: Path = field(default_factory=lambda: Path("automation/or/app_or.yaml"))
    config_path: Path | None = None
    jira_filter: str | None = None
    allure_enabled: bool = False


def setup_suite(cfg: SuiteConfig) -> "Context":
    """Initialise a Context object for one suite run.

    1. Loads framework config from *cfg.config_path* when given.
    2. Loads the Visual OR from *cfg.or_path*.
    3. Ensures Citrix is focused (no-op on non-Windows).
    4. Returns a fully populated :class:`~automation.common.Context`.

    Raises ConfigError / CitrixNotFocusedError on hard failures.
    """
    from automation.common import Context
    from automation.core.citrix import assert_session_healthy, ensure_citrix_focused
    from automation.core.or_loader import load_or

    if cfg.config_path and cfg.config_path.exists():
        load_config(cfg.config_path)
        logger.info("suite: loaded config from {}", cfg.config_path)

    or_repo = load_or(cfg.or_path)
    logger.info("suite: loaded OR ({} objects) from {}", len(or_repo), cfg.or_path)

    ensure_citrix_focused(timeout=get_config().get("citrix_focus_timeout", 10.0))
    assert_session_healthy()

    reporter = ReporterAdapter(test_id=cfg.test_id, allure_enabled=cfg.allure_enabled)
    logger.info("suite: {} — setup complete", cfg.test_id)

    return Context(or_repo=or_repo, reporter=reporter)


def teardown_suite(ctx: "Context") -> None:
    """Flush the reporter and release Citrix focus guard.

    Always runs; swallows non-fatal errors and logs them.
    """
    try:
        if ctx.reporter and ctx.reporter.has_failures():
            logger.error(
                "suite: teardown — {} failure(s) recorded",
                sum(1 for e in ctx.reporter.events if e["status"] == "FAIL"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("suite: teardown reporter flush error: {}", exc)

    logger.info("suite: teardown complete")


def refresh_test_data(ctx: "Context", suite: str, jira: str | None = None) -> "list[DataRow]":
    """Re-read test data rows from *suite* and attach the first row to *ctx*.

    Returns all matching rows.  Side-effect: sets *ctx.row* to the first row
    when *jira* is given and exactly one row matches.
    """
    rows = load_suite_data(suite, jira=jira)
    if rows and jira:
        ctx.row = rows[0]
        logger.debug("suite: data refreshed — {} row(s) for jira={!r}", len(rows), jira)
    return rows
