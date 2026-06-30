"""Azure authentication via DefaultAzureCredential.

Supports Azure CLI login, Managed Identity, and Service Principal. Secrets are
only ever read from environment variables (never persisted). Falls back to a
broad credential chain so the accelerator works locally and in CI.
"""
from __future__ import annotations

import logging

from azure.core.credentials import TokenCredential
from azure.identity import (
    ClientSecretCredential,
    DefaultAzureCredential,
)

from ..utils.config import Settings

logger = logging.getLogger("auth")


def get_credential(settings: Settings) -> TokenCredential:
    """Return a credential. Uses SP when provided, else DefaultAzureCredential."""
    if settings.client_id and settings.client_secret and settings.tenant_id:
        logger.info("Using Service Principal credential")
        return ClientSecretCredential(
            tenant_id=settings.tenant_id,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
        )
    logger.info("Using DefaultAzureCredential (CLI / Managed Identity / env)")
    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def get_token(credential: TokenCredential, scope: str) -> str:
    """Acquire a bearer token for a given resource scope."""
    return credential.get_token(scope).token
