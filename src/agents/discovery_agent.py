"""Discovery Agent.

Discovers the Azure Synapse estate: subscriptions, resource groups, and
workspaces (with regions, tags, managed RG, endpoints, Git metadata, and
access validation). Performs no deep artifact analysis.
"""
from __future__ import annotations

from azure.core.exceptions import HttpResponseError

from ..exporters.json_writer import write_json
from ..exporters.markdown_writer import write_markdown
from ..models.inventory import ResourceGroup, Subscription, Workspace
from ..services.auth import get_credential
from ..services.azure_clients import AzureClients
from ..utils.retry import with_retry
from .base_agent import BaseAgent


class DiscoveryAgent(BaseAgent):
    name = "discovery"
    output_subdir = "discovery"

    def __init__(self, settings=None):
        super().__init__(settings)
        self.credential = get_credential(self.settings)
        self.clients = AzureClients(self.credential)

    def discover_subscriptions(self) -> list[Subscription]:
        subs: list[Subscription] = []
        try:
            client = self.clients.subscriptions()
            for sub in with_retry(
                lambda: list(client.subscriptions.list()),
                max_attempts=self.settings.retry_max_attempts,
                backoff_seconds=self.settings.retry_backoff_seconds,
                logger=self.logger,
            ):
                if self.settings.subscriptions and sub.subscription_id not in self.settings.subscriptions:
                    continue
                subs.append(
                    Subscription(
                        subscription_id=sub.subscription_id or "",
                        display_name=sub.display_name or "",
                        state=str(sub.state) if sub.state else "",
                        tenant_id=getattr(sub, "tenant_id", "") or self.settings.tenant_id,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self.errors.add("list_subscriptions", exc)
            self.logger.error("Subscription discovery failed: %s", exc)
        self.logger.info("Discovered %d subscriptions", len(subs))
        return subs

    def discover_resource_groups(self, subs: list[Subscription]) -> list[ResourceGroup]:
        groups: list[ResourceGroup] = []
        for sub in subs:
            try:
                rm = self.clients.resource(sub.subscription_id)
                for rg in rm.resource_groups.list():
                    if self.settings.resource_groups and rg.name not in self.settings.resource_groups:
                        continue
                    groups.append(
                        ResourceGroup(
                            name=rg.name or "",
                            subscription_id=sub.subscription_id,
                            location=rg.location or "",
                            tags=rg.tags or {},
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                self.errors.add(f"list_resource_groups:{sub.subscription_id}", exc)
        self.logger.info("Discovered %d resource groups", len(groups))
        return groups

    def discover_workspaces(self, subs: list[Subscription]) -> list[Workspace]:
        workspaces: list[Workspace] = []
        for sub in subs:
            try:
                synapse = self.clients.synapse(sub.subscription_id)
                for ws in synapse.workspaces.list():
                    if not self._matches_filters(ws):
                        continue
                    workspaces.append(self._map_workspace(ws, sub.subscription_id))
            except HttpResponseError as exc:
                self.errors.add(f"list_workspaces:{sub.subscription_id}", exc)
                self.logger.warning("Workspace listing failed for %s: %s", sub.subscription_id, exc)
            except Exception as exc:  # noqa: BLE001
                self.errors.add(f"list_workspaces:{sub.subscription_id}", exc)
        self.logger.info("Discovered %d Synapse workspaces", len(workspaces))
        return workspaces

    def _matches_filters(self, ws) -> bool:
        if self.settings.workspace_names and ws.name not in self.settings.workspace_names:
            return False
        if self.settings.regions and (ws.location or "").lower() not in [r.lower() for r in self.settings.regions]:
            return False
        return True

    def _map_workspace(self, ws, subscription_id: str) -> Workspace:
        rg = ""
        if ws.id:
            parts = ws.id.split("/")
            if "resourceGroups" in parts:
                rg = parts[parts.index("resourceGroups") + 1]
        git = getattr(ws, "workspace_repository_configuration", None)
        endpoints = getattr(ws, "connectivity_endpoints", {}) or {}
        return Workspace(
            name=ws.name or "",
            workspace_id=ws.id or "",
            subscription_id=subscription_id,
            resource_group=rg,
            location=ws.location or "",
            tags=ws.tags or {},
            managed_resource_group=getattr(ws, "managed_resource_group_name", "") or "",
            dev_endpoint=endpoints.get("dev", ""),
            sql_endpoint=endpoints.get("sql", ""),
            sql_ondemand_endpoint=endpoints.get("sqlOnDemand", ""),
            default_storage_account=getattr(
                getattr(ws, "default_data_lake_storage", None), "account_url", ""
            ) or "",
            default_filesystem=getattr(
                getattr(ws, "default_data_lake_storage", None), "filesystem", ""
            ) or "",
            git_provider=getattr(git, "type", "") or "",
            git_repo=getattr(git, "repository_name", "") or "",
            public_network_access=str(getattr(ws, "public_network_access", "") or ""),
        )

    def run(self) -> dict:
        self.logger.info("Discovery starting")
        subs = self.discover_subscriptions()
        groups = self.discover_resource_groups(subs)
        workspaces = self.discover_workspaces(subs)

        out = self.output_dir
        write_json([s.model_dump() for s in subs], out / "subscriptions.json")
        write_json([g.model_dump() for g in groups], out / "resource_groups.json")
        write_json([w.model_dump() for w in workspaces], out / "workspaces.json")

        access_ok = bool(subs) and len(self.errors.errors) == 0
        summary = (
            f"# Discovery Summary\n\n"
            f"- Subscriptions: {len(subs)}\n"
            f"- Resource groups: {len(groups)}\n"
            f"- Synapse workspaces: {len(workspaces)}\n"
            f"- Access validation: {'OK' if access_ok else 'partial — see error log'}\n\n"
            f"## Workspaces\n\n"
            + ("\n".join(f"- {w.name} ({w.location}) — {w.resource_group}" for w in workspaces) or "- none")
        )
        write_markdown(summary, out / "discovery_summary.md")
        self.save_errors("discovery_errors.json")
        self.logger.info("Discovery complete")
        return {"subscriptions": len(subs), "resource_groups": len(groups), "workspaces": len(workspaces)}
