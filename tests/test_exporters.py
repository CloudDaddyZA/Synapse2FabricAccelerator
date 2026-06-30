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
