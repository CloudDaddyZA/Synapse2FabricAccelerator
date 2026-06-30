"""Configuration loading and settings model.

Loads YAML settings, layers environment variables, and exposes a typed
``Settings`` object used across all agents. Secrets are never stored in
configuration files: they come exclusively from environment variables / .env.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("config/settings.yaml")


class Settings(BaseModel):
    """Typed accelerator settings."""

    tenant_id: str = ""
    subscriptions: list[str] = Field(default_factory=list)
    resource_groups: list[str] = Field(default_factory=list)
    workspace_names: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)

    output_path: str = "output"

    include_security_scan: bool = True
    include_usage_analysis: bool = True
    include_powerbi_outputs: bool = True
    include_html_dashboard: bool = True
    include_copilot_optimization_pack: bool = True

    log_level: str = "INFO"
    retry_max_attempts: int = 5
    retry_backoff_seconds: int = 2
    synapse_api_version: str = "2020-12-01"
    pipeline_run_history_days: int = 30
    include_pipeline_run_history: bool = True

    # Resolved at runtime from .env, never persisted to YAML.
    client_id: str | None = Field(default=None, exclude=True)
    client_secret: str | None = Field(default=None, exclude=True)

    @property
    def output_dir(self) -> Path:
        return Path(self.output_path)

    def subdir(self, name: str) -> Path:
        """Return (and create) an output subdirectory."""
        path = self.output_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML and overlay environment variables.

    Environment variables take precedence for auth; secrets are pulled from
    the environment only. Missing config file falls back to defaults.
    """
    load_dotenv()
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    data: dict = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    settings = Settings(**data)

    # Layer auth context from environment (no secrets in YAML).
    settings.tenant_id = os.getenv("AZURE_TENANT_ID") or settings.tenant_id
    settings.client_id = os.getenv("AZURE_CLIENT_ID")
    settings.client_secret = os.getenv("AZURE_CLIENT_SECRET")

    env_sub = os.getenv("AZURE_SUBSCRIPTION_ID")
    if env_sub and not settings.subscriptions:
        settings.subscriptions = [s.strip() for s in env_sub.split(",") if s.strip()]

    return settings
