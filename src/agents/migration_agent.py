"""Migration Agent.

Recommends Microsoft Fabric target components for each artifact and generates a
phased migration path + wave plan, cutover/validation checklists, mapping doc,
and decommission plan.
"""
from __future__ import annotations

from ..exporters.excel_writer import write_workbook
from ..exporters.json_writer import read_json, write_json
from ..exporters.markdown_writer import write_markdown
from ..models.assessment import (
    FabricRecommendation,
    MigrationPlan,
    MigrationWaveItem,
)
from ..models.enums import ArtifactType, FabricTarget, RiskLevel
from ..models.inventory import Inventory
from .base_agent import BaseAgent

MAPPING = [
    ("Synapse Workspace", "Fabric Workspace"),
    ("Synapse Pipelines", "Fabric Data Factory Data Pipelines"),
    ("Synapse Mapping Data Flows", "Dataflow Gen2 or Fabric Notebook rewrite"),
    ("Synapse Spark Notebooks", "Fabric Notebooks"),
    ("Synapse Spark Pools", "Fabric Spark Compute"),
    ("Dedicated SQL Pool", "Fabric Warehouse or Lakehouse"),
    ("Serverless SQL Views", "Lakehouse SQL Endpoint or Warehouse Views"),
    ("SQL Scripts", "Fabric Warehouse SQL Scripts"),
    ("ADLS Gen2 Zones", "OneLake Lakehouse Files/Tables or Shortcuts"),
    ("Linked Services", "Fabric Connections"),
    ("Integration Runtime", "Fabric Gateway or Managed VNet Gateway"),
    ("Triggers", "Fabric Pipeline Schedules"),
    ("Git Integration", "Fabric Git Integration"),
    ("Power BI Dependencies", "Semantic Models and Reports"),
]
PHASES = [
    "Discovery and Assessment", "Fabric Foundation", "Data Landing and Lakehouse",
    "Pipeline Migration", "Notebook and Spark Migration", "SQL and Serving Migration",
    "Reporting and Semantic Layer", "Testing and Cutover", "Decommission",
]


class MigrationAgent(BaseAgent):
    name = "migration"
    output_subdir = "migration"

    def _load(self):
        inv = self.settings.subdir("inventory") / "synapse_inventory.json"
        return Inventory(**read_json(inv)) if inv.exists() else Inventory()

    def recommend(self, inv: Inventory) -> list[FabricRecommendation]:
        recs = []
        for w in inv.workspaces:
            recs.append(FabricRecommendation(source_artifact=w.workspace.name, source_type=ArtifactType.WORKSPACE, workspace=w.workspace.name, fabric_target=FabricTarget.FABRIC_WORKSPACE, effort_band=RiskLevel.MEDIUM, rationale="1:1 workspace mapping"))
            for p in w.pipelines:
                recs.append(FabricRecommendation(source_artifact=p.name, source_type=ArtifactType.PIPELINE, workspace=w.workspace.name, fabric_target=FabricTarget.DATA_PIPELINE, effort_band=RiskLevel.HIGH if p.activity_count > 10 else RiskLevel.MEDIUM, rationale="Rebuild in Fabric Data Factory"))
            for n in w.notebooks:
                recs.append(FabricRecommendation(source_artifact=n.name, source_type=ArtifactType.NOTEBOOK, workspace=w.workspace.name, fabric_target=FabricTarget.FABRIC_NOTEBOOK, effort_band=RiskLevel.MEDIUM, rationale="Port to Fabric Notebook + OneLake"))
            for df in w.dataflows:
                recs.append(FabricRecommendation(source_artifact=df.name, source_type=ArtifactType.DATAFLOW, workspace=w.workspace.name, fabric_target=FabricTarget.DATAFLOW_GEN2, effort_band=RiskLevel.HIGH if df.transformation_count > 5 else RiskLevel.MEDIUM, rationale="Rebuild as Dataflow Gen2 or Spark notebook"))
            for sp in w.spark_pools:
                recs.append(FabricRecommendation(source_artifact=sp.name, source_type=ArtifactType.SPARK_POOL, workspace=w.workspace.name, fabric_target=FabricTarget.FABRIC_SPARK, effort_band=RiskLevel.LOW, rationale="Use Fabric Spark compute"))
            for dp in w.sql_pools:
                recs.append(FabricRecommendation(source_artifact=dp.name, source_type=ArtifactType.SQL_POOL, workspace=w.workspace.name, fabric_target=FabricTarget.WAREHOUSE, effort_band=RiskLevel.HIGH, rationale="Migrate to Fabric Warehouse"))
        return recs

    def waves(self, recs: list[FabricRecommendation]) -> list[MigrationWaveItem]:
        wave_map = {ArtifactType.WORKSPACE: 2, ArtifactType.SQL_POOL: 6, ArtifactType.PIPELINE: 4, ArtifactType.DATAFLOW: 4, ArtifactType.NOTEBOOK: 5, ArtifactType.SPARK_POOL: 5}
        return [MigrationWaveItem(wave=wave_map.get(r.source_type, 4), phase=PHASES[wave_map.get(r.source_type, 4) - 1], artifact=r.source_artifact, artifact_type=r.source_type, workspace=r.workspace, effort_band=r.effort_band, fabric_target=r.fabric_target) for r in recs]

    def run(self) -> dict:
        self.logger.info("Migration planning starting")
        inv = self._load()
        plan = MigrationPlan(recommendations=self.recommend(inv))
        plan.waves = self.waves(plan.recommendations)
        out = self.output_dir
        write_markdown("# Synapse to Fabric Mapping\n\n| Synapse | Fabric |\n|---|---|\n" + "".join(f"| {a} | {b} |\n" for a, b in MAPPING), out / "synapse_to_fabric_mapping.md")
        write_workbook({"Recommendations": [r.model_dump() for r in plan.recommendations]}, out / "fabric_component_recommendations.xlsx")
        write_workbook({"Wave Plan": [w.model_dump() for w in plan.waves]}, out / "migration_wave_plan.xlsx")
        write_json([r.model_dump() for r in plan.recommendations], out / "fabric_recommendations.json")
        write_json([w.model_dump() for w in plan.waves], out / "migration_waves.json")
        write_markdown("# Migration Path\n\n" + "".join(f"{i}. {p}\n" for i, p in enumerate(PHASES, 1)), out / "migration_path.md")
        write_markdown("# Cutover Checklist\n\n- Freeze source pipelines\n- Validate Fabric pipelines\n- Switch reporting to semantic models\n- Confirm OneLake data parity", out / "cutover_checklist.md")
        write_markdown("# Validation Checklist\n\n- Row counts match\n- Schema parity\n- Job duration baseline\n- Security/RBAC parity", out / "validation_checklist.md")
        write_markdown("# Decommission Plan\n\n- Confirm Fabric stability (2 weeks)\n- Archive Synapse artifacts\n- Remove pools\n- Delete workspace", out / "decommission_plan.md")
        self.save_errors("migration_errors.json")
        self.logger.info("Migration planning complete: %d recs", len(plan.recommendations))
        return {"recommendations": len(plan.recommendations), "waves": len(set(w.wave for w in plan.waves))}
