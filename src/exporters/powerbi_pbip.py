"""Power BI Project (PBIP) generator.

Emits a text-based PBIP project (semantic model in TMDL + report in PBIR) that
opens directly in Power BI Desktop. The model imports the accelerator's CSV
extracts (workspaces, pipelines, notebooks, spark/sql pools, etc.) and ships a
multi-page migration dashboard. PBIP is regenerated on every dashboard run.

To open: enable Power BI Desktop preview "Power BI Project (.pbip) save option",
then File > Open > SynapseMigration.pbip. The DataFolder parameter defaults to
the powerbi folder; adjust it if you move the CSVs.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

PROJECT = "SynapseMigration"

# (table, [columns]) — empty list means columns auto-detected from CSV headers.
_TABLES: dict[str, list[str]] = {
    "workspaces": [
        "name", "workspace_id", "subscription_id", "resource_group", "location",
        "tags", "managed_resource_group", "dev_endpoint", "sql_endpoint",
        "sql_ondemand_endpoint", "default_storage_account", "default_filesystem",
        "git_provider", "git_repo", "managed_vnet", "public_network_access",
    ],
    "pipelines": ["name", "workspace", "activity_count", "parameter_count", "has_nested_activities"],
    "pipeline_activities": ["pipeline", "workspace", "name", "activity_type", "has_retry", "depends_on_count"],
    "notebooks": ["name", "workspace", "language", "cell_count", "uses_spark", "uses_delta", "uses_synapse_utils", "uses_spark_config"],
    "spark_pools": [
        "name", "workspace", "node_size", "node_size_family", "node_count",
        "autoscale_enabled", "min_nodes", "max_nodes", "auto_pause_enabled",
        "auto_pause_minutes", "spark_version", "library_count",
    ],
    "sql_pools": ["name", "workspace", "sku", "tier", "status", "is_serverless", "collation", "table_count", "total_size_mb", "largest_table"],
    "linked_services": ["name", "workspace", "service_type", "references_key_vault"],
    "datasets": ["name", "workspace", "dataset_type", "linked_service"],
    "security_findings": ["artifact", "severity", "message"],
    "migration_complexity": ["artifact", "score"],
    "fabric_recommendations": ["artifact", "fabric_target"],
}

_MEASURES = {
    "workspaces": [
        ("Workspace Count", "COUNTROWS('workspaces')"),
        ("Regions", "DISTINCTCOUNT('workspaces'[location])"),
    ],
    "pipelines": [("Pipeline Count", "COUNTROWS('pipelines')")],
    "notebooks": [
        ("Notebook Count", "COUNTROWS('notebooks')"),
        ("Delta Notebooks %", "DIVIDE(CALCULATE(COUNTROWS('notebooks'),'notebooks'[uses_delta]=\"True\"),COUNTROWS('notebooks'))"),
    ],
    "spark_pools": [("Spark Pool Count", "COUNTROWS('spark_pools')")],
    "sql_pools": [("SQL Pool Count", "COUNTROWS('sql_pools')")],
    "security_findings": [("Open Findings", "COUNTROWS('security_findings')")],
    "migration_complexity": [("Avg Complexity", "AVERAGE('migration_complexity'[score])")],
}


def _platform(name: str, kind: str) -> str:
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": kind, "displayName": name},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }, indent=2)


def _m_query(table: str) -> str:
    return (
        "let\n"
        f'    Source = Csv.Document(File.Contents(DataFolder & "{table}.csv"),'
        "[Delimiter=\",\",Encoding=65001,QuoteStyle=QuoteStyle.Csv]),\n"
        "    Headers = Table.PromoteHeaders(Source,[PromoteAllScalars=true])\n"
        "in\n    Headers"
    )


def _table_tmdl(table: str, cols: list[str]) -> str:
    lines = [f"table {table}", ""]
    for c in cols:
        dtype = "int64" if c in {"score"} else ("double" if c.endswith("_mb") else "string")
        lines += [f"\tcolumn {c}", f"\t\tdataType: {dtype}", f"\t\tsourceColumn: {c}", ""]
    for mname, expr in _MEASURES.get(table, []):
        lines += [f"\tmeasure '{mname}' = {expr}", ""]
    src = _m_query(table).replace("\n", "\n\t\t\t")
    lines += [
        f"\tpartition {table} = m",
        "\t\tmode: import",
        f"\t\tsource =\n\t\t\t{src}",
        "",
    ]
    return "\n".join(lines)


def _card(x, y, table, measure):
    cfg = {"name": str(uuid.uuid4())[:8], "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": 220, "height": 110}}],
           "singleVisual": {"visualType": "card",
               "projections": {"Values": [{"queryRef": f"{table}.{measure}"}]},
               "prototypeQuery": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                   "Select": [{"Measure": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": measure}, "Name": f"{table}.{measure}"}]},
               "drillFilterOtherVisuals": True}}
    return {"x": x, "y": y, "width": 220, "height": 110, "z": 0, "config": json.dumps(cfg)}


def _bar(x, y, w, h, table, cat, measure):
    cfg = {"name": str(uuid.uuid4())[:8], "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 1, "width": w, "height": h}}],
           "singleVisual": {"visualType": "clusteredColumnChart",
               "projections": {"Category": [{"queryRef": f"{table}.{cat}"}], "Y": [{"queryRef": f"{table}.{measure}"}]},
               "prototypeQuery": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                   "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": cat}, "Name": f"{table}.{cat}"},
                              {"Measure": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": measure}, "Name": f"{table}.{measure}"}]},
               "drillFilterOtherVisuals": True}}
    return {"x": x, "y": y, "width": w, "height": h, "z": 1, "config": json.dumps(cfg)}


def _table(x, y, w, h, table, cols):
    sel = [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": c}, "Name": f"{table}.{c}"} for c in cols]
    cfg = {"name": str(uuid.uuid4())[:8], "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 1, "width": w, "height": h}}],
           "singleVisual": {"visualType": "tableEx",
               "projections": {"Values": [{"queryRef": f"{table}.{c}"} for c in cols]},
               "prototypeQuery": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}], "Select": sel},
               "drillFilterOtherVisuals": True}}
    return {"x": x, "y": y, "width": w, "height": h, "z": 1, "config": json.dumps(cfg)}


def _pages():
    overview = [
        _card(20, 20, "workspaces", "Workspace Count"), _card(260, 20, "pipelines", "Pipeline Count"),
        _card(500, 20, "notebooks", "Notebook Count"), _card(740, 20, "spark_pools", "Spark Pool Count"),
        _card(980, 20, "sql_pools", "SQL Pool Count"),
        _bar(20, 150, 600, 320, "workspaces", "location", "Workspace Count"),
        _bar(640, 150, 600, 320, "spark_pools", "node_size", "Spark Pool Count"),
    ]
    estate = [_table(20, 20, 1240, 660, "workspaces",
        ["name", "location", "resource_group", "public_network_access", "git_provider"])]
    sparksql = [
        _table(20, 20, 1240, 320, "spark_pools", ["name", "workspace", "node_size", "node_count", "autoscale_enabled", "spark_version"]),
        _table(20, 360, 1240, 320, "sql_pools", ["name", "workspace", "sku", "tier", "status"]),
    ]
    risk = [_card(20, 20, "migration_complexity", "Avg Complexity"), _card(260, 20, "security_findings", "Open Findings"),
            _table(20, 150, 1240, 530, "migration_complexity", ["artifact", "score"])]
    fabric = [_table(20, 20, 1240, 660, "fabric_recommendations", ["artifact", "fabric_target"])]
    return [overview, estate, sparksql, risk, fabric]


def _report_json() -> str:
    names = ["Overview", "Estate Inventory", "Spark & SQL", "Migration Risk", "Fabric Targets"]
    visuals = _pages()
    sections = []
    for i, (p, vis) in enumerate(zip(names, visuals, strict=True)):
        sections.append({
            "name": f"page{i}", "displayName": p, "ordinal": i,
            "width": 1280, "height": 720, "visualContainers": vis,
        })
    return json.dumps({
        "version": "1.0", "themeCollection": {"baseTheme": {"name": "CY24SU10"}},
        "sections": sections, "config": json.dumps({"activeSectionIndex": 0}),
    }, indent=2)


def generate_pbip(pb_dir: str | Path) -> Path:
    pb = Path(pb_dir)
    sm = pb / f"{PROJECT}.SemanticModel"
    rep = pb / f"{PROJECT}.Report"
    (sm / "definition" / "tables").mkdir(parents=True, exist_ok=True)
    rep.mkdir(parents=True, exist_ok=True)

    pbip = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }
    (pb / f"{PROJECT}.pbip").write_text(json.dumps(pbip, indent=2), encoding="utf-8")

    (sm / ".platform").write_text(_platform(PROJECT, "SemanticModel"), encoding="utf-8")
    (sm / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "settings": {},
    }, indent=2), encoding="utf-8")

    folder = (pb.resolve().as_posix() + "/")
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "",
        "expression DataFolder = \"" + folder + "\" meta [IsParameterQuery=true, Type=\"Text\", IsParameterQueryRequired=true]",
        "",
    ]
    for t in _TABLES:
        model.append(f"ref table {t}")
    (sm / "definition" / "model.tmdl").write_text("\n".join(model), encoding="utf-8")

    for t, cols in _TABLES.items():
        (sm / "definition" / "tables" / f"{t}.tmdl").write_text(_table_tmdl(t, cols), encoding="utf-8")

    (rep / ".platform").write_text(_platform(PROJECT, "Report"), encoding="utf-8")
    (rep / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
        "version": "1.0",
        "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}},
    }, indent=2), encoding="utf-8")
    (rep / "report.json").write_text(_report_json(), encoding="utf-8")
    return pb / f"{PROJECT}.pbip"
