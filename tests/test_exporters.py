"""Tests for exporters (JSON/CSV/Excel/Markdown/HTML)."""
from src.exporters.csv_writer import write_csv
from src.exporters.excel_writer import write_workbook
from src.exporters.json_writer import read_json, write_json
from src.exporters.markdown_writer import markdown_to_html_body, write_html, write_markdown


def test_json_roundtrip(tmp_path):
    p = write_json({"a": 1}, tmp_path / "x.json")
    assert read_json(p)["a"] == 1


def test_csv(tmp_path):
    p = write_csv([{"a": 1, "b": 2}], tmp_path / "x.csv")
    assert "a,b" in p.read_text()


def test_excel(tmp_path):
    p = write_workbook({"S": [{"x": 1}]}, tmp_path / "x.xlsx")
    assert p.exists() and p.stat().st_size > 0


def test_markdown_html(tmp_path):
    write_markdown("# Title\n- item", tmp_path / "x.md")
    body = markdown_to_html_body("# Title\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<h1>" in body and "<table>" in body
    p = write_html("T", "# H", tmp_path / "x.html")
    assert "<html" in p.read_text()


def test_pbip(tmp_path):
    from src.exporters.powerbi_pbip import generate_pbip
    pbip = generate_pbip(tmp_path)
    assert pbip.exists()
    assert (tmp_path / "SynapseMigration.SemanticModel" / "definition" / "model.tmdl").exists()
    assert (tmp_path / "SynapseMigration.SemanticModel" / "definition" / "tables" / "workspaces.tmdl").exists()
    assert (tmp_path / "SynapseMigration.Report" / "report.json").exists()


def test_arm_template():
    from src.exporters.arm_template import build_arm_template
    raw = {
        "linkedservices": [{"name": "ls1", "properties": {"type": "AzureBlobFS"}}],
        "datasets": [{"name": "ds1", "properties": {"type": "Parquet", "linkedServiceName": {"referenceName": "ls1", "type": "LinkedServiceReference"}}}],
        "pipelines": [{"name": "pl1", "properties": {"activities": [{"name": "c", "type": "Copy", "inputs": [{"referenceName": "ds1", "type": "DatasetReference"}]}]}}],
        "triggers": [{"name": "tr1", "properties": {"type": "ScheduleTrigger", "pipelines": [{"pipelineReference": {"referenceName": "pl1", "type": "PipelineReference"}}]}}],
    }
    tpl = build_arm_template("synw-demo", raw)
    assert tpl["$schema"].endswith("deploymentTemplate.json#")
    assert tpl["parameters"]["workspaceName"]["defaultValue"] == "synw-demo"
    types = {r["type"] for r in tpl["resources"]}
    assert "Microsoft.Synapse/workspaces/pipelines" in types
    ds = next(r for r in tpl["resources"] if r["type"].endswith("/datasets"))
    assert any("linkedServices/ls1" in d for d in ds["dependsOn"])
    pl = next(r for r in tpl["resources"] if r["type"].endswith("/pipelines"))
    assert any("datasets/ds1" in d for d in pl["dependsOn"])
    tr = next(r for r in tpl["resources"] if r["type"].endswith("/triggers"))
    assert any("pipelines/pl1" in d for d in tr["dependsOn"])


def test_migration_assistant_pack(tmp_path, sample_inventory):
    from src.exporters.migration_assistant import write_migration_assistant_pack
    from src.models.inventory import Inventory
    inv = Inventory(**sample_inventory)
    raw = {"synw-demo": {
        "linkedservices": [{"name": "ls1", "properties": {"type": "AzureBlobFS"}}],
        "pipelines": [{"name": "pl1", "properties": {"activities": []}}],
    }}
    manifest = write_migration_assistant_pack(tmp_path / "ma", inv, raw)
    assert (tmp_path / "ma" / "handoff_manifest.json").exists()
    assert (tmp_path / "ma" / "fdfma_scope.csv").exists()
    assert (tmp_path / "ma" / "README.md").exists()
    assert (tmp_path / "ma" / "synw-demo.arm.json").exists()
    assert manifest["raw_definitions_available"] is True
    assert manifest["totals"]["auto"] >= 1   # pipeline + linked service
    assert manifest["totals"]["manual"] >= 1  # dataflow df1


def test_migration_assistant_pack_no_raw(tmp_path, sample_inventory):
    from src.exporters.migration_assistant import write_migration_assistant_pack
    from src.models.inventory import Inventory
    inv = Inventory(**sample_inventory)
    manifest = write_migration_assistant_pack(tmp_path / "ma2", inv, None)
    assert manifest["raw_definitions_available"] is False
    assert not list((tmp_path / "ma2").glob("*.arm.json"))
    assert (tmp_path / "ma2" / "README.md").exists()
