"""Assessment Agent.

Scores each artifact for migration complexity, performance/security/operational
risk, Fabric compatibility, and modernization opportunity. Produces findings,
complexity scores, risk register (Excel), and a Fabric readiness markdown.
"""
from __future__ import annotations

from ..exporters.excel_writer import write_workbook
from ..exporters.json_writer import read_json, write_json
from ..exporters.markdown_writer import write_markdown
from ..models.assessment import (
    ArtifactScore,
    Assessment,
    FabricOptimization,
    Finding,
    MigrationComplexity,
)
from ..models.enums import ArtifactType, RiskLevel
from ..models.inventory import Dataflow, Inventory, Notebook, Pipeline, SparkPool, SqlPool
from ..utils.scoring import score_to_level, weighted_score
from .base_agent import BaseAgent


class AssessmentAgent(BaseAgent):
    name = "assessment"
    output_subdir = "assessment"

    def _load_inventory(self) -> Inventory:
        path = self.settings.subdir("inventory") / "synapse_inventory.json"
        if not path.exists():
            self.logger.error("No inventory — run inventory first")
            return Inventory()
        return Inventory(**read_json(path))

    def assess_pipeline(self, p: Pipeline) -> ArtifactScore:
        notes = []
        cx = weighted_score({
            "activities": min(p.activity_count * 3, 40),
            "types": len(p.activity_types) * 4,
            "nested": 20 if p.has_nested_activities else 0,
            "params": min(p.parameter_count * 2, 15),
        })
        if p.has_nested_activities:
            notes.append("Nested activities increase migration effort")
        if p.activity_count > 15:
            notes.append("Large pipeline; consider modularization")
        fc = 30 if any(t in {"ExecuteDataFlow"} for t in p.activity_types) else 10
        return ArtifactScore(
            artifact=p.name, artifact_type=ArtifactType.PIPELINE, workspace=p.workspace,
            migration_complexity=score_to_level(cx), fabric_compatibility_risk=score_to_level(fc),
            operational_risk=score_to_level(min(p.activity_count * 2, 50)),
            modernization_opportunity=score_to_level(40 if p.activity_count > 10 else 20),
            score=cx, notes=notes)

    def assess_notebook(self, n: Notebook) -> tuple[ArtifactScore, list[Finding]]:
        notes, findings = [], []
        cx = weighted_score({"lines": min(n.line_count // 10, 40), "imports": min(len(n.imports) * 2, 20), "synapse": 25 if n.uses_synapse_utils else 0})
        sec = 0
        if n.has_secrets:
            sec = 70
            findings.append(Finding(artifact=n.name, artifact_type=ArtifactType.NOTEBOOK, workspace=n.workspace, category="Security", severity=RiskLevel.HIGH, message="Possible hardcoded secret"))
        if n.has_hardcoded_paths:
            notes.append("Hardcoded storage paths; parameterize for OneLake")
        fc = 40 if n.uses_synapse_utils else 15
        return ArtifactScore(artifact=n.name, artifact_type=ArtifactType.NOTEBOOK, workspace=n.workspace, migration_complexity=score_to_level(cx), security_risk=score_to_level(sec), fabric_compatibility_risk=score_to_level(fc), modernization_opportunity=score_to_level(60 if not n.uses_delta else 20), score=cx, notes=notes), findings

    def assess_spark(self, sp: SparkPool) -> ArtifactScore:
        notes = []
        perf = 0 if sp.autoscale_enabled else 30
        if not sp.auto_pause_enabled:
            perf += 30
            notes.append("No auto-pause; cost optimization opportunity")
        return ArtifactScore(artifact=sp.name, artifact_type=ArtifactType.SPARK_POOL, workspace=sp.workspace, performance_risk=score_to_level(perf), modernization_opportunity=score_to_level(perf), score=perf, notes=notes)

    def assess_sql(self, dp: SqlPool) -> ArtifactScore:
        cx = 60 if not dp.is_serverless else 30
        notes = ["Map to Fabric Warehouse/Lakehouse"]
        if dp.sizes_collected:
            if dp.total_size_mb > 1_000_000:
                cx = min(cx + 20, 100)
                notes.append(f"Large dataset ~{dp.total_size_mb/1024:.0f} GB; plan staged data migration")
            notes.append(f"{dp.table_count} tables, largest {dp.largest_table} ~{dp.largest_table_mb:.0f} MB")
        return ArtifactScore(artifact=dp.name, artifact_type=ArtifactType.SQL_POOL, workspace=dp.workspace, migration_complexity=score_to_level(cx), fabric_compatibility_risk=score_to_level(40), score=cx, notes=notes)

    def assess_dataflow(self, df: Dataflow) -> ArtifactScore:
        notes = ["Rebuild as Dataflow Gen2 or Spark notebook"]
        cx = weighted_score({
            "transforms": min(df.transformation_count * 3, 40),
            "io": min((df.source_count + df.sink_count) * 4, 20),
            "heavy": 20 if set(df.transformation_types) & {"join", "aggregate", "window", "pivot", "unpivot", "surrogateKey", "rank", "flatten"} else 0,
        })
        if df.transformation_count > 10:
            notes.append("Many transformations; consider splitting into staged Dataflow Gen2 queries")
        fc = 35 if df.dataflow_type == "WranglingDataFlow" else 50
        return ArtifactScore(
            artifact=df.name, artifact_type=ArtifactType.DATAFLOW, workspace=df.workspace,
            migration_complexity=score_to_level(cx), fabric_compatibility_risk=score_to_level(fc),
            modernization_opportunity=score_to_level(50), score=cx, notes=notes)

    # ---- Detailed migration-complexity + Fabric optimization ----------------

    def pipeline_complexity(self, p: Pipeline) -> MigrationComplexity:
        """Score how hard a pipeline is to migrate, with explicit drivers."""
        types = set(p.activity_types)
        factors: list[str] = []
        sig: dict[str, int] = {"activities": min(p.activity_count * 2, 30),
                               "types": min(len(types) * 3, 18)}
        if p.activity_count:
            factors.append(f"{p.activity_count} activities across {len(types)} activity type(s)")
        if p.has_nested_activities:
            sig["nested"] = 18
            factors.append("Nested control-flow (ForEach/If/Until) containers to rebuild")
        if "ExecuteDataFlow" in types:
            sig["dataflow"] = 25
            factors.append("Mapping Data Flow(s) — no direct Fabric equivalent; rebuild as Dataflow Gen2 or Spark")
        if "ExecutePipeline" in types:
            sig["orchestration"] = 8
            factors.append("Invokes child pipelines — orchestration dependencies to preserve")
        if types & {"SqlPoolStoredProcedure", "Script"}:
            sig["sql"] = 10
            factors.append("Dedicated SQL pool stored-procedure/script dependency")
        if "Copy" in types:
            sig["copy"] = 6
            factors.append("Copy activities — relink sources to Fabric Connections/OneLake")
        if types & {"WebActivity", "WebHook", "Custom", "AzureFunctionActivity"}:
            sig["custom"] = 10
            factors.append("Web/Custom/Function activities may need refactor to Fabric-supported patterns")
        sig["params"] = min(p.parameter_count, 8)
        lsr = len(p.linked_service_refs)
        if lsr:
            sig["connections"] = min(lsr * 2, 10)
            factors.append(f"{lsr} linked-service reference(s) to map to Fabric Connections")
        score = weighted_score(sig)
        target = "Dataflow Gen2 + Data Pipeline" if "ExecuteDataFlow" in types else "Fabric Data Pipeline"
        return MigrationComplexity(
            artifact=p.name, artifact_type=ArtifactType.PIPELINE, workspace=p.workspace,
            score=score, complexity=score_to_level(score),
            estimated_effort_days=round(0.5 + score / 20, 1),
            factors=factors or ["Simple pipeline; near 1:1 rebuild in Fabric Data Factory"],
            fabric_target=target)

    def notebook_complexity(self, n: Notebook) -> MigrationComplexity:
        """Score how hard a notebook is to migrate, with explicit drivers."""
        factors: list[str] = []
        sig: dict[str, int] = {"size": min(n.line_count // 15, 30),
                               "imports": min(len(n.imports) * 2, 16)}
        if n.line_count:
            factors.append(f"{n.line_count} lines across {n.cell_count} cell(s)")
        if n.uses_synapse_utils:
            sig["mssparkutils"] = 18
            factors.append("Uses mssparkutils/Synapse APIs — migrate to Fabric notebookutils")
        if n.has_hardcoded_paths:
            sig["paths"] = 12
            factors.append("Hardcoded storage paths — repoint to OneLake")
        if n.has_secrets:
            sig["secrets"] = 15
            factors.append("Possible inline secret — externalize before migration")
        if n.uses_spark_config:
            sig["config"] = 8
            factors.append("Custom Spark configuration — move to a Fabric Environment")
        if n.language.lower() in {"scala", "csharp", "c#"}:
            sig["lang"] = 10
            factors.append(f"{n.language} notebook — validate Fabric runtime support")
        if not n.uses_delta:
            factors.append("Non-Delta storage — opportunity to adopt Delta on migration")
        score = weighted_score(sig)
        return MigrationComplexity(
            artifact=n.name, artifact_type=ArtifactType.NOTEBOOK, workspace=n.workspace,
            score=score, complexity=score_to_level(score),
            estimated_effort_days=round(0.5 + score / 25, 1),
            factors=factors or ["Self-contained notebook; light-touch port to Fabric"],
            fabric_target="Fabric Notebook")

    def pipeline_optimizations(self, p: Pipeline) -> list[FabricOptimization]:
        types = set(p.activity_types)
        opt: list[FabricOptimization] = []

        def add(cat: str, rec: str, feat: str, impact: RiskLevel) -> None:
            opt.append(FabricOptimization(artifact=p.name, artifact_type=ArtifactType.PIPELINE,
                                          workspace=p.workspace, category=cat, recommendation=rec,
                                          fabric_feature=feat, impact=impact))
        if "ExecuteDataFlow" in types:
            add("Modernization", "Rebuild Mapping Data Flows as Dataflow Gen2; push complex transforms into Spark notebooks.", "Dataflow Gen2", RiskLevel.HIGH)
        if "Copy" in types:
            add("Cost", "Replace copy-to-staging with OneLake shortcuts to query source data in place and avoid duplication.", "OneLake shortcuts", RiskLevel.HIGH)
            add("Performance", "Use incremental copy / CDC with watermark parameters instead of full reloads.", "Incremental copy", RiskLevel.MEDIUM)
        if p.linked_service_refs or "Copy" in types:
            add("Security", "Map linked services to Fabric Connections and authenticate with the workspace identity instead of stored keys.", "Fabric Connections", RiskLevel.MEDIUM)
        if p.has_nested_activities or p.activity_count > 15:
            add("Maintainability", "Modularize into child pipelines invoked via the Invoke Pipeline activity for reuse and clarity.", "Invoke Pipeline", RiskLevel.MEDIUM)
        if types & {"SqlPoolStoredProcedure", "Script"}:
            add("Modernization", "Repoint stored-procedure/script steps at a Fabric Warehouse; use T-SQL notebooks for set-based logic.", "Fabric Warehouse", RiskLevel.MEDIUM)
        add("Operational", "Replace schedule/tumbling-window triggers with Fabric schedules or event-driven Data Activator reflexes.", "Data Activator", RiskLevel.LOW)
        add("Maintainability", "Parameterize connections and paths to remove environment-specific hardcoding before promotion.", "Pipeline parameters", RiskLevel.LOW)
        return opt

    def notebook_optimizations(self, n: Notebook) -> list[FabricOptimization]:
        opt: list[FabricOptimization] = []

        def add(cat: str, rec: str, feat: str, impact: RiskLevel) -> None:
            opt.append(FabricOptimization(artifact=n.name, artifact_type=ArtifactType.NOTEBOOK,
                                          workspace=n.workspace, category=cat, recommendation=rec,
                                          fabric_feature=feat, impact=impact))
        if n.uses_synapse_utils:
            add("Modernization", "Replace mssparkutils calls with the Fabric notebookutils API (fs, credentials, notebook.run).", "notebookutils", RiskLevel.HIGH)
        if n.has_hardcoded_paths:
            add("Modernization", "Swap abfss:// hardcoded paths for OneLake relative paths or Lakehouse shortcuts.", "OneLake", RiskLevel.HIGH)
        if n.has_secrets:
            add("Security", "Move inline secrets to Azure Key Vault referenced through a Fabric workspace connection.", "Key Vault connection", RiskLevel.HIGH)
        if n.uses_delta:
            add("Performance", "Enable V-Order and schedule OPTIMIZE/VACUUM (or predictive optimization) on Delta tables.", "V-Order + Predictive Optimization", RiskLevel.MEDIUM)
        else:
            add("Performance", "Adopt Delta Lake tables with V-Order for faster reads and time-travel.", "Delta Lake", RiskLevel.MEDIUM)
        if n.uses_spark_config:
            add("Maintainability", "Move custom Spark configuration into a reusable Fabric Environment item.", "Fabric Environment", RiskLevel.MEDIUM)
        if n.line_count > 400:
            add("Maintainability", "Refactor the monolithic notebook into modular notebooks orchestrated via notebookutils.notebook.run.", "Modular notebooks", RiskLevel.MEDIUM)
        add("Performance", "Enable the Native Execution Engine and Spark autotune; use high-concurrency sessions to cut start-up cost.", "Native Execution Engine", RiskLevel.MEDIUM)
        return opt

    def dataflow_complexity(self, df: Dataflow) -> MigrationComplexity:
        """Score how hard a Mapping/Wrangling Data Flow is to migrate."""
        tset = set(df.transformation_types)
        factors: list[str] = []
        sig: dict[str, int] = {"transforms": min(df.transformation_count * 3, 30),
                               "io": min((df.source_count + df.sink_count) * 4, 20)}
        if df.transformation_count:
            factors.append(f"{df.transformation_count} transformation(s); {df.source_count} source(s) / {df.sink_count} sink(s)")
        heavy = tset & {"join", "aggregate", "window", "pivot", "unpivot", "surrogateKey", "rank", "flatten"}
        if heavy:
            sig["heavy"] = 20
            factors.append("Complex transforms (" + ", ".join(sorted(heavy)) + ") to re-express in Dataflow Gen2/Spark")
        if df.dataflow_type == "WranglingDataFlow":
            sig["wrangling"] = 8
            factors.append("Power Query (wrangling) data flow — maps closely to Dataflow Gen2")
        else:
            sig["mapping"] = 15
            factors.append("Mapping Data Flow — no 1:1 Fabric equivalent; rebuild as Dataflow Gen2 or Spark notebook")
        if df.parameter_count:
            sig["params"] = min(df.parameter_count * 2, 10)
        refs = len(df.linked_service_refs) + len(df.dataset_refs)
        if refs:
            sig["connections"] = min(refs * 2, 10)
            factors.append(f"{refs} dataset/linked-service reference(s) to map to Fabric Connections")
        score = weighted_score(sig)
        return MigrationComplexity(
            artifact=df.name, artifact_type=ArtifactType.DATAFLOW, workspace=df.workspace,
            score=score, complexity=score_to_level(score),
            estimated_effort_days=round(0.5 + score / 18, 1),
            factors=factors or ["Simple data flow; rebuild as a Dataflow Gen2 query"],
            fabric_target="Dataflow Gen2")

    def dataflow_optimizations(self, df: Dataflow) -> list[FabricOptimization]:
        opt: list[FabricOptimization] = []

        def add(cat: str, rec: str, feat: str, impact: RiskLevel) -> None:
            opt.append(FabricOptimization(artifact=df.name, artifact_type=ArtifactType.DATAFLOW,
                                          workspace=df.workspace, category=cat, recommendation=rec,
                                          fabric_feature=feat, impact=impact))
        tset = set(df.transformation_types)
        add("Modernization", "Rebuild this data flow as a Dataflow Gen2; move heavy or iterative logic into a Spark notebook for scale.", "Dataflow Gen2", RiskLevel.HIGH)
        if tset & {"join", "lookup", "exists"}:
            add("Performance", "Stage large join/lookup inputs as Delta tables and use broadcast joins to cut shuffle.", "Delta + Spark", RiskLevel.MEDIUM)
        if tset & {"aggregate", "window", "rank", "pivot", "unpivot"}:
            add("Performance", "Re-express set-based aggregate/window logic as T-SQL in a Fabric Warehouse or Spark SQL.", "Fabric Warehouse", RiskLevel.MEDIUM)
        if df.sink_count > 1:
            add("Maintainability", "Split the multi-sink data flow into focused Dataflow Gen2 queries sharing a staging Lakehouse.", "Staging Lakehouse", RiskLevel.LOW)
        add("Cost", "Land sources via OneLake shortcuts instead of copying into staging before transformation.", "OneLake shortcuts", RiskLevel.MEDIUM)
        add("Security", "Map source/sink linked services to Fabric Connections authenticated with the workspace identity.", "Fabric Connections", RiskLevel.LOW)
        return opt

    def run(self) -> dict:
        self.logger.info("Assessment starting")
        inv = self._load_inventory()
        a = Assessment()
        for w in inv.workspaces:
            for p in w.pipelines:
                a.scores.append(self.assess_pipeline(p))
                a.complexity.append(self.pipeline_complexity(p))
                a.optimizations += self.pipeline_optimizations(p)
            for n in w.notebooks:
                sc, fs = self.assess_notebook(n)
                a.scores.append(sc)
                a.findings += fs
                a.complexity.append(self.notebook_complexity(n))
                a.optimizations += self.notebook_optimizations(n)
            for sp in w.spark_pools:
                a.scores.append(self.assess_spark(sp))
            for dp in w.sql_pools:
                a.scores.append(self.assess_sql(dp))
            for df in w.dataflows:
                a.scores.append(self.assess_dataflow(df))
                a.complexity.append(self.dataflow_complexity(df))
                a.optimizations += self.dataflow_optimizations(df)
        a.summary = {lvl.value: sum(1 for s in a.scores if s.migration_complexity == lvl) for lvl in RiskLevel}
        out = self.output_dir
        write_json(a.summary, out / "assessment_summary.json")
        write_json([s.model_dump() for s in a.scores], out / "complexity_scores.json")
        write_json([c.model_dump() for c in a.complexity], out / "migration_complexity.json")
        write_json([o.model_dump() for o in a.optimizations], out / "fabric_optimizations.json")
        write_json([f.model_dump() for f in a.findings if f.category == "Security"], out / "security_findings.json")
        write_json([s.model_dump() for s in a.scores if s.performance_risk != RiskLevel.LOW], out / "performance_findings.json")
        write_workbook({
            "Risk Register": [s.model_dump() for s in a.scores],
            "Findings": [f.model_dump() for f in a.findings],
            "Migration Complexity": [c.model_dump() for c in a.complexity],
            "Fabric Optimizations": [o.model_dump() for o in a.optimizations],
        }, out / "risk_register.xlsx")
        readiness = self._readiness_md(a)
        write_markdown(readiness, out / "fabric_readiness.md")
        self.save_errors("assessment_errors.json")
        self.logger.info("Assessment complete: %d scores, %d complexity, %d optimizations",
                         len(a.scores), len(a.complexity), len(a.optimizations))
        return {"scores": len(a.scores), "findings": len(a.findings),
                "complexity": len(a.complexity), "optimizations": len(a.optimizations)}

    @staticmethod
    def _readiness_md(a: Assessment) -> str:
        lines = ["# Fabric Readiness\n", "## Migration complexity bands\n",
                 "| Band | Count |\n|---|---|\n"]
        lines += [f"| {k} | {v} |\n" for k, v in a.summary.items()]
        pipes = [c for c in a.complexity if c.artifact_type == ArtifactType.PIPELINE]
        nbs = [c for c in a.complexity if c.artifact_type == ArtifactType.NOTEBOOK]
        dfs = [c for c in a.complexity if c.artifact_type == ArtifactType.DATAFLOW]
        eff = sum(c.estimated_effort_days for c in a.complexity)
        lines.append("\n## Pipeline, notebook & dataflow migration\n\n")
        lines.append(f"- Pipelines assessed: **{len(pipes)}**\n")
        lines.append(f"- Notebooks assessed: **{len(nbs)}**\n")
        lines.append(f"- Data flows assessed: **{len(dfs)}**\n")
        lines.append(f"- Estimated rebuild effort: **{eff:.1f} person-days**\n")
        lines.append(f"- Fabric optimizations identified: **{len(a.optimizations)}**\n")
        by_cat: dict[str, int] = {}
        for o in a.optimizations:
            by_cat[o.category] = by_cat.get(o.category, 0) + 1
        lines.append("\n## Optimization opportunities by category\n\n| Category | Count |\n|---|---|\n")
        lines += [f"| {k} | {v} |\n" for k, v in sorted(by_cat.items())]
        return "".join(lines)
