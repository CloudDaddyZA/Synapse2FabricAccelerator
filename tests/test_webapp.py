"""Tests for the web UI (Flask test client, no live server)."""
import yaml

from src.webapp.app import create_app


def test_pages_render(seeded):
    app = create_app(None)
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/config").status_code == 200
    assert client.get("/outputs").status_code == 200


def test_status_and_invalid_run():
    app = create_app(None)
    client = app.test_client()
    body = client.get("/status").get_json()
    assert "status" in body
    assert client.post("/run/bogus").status_code == 404


def test_file_traversal_blocked():
    app = create_app(None)
    client = app.test_client()
    assert client.get("/file/../config/settings.yaml").status_code in (403, 404)


def test_account_endpoint():
    app = create_app(None)
    client = app.test_client()
    body = client.get("/account").get_json()
    assert "signed_in" in body and "login" in body


def test_workspace_selection(tmp_path):
    out = tmp_path / "out"
    (out / "discovery").mkdir(parents=True)
    (out / "discovery" / "workspaces.json").write_text(
        '[{"name": "ws-a"}, {"name": "ws-b"}]', encoding="utf-8"
    )
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(yaml.safe_dump({"output_path": str(out)}), encoding="utf-8")
    client = create_app(str(cfg)).test_client()

    body = client.get("/workspaces").get_json()
    assert sorted(body["available"]) == ["ws-a", "ws-b"]
    assert body["selected"] == []

    assert client.post("/workspaces", json={"workspaces": ["ws-a"]}).status_code == 200
    assert client.get("/workspaces").get_json()["selected"] == ["ws-a"]


def test_fabric_scope_selection(tmp_path):
    out = tmp_path / "out"
    (out / "fabric_audit").mkdir(parents=True)
    (out / "fabric_audit" / "fabric_estate.json").write_text(
        '{"workspaces": [{"name": "fw-a"}, {"name": "fw-b"}], '
        '"capacities": [{"display_name": "cap-1"}, {"display_name": "cap-2"}]}',
        encoding="utf-8",
    )
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(yaml.safe_dump({"output_path": str(out)}), encoding="utf-8")
    client = create_app(str(cfg)).test_client()

    body = client.get("/fabric-scope").get_json()
    assert sorted(body["workspaces"]["available"]) == ["fw-a", "fw-b"]
    assert sorted(body["capacities"]["available"]) == ["cap-1", "cap-2"]
    assert body["workspaces"]["selected"] == [] and body["capacities"]["selected"] == []

    assert client.post("/fabric-scope",
                       json={"workspaces": ["fw-a"], "capacities": ["cap-1"]}).status_code == 200
    body = client.get("/fabric-scope").get_json()
    assert body["workspaces"]["selected"] == ["fw-a"]
    assert body["capacities"]["selected"] == ["cap-1"]
    # Saved filters land in the config that the fabric-audit agent reads.
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["fabric_workspace_names"] == ["fw-a"]
    assert saved["fabric_capacity_names"] == ["cap-1"]
