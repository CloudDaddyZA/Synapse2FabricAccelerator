"""Flask web UI for the Synapse to Fabric Migration Accelerator.

Lets consultants edit configuration (no secrets), run individual agents or the
full pipeline, watch live logs, and browse/download every generated output.
Run with: python -m src.webapp  (or: python -m src.cli serve)
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from ..utils.config import DEFAULT_CONFIG_PATH, load_settings
from .auth import AzureAuth
from .jobs import AGENTS, JobRunner

EDITABLE_KEYS = [
    "tenant_id", "subscriptions", "resource_groups", "workspace_names", "regions",
    "output_path", "include_security_scan", "include_usage_analysis",
    "include_powerbi_outputs", "include_html_dashboard",
    "include_copilot_optimization_pack", "log_level",
]
LIST_KEYS = {"subscriptions", "resource_groups", "workspace_names", "regions"}
BOOL_KEYS = {k for k in EDITABLE_KEYS if k.startswith("include_")}

runner = JobRunner()
auth = AzureAuth()


def _discovered_workspaces(config_path: str | None) -> list[str]:
    """Names of workspaces found by the discovery stage (if it has run)."""
    f = load_settings(config_path).output_dir / "discovery" / "workspaces.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return sorted({w["name"] for w in data if isinstance(w, dict) and w.get("name")})


def _fabric_scope(config_path: str | None) -> tuple[list[str], list[str]]:
    """Fabric workspaces and capacities found by a prior fabric-audit run."""
    f = load_settings(config_path).output_dir / "fabric_audit" / "fabric_estate.json"
    if not f.exists():
        return [], []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return [], []
    workspaces = sorted({w.get("name") for w in data.get("workspaces", [])
                         if isinstance(w, dict) and w.get("name")})
    capacities = sorted({c.get("display_name") for c in data.get("capacities", [])
                         if isinstance(c, dict) and c.get("display_name")})
    return workspaces, capacities


def create_app(config_path: str | None = None) -> Flask:
    app = Flask(__name__)
    runner.config_path = config_path
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    @app.get("/")
    def index():
        settings = load_settings(config_path)
        return render_template("index.html", agents=list(AGENTS), settings=settings)

    @app.get("/config")
    def config():
        settings = load_settings(config_path)
        return render_template("config.html", settings=settings, list_keys=LIST_KEYS, bool_keys=BOOL_KEYS, editable=EDITABLE_KEYS)
    @app.post("/config")
    def save_config():
        data: dict = {}
        for key in EDITABLE_KEYS:
            if key in LIST_KEYS:
                raw = request.form.get(key, "").strip()
                data[key] = [v.strip() for v in raw.splitlines() for v in v.split(",") if v.strip()]
            elif key in BOOL_KEYS:
                data[key] = request.form.get(key) == "on"
            else:
                data[key] = request.form.get(key, "").strip()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if cfg_path.exists():
            existing = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        existing.update(data)
        cfg_path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
        return redirect(url_for("config"))

    @app.post("/run/<target>")
    def run(target: str):
        if target != "run-all" and target not in AGENTS:
            abort(404)
        if not runner.start(target):
            return jsonify({"ok": False, "msg": "A job is already running"}), 409
        return jsonify({"ok": True})

    @app.post("/cancel")
    def cancel():
        if runner.cancel():
            return jsonify({"ok": True})
        return jsonify({"ok": False, "msg": "No job is running"}), 409

    @app.get("/workspaces")
    def workspaces():
        settings = load_settings(config_path)
        return jsonify({
            "available": _discovered_workspaces(config_path),
            "selected": settings.workspace_names,
        })

    @app.post("/workspaces")
    def save_workspaces():
        payload = request.get_json(silent=True) or {}
        selected = payload.get("workspaces", [])
        if not isinstance(selected, list):
            selected = []
        selected = [str(s).strip() for s in selected if str(s).strip()]
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if cfg_path.exists():
            existing = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        existing["workspace_names"] = selected
        cfg_path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
        return jsonify({"ok": True, "selected": selected})

    @app.get("/fabric-scope")
    def fabric_scope():
        settings = load_settings(config_path)
        ws, caps = _fabric_scope(config_path)
        return jsonify({
            "workspaces": {"available": ws, "selected": settings.fabric_workspace_names},
            "capacities": {"available": caps, "selected": settings.fabric_capacity_names},
        })

    @app.post("/fabric-scope")
    def save_fabric_scope():
        payload = request.get_json(silent=True) or {}

        def _clean(v):
            return [str(s).strip() for s in v if str(s).strip()] if isinstance(v, list) else []

        ws = _clean(payload.get("workspaces", []))
        caps = _clean(payload.get("capacities", []))
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if cfg_path.exists():
            existing = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        existing["fabric_workspace_names"] = ws
        existing["fabric_capacity_names"] = caps
        cfg_path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
        return jsonify({"ok": True, "workspaces": ws, "capacities": caps})

    @app.get("/fabric-map")
    def fabric_map():
        settings = load_settings(config_path)
        targets, _caps = _fabric_scope(config_path)
        return jsonify({
            "sources": _discovered_workspaces(config_path),
            "targets": targets,
            "mapping": settings.fabric_workspace_map or {},
        })

    @app.post("/fabric-map")
    def save_fabric_map():
        payload = request.get_json(silent=True) or {}
        mapping = payload.get("mapping", {})
        if not isinstance(mapping, dict):
            mapping = {}
        clean = {str(k).strip(): str(v).strip() for k, v in mapping.items()
                 if str(k).strip() and str(v).strip()}
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if cfg_path.exists():
            existing = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        existing["fabric_workspace_map"] = clean
        cfg_path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
        return jsonify({"ok": True, "mapping": clean})

    @app.get("/status")
    def status():
        return jsonify(runner.snapshot())

    @app.get("/account")
    def account():
        acct = auth.account()
        acct["login"] = {"status": auth.state.status, "message": auth.state.message}
        return jsonify(acct)

    @app.post("/login")
    def login():
        tenant = request.form.get("tenant", "").strip()
        subscription = request.form.get("subscription", "").strip()
        if not auth.login(tenant, subscription):
            return jsonify({"ok": False, "msg": "Login already in progress"}), 409
        return jsonify({"ok": True})

    @app.get("/outputs")
    def outputs():
        root = load_settings(config_path).output_dir
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) if root.exists() else []
        return render_template("outputs.html", files=files)

    @app.get("/file/<path:rel>")
    def file(rel: str):
        rel = rel.replace("\\", "/")
        root = load_settings(config_path).output_dir.resolve()
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            abort(403)
        if not target.exists():
            abort(404)
        return send_from_directory(root, rel, as_attachment=target.suffix != ".html")

    return app
