"""Inventory Agent.

Collects all Synapse artifacts from discovered workspaces: Spark/SQL pools via
the management SDK, and pipelines/notebooks/triggers/linked services/datasets/
SQL scripts/Spark jobs via the data-plane REST client. Builds a dependency map
and exports JSON, Excel, CSV index. Continues on per-artifact failure.
"""
from __future__ import annotations

import re
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from ..exporters.csv_writer import write_csv
from ..exporters.excel_writer import write_workbook
from ..exporters.json_writer import read_json, write_json
from ..models.inventory import (
    Dataflow,
    Dataset,
    IntegrationRuntime,
    Inventory,
    LinkedService,
    Notebook,
    Pipeline,
    PipelineActivity,
    PipelineRun,
    PipelineRunStats,
    SparkPool,
    SqlPool,
    StorageDependency,
    Trigger,
    Workspace,
    WorkspaceInventory,
)
from ..services.auth import get_credential
from ..services.azure_clients import AzureClients
from ..services.synapse_rest import SynapseRestClient
from .base_agent import BaseAgent

_SECRET_PAT = re.compile(r"(password|secret|key|token|pwd)\s*[=:]", re.I)
_PATH_PAT = re.compile(r"(abfss://|wasbs?://|adl://|https://[\w.-]+\.blob\.core)")


class InventoryAgent(BaseAgent):
    name = "inventory"
    output_subdir = "inventory"

    def __init__(self, settings=None):
        super().__init__(settings)
        self.credential = get_credential(self.settings)
        self.clients = AzureClients(self.credential)

    def _load_workspaces(self) -> list[Workspace]:
        path = self.settings.subdir("discovery") / "workspaces.json"
        if not path.exists():
            self.logger.error("No workspaces.json — run discover first")
            return []
        return [Workspace(**w) for w in read_json(path)]

    def collect_pools(self, ws: Workspace) -> tuple[list[SparkPool], list[SqlPool]]:
        spark: list[SparkPool] = []
        sql: list[SqlPool] = []
        try:
            mgmt = self.clients.synapse(ws.subscription_id)
            for sp in mgmt.big_data_pools.list_by_workspace(ws.resource_group, ws.name):
                auto = getattr(sp, "auto_scale", None)
                pause = getattr(sp, "auto_pause", None)
                spark.append(SparkPool(
                    name=sp.name or "", workspace=ws.name,
                    node_size=str(getattr(sp, "node_size", "") or ""),
                    node_size_family=str(getattr(sp, "node_size_family", "") or ""),
                    node_count=getattr(sp, "node_count", 0) or 0,
                    autoscale_enabled=bool(getattr(auto, "enabled", False)),
                    min_nodes=getattr(auto, "min_node_count", 0) or 0,
                    max_nodes=getattr(auto, "max_node_count", 0) or 0,
                    auto_pause_enabled=bool(getattr(pause, "enabled", False)),
                    auto_pause_minutes=getattr(pause, "delay_in_minutes", 0) or 0,
                    spark_version=getattr(sp, "spark_version", "") or "",
                ))
        except Exception as exc:  # noqa: BLE001
            self.errors.add(f"spark_pools:{ws.name}", exc)
        try:
            mgmt = self.clients.synapse(ws.subscription_id)
            for dp in mgmt.sql_pools.list_by_workspace(ws.resource_group, ws.name):
                sku_obj = getattr(dp, "sku", None)
                pool = SqlPool(
                    name=dp.name or "", workspace=ws.name,
                    sku=getattr(sku_obj, "name", "") or "",
                    tier=getattr(sku_obj, "tier", "") or "",
                    status=getattr(dp, "status", "") or "",
                    is_serverless="serverless" in str(getattr(sku_obj, "name", "")).lower(),
                    collation=getattr(dp, "collation", "") or "",
                )
                self._collect_table_sizes(ws, pool)
                sql.append(pool)
        except Exception as exc:  # noqa: BLE001
            self.errors.add(f"sql_pools:{ws.name}", exc)
        return spark, sql

    def _collect_table_sizes(self, ws: Workspace, pool: SqlPool) -> None:
        """Best-effort DMV table-size collection for dedicated SQL pools.

        Requires pyodbc + an ODBC driver and network/Entra access to the SQL
        endpoint. Any failure is captured non-fatally and sizes stay zeroed.
        """
        if pool.is_serverless or not ws.sql_endpoint:
            return
        try:
            import pyodbc  # type: ignore
        except Exception:  # noqa: BLE001
            return
        query = (
            "SELECT t.name AS table_name, SUM(p.reserved_page_count)*8/1024.0 AS mb "
            "FROM sys.dm_pdw_nodes_db_partition_stats p "
            "JOIN sys.tables t ON p.object_id=t.object_id "
            "GROUP BY t.name ORDER BY mb DESC"
        )
        try:
            token = self.credential.get_token("https://database.windows.net/.default").token
            conn_str = (
                "Driver={ODBC Driver 18 for SQL Server};"
                f"Server={ws.sql_endpoint},1433;Database={pool.name};Encrypt=yes;"
            )
            import struct
            packed = token.encode("utf-16-le")
            attrs = {1256: struct.pack("=i", len(packed)) + packed}
            with pyodbc.connect(conn_str, attrs_before=attrs, timeout=15) as cn:
                rows = cn.cursor().execute(query).fetchall()
            pool.table_count = len(rows)
            pool.total_size_mb = round(sum(float(r[1] or 0) for r in rows), 2)
            if rows:
                pool.largest_table, pool.largest_table_mb = rows[0][0], round(float(rows[0][1] or 0), 2)
            pool.sizes_collected = True
        except Exception as exc:  # noqa: BLE001
            self.errors.add(f"sql_table_sizes:{ws.name}/{pool.name}", exc)

    def _rest(self, ws: Workspace) -> SynapseRestClient | None:
        if not ws.dev_endpoint:
            self.errors.add(f"rest:{ws.name}", ValueError("no dev endpoint"))
            return None
        return SynapseRestClient(ws.dev_endpoint, self.credential, self.settings)

    def collect_artifacts(self, ws: Workspace) -> WorkspaceInventory:
        inv = WorkspaceInventory(workspace=ws)
        spark, sql = self.collect_pools(ws)
        inv.spark_pools, inv.sql_pools = spark, sql
        rest = self._rest(ws)
        if not rest:
            return inv
        inv.pipelines, inv.pipeline_activities = self._pipelines(ws, rest)
        inv.notebooks = self._notebooks(ws, rest)
        inv.triggers = self._triggers(ws, rest)
        inv.linked_services = self._linked_services(ws, rest)
        inv.datasets = self._datasets(ws, rest)
        inv.dataflows = self._dataflows(ws, rest)
        inv.integration_runtimes = self._irs(ws, rest)
        if self.settings.include_pipeline_run_history:
            inv.pipeline_runs, inv.pipeline_run_stats = self._pipeline_runs(ws, rest, inv.triggers)
        inv.storage_dependencies = self._storage(ws)
        self._set_status(ws, inv)
        return inv

    def _set_status(self, ws: Workspace, inv: WorkspaceInventory) -> None:
        """Derive Accessible / Partial / Forbidden from non-fatal errors."""
        blocked = [e["context"].split(":", 1)[0] for e in self.errors.errors
                   if e["context"].endswith(f":{ws.name}") and "403" in (e.get("error") or "")]
        inv.inaccessible_artifacts = sorted(set(blocked))
        artifacts = [inv.pipelines, inv.notebooks, inv.triggers, inv.linked_services, inv.datasets, inv.dataflows]
        if blocked and not any(artifacts):
            inv.assessment_status = "Forbidden"
        elif blocked:
            inv.assessment_status = "Partial"
        else:
            inv.assessment_status = "Accessible"

    def _safe(self, ctx: str, fn, *args) -> list[dict[str, Any]]:
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001
            self.errors.add(ctx, exc)
            return []

    def _pipelines(self, ws, rest) -> tuple[list[Pipeline], list[PipelineActivity]]:
        pls, acts = [], []
        for raw in self._safe(f"pipelines:{ws.name}", rest.pipelines):
            props = raw.get("properties", {})
            activities = props.get("activities", [])
            types = [a.get("type", "") for a in activities]
            ls_refs, ds_refs = [], []
            for a in activities:
                for ls in re.findall(r'"referenceName"\s*:\s*"([^"]+)"', str(a)):
                    ls_refs.append(ls)
                deps = [d.get("activity", "") for d in a.get("dependsOn", []) if d.get("activity")]
                acts.append(PipelineActivity(
                    pipeline=raw.get("name", ""), workspace=ws.name,
                    name=a.get("name", ""), activity_type=a.get("type", ""),
                    has_retry=bool(a.get("policy", {}).get("retry")),
                    depends_on_count=len(a.get("dependsOn", [])),
                    depends_on=deps,
                ))
            pls.append(Pipeline(
                name=raw.get("name", ""), workspace=ws.name,
                activity_count=len(activities), activity_types=sorted(set(types)),
                parameter_count=len(props.get("parameters", {})),
                has_nested_activities=any("activities" in a for a in activities),
                linked_service_refs=sorted(set(ls_refs)), dataset_refs=sorted(set(ds_refs)),
            ))
        return pls, acts

    # Batch trigger types map to scheduled/window workloads; rest treated as real-time/event.
    _BATCH_TRIGGERS = {"ScheduleTrigger", "TumblingWindowTrigger"}

    def _pipeline_runs(self, ws, rest, triggers) -> tuple[list[PipelineRun], list[PipelineRunStats]]:
        days = max(1, self.settings.pipeline_run_history_days)
        now = datetime.now(UTC)
        after = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        before = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_runs = self._safe(f"pipeline_runs:{ws.name}", rest.pipeline_runs, after, before) or []
        runs: list[PipelineRun] = []
        for r in raw_runs:
            inv_type = (r.get("invokedBy", {}) or {}).get("invokedByType", "")
            runs.append(PipelineRun(
                run_id=r.get("runId", ""), pipeline=r.get("pipelineName", ""), workspace=ws.name,
                status=r.get("status", ""), invoked_by=(r.get("invokedBy", {}) or {}).get("name", ""),
                invoked_type=inv_type, is_rerun=bool(r.get("isLatest") is False) or inv_type == "Rerun",
                run_start=r.get("runStart", "") or "", run_end=r.get("runEnd", "") or "",
                duration_ms=int(r.get("durationInMs") or 0),
            ))
        return runs, self._run_stats(ws.name, runs)

    def _run_stats(self, wsname: str, runs: list[PipelineRun]) -> list[PipelineRunStats]:
        by_pipe: dict[str, list[PipelineRun]] = {}
        for r in runs:
            by_pipe.setdefault(r.pipeline, []).append(r)
        stats: list[PipelineRunStats] = []
        for pipe, rs in by_pipe.items():
            durs = [r.duration_ms for r in rs if r.duration_ms > 0]
            ok = sum(1 for r in rs if r.status == "Succeeded")
            starts = sorted(r.run_start for r in rs if r.run_start)
            stats.append(PipelineRunStats(
                pipeline=pipe, workspace=wsname, total_runs=len(rs), succeeded=ok,
                failed=sum(1 for r in rs if r.status == "Failed"),
                cancelled=sum(1 for r in rs if r.status == "Cancelled"),
                in_progress=sum(1 for r in rs if r.status in ("InProgress", "Queued")),
                reruns=sum(1 for r in rs if r.is_rerun),
                batch_runs=sum(1 for r in rs if r.invoked_type in self._BATCH_TRIGGERS),
                realtime_runs=sum(1 for r in rs if r.invoked_type not in self._BATCH_TRIGGERS),
                success_rate=round(100 * ok / len(rs), 1) if rs else 0.0,
                avg_duration_ms=int(statistics.mean(durs)) if durs else 0,
                max_duration_ms=max(durs) if durs else 0, min_duration_ms=min(durs) if durs else 0,
                first_run=starts[0] if starts else "", last_run=starts[-1] if starts else "",
            ))
        return sorted(stats, key=lambda s: s.total_runs, reverse=True)


    def _notebooks(self, ws, rest) -> list[Notebook]:
        out = []
        for raw in self._safe(f"notebooks:{ws.name}", rest.notebooks):
            props = raw.get("properties", {})
            cells = props.get("cells", [])
            source = "\n".join("".join(c.get("source", [])) for c in cells)
            imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", source, re.M)
            out.append(Notebook(
                name=raw.get("name", ""), workspace=ws.name,
                language=props.get("metadata", {}).get("language_info", {}).get("name", ""),
                cell_count=len(cells), line_count=source.count("\n") + 1,
                imports=sorted(set(imports))[:50], uses_spark="spark" in source.lower(),
                has_hardcoded_paths=bool(_PATH_PAT.search(source)),
                has_secrets=bool(_SECRET_PAT.search(source)),
                uses_synapse_utils="mssparkutils" in source.lower(),
                uses_delta="delta" in source.lower(),
                uses_spark_config=bool(re.search(r"spark\.conf\.set|SparkConf|--conf\s|spark\.executor|spark\.sql\.shuffle", source, re.I)),
                code_preview=source[:8000],
            ))
        return out

    # Maps the Synapse trigger type to a friendly initiation method.
    _TRIGGER_INIT = {
        "ScheduleTrigger": "Schedule",
        "TumblingWindowTrigger": "Tumbling window",
        "BlobEventsTrigger": "Storage event",
        "CustomEventsTrigger": "Custom event",
    }

    def _triggers(self, ws, rest) -> list[Trigger]:
        out = []
        for raw in self._safe(f"triggers:{ws.name}", rest.triggers):
            p = raw.get("properties", {})
            ttype = p.get("type", "")
            tp = p.get("typeProperties", {})
            rec = tp.get("recurrence", tp)  # schedule uses .recurrence; tumbling-window is flat
            freq = rec.get("frequency", "") if isinstance(rec, dict) else ""
            interval = rec.get("interval", 0) if isinstance(rec, dict) else 0
            recurrence = f"Every {interval} {freq}".strip() if freq else ""
            scope = tp.get("scope", "")
            if scope:
                scope = scope.split("/")[-1]
            pipes = [x.get("pipelineReference", {}).get("referenceName", "") for x in p.get("pipelines", [])]
            out.append(Trigger(
                name=raw.get("name", ""), workspace=ws.name, trigger_type=ttype,
                runtime_state=p.get("runtimeState", ""),
                init_method=self._TRIGGER_INIT.get(ttype, "Manual"),
                recurrence=recurrence, frequency=freq, interval=interval,
                start_time=rec.get("startTime", "") if isinstance(rec, dict) else "",
                end_time=rec.get("endTime", "") if isinstance(rec, dict) else "",
                time_zone=rec.get("timeZone", "") if isinstance(rec, dict) else "",
                event_scope=scope,
                pipeline_count=len(pipes),
                pipelines=[x for x in pipes if x],
            ))
        return out

    def _linked_services(self, ws, rest) -> list[LinkedService]:
        out = []
        for raw in self._safe(f"linked_services:{ws.name}", rest.linked_services):
            p = raw.get("properties", {})
            out.append(LinkedService(
                name=raw.get("name", ""), workspace=ws.name, service_type=p.get("type", ""),
                references_key_vault="keyVault" in str(p).lower() or "AzureKeyVault" in str(p),
            ))
        return out

    def _datasets(self, ws, rest) -> list[Dataset]:
        out = []
        for raw in self._safe(f"datasets:{ws.name}", rest.datasets):
            p = raw.get("properties", {})
            out.append(Dataset(
                name=raw.get("name", ""), workspace=ws.name, dataset_type=p.get("type", ""),
                linked_service=p.get("linkedServiceName", {}).get("referenceName", ""),
            ))
        return out

    # Mapping Data Flow transformation verbs detected from the data-flow script.
    _DF_TRANSFORMS = [
        "join", "lookup", "exists", "aggregate", "window", "pivot", "unpivot",
        "flatten", "derive", "select", "filter", "sort", "union", "split",
        "alterRow", "surrogateKey", "rank", "parse", "stringify", "cast", "assert",
    ]

    def _dataflows(self, ws, rest) -> list[Dataflow]:
        out = []
        for raw in self._safe(f"dataflows:{ws.name}", rest.dataflows):
            p = raw.get("properties", {})
            tp = p.get("typeProperties", {})
            sources = tp.get("sources", []) or []
            sinks = tp.get("sinks", []) or []
            transforms = tp.get("transformations", []) or []
            script = "\n".join(tp.get("scriptLines", []) or [])
            ttypes = sorted({t for t in self._DF_TRANSFORMS if re.search(rf"\b{t}\s*\(", script)})
            ds_refs, ls_refs = [], []
            for s in sources + sinks:
                dref = (s.get("dataset") or {}).get("referenceName")
                lref = (s.get("linkedService") or {}).get("referenceName")
                if dref:
                    ds_refs.append(dref)
                if lref:
                    ls_refs.append(lref)
            out.append(Dataflow(
                name=raw.get("name", ""), workspace=ws.name,
                dataflow_type=p.get("type", ""),
                source_count=len(sources), sink_count=len(sinks),
                transformation_count=len(transforms),
                transformation_types=ttypes,
                sources=[s.get("name", "") for s in sources],
                sinks=[s.get("name", "") for s in sinks],
                linked_service_refs=sorted(set(ls_refs)),
                dataset_refs=sorted(set(ds_refs)),
                parameter_count=len(p.get("parameters", {}) or {}),
                script_line_count=len(tp.get("scriptLines", []) or []),
                folder=(p.get("folder") or {}).get("name", ""),
            ))
        return out

    def _irs(self, ws, rest) -> list[IntegrationRuntime]:
        out = []
        try:
            mgmt = self.clients.synapse(ws.subscription_id)
            for ir in mgmt.integration_runtimes.list_by_workspace(ws.resource_group, ws.name):
                props = getattr(ir, "properties", None)
                out.append(IntegrationRuntime(
                    name=ir.name or "", workspace=ws.name,
                    ir_type=getattr(props, "type", "") or "",
                ))
        except Exception as exc:  # noqa: BLE001
            self.errors.add(f"integration_runtimes:{ws.name}", exc)
        return out

    def _storage(self, ws) -> list[StorageDependency]:
        deps = []
        if ws.default_storage_account:
            deps.append(StorageDependency(
                workspace=ws.name, storage_account=ws.default_storage_account,
                filesystem=ws.default_filesystem, source="default",
            ))
        return deps

    def run(self) -> dict:
        self.logger.info("Inventory starting")
        workspaces = self._load_workspaces()
        inventory = Inventory()
        for ws in workspaces:
            self.logger.info("Inventorying %s", ws.name)
            try:
                inventory.workspaces.append(self.collect_artifacts(ws))
            except Exception as exc:  # noqa: BLE001
                self.errors.add(f"workspace:{ws.name}", exc)
        out = self.output_dir
        write_json(inventory.model_dump(), out / "synapse_inventory.json")
        self._write_excel(inventory, out)
        self._write_index(inventory, out)
        self._write_dependency_map(inventory, out)
        self.save_errors("inventory_errors.json")
        counts = {
            "workspaces": len(inventory.workspaces),
            "pipelines": sum(len(w.pipelines) for w in inventory.workspaces),
            "notebooks": sum(len(w.notebooks) for w in inventory.workspaces),
            "dataflows": sum(len(w.dataflows) for w in inventory.workspaces),
        }
        self.logger.info("Inventory complete: %s", counts)
        return counts

    def _write_excel(self, inv: Inventory, out) -> None:
        s: dict[str, list[dict]] = {n: [] for n in [
            "Workspaces", "Spark Pools", "SQL Pools", "Pipelines", "Pipeline Activities",
            "Triggers", "Linked Services", "Datasets", "Dataflows", "Integration Runtimes", "Notebooks",
            "Spark Usage", "Storage Dependencies", "Security Findings", "Networking",
            "Migration Complexity", "Recommendations"]}
        for w in inv.workspaces:
            s["Workspaces"].append({**w.workspace.model_dump(), "assessment_status": w.assessment_status,
                                    "inaccessible_artifacts": ",".join(w.inaccessible_artifacts)})
            s["Spark Pools"] += [p.model_dump() for p in w.spark_pools]
            s["SQL Pools"] += [p.model_dump() for p in w.sql_pools]
            s["Pipelines"] += [p.model_dump() for p in w.pipelines]
            s["Pipeline Activities"] += [a.model_dump() for a in w.pipeline_activities]
            s["Triggers"] += [t.model_dump() for t in w.triggers]
            s["Linked Services"] += [x.model_dump() for x in w.linked_services]
            s["Datasets"] += [d.model_dump() for d in w.datasets]
            s["Dataflows"] += [d.model_dump() for d in w.dataflows]
            s["Integration Runtimes"] += [i.model_dump() for i in w.integration_runtimes]
            s["Notebooks"] += [n.model_dump() for n in w.notebooks]
            s["Spark Usage"] += [{"workspace": w.workspace.name, "notebook": n.name, "uses_spark": n.uses_spark, "uses_delta": n.uses_delta} for n in w.notebooks]
            s["Storage Dependencies"] += [d.model_dump() for d in w.storage_dependencies]
        write_workbook(s, out / "synapse_inventory.xlsx")

    def _write_index(self, inv: Inventory, out) -> None:
        rows = []
        for w in inv.workspaces:
            for p in w.pipelines:
                rows.append({"artifact": p.name, "type": "Pipeline", "workspace": w.workspace.name})
            for n in w.notebooks:
                rows.append({"artifact": n.name, "type": "Notebook", "workspace": w.workspace.name})
            for d in w.dataflows:
                rows.append({"artifact": d.name, "type": "Dataflow", "workspace": w.workspace.name})
        write_csv(rows, out / "artifact_index.csv", ["artifact", "type", "workspace"])

    def _write_dependency_map(self, inv: Inventory, out) -> None:
        dep = {w.workspace.name: {p.name: p.linked_service_refs for p in w.pipelines} for w in inv.workspaces}
        write_json(dep, out / "dependency_map.json")
