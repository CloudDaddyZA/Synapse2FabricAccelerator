"""Base agent providing shared lifecycle for all specialized agents."""
from __future__ import annotations

import logging
from pathlib import Path

from ..utils.config import Settings, load_settings
from ..utils.logging_config import ErrorCollector, get_logger


class BaseAgent:
    """Common lifecycle: settings, logger, error collector, output paths.

    Each agent reads only required inputs, writes to its own output folder,
    logs progress, captures errors, and continues on partial failures.
    """

    name: str = "base"
    output_subdir: str = ""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.logger: logging.Logger = get_logger(
            self.name, self.settings.log_level, self.settings.output_path
        )
        self.errors = ErrorCollector(self.name)

    @property
    def output_dir(self) -> Path:
        return self.settings.subdir(self.output_subdir) if self.output_subdir else self.settings.output_dir

    def save_errors(self, filename: str) -> None:
        if self.errors.errors:
            path = self.errors.save(self.settings.output_path, filename)
            self.logger.warning("Captured %d non-fatal errors -> %s", len(self.errors.errors), path)

    def run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
