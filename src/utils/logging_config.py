"""Centralized logging setup.

Each agent gets a console logger (Rich) plus a dedicated per-agent file under
``output/logs/``. Errors are also collected for structured JSON error logs.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.logging import RichHandler

_LOG_DIR = Path("output/logs")


def get_logger(name: str, log_level: str = "INFO", output_path: str = "output") -> logging.Logger:
    """Return a configured logger with console + per-agent file handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(log_level.upper())
    logger.propagate = False

    console = RichHandler(rich_tracebacks=True, show_path=False)
    console.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    logger.addHandler(console)

    log_dir = Path(output_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(file_handler)
    return logger


class ErrorCollector:
    """Collects non-fatal errors so one artifact failure never aborts an agent."""

    def __init__(self, agent: str) -> None:
        self.agent = agent
        self._errors: list[dict[str, Any]] = []

    def add(self, context: str, error: Exception, detail: str | None = None) -> None:
        self._errors.append(
            {
                "agent": self.agent,
                "context": context,
                "error_type": type(error).__name__,
                "error": str(error),
                "detail": detail,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    @property
    def errors(self) -> list[dict[str, Any]]:
        return self._errors

    def save(self, output_path: str, filename: str) -> Path:
        log_dir = Path(output_path) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        dest = log_dir / filename
        with dest.open("w", encoding="utf-8") as fh:
            json.dump(self._errors, fh, indent=2)
        return dest
