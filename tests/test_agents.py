"""Offline agent tests using seeded inventory (no Azure calls)."""
from src.agents.assessment_agent import AssessmentAgent
from src.agents.dashboard_agent import DashboardAgent
from src.agents.migration_agent import MigrationAgent
from src.agents.optimization_agent import OptimizationAgent
from src.agents.reporting_agent import ReportingAgent


def test_assessment(seeded):
    r = AssessmentAgent(seeded).run()
    assert r["scores"] >= 4
    assert (seeded.subdir("assessment") / "risk_register.xlsx").exists()
    assert (seeded.subdir("assessment") / "security_findings.json").exists()


def test_migration(seeded):
    r = MigrationAgent(seeded).run()
    assert r["recommendations"] >= 4
    assert (seeded.subdir("migration") / "migration_wave_plan.xlsx").exists()
    assert (seeded.subdir("migration") / "synapse_to_fabric_mapping.md").exists()
    assert (seeded.subdir("migration") / "migration_assistant" / "handoff_manifest.json").exists()
    assert r["fdfma_auto"] >= 1
    assert (seeded.subdir("migration") / "notebook_modernization" / "modernization_manifest.json").exists()
    assert r["notebooks_modernized"] >= 1


def test_reporting(seeded):
    AssessmentAgent(seeded).run()
    MigrationAgent(seeded).run()
    ReportingAgent(seeded).run()
    assert (seeded.subdir("reports") / "executive_migration_summary.html").exists()


def test_dashboard(seeded):
    DashboardAgent(seeded).run()
    assert (seeded.subdir("dashboard") / "index.html").exists()
    assert (seeded.subdir("dashboard") / "data" / "dashboard.json").exists()
    html = (seeded.subdir("dashboard") / "index.html").read_text(encoding="utf-8")
    assert 'data-view="migrate"' in html
    assert "Migration Assistant" in html
    assert 'data-view="objdep"' in html
    assert "Object Dependency Diagram" in html
    assert "Edge colour shows table access" in html
    assert 'data-view="revspider"' not in html


def test_dashboard_notebook_modernization(seeded):
    MigrationAgent(seeded).run()
    DashboardAgent(seeded).run()
    html = (seeded.subdir("dashboard") / "index.html").read_text(encoding="utf-8")
    assert 'data-view="notebooks"' in html
    assert "Notebook Modernizer" in html
    assert "Per-notebook Fabric readiness" in html


def test_optimization(seeded):
    r = OptimizationAgent(seeded).run()
    assert r["prompts"] >= 3
    assert (seeded.subdir("copilot_optimization_pack") / "copilot_review_index.xlsx").exists()
