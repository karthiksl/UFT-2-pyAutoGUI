"""CLI entry point — thin wrapper around pytest with suite/marker selection."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m automation.run",
        description="Run UFT-migrated Epic Hyperdrive automation tests.",
    )
    p.add_argument(
        "--suite",
        metavar="MARKER",
        help="pytest marker to select (e.g. smoke, regression, suite_enrollment)",
    )
    p.add_argument(
        "--test-id",
        metavar="ID",
        help="Run a single test by ID (e.g. TEST_188001)",
    )
    p.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to YAML config file (default: built-in defaults + env vars)",
    )
    p.add_argument(
        "--report-dir",
        metavar="DIR",
        default="allure-results",
        help="Allure results output directory",
    )
    p.add_argument(
        "--log-level",
        choices=["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the pytest command that would be executed, then exit",
    )
    # TODO(prompt-NN): add --parallel flag once multi-session VDI is confirmed safe.
    return p


def main(argv: list[str] | None = None) -> int:
    """Parse args and invoke pytest; return its exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    cmd = [sys.executable, "-m", "pytest", "-v"]

    if args.suite:
        cmd += ["-m", args.suite]

    if args.test_id:
        cmd += ["-k", args.test_id]

    if args.report_dir:
        cmd += [f"--alluredir={args.report_dir}"]

    cmd += [f"--log-cli-level={args.log_level}"]

    # Pass config path as env var so conftest.py picks it up.
    import os
    env = os.environ.copy()
    if args.config:
        env["AUTOMATION_CONFIG_PATH"] = str(Path(args.config).resolve())
    env["AUTOMATION_LOG_LEVEL"] = args.log_level

    if args.dry_run:
        print("Would run:", " ".join(cmd))
        return 0

    result = subprocess.run(cmd, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
