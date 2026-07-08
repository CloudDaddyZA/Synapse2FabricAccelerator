"""Microsoft Fabric REST client (control-plane / admin APIs).

Thin wrapper over the Fabric REST API (``https://api.fabric.microsoft.com/v1``)
used to enumerate the target estate: capacities, workspaces, items, and role
assignments. SDK coverage for Fabric is still thin, so REST is preferred here.

All calls are best-effort: the caller catches exceptions and degrades
gracefully (an unprovisioned tenant or missing permission must never fail the
whole accelerator).
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from azure.core.credentials import TokenCredential

from ..utils.config import Settings
from ..utils.retry import with_retry

_SCOPE = "https://api.fabric.microsoft.com/.default"
_BASE = "https://api.fabric.microsoft.com/v1"
logger = logging.getLogger("fabric_rest")


class FabricRestClient:
    """Client for the Fabric REST control-plane API."""

    def __init__(self, credential: TokenCredential, settings: Settings):
        self.credential = credential
        self.settings = settings

    def _token(self) -> str:
        return self.credential.get_token(_SCOPE).token

    def _get(self, url: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token()}"}
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _list(self, path: str, key: str = "value") -> list[dict[str, Any]]:
        """List a collection, following Fabric's ``continuationUri`` paging."""
        items: list[dict[str, Any]] = []
        url = f"{_BASE}{path}"
        data = with_retry(
            self._get, url,
            max_attempts=self.settings.retry_max_attempts,
            backoff_seconds=self.settings.retry_backoff_seconds,
            logger=logger,
        )
        items.extend(data.get(key, []))
        # Fabric returns either continuationUri (absolute) or continuationToken.
        nxt = data.get("continuationUri")
        while nxt:
            data = self._get(nxt)
            items.extend(data.get(key, []))
            nxt = data.get("continuationUri")
        return items

    def capacities(self) -> list[dict[str, Any]]:
        """List capacities visible to the caller."""
        return self._list("/capacities")

    def workspaces(self) -> list[dict[str, Any]]:
        """List workspaces the caller can access."""
        return self._list("/workspaces")

    def workspace_items(self, workspace_id: str) -> list[dict[str, Any]]:
        """List all items in a workspace (Lakehouse/Warehouse/Notebook/...)."""
        return self._list(f"/workspaces/{workspace_id}/items")

    def workspace_role_assignments(self, workspace_id: str) -> list[dict[str, Any]]:
        """List role assignments for a workspace."""
        return self._list(f"/workspaces/{workspace_id}/roleAssignments")
