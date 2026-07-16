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
    assert 'data-view="fabestate"' in html
    assert "Fabric Environment Audit" in html
    assert 'data-view="dflineage"' in html
    assert "Dataflow Lineage" in html


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


class _FakeFabricReady:
    """Fake Fabric REST client returning a healthy, well-sized estate."""

    def __init__(self, credential, settings):
        pass

    def capacities(self):
        return [{"id": "cap1", "displayName": "prod-cap", "sku": "F64",
                 "region": "East US", "state": "Active"}]

    def workspaces(self):
        return [{"id": "ws1", "displayName": "synw-demo", "type": "Workspace",
                 "capacityId": "cap1"}]

    def workspace_items(self, workspace_id):
        return [{"id": "i1", "displayName": "pl1", "type": "DataPipeline"},
                {"id": "i2", "displayName": "nb1", "type": "Notebook"},
                {"id": "i3", "displayName": "df1", "type": "Dataflow"},
                {"id": "i4", "displayName": "dwh", "type": "Warehouse"},
                {"id": "i5", "displayName": "lh", "type": "Lakehouse"}]

    def workspace_role_assignments(self, workspace_id):
        return [{"principal": {"displayName": "admin", "type": "User"}, "role": "Admin"}]


class _FakeFabricNoAccess:
    """Fake Fabric REST client that always fails (unprovisioned / no permission)."""

    def __init__(self, credential, settings):
        pass

    def _boom(self, *a, **k):
        raise RuntimeError("403 Forbidden")

    capacities = workspaces = _boom

    def workspace_items(self, workspace_id):
        raise RuntimeError("403 Forbidden")

    def workspace_role_assignments(self, workspace_id):
        raise RuntimeError("403 Forbidden")


def _patch_fabric(monkeypatch, fake):
    from src.agents import fabric_audit_agent as mod
    monkeypatch.setattr(mod, "get_credential", lambda settings: object())
    monkeypatch.setattr(mod, "FabricRestClient", fake)


def test_fabric_audit_ready(seeded, monkeypatch):
    from src.agents.fabric_audit_agent import FabricAuditAgent
    _patch_fabric(monkeypatch, _FakeFabricReady)
    r = FabricAuditAgent(seeded).run()
    assert r["accessible"] is True
    assert r["capacities"] == 1
    assert r["items"] == 5
    assert r["verdict"] in ("Ready", "Ready with actions")
    est = (seeded.subdir("fabric_audit") / "fabric_estate.json")
    rd = (seeded.subdir("fabric_audit") / "fabric_readiness_assessment.json")
    assert est.exists() and rd.exists()
    assert (seeded.subdir("fabric_audit") / "fabric_audit_summary.md").exists()


def test_fabric_audit_no_access(seeded, monkeypatch):
    from src.agents.fabric_audit_agent import FabricAuditAgent
    _patch_fabric(monkeypatch, _FakeFabricNoAccess)
    r = FabricAuditAgent(seeded).run()
    assert r["accessible"] is False
    assert r["verdict"] == "Unknown"
    # Still writes valid outputs so downstream agents never break.
    assert (seeded.subdir("fabric_audit") / "fabric_readiness_assessment.json").exists()


def test_fabric_audit_in_reports_and_dashboard(seeded, monkeypatch):
    from src.agents.fabric_audit_agent import FabricAuditAgent
    from src.agents.reporting_agent import ReportingAgent
    _patch_fabric(monkeypatch, _FakeFabricReady)
    FabricAuditAgent(seeded).run()
    AssessmentAgent(seeded).run()
    MigrationAgent(seeded).run()
    ReportingAgent(seeded).run()
    assert (seeded.subdir("reports") / "fabric_environment_readiness.html").exists()
    fenv = (seeded.subdir("reports") / "fabric_environment_readiness.md").read_text(encoding="utf-8")
    assert "Readiness verdict" in fenv
    DashboardAgent(seeded).run()
    html = (seeded.subdir("dashboard") / "index.html").read_text(encoding="utf-8")
    assert "Readiness:" in html
    assert "prod-cap" in html

