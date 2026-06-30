"""Dashboard Agent.

Generates an offline static HTML dashboard (Chart.js) plus Power BI-ready CSV
datasets and a Power BI model guide.
"""
from __future__ import annotations

from ..exporters.csv_writer import write_csv
from ..exporters.json_writer import read_json, write_json
from ..exporters.markdown_writer import write_markdown
from ..exporters.powerbi_pbip import generate_pbip
from ..templates.dashboard_template import render_dashboard
from .base_agent import BaseAgent


class DashboardAgent(BaseAgent):
    name = "dashboard"
    output_subdir = "dashboard"

    def _inv(self):
        p = self.settings.subdir("inventory") / "synapse_inventory.json"
        return read_json(p) if p.exists() else {"workspaces": []}

    def _scores(self):
        p = self.settings.subdir("assessment") / "complexity_scores.json"
        return read_json(p) if p.exists() else []

    def _findings(self):
        p = self.settings.subdir("assessment") / "security_findings.json"
        return read_json(p) if p.exists() else []

    def _complexity(self):
        p = self.settings.subdir("assessment") / "migration_complexity.json"
        return read_json(p) if p.exists() else []

    def _optimizations(self):
        p = self.settings.subdir("assessment") / "fabric_optimizations.json"
        return read_json(p) if p.exists() else []

    def _run_errors(self):
        p = self.settings.output_dir / "logs" / "inventory_errors.json"
        if not p.exists():
            return []
        out = []
        for e in read_json(p):
            ctx = e.get("context", "")
            if ctx.startswith("pipeline_runs:"):
                err = str(e.get("error") or "")
                kind = "Forbidden (missing monitoring permission)" if "403" in err else err[:120]
                out.append({"workspace": ctx.split(":", 1)[1], "issue": kind})
        return out

    def run(self) -> dict:
        self.logger.info("Dashboard starting")
        inv = self._inv()
        ws = inv.get("workspaces", [])
        names = sorted(w["workspace"]["name"] for w in ws)

        def collect(key):
            return [r for w in ws for r in w.get(key, [])]

        data = {
            "workspaces": len(ws),
            "workspace_names": names,
            "workspaces_t": [{**w["workspace"], "assessment_status": w.get("assessment_status", ""),
                              "inaccessible_artifacts": ",".join(w.get("inaccessible_artifacts", []))} for w in ws],
            "spark_pools": collect("spark_pools"), "sql_pools": collect("sql_pools"),
            "pipelines": collect("pipelines"), "notebooks": collect("notebooks"),
            "pipeline_activities": collect("pipeline_activities"),
            "triggers": collect("triggers"), "linked_services": collect("linked_services"),
            "datasets": collect("datasets"), "dataflows": collect("dataflows"),
            "integration_runtimes": collect("integration_runtimes"),
            "pipeline_runs": collect("pipeline_runs"), "pipeline_run_stats": collect("pipeline_run_stats"),
            "pipeline_run_errors": self._run_errors(),
            "migration_complexity": self._complexity(),
            "fabric_optimizations": self._optimizations(),
        }
        data["run_summary"] = _run_summary(data["pipeline_runs"], data["pipeline_run_stats"])
        out = self.output_dir
        (out / "data").mkdir(exist_ok=True)
        (out / "assets").mkdir(exist_ok=True)
        write_json(data, out / "data" / "dashboard.json")
        (out / "index.html").write_text(render_dashboard(data), encoding="utf-8")
        if self.settings.include_powerbi_outputs:
            self._powerbi(inv)
        self.logger.info("Dashboard complete")
        return {"workspaces": len(ws)}

    def _powerbi(self, inv) -> None:
        pb = self.settings.output_dir.parent / "powerbi"
        pb.mkdir(parents=True, exist_ok=True)
        ws = inv.get("workspaces", [])
        write_csv([w["workspace"] for w in ws], pb / "workspaces.csv")
        write_csv([p for w in ws for p in w.get("pipelines", [])], pb / "pipelines.csv")
        write_csv([a for w in ws for a in w.get("pipeline_activities", [])], pb / "pipeline_activities.csv")
        write_csv([s for w in ws for s in w.get("pipeline_run_stats", [])] or [{"pipeline": "", "workspace": ""}],
                  pb / "pipeline_run_stats.csv")
        write_csv([n for w in ws for n in w.get("notebooks", [])], pb / "notebooks.csv")
        write_csv([s for w in ws for s in w.get("spark_pools", [])], pb / "spark_pools.csv")
        write_csv([s for w in ws for s in w.get("sql_pools", [])], pb / "sql_pools.csv")
        write_csv([s for w in ws for s in w.get("linked_services", [])], pb / "linked_services.csv")
        write_csv([d for w in ws for d in w.get("datasets", [])], pb / "datasets.csv")
        write_csv([{"name": d.get("name"), "workspace": d.get("workspace"), "dataflow_type": d.get("dataflow_type"),
                    "source_count": d.get("source_count", 0), "sink_count": d.get("sink_count", 0),
                    "transformation_count": d.get("transformation_count", 0),
                    "transformation_types": ",".join(d.get("transformation_types", [])),
                    "parameter_count": d.get("parameter_count", 0), "folder": d.get("folder", "")}
                   for w in ws for d in w.get("dataflows", [])]
                  or [{"name": "", "workspace": "", "dataflow_type": "", "source_count": 0, "sink_count": 0,
                       "transformation_count": 0, "transformation_types": "", "parameter_count": 0, "folder": ""}],
                  pb / "dataflows.csv",
                  ["name", "workspace", "dataflow_type", "source_count", "sink_count",
                   "transformation_count", "transformation_types", "parameter_count", "folder"])
        scores = self._scores()
        findings = self._findings()
        write_csv([{"artifact": f.get("artifact"), "severity": str(f.get("severity")), "message": f.get("message")}
                   for f in findings] or [{"artifact": "", "severity": "", "message": ""}],
                  pb / "security_findings.csv", ["artifact", "severity", "message"])
        write_csv([{"artifact": s.get("artifact"), "score": s.get("score", 0)} for s in scores]
                  or [{"artifact": "", "score": 0}], pb / "migration_complexity.csv", ["artifact", "score"])
        write_csv([{"artifact": s.get("artifact"),
                    "fabric_target": (n[0] if (n := s.get("notes")) else "")} for s in scores]
                  or [{"artifact": "", "fabric_target": ""}], pb / "fabric_recommendations.csv", ["artifact", "fabric_target"])
        cx_cols = ["artifact", "artifact_type", "workspace", "score", "complexity", "estimated_effort_days", "fabric_target"]
        write_csv([{k: c.get(k) for k in cx_cols} for c in self._complexity()]
                  or [dict.fromkeys(cx_cols, "")], pb / "migration_complexity_detail.csv", cx_cols)
        opt_cols = ["artifact", "artifact_type", "workspace", "category", "recommendation", "fabric_feature", "impact"]
        write_csv([{k: o.get(k) for k in opt_cols} for o in self._optimizations()]
                  or [dict.fromkeys(opt_cols, "")], pb / "fabric_optimizations.csv", opt_cols)
        generate_pbip(pb)
        write_markdown(_MODEL_GUIDE, pb / "PowerBI_Model_Guide.md")


def _run_summary(runs: list[dict], stats: list[dict]) -> dict:
    """Estate-wide pipeline-run rollup for dashboard KPIs and charts."""
    total = len(runs)
    status: dict[str, int] = {}
    by_day: dict[str, int] = {}
    durs = []
    for r in runs:
        status[r.get("status", "")] = status.get(r.get("status", ""), 0) + 1
        d = (r.get("run_start") or "")[:10]
        if d:
            by_day[d] = by_day.get(d, 0) + 1
        if r.get("duration_ms"):
            durs.append(r["duration_ms"])
    batch = sum(s.get("batch_runs", 0) for s in stats)
    realtime = sum(s.get("realtime_runs", 0) for s in stats)
    reruns = sum(s.get("reruns", 0) for s in stats)
    return {
        "total_runs": total, "succeeded": status.get("Succeeded", 0),
        "failed": status.get("Failed", 0), "cancelled": status.get("Cancelled", 0),
        "reruns": reruns, "batch": batch, "realtime": realtime,
        "success_rate": round(100 * status.get("Succeeded", 0) / total, 1) if total else 0.0,
        "avg_duration_ms": int(sum(durs) / len(durs)) if durs else 0,
        "status_breakdown": dict(sorted(status.items())),
        "runs_by_day": dict(sorted(by_day.items())),
    }


_MODEL_GUIDE = """# Power BI Model Guide

A ready-to-open Power BI Project (`SynapseMigration.pbip`) is generated alongside
the CSVs. Enable **File > Options > Preview features > Power BI Project save**,
then open `SynapseMigration.pbip` in Power BI Desktop.

## Data source
All tables import from the CSV extracts via the `DataFolder` parameter (defaults
to this folder). Move the CSVs? Update `DataFolder` under Transform data.

## Tables
workspaces, pipelines, pipeline_activities, notebooks, spark_pools, sql_pools,
linked_services, datasets, dataflows, security_findings, migration_complexity,
fabric_recommendations.

## Relationships
Link each child table to `workspaces[name]` via its `workspace` column. Link
security_findings / migration_complexity / fabric_recommendations on `artifact`.

## Key measures (pre-built)
- Workspace Count, Regions, Pipeline Count, Notebook Count, Delta Notebooks %
- Spark Pool Count, SQL Pool Count, Open Findings, Avg Complexity

## Slicers
region (workspaces[location]), workspace, severity, fabric_target.

## Report pages
Overview, Estate Inventory, Spark & SQL, Migration Risk, Fabric Targets.
Add visuals on each page from the pre-built measures and dimension columns.
"""
