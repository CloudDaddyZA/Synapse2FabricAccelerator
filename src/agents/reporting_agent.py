"""Reporting Agent.

Generates consultant-ready executive and technical reports (Markdown + HTML),
risk register, dependency, and Fabric recommendation reports from inventory,
assessment, and migration outputs. Every section is data-driven: populated
from collected artifacts, complexity scores, findings, and wave plans.
"""
from __future__ import annotations

from collections import Counter

from ..exporters.json_writer import read_json
from ..exporters.markdown_writer import write_html, write_markdown
from .base_agent import BaseAgent


def _table(headers: list[str], rows: list[list], empty: str = "No data collected.") -> str:
    if not rows:
        return f"_{empty}_\n"
    h = "| " + " | ".join(headers) + " |\n"
    sep = "|" + "|".join("---" for _ in headers) + "|\n"
    body = "".join("| " + " | ".join(str(c) for c in r) + " |\n" for r in rows)
    return h + sep + body


def _pct(part: int, whole: int) -> str:
    return f"{(100 * part / whole):.0f}%" if whole else "0%"


class ReportingAgent(BaseAgent):
    name = "reporting"
    output_subdir = "reports"

    def _load(self, sub: str, file: str, default):
        p = self.settings.subdir(sub) / file
        return read_json(p) if p.exists() else default

    def run(self) -> dict:
        self.logger.info("Reporting starting")
        inv = self._load("inventory", "synapse_inventory.json", {"workspaces": []})
        summary = self._load("assessment", "assessment_summary.json", {})
        scores = self._load("assessment", "complexity_scores.json", [])
        findings = self._load("assessment", "security_findings.json", [])
        recs = self._load("migration", "fabric_recommendations.json", [])
        waves = self._load("migration", "migration_waves.json", [])
        out = self.output_dir

        exec_md = self._executive(inv, summary, scores, findings, recs, waves)
        tech_md = self._technical(inv, scores, findings, recs)
        write_markdown(exec_md, out / "executive_migration_summary.md")
        write_html("Executive Migration Summary", exec_md, out / "executive_migration_summary.html")
        write_markdown(tech_md, out / "technical_assessment_report.md")
        write_html("Technical Assessment Report", tech_md, out / "technical_assessment_report.html")
        write_markdown("# Synapse Audit Report\n\n" + exec_md + "\n\n---\n\n" + tech_md, out / "synapse_audit_report.md")
        write_html("Synapse Audit Report", exec_md + "\n\n" + tech_md, out / "synapse_audit_report.html")
        write_markdown(self._risk_register(scores), out / "risk_register.md")
        write_markdown(self._dependency(inv), out / "dependency_report.md")
        write_markdown(self._fabric_recs(recs), out / "fabric_recommendations_report.md")
        write_html("Risk Register", self._risk_register(scores), out / "risk_register.html")
        write_html("Dependency Report", self._dependency(inv), out / "dependency_report.html")
        write_html("Fabric Recommendations", self._fabric_recs(recs), out / "fabric_recommendations_report.html")
        for fname, title, md in [
            ("admin_report", "Admin Report", self._admin(inv)),
            ("data_engineering_report", "Data Engineering Report", self._dataeng(inv)),
            ("data_warehousing_report", "Data Warehousing Report", self._warehouse(inv)),
            ("data_integration_report", "Data Integration Report", self._integration(inv)),
        ]:
            write_markdown(md, out / f"{fname}.md")
            write_html(title, md, out / f"{fname}.html")
        self.save_errors("reporting_errors.json")
        self.logger.info("Reporting complete")
        return {"reports": 13}

    def _executive(self, inv, summary, scores, findings, recs, waves) -> str:
        ws = inv.get("workspaces", [])
        n_pipe = sum(len(w.get("pipelines", [])) for w in ws)
        n_nb = sum(len(w.get("notebooks", [])) for w in ws)
        n_df = sum(len(w.get("dataflows", [])) for w in ws)
        n_spark = sum(len(w.get("spark_pools", [])) for w in ws)
        n_sql = sum(len(w.get("sql_pools", [])) for w in ws)
        total = len(scores) or 1
        crit = sum(1 for s in scores if s.get("migration_complexity") == "Critical")
        high = sum(1 for s in scores if s.get("migration_complexity") == "High")
        regions = sorted({w["workspace"].get("location", "?") for w in ws})
        accessible = sum(1 for w in ws if w.get("assessment_status") == "Accessible")
        status = Counter(w.get("assessment_status", "Accessible") for w in ws)
        max_wave = max((w.get("wave", 0) for w in waves), default=0)
        kpis = _table(["Metric", "Value"], [
            ["Workspaces", len(ws)], ["Pipelines", n_pipe], ["Notebooks", n_nb],            ["Dataflows", n_df],            ["Spark Pools", n_spark], ["SQL Pools", n_sql], ["Regions", ", ".join(regions) or "—"],
            ["Artifacts assessed", len(scores)], ["High/Critical complexity", f"{high + crit} ({_pct(high + crit, total)})"],
            ["Security findings", len(findings)], ["Fabric recommendations", len(recs)],
            ["Migration waves", max_wave], ["Fully accessible workspaces", f"{accessible}/{len(ws)}"],
        ])
        bands = _table(["Complexity Band", "Count", "Share"],
                       [[k, v, _pct(v, sum(summary.values()) or 1)] for k, v in summary.items()])
        topc = sorted(scores, key=lambda s: s.get("score", 0), reverse=True)[:10]
        top = _table(["Artifact", "Type", "Workspace", "Score", "Complexity"],
                     [[s["artifact"], s["artifact_type"], s["workspace"], s.get("score", 0), s.get("migration_complexity")] for s in topc])
        statusrows = _table(["Status", "Workspaces"], [[k, v] for k, v in status.items()])
        return (
            "# Executive Migration Summary\n\n"
            "## Estate Overview\n" + kpis + "\n"
            "## Workspace Access Status\n" + statusrows + "\n"
            "## Migration Complexity Distribution\n" + bands + "\n"
            "## Migration Readiness\n"
            f"The estate spans **{len(ws)}** workspace(s) across **{len(regions)}** region(s) "
            f"with **{n_pipe + n_nb + n_df + n_spark + n_sql}** core artifacts. "
            f"**{_pct(high + crit, total)}** are High/Critical complexity; the rest are low-effort lift-and-shift. "
            "Suitable for phased, lakehouse-first Fabric migration.\n\n"
            "## High-Risk Areas\n" + top + "\n"
            "## Recommended Approach\n"
            "Phased waves, lakehouse-first: shadow Spark/notebook workloads onto Fabric Spark + OneLake, "
            "rebuild pipelines in Fabric Data Factory, migrate dedicated SQL pools to Warehouse last.\n\n"
            f"## Migration Waves\n{max_wave} phased waves cover all artifacts (see migration plan).\n\n"
            "## Executive Decisions Required\n- Fabric capacity (F-SKU) sizing\n- Cutover windows per wave\n"
            "- Networking/Private Link parity\n- RBAC and security model mapping"
        )

    def _technical(self, inv, scores, findings, recs) -> str:
        ws = inv.get("workspaces", [])
        wsrows = [[w["workspace"].get("name", ""), w["workspace"].get("location", ""),
                   len(w.get("pipelines", [])), len(w.get("notebooks", [])),
                   len(w.get("dataflows", [])),
                   len(w.get("spark_pools", [])), len(w.get("sql_pools", [])),
                   w.get("assessment_status", "")] for w in ws]
        inventory = _table(["Workspace", "Region", "Pipelines", "Notebooks", "Dataflows", "Spark", "SQL", "Status"], wsrows)
        nbs = [n for w in ws for n in w.get("notebooks", [])]
        nbtable = _table(["Notebook", "Workspace", "Lang", "Cells", "Spark", "Delta", "MSSparkUtils", "SparkConf"],
                         [[n["name"], n["workspace"], n.get("language", ""), n.get("cell_count", 0),
                           n.get("uses_spark"), n.get("uses_delta"), n.get("uses_synapse_utils"), n.get("uses_spark_config")] for n in nbs[:25]])
        sqls = [s for w in ws for s in w.get("sql_pools", [])]
        sqltable = _table(["SQL Pool", "Workspace", "SKU", "Tier", "Tables", "Size MB", "Serverless"],
                          [[s["name"], s["workspace"], s.get("sku", ""), s.get("tier", ""), s.get("table_count", 0), s.get("total_size_mb", 0), s.get("is_serverless")] for s in sqls])
        dfs = [d for w in ws for d in w.get("dataflows", [])]
        dftable = _table(["Dataflow", "Workspace", "Type", "Sources", "Sinks", "Transforms", "Transform Types"],
                         [[d["name"], d["workspace"], d.get("dataflow_type", ""), d.get("source_count", 0), d.get("sink_count", 0),
                           d.get("transformation_count", 0), ", ".join(d.get("transformation_types", [])[:6])] for d in dfs[:25]],
                         "No mapping/wrangling data flows found.")
        sec = _table(["Artifact", "Severity", "Finding"], [[f["artifact"], f.get("severity"), f.get("message")] for f in findings], "No security findings.")
        fmap = _table(["Source", "Type", "Fabric Target", "Effort"], [[r["source_artifact"], r["source_type"], r["fabric_target"], r["effort_band"]] for r in recs[:30]])
        return (
            "# Technical Assessment Report\n\n"
            "## Workspace Inventory\n" + inventory + "\n"
            "## Notebooks (Spark / Delta / MSSparkUtils)\n" + nbtable + "\n"
            "## Mapping & Wrangling Data Flows\n" + dftable + "\n"
            "## Dedicated/Serverless SQL Pools\n" + sqltable + "\n"
            "## Security & Networking Findings\n" + sec + "\n"
            "## Fabric Target Recommendations\n" + fmap + "\n"
            "## Validation Plan\n- Row counts match per table\n- Schema/type parity\n- Job duration baseline vs Fabric\n- RBAC/security parity"
        )

    def _risk_register(self, scores) -> str:
        rows = [[s["artifact"], s["artifact_type"], s["workspace"], s.get("migration_complexity"),
                 s.get("security_risk"), s.get("performance_risk"), s.get("score", 0)] for s in scores]
        return "# Risk Register\n\n" + _table(["Artifact", "Type", "Workspace", "Complexity", "Security", "Performance", "Score"], rows)

    def _dependency(self, inv) -> str:
        rows = [[w["workspace"]["name"], ls.get("name", ""), ls.get("service_type", ""), ls.get("references_key_vault")]
                for w in inv.get("workspaces", []) for ls in w.get("linked_services", [])]
        return "# Dependency Report\n\n" + _table(["Workspace", "Linked Service", "Type", "KeyVault"], rows)

    def _fabric_recs(self, recs) -> str:
        rows = [[r["source_artifact"], r["source_type"], r["fabric_target"], r["effort_band"], r.get("rationale", "")] for r in recs]
        return "# Fabric Recommendations\n\n" + _table(["Source", "Type", "Fabric Target", "Effort", "Rationale"], rows)

    # --- FAT-aligned category reports (Overview/Admin/DataEng/DW/Integration) ---
    def _admin(self, inv) -> str:
        ws = inv.get("workspaces", [])
        wsrows = [[w["workspace"].get("name", ""), w["workspace"].get("location", ""),
                   w["workspace"].get("managed_vnet"), w["workspace"].get("public_network_access", ""),
                   w["workspace"].get("git_provider", ""), w.get("assessment_status", "")] for w in ws]
        ls = [[x.get("name", ""), x["workspace"], x.get("service_type", ""), x.get("references_key_vault")]
              for w in ws for x in w.get("linked_services", [])]
        irs = [[i.get("name", ""), i["workspace"], i.get("ir_type", "")] for w in ws for i in w.get("integration_runtimes", [])]
        return ("# Admin Report\n\n## Workspaces, Networking & Git\n"
                + _table(["Workspace", "Region", "Managed VNet", "Public Access", "Git", "Status"], wsrows)
                + "\n## Linked Services\n" + _table(["Name", "Workspace", "Type", "KeyVault"], ls)
                + "\n## Integration Runtimes\n" + _table(["Name", "Workspace", "Type"], irs))

    def _dataeng(self, inv) -> str:
        ws = inv.get("workspaces", [])
        nb = [[n.get("name", ""), n["workspace"], n.get("language", ""), n.get("cell_count", 0),
               n.get("uses_spark"), n.get("uses_delta"), n.get("uses_synapse_utils"), n.get("uses_spark_config")]
              for w in ws for n in w.get("notebooks", [])]
        sp = [[s.get("name", ""), s["workspace"], s.get("node_size", ""), s.get("node_count", 0),
               s.get("autoscale_enabled"), s.get("auto_pause_enabled"), s.get("spark_version", "")]
              for w in ws for s in w.get("spark_pools", [])]
        return ("# Data Engineering Report\n\n## Spark Pools\n"
                + _table(["Name", "Workspace", "Node Size", "Nodes", "Autoscale", "Auto-pause", "Spark Ver"], sp)
                + "\n## Notebooks (Spark / Delta / MSSparkUtils / SparkConf)\n"
                + _table(["Notebook", "Workspace", "Lang", "Cells", "Spark", "Delta", "MSSparkUtils", "SparkConf"], nb)
                + "\n## Mapping & Wrangling Data Flows\n"
                + _table(["Dataflow", "Workspace", "Type", "Sources", "Sinks", "Transforms", "Transform Types"],
                         [[d.get("name", ""), d["workspace"], d.get("dataflow_type", ""), d.get("source_count", 0),
                           d.get("sink_count", 0), d.get("transformation_count", 0), ", ".join(d.get("transformation_types", [])[:6])]
                          for w in ws for d in w.get("dataflows", [])],
                         "No mapping/wrangling data flows found."))

    def _warehouse(self, inv) -> str:
        ws = inv.get("workspaces", [])
        sql = [[s.get("name", ""), s["workspace"], s.get("sku", ""), s.get("tier", ""), s.get("is_serverless"),
                s.get("table_count", 0), s.get("total_size_mb", 0), s.get("largest_table", "")]
               for w in ws for s in w.get("sql_pools", [])]
        return ("# Data Warehousing Report\n\n## Dedicated / Serverless SQL Pools\n"
                + _table(["Pool", "Workspace", "SKU", "Tier", "Serverless", "Tables", "Size MB", "Largest Table"], sql))

    def _integration(self, inv) -> str:
        ws = inv.get("workspaces", [])
        pl = [[p.get("name", ""), p["workspace"], p.get("activity_count", 0), p.get("parameter_count", 0),
               p.get("has_nested_activities"), ", ".join(p.get("activity_types", [])[:6])]
              for w in ws for p in w.get("pipelines", [])]
        tr = [[t.get("name", ""), t["workspace"], t.get("trigger_type", ""), t.get("runtime_state", "")]
              for w in ws for t in w.get("triggers", [])]
        ds = [[d.get("name", ""), d["workspace"], d.get("dataset_type", ""), d.get("linked_service", "")]
              for w in ws for d in w.get("datasets", [])]
        dfl = [[d.get("name", ""), d["workspace"], d.get("dataflow_type", ""), d.get("source_count", 0),
                d.get("sink_count", 0), d.get("transformation_count", 0), ", ".join(d.get("transformation_types", [])[:6])]
               for w in ws for d in w.get("dataflows", [])]
        return ("# Data Integration Report\n\n## Pipelines\n"
                + _table(["Pipeline", "Workspace", "Activities", "Params", "Nested", "Activity Types"], pl)
                + "\n## Mapping & Wrangling Data Flows\n"
                + _table(["Dataflow", "Workspace", "Type", "Sources", "Sinks", "Transforms", "Transform Types"], dfl,
                         "No mapping/wrangling data flows found.")
                + "\n## Triggers\n" + _table(["Name", "Workspace", "Type", "State"], tr)
                + "\n## Datasets\n" + _table(["Name", "Workspace", "Type", "Linked Service"], ds))
