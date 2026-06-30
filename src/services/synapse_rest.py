"""Synapse data-plane REST client (artifacts API; SDK coverage is thin)."""
from __future__ import annotations

import logging
from typing import Any

import requests
from azure.core.credentials import TokenCredential

from ..utils.config import Settings
from ..utils.retry import with_retry

_SCOPE = "https://dev.azuresynapse.net/.default"
logger = logging.getLogger("synapse_rest")


class SynapseRestClient:
    """Thin wrapper around the workspace dev endpoint artifact APIs."""

    def __init__(self, dev_endpoint: str, credential: TokenCredential, settings: Settings):
        self.endpoint = dev_endpoint.rstrip("/")
        self.credential = credential
        self.settings = settings
        self.api_version = settings.synapse_api_version

    def _token(self) -> str:
        return self.credential.get_token(_SCOPE).token

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        headers = {"Authorization": f"Bearer {self._token()}"}
        params = {"api-version": self.api_version}
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        headers = {"Authorization": f"Bearer {self._token()}"}
        params = {"api-version": self.api_version}
        resp = requests.post(url, headers=headers, params=params, json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def list_all(self, path: str) -> list[dict[str, Any]]:
        """List a paged artifact collection, following nextLink."""
        items: list[dict[str, Any]] = []
        data = with_retry(
            self._get, path,
            max_attempts=self.settings.retry_max_attempts,
            backoff_seconds=self.settings.retry_backoff_seconds,
            logger=logger,
        )
        items.extend(data.get("value", []))
        while data.get("nextLink"):
            resp = requests.get(
                data["nextLink"],
                headers={"Authorization": f"Bearer {self._token()}"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
        return items

    def pipelines(self) -> list[dict[str, Any]]:
        return self.list_all("/pipelines")

    def pipeline_runs(self, last_updated_after: str, last_updated_before: str) -> list[dict[str, Any]]:
        """Query historical pipeline runs in a window (ISO-8601 timestamps)."""
        items: list[dict[str, Any]] = []
        body: dict[str, Any] = {"lastUpdatedAfter": last_updated_after,
                                "lastUpdatedBefore": last_updated_before}
        while True:
            data = with_retry(
                self._post, "/queryPipelineRuns", body,
                max_attempts=self.settings.retry_max_attempts,
                backoff_seconds=self.settings.retry_backoff_seconds,
                logger=logger,
            )
            items.extend(data.get("value", []))
            token = data.get("continuationToken")
            if not token:
                break
            body = {**body, "continuationToken": token}
        return items

    def notebooks(self) -> list[dict[str, Any]]:
        return self.list_all("/notebooks")

    def triggers(self) -> list[dict[str, Any]]:
        return self.list_all("/triggers")

    def linked_services(self) -> list[dict[str, Any]]:
        return self.list_all("/linkedservices")

    def datasets(self) -> list[dict[str, Any]]:
        return self.list_all("/datasets")

    def dataflows(self) -> list[dict[str, Any]]:
        return self.list_all("/dataflows")

    def sql_scripts(self) -> list[dict[str, Any]]:
        return self.list_all("/sqlScripts")

    def spark_job_definitions(self) -> list[dict[str, Any]]:
        return self.list_all("/sparkJobDefinitions")
