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
