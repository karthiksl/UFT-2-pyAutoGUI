"""Loguru + Rich logging configuration for the framework."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from loguru import logger

LogLevel = Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]

_configured = False


def configure_logging(
    level: LogLevel = "INFO",
    log_file: Path | str | None = None,
    *,
    json_sink: bool = False,
) -> None:
    """Configure loguru handlers; idempotent if called multiple times."""
    global _configured
    logger.remove()  # drop loguru default handler

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
    )
    logger.add(sys.stderr, level=level, format=fmt, colorize=True)

    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if json_sink:
            logger.add(
                log_path,
                level=level,
                serialize=True,
                rotation="10 MB",
                retention=5,
            )
        else:
            logger.add(
                log_path,
                level=level,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} — {message}",
                rotation="10 MB",
                retention=5,
            )

    _configured = True
    logger.debug("Logging configured: level={}, file={}", level, log_file)


def get_logger(name: str = "automation"):
    """Return a loguru logger bound to *name*."""
    return logger.bind(name=name)
