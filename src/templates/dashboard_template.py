"""Offline static HTML dashboard renderer with bundled Chart.js fallback.

Renders a multi-view migration report — Overview, Admin, Data Engineering,
Data Warehousing, Data Integration — sharing one workspace checkbox filter
that scopes every table and KPI. Self-contained; charts degrade gracefully.
"""
from __future__ import annotations

import html
import json
from typing import Any

_VIEWS = [
    ("overview", "Overview"),
    ("admin", "Admin"),
    ("dataeng", "Data Engineering"),
    ("warehouse", "Data Warehousing"),
    ("integration", "Data Integration"),
    ("fabready", "Fabric Readiness"),
    ("pipelineops", "Pipeline Ops"),
    ("spider", "Dependency Spider"),
    ("trigspider", "Trigger Spider"),
    ("revspider", "Reverse Spider"),
    ("lineage", "Lineage"),
]


def table(title: str, rows: list[dict[str, Any]], cols: list[str]) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = []
    for r in rows:
        ws = html.escape(str(r.get("workspace") or r.get("name") or ""))
        rowjson = html.escape(json.dumps(r), quote=True)
        cells = "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols)
        body.append(f'<tr data-ws="{ws}" data-row="{rowjson}">{cells}</tr>')
    inner = "".join(body) or f'<tr><td colspan="{len(cols)}">No data (run inventory with access)</td></tr>'
    return (f'<div class="card"><h3>{html.escape(title)}</h3>'
            f'<table><thead><tr>{head}</tr></thead><tbody>{inner}</tbody></table></div>')


def kpi(label: str, kind: str) -> str:
    return f'<div class="card"><div class="kpi" data-count="{kind}">0</div>{html.escape(label)}</div>'


def render_dashboard(data: dict[str, Any]) -> str:
    tabs = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" data-view="{k}">{html.escape(t)}</button>'
        for i, (k, t) in enumerate(_VIEWS)
    )
    boxes = "".join(
        f'<label><input type="checkbox" class="wsf" value="{html.escape(w)}" checked> {html.escape(w)}</label>'
        for w in data.get("workspace_names", [])
    )
    mc = data.get("migration_complexity", [])
    pipe_mc = [r for r in mc if r.get("artifact_type") == "Pipeline"]
    nb_mc = [r for r in mc if r.get("artifact_type") == "Notebook"]
    df_mc = [r for r in mc if r.get("artifact_type") == "Dataflow"]
    cx_cols = ["artifact", "workspace", "complexity", "score", "estimated_effort_days", "fabric_target"]
    team_roles = [("architect", "Architects", 30, 1), ("data_engineer", "Data Engineers", 100, 2),
                  ("data_integration", "Data Integration Engineers", 100, 2),
                  ("infra_engineer", "Infra Engineers", 50, 1), ("qa_engineer", "QA / Test Engineers", 60, 1)]
    team_inputs = "".join(
        f'<label style="font-size:.82rem;color:#555;display:inline-block">{html.escape(label)} '
        f'<span style="color:#9aa">({pct}%)</span><br>'
        f'<input type="number" min="0" step="1" value="{dflt}" id="team_{k}" data-alloc="{pct / 100}" '
        f'class="teamc" style="width:74px;padding:.3rem;margin-top:.2rem;border:1px solid #ccc;border-radius:4px"></label>'
        for k, label, pct, dflt in team_roles
    )
    team_inputs += ('<label style="font-size:.82rem;color:#555;display:inline-block">Productive days / week<br>'
                    '<input type="number" min="1" max="7" step="0.5" value="5" id="team_dpw" '
                    'style="width:74px;padding:.3rem;margin-top:.2rem;border:1px solid #ccc;border-radius:4px"></label>')
    team_inputs += ('<label style="font-size:.82rem;color:#555;display:inline-block">GitHub Copilot for engineers<br>'
                    '<select id="team_copilot" style="width:230px;padding:.34rem;margin-top:.2rem;border:1px solid #ccc;border-radius:4px">'
                    '<option value="1" selected>None &mdash; no AI assistance</option>'
                    '<option value="0.8">Copilot enabled &mdash; 20% faster</option>'
                    '<option value="0.65">Copilot + agent mode &mdash; 35% faster</option>'
                    '<option value="0.5">Copilot power users &mdash; 50% faster</option>'
                    '</select></label>')
    views = {
        "overview": (
            '<div class="grid">'
            + kpi("Workspaces", "workspaces_t")
            + kpi("Pipelines", "pipelines") + kpi("Notebooks", "notebooks")
            + kpi("Dataflows", "dataflows")
            + kpi("Spark Pools", "spark_pools") + kpi("SQL Pools", "sql_pools")
            + '<div class="card" style="grid-column:1/-1"><h3>Resource summary</h3>'
              '<svg id="ov_res" width="100%" height="240" viewBox="0 0 1200 240"></svg></div>'
            + '<div class="card" style="grid-column:1/-1"><h3>Batch vs real-time runs</h3><div id="ov_split"></div></div>'
            + table("Workspace Access Status", data.get("workspaces_t", []),
                    ["name", "location", "assessment_status", "inaccessible_artifacts"])
            + "</div>"),
        "admin": '<div class="grid">' + table("Workspaces", data.get("workspaces_t", []),
            ["name", "location", "resource_group", "public_network_access", "managed_vnet", "git_provider", "assessment_status"])
            + table("Integration Runtimes", data.get("integration_runtimes", []), ["name", "workspace", "ir_type"])
            + table("Linked Services", data.get("linked_services", []), ["name", "workspace", "service_type", "references_key_vault"]) + "</div>",
        "dataeng": '<div class="grid">' + table("Spark Pools", data.get("spark_pools", []),
            ["name", "workspace", "node_size", "node_count", "autoscale_enabled", "auto_pause_enabled", "spark_version"])
            + table("Notebooks", data.get("notebooks", []),
            ["name", "workspace", "language", "cell_count", "uses_spark", "uses_delta", "uses_synapse_utils", "uses_spark_config"]) + "</div>",
        "warehouse": '<div class="grid">' + table("SQL Pools", data.get("sql_pools", []),
            ["name", "workspace", "sku", "tier", "status", "is_serverless", "table_count", "total_size_mb", "largest_table"]) + "</div>",
        "integration": '<div class="grid">' + table("Pipelines", data.get("pipelines", []),
            ["name", "workspace", "activity_count", "parameter_count", "has_nested_activities"])
            + table("Dataflows", data.get("dataflows", []),
                    ["name", "workspace", "dataflow_type", "source_count", "sink_count", "transformation_count", "folder"])
            + table("Triggers", data.get("triggers", []),
                    ["name", "workspace", "trigger_type", "init_method", "recurrence", "runtime_state", "pipeline_count"])
            + table("Datasets", data.get("datasets", []), ["name", "workspace", "dataset_type", "linked_service"]) + "</div>",
        "fabready": '<div class="grid">'
            '<div class="card" style="grid-column:1/-1"><h3>Delivery team &amp; timeline planner</h3>'
            '<div style="display:flex;flex-wrap:wrap;gap:1.2rem;align-items:flex-end">' + team_inputs + '</div>'
            '<div style="display:flex;gap:2.5rem;margin-top:.9rem;flex-wrap:wrap">'
            '<div><div class="kpi" id="team_capacity">0</div>Effective FTE</div>'
            '<div><div class="kpi" id="team_weeks">0</div>Calendar duration</div>'
            '<div><div class="kpi" id="team_people">0</div>Total head-count</div></div>'
            '<p id="team_detail" class="muted" style="margin:.5rem 0 0"></p>'
            '<p class="muted" style="margin:.3rem 0 0">Effective FTE = &Sigma; (head-count &times; role allocation %). '
            'Calendar duration = (total rebuild effort &times; Copilot factor) &divide; effective FTE, in working weeks. '
            'Percentages are each role&rsquo;s assumed hands-on rebuild allocation &mdash; adjust head-counts to model your delivery team. '
            'The GitHub Copilot selector applies an AI productivity uplift that reduces the person-days engineers spend rebuilding artifacts. '
            'Respects the workspace filter.</p></div>'
            '<div class="card"><div class="kpi" id="mc_pipes">0</div>Pipelines assessed</div>'
            '<div class="card"><div class="kpi" id="mc_nbs">0</div>Notebooks assessed</div>'
            '<div class="card"><div class="kpi" id="mc_dfs">0</div>Dataflows assessed</div>'
            '<div class="card"><div class="kpi" id="mc_effort">0d</div>Est. rebuild effort</div>'
            '<div class="card"><div class="kpi" id="mc_opts">0</div>Fabric optimizations</div>'
            '<div class="card" style="grid-column:1/-1"><h3>Migration complexity by band</h3>'
            '<svg id="mc_band" width="100%" height="240" viewBox="0 0 1200 240"></svg>'
            '<p class="muted" style="margin:.3rem 0 0">Click a band in the chart to filter the tables below; click it again to clear. Click any row for complexity drivers and Fabric optimizations.</p>'
            '<p id="mc_filter" style="margin:.2rem 0 0;color:#1565C0;font-weight:600;font-size:.84rem"></p></div>'
            '<details class="card" style="grid-column:1/-1"><summary style="cursor:pointer;font-weight:600">How is migration complexity calculated?</summary>'
            '<div style="font-size:.86rem;line-height:1.5;margin-top:.5rem">'
            '<p>Each artifact is scored on a <b>0&ndash;100</b> scale by summing weighted <i>signals</i> &mdash; characteristics that make a Fabric rebuild harder. Each signal contributes capped points, the total is clamped to 100, and the score maps to a band:</p>'
            '<p style="margin:.4rem 0">'
            '<span style="background:#107c10;color:#fff;padding:.05rem .45rem;border-radius:3px">Low 0&ndash;24</span> &nbsp;'
            '<span style="background:#c47f00;color:#fff;padding:.05rem .45rem;border-radius:3px">Medium 25&ndash;49</span> &nbsp;'
            '<span style="background:#d05a00;color:#fff;padding:.05rem .45rem;border-radius:3px">High 50&ndash;74</span> &nbsp;'
            '<span style="background:#b00020;color:#fff;padding:.05rem .45rem;border-radius:3px">Critical 75&ndash;100</span></p>'
            '<p style="margin:.4rem 0 .2rem"><b>Signals per artifact type</b></p>'
            '<ul style="margin:.2rem 0 .4rem 1.1rem;padding:0">'
            '<li><b>Pipelines</b> &mdash; activity count &amp; distinct activity types, nested control-flow (ForEach/If/Until), Mapping Data Flow activities, child-pipeline orchestration, dedicated-SQL stored-proc/script, Copy activities, Web/Custom/Function activities, parameters, and linked-service connections.</li>'
            '<li><b>Notebooks</b> &mdash; size (lines/cells), imports, <code>mssparkutils</code>/Synapse API usage, hardcoded storage paths, inline secrets, custom Spark config, non-Python language, and non-Delta storage.</li>'
            '<li><b>Dataflows</b> &mdash; transformation count, source/sink count, presence of heavy transforms (join, aggregate, window, pivot, surrogate key&hellip;), Mapping vs. Wrangling type, parameters, and dataset/linked-service references.</li>'
            '</ul>'
            '<p style="margin:.2rem 0"><b>Estimated rebuild effort</b> is derived from the score: <code>0.5 + score / N</code> person-days '
            '(N = 20 for pipelines, 25 for notebooks, 18 for dataflows), so higher-complexity artifacts carry more effort. '
            'Click any row above to see the exact <i>complexity drivers</i> that contributed to its score.</p>'
            '</div></details>'
            + table("Pipeline migration complexity", pipe_mc, cx_cols)
            + table("Notebook migration complexity", nb_mc, cx_cols)
            + table("Dataflow migration complexity", df_mc, cx_cols)
            + table("Fabric optimization opportunities", data.get("fabric_optimizations", []),
                    ["artifact", "artifact_type", "category", "recommendation", "fabric_feature", "impact"])
            + "</div>",
        "pipelineops": '<div class="grid">'
            '<div class="card"><div class="kpi" id="po_total">0</div>Pipeline Runs</div>'
            '<div class="card"><div class="kpi" id="po_success">0%</div>Success Rate</div>'
            '<div class="card"><div class="kpi" id="po_failed">0</div>Failed</div>'
            '<div class="card"><div class="kpi" id="po_reruns">0</div>Reruns</div>'
            '<div class="card"><div class="kpi" id="po_avg">0</div>Avg Duration</div>'
            '<div class="card" style="grid-column:1/-1"><h3>Status breakdown</h3><div id="po_status"></div></div>'
            '<div class="card" style="grid-column:1/-1"><h3>Batch vs real-time</h3><div id="po_split"></div></div>'
            '<div class="card" style="grid-column:1/-1"><h3>Runs by day (timeframe)</h3>'
            '<svg id="po_hist" width="100%" height="180" viewBox="0 0 1200 180"></svg>'
            '<p class="muted" style="margin:.3rem 0 0">Click a row in <b>Per-pipeline statistics</b> to filter these charts to one pipeline; click it again to clear.</p>'
            '<p id="po_filter" style="margin:.2rem 0 0;color:#1565C0;font-weight:600;font-size:.84rem"></p></div>'
            '<div class="card" id="po_note" style="grid-column:1/-1;display:none"></div>'
            + table("Per-pipeline statistics", data.get("pipeline_run_stats", []),
                    ["pipeline", "workspace", "total_runs", "succeeded", "failed", "reruns",
                     "batch_runs", "realtime_runs", "success_rate", "avg_duration_ms", "max_duration_ms", "last_run"])
            + "</div>",
        "spider": '<div class="grid"><div class="card" style="grid-column:1/-1">'
            '<h3>Workspace Dependency Spider</h3>'
            '<p>Each workspace radiates to its artifact groups; click a node to inspect. Use the workspace filter above to focus.</p>'
            '<svg id="spiderSvg" width="100%" height="640" viewBox="0 0 1280 640"></svg></div></div>',
        "trigspider": '<div class="grid"><div class="card" style="grid-column:1/-1">'
            '<h3>Trigger Dependency Spider</h3>'
            '<p>Follows each trigger to the pipelines it fires, then on to the notebooks and data flows those pipelines run — the schedule/event-driven chains you must re-wire in Fabric. '
            '<span style="color:#a05a2c;font-weight:600">● Trigger</span> → '
            '<span style="color:#c47f00;font-weight:600">● Pipeline</span> → '
            '<span style="color:#107c10;font-weight:600">● Notebook</span> / '
            '<span style="color:#5b8a3a;font-weight:600">● Data flow</span>. Use the workspace filter above to focus.</p>'
            '<svg id="trigSvg" width="100%" height="360" viewBox="0 0 1120 360"></svg></div></div>',
        "revspider": '<div class="grid"><div class="card" style="grid-column:1/-1">'
            '<h3>Reverse Dependency Spider</h3>'
            '<p>Traces each notebook and data flow back to the pipeline(s) that run it, then to the trigger(s) that fire those pipelines — the inverse of the Trigger Spider. Artifacts with no pipeline or no trigger are still shown (as orphans). '
            '<span style="color:#107c10;font-weight:600">● Notebook</span> / '
            '<span style="color:#5b8a3a;font-weight:600">● Data flow</span> → '
            '<span style="color:#c47f00;font-weight:600">● Pipeline</span> → '
            '<span style="color:#a05a2c;font-weight:600">● Trigger</span>. Click any node for details.</p>'
            '<p><button class="xbtn" id="revOrphanBtn">Hide unlinked</button> <span class="muted" id="revNote"></span></p>'
            '<svg id="revSvg" width="100%" height="360" viewBox="0 0 1120 360"></svg></div></div>',
        "lineage": '<div class="grid"><div class="card" style="grid-column:1/-1">'
            '<h3>Dependency &amp; Lineage Explorer</h3>'
            '<p>Every artifact with its <b>upstream</b> (what triggers or calls it) and <b>downstream</b> (what it runs or fires). Search or filter by type; click a row for full detail. '
            '⏰ trigger · ▷ pipeline · 📓 notebook · 🔀 data flow.</p>'
            '<div class="lin-ctrl"><input id="lin_q" type="search" placeholder="Search name, upstream or downstream…" oninput="renderLineage()">'
            '<span class="lin-chips">'
            '<button class="lchip active" data-lt="All" onclick="setLinType(this)">All</button>'
            '<button class="lchip" data-lt="Trigger" onclick="setLinType(this)">Triggers</button>'
            '<button class="lchip" data-lt="Pipeline" onclick="setLinType(this)">Pipelines</button>'
            '<button class="lchip" data-lt="Notebook" onclick="setLinType(this)">Notebooks</button>'
            '<button class="lchip" data-lt="Data flow" onclick="setLinType(this)">Data flows</button>'
            '</span><span class="muted" id="lin_count"></span></div>'
            '<div class="lin-tblwrap"><table class="lin-tbl"><thead><tr><th>Type</th><th>Artifact</th><th>Workspace</th>'
            '<th>Upstream ▶ this</th><th>this ▶ Downstream</th></tr></thead><tbody id="lin_body"></tbody></table></div>'
            '</div></div>',
    }
    body = "".join(f'<div id="{k}" class="view{" active" if i==0 else ""}">{views[k]}</div>'
                   for i, (k, _t) in enumerate(_VIEWS))
    return (_TEMPLATE.replace("{tabs}", tabs).replace("{boxes}", boxes)
            .replace("{workspaces}", str(data.get("workspaces", 0)))
            .replace("{body}", body).replace("{data}", json.dumps(data)))


_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Synapse to Fabric — Estate Dashboard</title>
<style>
 body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f7fa;color:#222}
 header.topbar{display:flex;align-items:center;gap:1rem;background:linear-gradient(90deg,#1565C0,#1976D2);color:#fff;padding:0 1.2rem;height:56px;box-shadow:0 2px 6px rgba(0,0,0,.18);position:sticky;top:0;z-index:70}
 .brand{display:flex;align-items:center;gap:.55rem;font-weight:600;font-size:1.05rem;white-space:nowrap}
 .brand-ico{flex:none}
 header.topbar .tabs{display:flex;align-items:center;gap:.2rem;margin-left:auto}
 .tab{background:transparent;border:0;color:#e3eefb;padding:.45rem .9rem;border-radius:20px;cursor:pointer;font-size:.9rem;white-space:nowrap;transition:background .15s,color .15s}
 .tab:hover{background:rgba(255,255,255,.16);color:#fff}
 .tab.active{background:#fff;color:#1565C0;font-weight:600}
 .ws-wrap{position:relative}
 .ws-btn{display:inline-flex;align-items:center;gap:.45rem;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.4);color:#fff;padding:.4rem .8rem;border-radius:20px;cursor:pointer;font-size:.88rem;white-space:nowrap}
 .ws-btn:hover{background:rgba(255,255,255,.24)}
 .ws-badge{background:#fff;color:#1565C0;border-radius:10px;padding:0 .5rem;font-size:.76rem;font-weight:700;line-height:1.5}
 .ws-caret{font-size:.7rem;opacity:.85}
 .ws-panel{position:absolute;right:0;top:118%;background:#fff;color:#222;border-radius:10px;box-shadow:0 8px 26px rgba(0,0,0,.25);padding:.6rem;min-width:250px;max-height:360px;overflow:auto;display:none}
 .ws-panel.open{display:block}
 .ws-panel-head{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:#888;padding:.2rem .3rem .45rem}
 .ws-panel label{display:flex;align-items:center;gap:.5rem;padding:.32rem .35rem;font-size:.86rem;cursor:pointer;border-radius:5px}
 .ws-panel label:hover{background:#eef4fb}
 .gear{flex:none;width:34px;height:34px;border-radius:50%;border:1px solid rgba(255,255,255,.4);background:rgba(255,255,255,.12);color:#fff;cursor:pointer;font-size:1rem;line-height:1}
 .gear:hover{background:rgba(255,255,255,.24)}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem;padding:1.5rem}
 .card{background:#fff;border-radius:8px;padding:1rem;box-shadow:0 1px 4px rgba(0,0,0,.1);overflow:auto}
 .kpi{font-size:2rem;font-weight:bold;color:#1F4E78}.view{display:none}.view.active{display:block}
 table{border-collapse:collapse;width:100%;font-size:.8rem}th,td{border:1px solid #e2e8f0;padding:4px 6px;text-align:left}
 th{background:#1F4E78;color:#fff}tbody tr{cursor:pointer}tbody tr:hover{background:#eef4fb}tbody tr.selrow{background:#dbeafe}
 .drawer{position:fixed;top:0;right:-460px;width:440px;height:100%;background:#fff;box-shadow:-2px 0 14px rgba(0,0,0,.2);transition:right .25s;overflow:auto;z-index:50;padding:1.2rem;box-sizing:border-box}
 .drawer.open{right:0}.drawer h2{margin-top:0;color:#1F4E78}.drawer h3{color:#1F4E78;margin:.8rem 0 .2rem}.close{float:right;cursor:pointer;font-size:1.6rem;color:#888}
 .ov{position:fixed;inset:0;background:rgba(0,0,0,.25);display:none;z-index:40}.ov.open{display:block}
 .flowbox{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;padding:.5rem;background:#fafcff;max-height:300px}
 .xbtn{font-size:.72rem;padding:2px 9px;margin-left:.5rem;cursor:pointer;border:1px solid #1F4E78;background:#1F4E78;color:#fff;border-radius:4px}
 .fs{position:fixed;inset:0;background:#fff;z-index:60;display:none;flex-direction:column}.fs.open{display:flex}
 .fsbar{background:#1F4E78;color:#fff;padding:.7rem 1.2rem;display:flex;justify-content:space-between;align-items:center}
 .fsbar .close{color:#fff;float:none}.fsbody{flex:1;overflow:auto;padding:1.5rem;background:#f5f7fa}
 .flegend{display:flex;flex-wrap:wrap;gap:.6rem;font-size:.75rem;margin:.4rem 0}.flegend span{display:inline-flex;align-items:center;gap:.3rem}.flegend i{width:12px;height:12px;border-radius:3px;display:inline-block}
 .code{background:#0d1b2a;color:#cfe;padding:.8rem;border-radius:6px;max-height:340px;overflow:auto;font-size:.78rem;white-space:pre-wrap;word-break:break-word;margin:.3rem 0}
 .muted{color:#7a8aa0;font-size:.82rem}
 .facts{margin:.3rem 0 .6rem;padding-left:1.1rem}.facts li{margin:.15rem 0;font-size:.84rem}
 .pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:.7rem;font-weight:700;color:#fff}
 .pill.trig{background:#a05a2c}.pill.pipe{background:#c47f00}.pill.nb{background:#107c10}.pill.df{background:#5b8a3a}
 .lin-ctrl{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin:.4rem 0 .6rem}
 .lin-ctrl input[type=search]{flex:1;min-width:220px;padding:.4rem .6rem;border:1px solid #cfd8e3;border-radius:6px;font-size:.85rem}
 .lchip{font-size:.75rem;padding:3px 10px;border:1px solid #cfd8e3;background:#fff;color:#334;border-radius:14px;cursor:pointer}
 .lchip.active{background:#1F4E78;color:#fff;border-color:#1F4E78}
 .lin-tblwrap{max-height:640px;overflow:auto;border:1px solid #e2e8f0;border-radius:6px}
 .lin-tbl{width:100%;border-collapse:collapse;font-size:.82rem}
 .lin-tbl th{position:sticky;top:0;background:#f0f4f9;text-align:left;padding:.45rem .6rem;border-bottom:1px solid #dce4ee;z-index:1}
 .lin-tbl td{padding:.4rem .6rem;border-bottom:1px solid #eef2f7;vertical-align:top}
 .lin-tbl td:nth-child(4),.lin-tbl td:nth-child(5){color:#425067;font-size:.78rem;max-width:340px}
 .lin-tbl tr:hover{background:#f7fafd}
 .lin-name{font-weight:700;color:#1F4E78;cursor:pointer}
 .lin-name:hover{text-decoration:underline}
 .linref{display:inline-block;cursor:pointer;border-radius:4px;padding:0 3px;margin:1px 0;white-space:nowrap;border-bottom:1px dotted transparent}
 .linref:hover{background:#eef4fb;border-bottom-color:currentColor}
 .linref.trig{color:#a05a2c}.linref.pipe{color:#c47f00}.linref.nb{color:#107c10}.linref.df{color:#5b8a3a}
</style></head><body>
<header class="topbar">
 <div class="brand"><svg class="brand-ico" width="22" height="22" viewBox="0 0 24 24"><rect x="2" y="2" width="9" height="9" rx="2" fill="#fff"/><rect x="13" y="2" width="9" height="9" rx="2" fill="#bcd9f5"/><rect x="2" y="13" width="9" height="9" rx="2" fill="#bcd9f5"/><rect x="13" y="13" width="9" height="9" rx="2" fill="#fff"/></svg><span>Synapse Assessment Report</span></div>
 <nav class="tabs">{tabs}</nav>
 <div class="ws-wrap">
  <button class="ws-btn" id="wsBtn">▤ Workspaces <span class="ws-badge" id="wsCount">0</span><span class="ws-caret">▾</span></button>
  <div class="ws-panel" id="wsPanel"><div class="ws-panel-head">Filter workspaces</div>{boxes}</div>
 </div>
 <button class="gear" id="gear" title="Back to top">⚙</button>
</header>
{body}
<div class="ov" id="ov"></div>
<div class="drawer" id="drawer"><span class="close" id="dx">×</span><div id="dc"></div></div>
<div class="fs" id="fs"><div class="fsbar"><strong id="fsTitle"></strong><span class="close" id="fx">×</span></div><div class="fsbody" id="fsBody"></div></div>
<script>
const D={data};
function active(){return [...document.querySelectorAll('.wsf:checked')].map(c=>c.value);}
function updWsCount(){const el=document.getElementById('wsCount');if(el)el.textContent=active().length;}
(function(){const btn=document.getElementById('wsBtn'),panel=document.getElementById('wsPanel');if(btn)btn.onclick=e=>{e.stopPropagation();panel.classList.toggle('open');};document.addEventListener('click',e=>{if(panel&&panel.classList.contains('open')&&!panel.contains(e.target)&&!btn.contains(e.target))panel.classList.remove('open');});const g=document.getElementById('gear');if(g)g.onclick=()=>window.scrollTo({top:0,behavior:'smooth'});})();
function sync(){updWsCount();const a=active();document.querySelectorAll('tr[data-ws]').forEach(tr=>{tr.style.display=a.includes(tr.dataset.ws)?'':'none';});
 document.querySelectorAll('.kpi[data-count]').forEach(k=>{const keys=k.dataset.count.split('|');let s=new Set();keys.forEach(key=>(D[key]||[]).forEach(r=>{if(a.includes(r.workspace)||a.includes(r.name))s.add((r.name||'')+key);}));k.textContent=s.size;});if(typeof applyBandFilter==='function')applyBandFilter();}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.view).classList.add('active');if(b.dataset.view==='spider')spider();if(b.dataset.view==='trigspider')trigSpider();if(b.dataset.view==='revspider')revSpider();if(b.dataset.view==='lineage')lineageView();if(b.dataset.view==='pipelineops')pipelineOps();if(b.dataset.view==='overview')overviewCharts();if(b.dataset.view==='fabready')fabReady();});
document.querySelectorAll('.wsf').forEach(c=>c.onchange=()=>{sync();pipelineOps();overviewCharts();fabReady();if(document.getElementById('spider')&&document.getElementById('spider').closest('.view').classList.contains('active'))spider();if(document.getElementById('trigspider')&&document.getElementById('trigspider').classList.contains('active'))trigSpider();if(document.getElementById('revspider')&&document.getElementById('revspider').classList.contains('active'))revSpider();if(document.getElementById('lineage')&&document.getElementById('lineage').classList.contains('active'))lineageView();});
document.querySelectorAll('.teamc, #team_dpw').forEach(i=>i.oninput=recalcTeam);
const _cp=document.getElementById('team_copilot');if(_cp)_cp.onchange=recalcTeam;
function esc(v){return (''+(v==null?'':v)).replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));}
function detail(rowjson,ws){let r={};try{r=JSON.parse(rowjson);}catch(e){}
 const isWs=('assessment_status' in r)||(r.name&&r.name===ws&&!('node_size' in r));
 let h='<h2>'+esc(r.name||ws)+'</h2>';
 h+='<table>'+Object.keys(r).filter(k=>k!=='code_preview'&&k!=='factors').map(k=>'<tr><th>'+esc(k)+'</th><td>'+esc(r[k])+'</td></tr>').join('')+'</table>';
 if(isWs){const lists=['spark_pools','sql_pools','pipelines','notebooks','dataflows','triggers','linked_services','datasets','integration_runtimes'];
  lists.forEach(k=>{const items=(D[k]||[]).filter(x=>x.workspace===ws);if(!items.length)return;h+='<h3>'+k.replace(/_/g,' ')+' ('+items.length+')</h3><table>';const cols=Object.keys(items[0]).slice(0,4);h+='<tr>'+cols.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>';items.slice(0,50).forEach(it=>{h+='<tr>'+cols.map(c=>'<td>'+esc(it[c])+'</td>').join('')+'</tr>';});h+='</table>';});}
 const isPipe=('activity_count' in r)&&('activity_types' in r)&&!isWs;
 if(isPipe){const acts=(D.pipeline_activities||[]).filter(x=>x.pipeline===r.name&&x.workspace===ws);
  h+='<h3>Activity flow ('+acts.length+')<button class="xbtn" id="flowExpand" data-pl="'+att(r.name)+'" data-ws="'+att(ws)+'">\u26f6 Expand</button></h3>';
  h+='<div class="flowbox">'+flowSvg(acts,false)+'</div>';}
 const isNb=('cell_count' in r)&&('language' in r)&&!isWs;
 if(isNb){const code=r.code_preview||'';h+='<h3>Notebook code'+(r.cell_count?' ('+r.cell_count+' cells, '+r.language+')':'')+'</h3>';h+=code?'<pre class="code">'+esc(code)+'</pre>':'<p class="muted">No code captured — re-run inventory with read access to this notebook.</p>';}
 const isDF=('transformation_count' in r)&&('sink_count' in r)&&!isWs;
 if(isDF){h+='<h3>Data flow detail</h3><p class="muted">'+esc(r.dataflow_type||'MappingDataFlow')+' \u00b7 '+(r.source_count||0)+' source(s) \u00b7 '+(r.sink_count||0)+' sink(s) \u00b7 '+(r.transformation_count||0)+' transformation(s)</p>';
  const tt=r.transformation_types||[];if(tt.length){h+='<h4>Transformations</h4><p>'+tt.map(esc).join(', ')+'</p>';}
  if((r.sources||[]).length){h+='<h4>Sources</h4><p>'+r.sources.map(esc).join(', ')+'</p>';}
  if((r.sinks||[]).length){h+='<h4>Sinks</h4><p>'+r.sinks.map(esc).join(', ')+'</p>';}}
 const isMC=('estimated_effort_days' in r)&&('factors' in r);
 if(isMC){const f=r.factors||[];if(f.length){h+='<h3>Complexity drivers</h3><ul class="facts">'+f.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';}
  const opts=(D.fabric_optimizations||[]).filter(o=>o.artifact===r.artifact&&o.workspace===r.workspace);
  if(opts.length){h+='<h3>Fabric optimizations ('+opts.length+')</h3><table><tr><th>category</th><th>recommendation</th><th>feature</th><th>impact</th></tr>'+opts.map(o=>'<tr><td>'+esc(o.category)+'</td><td>'+esc(o.recommendation)+'</td><td>'+esc(o.fabric_feature)+'</td><td>'+esc(o.impact)+'</td></tr>').join('')+'</table>';}else{h+='<p class="muted">No specific optimizations flagged — near 1:1 migration.</p>';}}
 document.getElementById('dc').innerHTML=h;document.getElementById('drawer').classList.add('open');document.getElementById('ov').classList.add('open');
 const eb=document.getElementById('flowExpand');if(eb)eb.onclick=()=>expandFlow(eb.dataset.pl,eb.dataset.ws);}
function closeD(){document.getElementById('drawer').classList.remove('open');document.getElementById('ov').classList.remove('open');}
document.getElementById('dx').onclick=closeD;document.getElementById('ov').onclick=closeD;
document.getElementById('fx').onclick=()=>document.getElementById('fs').classList.remove('open');
(function(){const rb=document.getElementById('revOrphanBtn');if(rb)rb.onclick=()=>{showRevOrphans=!showRevOrphans;rb.textContent=showRevOrphans?'Hide unlinked':'Show unlinked';revSpider();};})();
document.querySelectorAll('tr[data-ws]').forEach(tr=>tr.onclick=()=>{detail(tr.dataset.row||'{}',tr.dataset.ws);});
document.querySelectorAll('#pipelineops tr[data-ws]').forEach(tr=>{tr.onclick=()=>{let r={};try{r=JSON.parse(tr.dataset.row||'{}');}catch(e){}if(!r.pipeline)return;poPipeline=(poPipeline&&poPipeline.pipeline===r.pipeline&&poPipeline.workspace===r.workspace)?null:{pipeline:r.pipeline,workspace:r.workspace};pipelineOps();};});
const SVGNS='http://www.w3.org/2000/svg';
function node(svg,x,y,r,fill,label,onClick){const c=document.createElementNS(SVGNS,'circle');c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r',r);c.setAttribute('fill',fill);c.setAttribute('stroke','#fff');c.setAttribute('stroke-width',1.5);c.style.cursor='pointer';if(onClick)c.onclick=onClick;svg.appendChild(c);const t=document.createElementNS(SVGNS,'text');t.setAttribute('x',x);t.setAttribute('y',y-r-3);t.setAttribute('text-anchor','middle');t.setAttribute('font-size',10);t.setAttribute('fill','#222');t.textContent=label;svg.appendChild(t);}
function edge(svg,x1,y1,x2,y2){const l=document.createElementNS(SVGNS,'line');l.setAttribute('x1',x1);l.setAttribute('y1',y1);l.setAttribute('x2',x2);l.setAttribute('y2',y2);l.setAttribute('stroke','#b9c7d6');l.setAttribute('stroke-width',1);svg.appendChild(l);}
function spider(){const svg=document.getElementById('spiderSvg');if(!svg)return;svg.innerHTML='';const a=active();const wss=D.workspace_names.filter(w=>a.includes(w));const cx=640,cy=320,R=240;const groups=[['spark_pools','#1F4E78'],['sql_pools','#7a3e9d'],['pipelines','#c47f00'],['notebooks','#107c10'],['dataflows','#5b8a3a'],['linked_services','#0b6cad'],['datasets','#b03060'],['integration_runtimes','#555'],['triggers','#a05a2c']];
 wss.forEach((ws,wi)=>{const wa=2*Math.PI*wi/wss.length;const wx=cx+Math.cos(wa)*R,wy=cy+Math.sin(wa)*R;edge(svg,cx,cy,wx,wy);
  groups.forEach((g,gi)=>{const items=(D[g[0]]||[]).filter(r=>r.workspace===ws);if(!items.length)return;const ga=wa+(gi-3.5)*0.18;const gx=wx+Math.cos(ga)*90,gy=wy+Math.sin(ga)*90;edge(svg,wx,wy,gx,gy);node(svg,gx,gy,7+Math.min(items.length,12),g[1],g[0].replace(/_/g,' ')+' ('+items.length+')',()=>drillGroup(ws,g[0]));});
  node(svg,wx,wy,14,'#16385a',ws,()=>detail(JSON.stringify({name:ws,assessment_status:''}),ws));});
 node(svg,cx,cy,18,'#1F4E78','Estate',null);}
let _trigActIdx=null,_trigNodes=[];
function trigActIndex(){if(!_trigActIdx){const m={};(D.pipeline_activities||[]).forEach(x=>{(m[x.workspace+'|'+x.pipeline]=m[x.workspace+'|'+x.pipeline]||[]).push(x);});_trigActIdx=m;}return _trigActIdx;}
function trigLeaves(ws,pipe,seen,depth){const idx=trigActIndex();if(depth>4||seen.has(pipe))return [];seen.add(pipe);let out=[];(idx[ws+'|'+pipe]||[]).forEach(x=>{const t=x.activity_type;if(t==='SynapseNotebook')out.push({type:'nb',name:x.target||x.name});else if(t==='ExecuteDataFlow')out.push({type:'df',name:x.target||x.name});else if(t==='ExecutePipeline'&&x.target)out=out.concat(trigLeaves(ws,x.target,seen,depth+1));});return out;}
function trigSpider(){const svg=document.getElementById('trigSvg');if(!svg)return;const a=active();_trigActIdx=null;
 const pipeByKey={};(D.pipelines||[]).forEach(p=>{pipeByKey[p.workspace+'|'+p.name]=p;});
 const nbByKey={};(D.notebooks||[]).forEach(nn=>{nbByKey[nn.workspace+'|'+nn.name]=nn;});
 const dfByKey={};(D.dataflows||[]).forEach(d=>{dfByKey[d.workspace+'|'+d.name]=d;});
 const trigs=(D.triggers||[]).filter(t=>a.includes(t.workspace)&&(t.pipelines||[]).length);
 const COL={trig:'#a05a2c',pipe:'#c47f00',nb:'#107c10',df:'#5b8a3a'};const W=1120,boxW=250,boxH=24;
 if(!trigs.length){svg.setAttribute('viewBox','0 0 '+W+' 90');svg.setAttribute('height',90);svg.innerHTML='<text x="20" y="48" font-size="13" fill="#888">No triggers reference pipelines for the selected workspaces. Triggers fire pipelines that run notebooks and data flows \u2014 adjust the workspace filter or run inventory with access to populate this view.</text>';_trigNodes=[];return;}
 const nodes=[],edges=[];const rowH=32,padT=46,colT=40,colP=435,colL=820;let slot=0;
 trigs.forEach(t=>{const pipeIdxs=[];
  (t.pipelines||[]).forEach(pn=>{let leaves=trigLeaves(t.workspace,pn,new Set(),0);
   const seen={};leaves=leaves.filter(l=>{const k=l.type+'|'+l.name;if(seen[k])return false;seen[k]=1;return true;});
   const leafIdx=[];leaves.forEach(l=>{const y=padT+slot*rowH;slot++;leafIdx.push(nodes.length);const data=(l.type==='nb'?nbByKey:dfByKey)[t.workspace+'|'+l.name]||null;nodes.push({x:colL,y,label:l.name,type:l.type,ws:t.workspace,data});});
   let py;if(leafIdx.length){py=leafIdx.reduce((s,i)=>s+nodes[i].y,0)/leafIdx.length;}else{py=padT+slot*rowH;slot++;}
   const pIdx=nodes.length;nodes.push({x:colP,y:py,label:pn,type:'pipe',ws:t.workspace,data:pipeByKey[t.workspace+'|'+pn]||{name:pn,workspace:t.workspace}});pipeIdxs.push(pIdx);leafIdx.forEach(i=>edges.push([pIdx,i]));});
  let ty;if(pipeIdxs.length){ty=pipeIdxs.reduce((s,i)=>s+nodes[i].y,0)/pipeIdxs.length;}else{ty=padT+slot*rowH;slot++;}
  const tIdx=nodes.length;nodes.push({x:colT,y:ty,label:t.name,type:'trig',sub:t.init_method||t.trigger_type,ws:t.workspace,data:t});pipeIdxs.forEach(i=>edges.push([tIdx,i]));});
 const H=Math.max(120,padT+slot*rowH+12);
 let e='';edges.forEach(p=>{const P=nodes[p[0]],C=nodes[p[1]];const x1=P.x+boxW,y1=P.y+boxH/2,x2=C.x,y2=C.y+boxH/2,mx=(x1+x2)/2;e+='<path d="M'+x1+' '+y1+' C'+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2+'" fill="none" stroke="#c3cdda" stroke-width="1.3"/>';});
 let n='';nodes.forEach((nd,i)=>{const c=COL[nd.type];const sub=nd.sub?'<text x="'+(nd.x+9)+'" y="'+(nd.y+boxH-5)+'" font-size="8.5" fill="#fce4d2" style="pointer-events:none">'+esc(trim(nd.sub,32))+'</text>':'';const tY=nd.sub?(nd.y+11):(nd.y+boxH/2+3.5);n+='<g data-ni="'+i+'" style="cursor:pointer"><title>'+esc(nd.label)+' \u2014 click for details</title><rect x="'+nd.x+'" y="'+nd.y+'" width="'+boxW+'" height="'+boxH+'" rx="5" fill="'+c+'" stroke="#fff" stroke-width="1"/><text x="'+(nd.x+9)+'" y="'+tY+'" font-size="10.5" fill="#fff" font-weight="bold" style="pointer-events:none">'+esc(trim(nd.label,33))+'</text>'+sub+'</g>';});
 const heads='<text x="'+colT+'" y="24" font-size="12" font-weight="bold" fill="#a05a2c">Triggers</text><text x="'+colP+'" y="24" font-size="12" font-weight="bold" fill="#c47f00">Pipelines</text><text x="'+colL+'" y="24" font-size="12" font-weight="bold" fill="#107c10">Notebooks / Data flows</text>';
 svg.setAttribute('viewBox','0 0 '+W+' '+H);svg.setAttribute('height',H);svg.innerHTML=heads+e+n;_trigNodes=nodes;
 svg.querySelectorAll('[data-ni]').forEach(g=>g.onclick=()=>trigDetail(_trigNodes[+g.getAttribute('data-ni')]));}
function trigDetail(nd){if(!nd)return;const open=h=>{document.getElementById('dc').innerHTML=h;document.getElementById('drawer').classList.add('open');document.getElementById('ov').classList.add('open');};
 if(nd.type==='trig'){const t=nd.data;let h='<h2>'+esc(t.name)+'</h2><p class="muted">Trigger \u2014 fires the pipelines below on its schedule/event. Re-create as a Fabric schedule or Data Activator reflex.</p>';
  const fields=['workspace','trigger_type','init_method','runtime_state','recurrence','frequency','interval','start_time','end_time','time_zone','event_scope','pipeline_count'];
  h+='<table>'+fields.filter(k=>t[k]!==undefined&&t[k]!==''&&t[k]!==0).map(k=>'<tr><th>'+esc(k)+'</th><td>'+esc(t[k])+'</td></tr>').join('')+'</table>';
  const pipes=t.pipelines||[];h+='<h3>Fires '+pipes.length+' pipeline(s)</h3>';
  pipes.forEach(pn=>{let leaves=trigLeaves(t.workspace,pn,new Set(),0);const u={};leaves=leaves.filter(l=>{const k=l.type+'|'+l.name;if(u[k])return false;u[k]=1;return true;});
   const nb=leaves.filter(l=>l.type==='nb'),df=leaves.filter(l=>l.type==='df');
   h+='<h4>'+esc(pn)+'</h4>';
   if(nb.length)h+='<p><b>Notebooks ('+nb.length+'):</b> '+nb.map(l=>esc(l.name)).join(', ')+'</p>';
   if(df.length)h+='<p><b>Data flows ('+df.length+'):</b> '+df.map(l=>esc(l.name)).join(', ')+'</p>';
   if(!nb.length&&!df.length)h+='<p class="muted">No notebook/data-flow steps captured (Copy-only pipeline, or re-run inventory to resolve ExecutePipeline chains and nested steps).</p>';});
  open(h);return;}
 if(nd.data&&(('activity_count' in nd.data)||('cell_count' in nd.data)||('transformation_count' in nd.data))){detail(JSON.stringify(nd.data),nd.ws);return;}
 let h='<h2>'+esc(nd.label)+'</h2>';
 if(nd.type==='nb'||nd.type==='df')h+='<p class="muted">'+(nd.type==='nb'?'Notebook':'Data flow')+' step invoked by a pipeline activity in <b>'+esc(nd.ws)+'</b>. The matching artifact was not found in the current inventory \u2014 the label shown is the activity name. Re-run inventory with read access to capture its full detail.</p>';
 else h+='<p class="muted">Pipeline <b>'+esc(nd.label)+'</b> in '+esc(nd.ws)+' \u2014 no detailed activity record captured. Re-run inventory to populate its activity flow.</p>';
 open(h);}
let _lineage=null;
function buildLineage(){if(_lineage)return _lineage;
 const runsLeaf={},callsPipe={},calledBy={},leafPipes={},pipeByKey={},trigByKey={},trigReach={},pipeTrigs={};
 (D.pipelines||[]).forEach(p=>{pipeByKey[p.workspace+'|'+p.name]=p;});
 (D.triggers||[]).forEach(t=>{trigByKey[t.workspace+'|'+t.name]=t;});
 (D.pipeline_activities||[]).forEach(x=>{const pk=x.workspace+'|'+x.pipeline,tp=x.activity_type;
  if(tp==='SynapseNotebook'&&x.target){(runsLeaf[pk]=runsLeaf[pk]||[]).push({type:'nb',name:x.target});const lk=x.workspace+'|nb|'+x.target;(leafPipes[lk]=leafPipes[lk]||new Set()).add(x.pipeline);}
  else if(tp==='ExecuteDataFlow'&&x.target){(runsLeaf[pk]=runsLeaf[pk]||[]).push({type:'df',name:x.target});const lk=x.workspace+'|df|'+x.target;(leafPipes[lk]=leafPipes[lk]||new Set()).add(x.pipeline);}
  else if(tp==='ExecutePipeline'&&x.target){(callsPipe[pk]=callsPipe[pk]||[]).push(x.target);const ck=x.workspace+'|'+x.target;(calledBy[ck]=calledBy[ck]||new Set()).add(x.pipeline);}});
 (D.triggers||[]).forEach(t=>{const ws=t.workspace,reach=new Set(),seen=new Set(),stack=[...(t.pipelines||[])];while(stack.length){const p=stack.pop();if(seen.has(p))continue;seen.add(p);reach.add(p);(callsPipe[ws+'|'+p]||[]).forEach(c=>{if(!seen.has(c))stack.push(c);});}trigReach[ws+'|'+t.name]=reach;reach.forEach(p=>{const pk=ws+'|'+p;(pipeTrigs[pk]=pipeTrigs[pk]||new Set()).add(t.name);});});
 const toArr=o=>{const r={};Object.keys(o).forEach(k=>r[k]=[...o[k]]);return r;};
 _lineage={runsLeaf,callsPipe,calledBy:toArr(calledBy),leafPipes:toArr(leafPipes),pipeByKey,trigByKey,pipeTrigs:toArr(pipeTrigs),trigReach};return _lineage;}
let showRevOrphans=true,_revNodes=[];
function revSpider(){const svg=document.getElementById('revSvg');if(!svg)return;const a=active();const L=buildLineage();
 const W=1120,boxW=250,boxH=24,rowH=32,padT=46,colL=40,colP=435,colT=820;const COL={nb:'#107c10',df:'#5b8a3a',pipe:'#c47f00',trig:'#a05a2c'};
 const pipesOf=l=>L.leafPipes[l.ws+'|'+l.type+'|'+l.name]||[];
 let leaves=[];(D.notebooks||[]).forEach(nn=>{if(a.includes(nn.workspace))leaves.push({type:'nb',name:nn.name,ws:nn.workspace,data:nn});});(D.dataflows||[]).forEach(dd=>{if(a.includes(dd.workspace))leaves.push({type:'df',name:dd.name,ws:dd.workspace,data:dd});});
 const total=leaves.length,linked=leaves.filter(l=>pipesOf(l).length).length;
 if(!showRevOrphans)leaves=leaves.filter(l=>pipesOf(l).length);
 leaves.sort((x,y)=>{const lx=pipesOf(x).length?0:1,ly=pipesOf(y).length?0:1;return lx-ly||x.type.localeCompare(y.type)||x.name.localeCompare(y.name);});
 const note=document.getElementById('revNote');if(note)note.textContent=total+' notebook/data-flow node(s) \u00b7 '+linked+' linked to a pipeline \u00b7 '+(total-linked)+' unlinked'+(showRevOrphans?'':' (hidden)');
 if(!leaves.length){svg.setAttribute('viewBox','0 0 '+W+' 90');svg.setAttribute('height',90);svg.innerHTML='<text x="20" y="48" font-size="13" fill="#888">No notebooks or data flows to show for the selected workspaces / toggle.</text>';_revNodes=[];return;}
 const nodes=[],edges=[],pipeIdx={},trigIdx={},pipeYs={},trigYs={};let slot=0;
 leaves.forEach(l=>{const y=padT+slot*rowH;slot++;const li=nodes.length;nodes.push({x:colL,y,label:l.name,type:l.type,ws:l.ws,data:l.data});
  pipesOf(l).forEach(pn=>{const pk=l.ws+'|'+pn;if(pipeIdx[pk]==null){pipeIdx[pk]=nodes.length;nodes.push({x:colP,y:0,label:pn,type:'pipe',ws:l.ws,data:L.pipeByKey[pk]||{name:pn,workspace:l.ws}});pipeYs[pk]=[];}edges.push([li,pipeIdx[pk]]);pipeYs[pk].push(y);});});
 Object.keys(pipeIdx).forEach(pk=>{const ys=pipeYs[pk];nodes[pipeIdx[pk]].y=ys.reduce((s,v)=>s+v,0)/ys.length;const ws=pk.slice(0,pk.indexOf('|'));
  (L.pipeTrigs[pk]||[]).forEach(tn=>{const tk=ws+'|'+tn;if(trigIdx[tk]==null){trigIdx[tk]=nodes.length;nodes.push({x:colT,y:0,label:tn,type:'trig',ws,data:L.trigByKey[tk]||{name:tn,workspace:ws}});trigYs[tk]=[];}edges.push([pipeIdx[pk],trigIdx[tk]]);trigYs[tk].push(nodes[pipeIdx[pk]].y);});});
 Object.keys(trigIdx).forEach(tk=>{const ys=trigYs[tk];nodes[trigIdx[tk]].y=ys.reduce((s,v)=>s+v,0)/ys.length;});
 const declut=idxs=>{idxs.sort((i,j)=>nodes[i].y-nodes[j].y);for(let k=1;k<idxs.length;k++){if(nodes[idxs[k]].y<nodes[idxs[k-1]].y+boxH+4)nodes[idxs[k]].y=nodes[idxs[k-1]].y+boxH+4;}};
 declut(Object.values(pipeIdx));declut(Object.values(trigIdx));
 let maxY=padT;nodes.forEach(nd=>{if(nd.y>maxY)maxY=nd.y;});const H=Math.max(120,maxY+boxH+12);
 let e='';edges.forEach(p=>{const P=nodes[p[0]],C=nodes[p[1]];const x1=P.x+boxW,y1=P.y+boxH/2,x2=C.x,y2=C.y+boxH/2,mx=(x1+x2)/2;e+='<path d="M'+x1+' '+y1+' C'+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2+'" fill="none" stroke="#c3cdda" stroke-width="1.2"/>';});
 let n='';nodes.forEach((nd,i)=>{const c=COL[nd.type];n+='<g data-ri="'+i+'" style="cursor:pointer"><title>'+esc(nd.label)+' \u2014 click for details</title><rect x="'+nd.x+'" y="'+nd.y+'" width="'+boxW+'" height="'+boxH+'" rx="5" fill="'+c+'" stroke="#fff" stroke-width="1"/><text x="'+(nd.x+9)+'" y="'+(nd.y+boxH/2+3.5)+'" font-size="10.5" fill="#fff" font-weight="bold" style="pointer-events:none">'+esc(trim(nd.label,33))+'</text></g>';});
 const heads='<text x="'+colL+'" y="24" font-size="12" font-weight="bold" fill="#107c10">Notebooks / Data flows</text><text x="'+colP+'" y="24" font-size="12" font-weight="bold" fill="#c47f00">Pipelines</text><text x="'+colT+'" y="24" font-size="12" font-weight="bold" fill="#a05a2c">Triggers</text>';
 svg.setAttribute('viewBox','0 0 '+W+' '+H);svg.setAttribute('height',H);svg.innerHTML=heads+e+n;_revNodes=nodes;
 svg.querySelectorAll('[data-ri]').forEach(g=>g.onclick=()=>trigDetail(_revNodes[+g.getAttribute('data-ri')]));}
let _linRows=[],_linFiltered=[],linType='All';
const _LICON={trig:'\u23f0',pipe:'\u25b7',nb:'\U0001F4D3',df:'\U0001F500'};
function lineageRows(){const L=buildLineage();const a=active();const rows=[];
 const mk=(o)=>{o._s=(o.name+' '+o.ws+' '+(o.upPlain||'')+' '+[...(o.upItems||[]),...(o.downItems||[])].map(i=>i.n).join(' ')).toLowerCase();rows.push(o);};
 (D.triggers||[]).forEach(t=>{if(!a.includes(t.workspace))return;mk({type:'Trigger',ntype:'trig',name:t.name,ws:t.workspace,upPlain:t.init_method||t.trigger_type||'schedule/event',upItems:[],downItems:(t.pipelines||[]).map(x=>({k:'pipe',n:x})),data:t});});
 (D.pipelines||[]).forEach(p=>{if(!a.includes(p.workspace))return;const pk=p.workspace+'|'+p.name;const trigs=L.pipeTrigs[pk]||[],parents=L.calledBy[pk]||[],kids=L.callsPipe[pk]||[],lv=L.runsLeaf[pk]||[];
  const upItems=[...trigs.map(x=>({k:'trig',n:x})),...parents.map(x=>({k:'pipe',n:x}))];
  const seen={},lvd=lv.filter(l=>{const k=l.type+l.name;if(seen[k])return false;seen[k]=1;return true;});
  const downItems=[...kids.map(x=>({k:'pipe',n:x})),...lvd.map(l=>({k:l.type,n:l.name}))];
  mk({type:'Pipeline',ntype:'pipe',name:p.name,ws:p.workspace,upItems,upEmpty:'\u2014 (no trigger/parent)',downItems,data:p});});
 const leafRow=(nn,tp,label)=>{const pipes=L.leafPipes[nn.workspace+'|'+tp+'|'+nn.name]||[];const trigs=new Set();pipes.forEach(pn=>(L.pipeTrigs[nn.workspace+'|'+pn]||[]).forEach(t=>trigs.add(t)));
  const upItems=[...[...trigs].map(x=>({k:'trig',n:x})),...pipes.map(x=>({k:'pipe',n:x}))];mk({type:label,ntype:tp,name:nn.name,ws:nn.workspace,upItems,upEmpty:'\u2014 (orphan \u2014 no pipeline)',downItems:[],data:nn});};
 (D.notebooks||[]).forEach(nn=>{if(a.includes(nn.workspace))leafRow(nn,'nb','Notebook');});
 (D.dataflows||[]).forEach(dd=>{if(a.includes(dd.workspace))leafRow(dd,'df','Data flow');});
 return rows;}
function _linCell(items,ws,emptyTxt,plain){if(plain)return esc(plain);if(!items||!items.length)return '<span class="muted">'+esc(emptyTxt||'\u2014')+'</span>';
 return items.map(it=>'<span class="linref '+it.k+'" data-k="'+it.k+'" data-n="'+att(it.n)+'" data-w="'+att(ws)+'" title="'+att(it.n)+' \u2014 click for details">'+_LICON[it.k]+esc(it.n)+'</span>').join(' ');}
function linOpen(k,n,ws){const map={trig:'triggers',pipe:'pipelines',nb:'notebooks',df:'dataflows'};const d=(D[map[k]]||[]).find(x=>x.name===n&&x.workspace===ws);trigDetail({type:k,label:n,ws,data:d||{name:n,workspace:ws}});}
function lineageView(){_linRows=lineageRows();renderLineage();}
function setLinType(btn){linType=btn.getAttribute('data-lt');document.querySelectorAll('.lchip').forEach(c=>c.classList.toggle('active',c===btn));renderLineage();}
function renderLineage(){const tbody=document.getElementById('lin_body');if(!tbody)return;const qEl=document.getElementById('lin_q');const q=(qEl?qEl.value:'').toLowerCase();
 let rows=_linRows;if(linType!=='All')rows=rows.filter(r=>r.type===linType);if(q)rows=rows.filter(r=>r._s.includes(q));
 _linFiltered=rows;const cnt=document.getElementById('lin_count');if(cnt)cnt.textContent=rows.length+' item(s)'+(rows.length>600?' (showing first 600)':'');
 tbody.innerHTML=rows.slice(0,600).map((r,i)=>'<tr data-li="'+i+'"><td><span class="pill '+r.ntype+'">'+esc(r.type)+'</span></td><td class="lin-name" title="'+att(r.name)+' \u2014 click for details">'+esc(r.name)+'</td><td>'+esc(r.ws)+'</td><td>'+_linCell(r.upItems,r.ws,r.upEmpty,r.upPlain)+'</td><td>'+_linCell(r.downItems,r.ws,'\u2014')+'</td></tr>').join('');
 tbody.querySelectorAll('.lin-name').forEach(td=>td.onclick=()=>{const r=_linFiltered[+td.parentNode.getAttribute('data-li')];trigDetail({type:r.ntype,label:r.name,ws:r.ws,data:r.data});});
 tbody.querySelectorAll('.linref').forEach(el=>el.onclick=e=>{e.stopPropagation();linOpen(el.dataset.k,el.dataset.n,el.dataset.w);});}
function drillGroup(ws,k){const items=(D[k]||[]).filter(r=>r.workspace===ws);let h='<h2>'+esc(ws)+' — '+k.replace(/_/g,' ')+'</h2><table>';if(items.length){const cols=Object.keys(items[0]).slice(0,4);h+='<tr>'+cols.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>';items.slice(0,80).forEach(it=>h+='<tr>'+cols.map(c=>'<td>'+esc(it[c])+'</td>').join('')+'</tr>');}h+='</table>';document.getElementById('dc').innerHTML=h;document.getElementById('drawer').classList.add('open');document.getElementById('ov').classList.add('open');}
function att(v){return esc(v).replace(/"/g,'&quot;');}
function trim(s,n){s=''+(s==null?'':s);return s.length>n?s.slice(0,n-1)+'\u2026':s;}
const ATYPE_COLORS={Copy:'#1F4E78',ExecuteDataFlow:'#7a3e9d',ExecutePipeline:'#c47f00',SynapseNotebook:'#107c10',SqlPoolStoredProcedure:'#0b6cad',Script:'#0b6cad',ForEach:'#a05a2c',IfCondition:'#b03060',Until:'#b03060',Switch:'#b03060',Wait:'#888',Lookup:'#2a7d7d',GetMetadata:'#2a7d7d',SetVariable:'#555',Filter:'#a05a2c',WebActivity:'#d05a00'};
function atypeColor(t){return ATYPE_COLORS[t]||'#445';}
function flowLayout(acts){const byName={};acts.forEach(a=>byName[a.name]=a);const level={};
 function lvl(name,seen){if(level[name]!=null)return level[name];if(seen.has(name)){return 0;}seen.add(name);const a=byName[name];const deps=((a&&a.depends_on)||[]).filter(d=>byName[d]);const m=deps.length?Math.max.apply(null,deps.map(d=>lvl(d,seen)))+1:0;level[name]=m;return m;}
 acts.forEach(a=>lvl(a.name,new Set()));const cols={};acts.forEach(a=>{const L=level[a.name]||0;(cols[L]=cols[L]||[]).push(a);});return {level,cols};}
function flowSvg(acts,full){if(!acts||!acts.length)return '<p class="muted">No activity-level detail captured for this pipeline. Re-run inventory with read access to view the flow.</p>';
 const s=full?1.3:1;const colW=210*s,rowH=70*s,padX=24*s,padY=34*s,boxW=158*s,boxH=44*s;const lay=flowLayout(acts);const cols=lay.cols;const ncol=Object.keys(cols).length;const maxRow=Math.max.apply(null,Object.values(cols).map(c=>c.length));
 const W=Math.ceil(padX*2+(ncol-1)*colW+boxW),H=Math.ceil(padY*2+(maxRow-1)*rowH+boxH);const pos={};
 Object.keys(cols).forEach(L=>{cols[L].forEach((a,i)=>{pos[a.name]={x:padX+L*colW,y:padY+i*rowH};});});
 let edges='',nodes='';
 acts.forEach(a=>{const p=pos[a.name];((a.depends_on)||[]).forEach(d=>{const q=pos[d];if(!q)return;const x1=q.x+boxW,y1=q.y+boxH/2,x2=p.x,y2=p.y+boxH/2,mx=(x1+x2)/2;edges+='<path d="M'+x1+' '+y1+' C'+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2+'" fill="none" stroke="#7a8aa0" stroke-width="1.5" marker-end="url(#arr)"/>';});});
 acts.forEach(a=>{const p=pos[a.name];const col=atypeColor(a.activity_type);nodes+='<g><title>'+esc(a.name)+' ('+esc(a.activity_type)+')</title><rect x="'+p.x+'" y="'+p.y+'" width="'+boxW+'" height="'+boxH+'" rx="6" fill="'+col+'" stroke="#fff" stroke-width="1.5"/><text x="'+(p.x+boxW/2)+'" y="'+(p.y+boxH/2-2)+'" text-anchor="middle" font-size="'+(11*s)+'" fill="#fff" font-weight="bold">'+esc(trim(a.name,22))+'</text><text x="'+(p.x+boxW/2)+'" y="'+(p.y+boxH/2+13)+'" text-anchor="middle" font-size="'+(9*s)+'" fill="#dde8f5">'+esc(a.activity_type)+'</text></g>';});
 const types=[...new Set(acts.map(a=>a.activity_type))];const legend='<div class="flegend">'+types.map(t=>'<span><i style="background:'+atypeColor(t)+'"></i>'+esc(t)+'</span>').join('')+'</div>';
 const defs='<defs><marker id="arr" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#7a8aa0"/></marker></defs>';
 return legend+'<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'"'+(full?'':' style="max-width:100%"')+'>'+defs+edges+nodes+'</svg>';}
function expandFlow(name,ws){const acts=(D.pipeline_activities||[]).filter(x=>x.pipeline===name&&x.workspace===ws);document.getElementById('fsTitle').textContent=name+' — activity flow ('+acts.length+')';document.getElementById('fsBody').innerHTML=flowSvg(acts,true);document.getElementById('fs').classList.add('open');}
function fmtDur(ms){if(!ms)return '0s';const s=ms/1000;if(s<60)return s.toFixed(0)+'s';const m=s/60;if(m<60)return m.toFixed(1)+'m';return (m/60).toFixed(1)+'h';}
function bars(el,obj,colors,onKey){const tot=Object.values(obj).reduce((a,b)=>a+b,0)||1;let h='';Object.keys(obj).forEach((k,i)=>{const v=obj[k];h+='<div data-k="'+att(k)+'" style="display:flex;align-items:center;gap:.5rem;margin:3px 0;'+(onKey?'cursor:pointer':'')+'"><span style="width:160px">'+esc(k)+'</span><div style="background:'+(colors[i%colors.length])+';height:16px;width:'+(100*v/tot)+'%;min-width:2px"></div><span>'+v+' ('+(100*v/tot).toFixed(0)+'%)</span></div>';});el.innerHTML=h;if(onKey){el.querySelectorAll('[data-k]').forEach(d=>d.onclick=()=>onKey(d.dataset.k));}}
function showPipelinesBy(kind){const a=active();const key=kind==='batch'?'batch_runs':'realtime_runs';const st=(D.pipeline_run_stats||[]).filter(s=>a.includes(s.workspace)&&(s[key]||0)>0).sort((x,y)=>(y[key]||0)-(x[key]||0));let h='<h2>'+(kind==='batch'?'Batch (scheduled/window)':'Real-time (event/manual)')+' pipelines ('+st.length+')</h2>';if(st.length){h+='<table><tr><th>pipeline</th><th>workspace</th><th>'+key+'</th><th>total</th><th>success%</th><th>avg</th></tr>';st.forEach(s=>{h+='<tr><td>'+esc(s.pipeline)+'</td><td>'+esc(s.workspace)+'</td><td>'+(s[key]||0)+'</td><td>'+(s.total_runs||0)+'</td><td>'+(s.success_rate||0)+'</td><td>'+fmtDur(s.avg_duration_ms)+'</td></tr>';});h+='</table>';}else{h+='<p class="muted">No '+kind+' pipelines for the selected workspaces.</p>';}document.getElementById('dc').innerHTML=h;document.getElementById('drawer').classList.add('open');document.getElementById('ov').classList.add('open');}
function svgBars(el,items,onClick,selected){if(!el)return;const W=1200,H=240,padL=44,padB=42,padT=20,padR=20;const max=Math.max(1,...items.map(i=>i.v));const bw=(W-padL-padR)/items.length;let s='';for(let g=0;g<=4;g++){const y=padT+(H-padT-padB)*g/4;const val=Math.round(max*(4-g)/4);s+='<line x1="'+padL+'" y1="'+y+'" x2="'+(W-padR)+'" y2="'+y+'" stroke="#eee"/><text x="'+(padL-6)+'" y="'+(y+4)+'" text-anchor="end" font-size="11" fill="#888">'+val+'</text>';}items.forEach((it,i)=>{const h=(H-padT-padB)*it.v/max;const x=padL+i*bw+bw*0.15,y=H-padB-h,w=bw*0.7;const op=(selected&&selected!==it.k)?0.32:1;s+='<g data-k="'+att(it.k)+'"'+(onClick?' style="cursor:pointer"':'')+' opacity="'+op+'"><rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" rx="3" fill="'+it.c+'"'+(selected===it.k?' stroke="#222" stroke-width="2"':'')+'><title>'+esc(it.k)+': '+it.v+'</title></rect><text x="'+(x+w/2)+'" y="'+(y-4)+'" text-anchor="middle" font-size="11" fill="#333">'+it.v+'</text><text x="'+(x+w/2)+'" y="'+(H-padB+16)+'" text-anchor="middle" font-size="11" fill="#555">'+esc(it.k)+'</text></g>';});el.innerHTML=s;if(onClick){el.querySelectorAll('[data-k]').forEach(gp=>gp.onclick=()=>onClick(gp.getAttribute('data-k')));}}
function overviewCharts(){const a=active();const cnt=k=>(D[k]||[]).filter(r=>a.includes(r.workspace)).length;const items=[{k:'Pipelines',v:cnt('pipelines'),c:'#107c10'},{k:'Notebooks',v:cnt('notebooks'),c:'#1F4E78'},{k:'Dataflows',v:cnt('dataflows'),c:'#5b8a3a'},{k:'Spark Pools',v:cnt('spark_pools'),c:'#7a3e9d'},{k:'SQL Pools',v:cnt('sql_pools'),c:'#c47f00'},{k:'Triggers',v:cnt('triggers'),c:'#a05a2c'},{k:'Datasets',v:cnt('datasets'),c:'#b03060'},{k:'Linked Svc',v:cnt('linked_services'),c:'#0b6cad'},{k:'Int Runtimes',v:cnt('integration_runtimes'),c:'#555'}];svgBars(document.getElementById('ov_res'),items);const st=(D.pipeline_run_stats||[]).filter(s=>a.includes(s.workspace));const batch=st.reduce((s,x)=>s+(x.batch_runs||0),0),rt=st.reduce((s,x)=>s+(x.realtime_runs||0),0);const sp=document.getElementById('ov_split');if(sp)bars(sp,{'Batch (scheduled/window)':batch,'Real-time (event/manual)':rt},['#1F4E78','#0b6cad'],k=>showPipelinesBy(k.indexOf('Batch')===0?'batch':'realtime'));}
const MC_BAND_COLORS={Low:'#107c10',Medium:'#c47f00',High:'#d05a00',Critical:'#b00020'};
let mcBand=null;
function mcBandLookup(){const m={};(D.migration_complexity||[]).forEach(r=>{m[r.workspace+'|'+r.artifact]=r.complexity;});return m;}
function applyBandFilter(){const a=active();const look=mcBand?mcBandLookup():null;document.querySelectorAll('#fabready tr[data-ws]').forEach(tr=>{const wsOk=a.includes(tr.dataset.ws);let bandOk=true;if(mcBand){let r={};try{r=JSON.parse(tr.dataset.row||'{}');}catch(e){}bandOk=('complexity' in r)?(r.complexity===mcBand):(look[tr.dataset.ws+'|'+r.artifact]===mcBand);}tr.style.display=(wsOk&&bandOk)?'':'none';});}
function onMcBand(k){mcBand=(mcBand===k)?null:k;fabReady();}
let mcEffort=0;
function recalcTeam(){const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};
 let cap=0,people=0;document.querySelectorAll('.teamc').forEach(i=>{const n=Math.max(0,parseFloat(i.value)||0);people+=n;cap+=n*(parseFloat(i.dataset.alloc)||0);});
 const dpwEl=document.getElementById('team_dpw');const dpw=Math.min(7,Math.max(1,parseFloat(dpwEl&&dpwEl.value)||5));
 const cpEl=document.getElementById('team_copilot');const cp=Math.min(1,Math.max(0.1,parseFloat(cpEl&&cpEl.value)||1));
 const effort=mcEffort*cp;
 set('team_people',people);set('team_capacity',cap.toFixed(1));
 const detail=document.getElementById('team_detail');
 if(cap<=0){set('team_weeks','\u2014');if(detail)detail.textContent='Add at least one engineer with a non-zero allocation to estimate a timeline.';return;}
 const days=effort/cap;const weeks=days/dpw;const months=days/(dpw*4.33);
 set('team_weeks',weeks.toFixed(1)+' wk');
 const saved=mcEffort-effort;const cpNote=cp<1?(' GitHub Copilot trims rebuild effort by '+Math.round((1-cp)*100)+'% (\u2212'+saved.toFixed(0)+' person-days, from '+mcEffort.toFixed(0)+'d).'):'';
 if(detail)detail.textContent=Math.round(days)+' working days (~'+months.toFixed(1)+' months) of elapsed time for '+effort.toFixed(0)+' person-days of rebuild effort at '+cap.toFixed(1)+' effective FTE.'+cpNote;}
function fabReady(){const a=active();const mcAll=(D.migration_complexity||[]).filter(r=>a.includes(r.workspace));const optAll=(D.fabric_optimizations||[]).filter(o=>a.includes(o.workspace));const mc=mcBand?mcAll.filter(r=>r.complexity===mcBand):mcAll;let opt=optAll;if(mcBand){const bandArts=new Set(mc.map(r=>r.workspace+'|'+r.artifact));opt=optAll.filter(o=>bandArts.has(o.workspace+'|'+o.artifact));}const pipes=mc.filter(r=>r.artifact_type==='Pipeline'),nbs=mc.filter(r=>r.artifact_type==='Notebook'),dfs=mc.filter(r=>r.artifact_type==='Dataflow');const eff=mc.reduce((s,r)=>s+(r.estimated_effort_days||0),0);const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};set('mc_pipes',pipes.length);set('mc_nbs',nbs.length);set('mc_dfs',dfs.length);set('mc_effort',eff.toFixed(1)+'d');set('mc_opts',opt.length);mcEffort=eff;recalcTeam();const bands=['Low','Medium','High','Critical'];const items=bands.map(b=>({k:b,v:mcAll.filter(r=>r.complexity===b).length,c:MC_BAND_COLORS[b]}));svgBars(document.getElementById('mc_band'),items,onMcBand,mcBand);const fl=document.getElementById('mc_filter');if(fl)fl.textContent=mcBand?('Filtered to '+mcBand+' complexity — the cards, effort and team planner above reflect only this band. Click the band again to clear.'):'';applyBandFilter();}
let poPipeline=null;
function poLineChart(svg,byDay){if(!svg)return;svg.innerHTML='';const NS=SVGNS;const mk=(t,at,tx)=>{const e=document.createElementNS(NS,t);for(const k in at)e.setAttribute(k,at[k]);if(tx!=null)e.textContent=tx;return e;};const days=Object.keys(byDay).sort();const W=1200,H=180,padL=40,padR=16,padT=14,padB=46,mx=Math.max(1,...Object.values(byDay)),n=days.length,iw=W-padL-padR;const xAt=i=>n>1?padL+iw*i/(n-1):padL+iw/2,yAt=v=>H-padB-(H-padT-padB)*v/mx;for(let q=0;q<=4;q++){const y=padT+(H-padT-padB)*q/4;svg.appendChild(mk('line',{x1:padL,y1:y,x2:W-padR,y2:y,stroke:'#eee'}));svg.appendChild(mk('text',{x:padL-6,y:y+4,'text-anchor':'end','font-size':11,fill:'#888'},Math.round(mx*(4-q)/4)));}if(!n)return;const pts=days.map((d,i)=>[xAt(i),yAt(byDay[d])]);let ap='M'+xAt(0)+','+(H-padB);pts.forEach(p=>ap+=' L'+p[0]+','+p[1]);ap+=' L'+xAt(n-1)+','+(H-padB)+' Z';svg.appendChild(mk('path',{d:ap,fill:'rgba(31,78,120,.12)'}));svg.appendChild(mk('path',{d:'M'+pts.map(p=>p[0]+','+p[1]).join(' L'),fill:'none',stroke:'#1F4E78','stroke-width':2}));const step=Math.max(1,Math.ceil(n/8));days.forEach((d,i)=>{const c=mk('circle',{cx:pts[i][0],cy:pts[i][1],r:3,fill:'#1F4E78'});c.appendChild(mk('title',{},d+': '+byDay[d]+' run(s)'));svg.appendChild(c);if(i%step===0||i===n-1){svg.appendChild(mk('text',{x:pts[i][0],y:H-padB+16,'text-anchor':'end','font-size':10,fill:'#555',transform:'rotate(-35 '+pts[i][0]+' '+(H-padB+16)+')'},d));}});}
function pipelineOps(){const a=active();const allRuns=(D.pipeline_runs||[]).filter(r=>a.includes(r.workspace));let runs=allRuns,st=(D.pipeline_run_stats||[]).filter(s=>a.includes(s.workspace));if(poPipeline){runs=allRuns.filter(r=>r.pipeline===poPipeline.pipeline&&r.workspace===poPipeline.workspace);st=st.filter(s=>s.pipeline===poPipeline.pipeline&&s.workspace===poPipeline.workspace);}const note=document.getElementById('po_note');const fnote=document.getElementById('po_filter');document.querySelectorAll('#pipelineops tr[data-ws]').forEach(tr=>{let rr={};try{rr=JSON.parse(tr.dataset.row||'{}');}catch(e){}tr.classList.toggle('selrow',!!poPipeline&&rr.pipeline===poPipeline.pipeline&&rr.workspace===poPipeline.workspace);});if(fnote)fnote.textContent=poPipeline?('Filtered to pipeline '+poPipeline.pipeline+' ('+poPipeline.workspace+') \u2014 click the row again to clear.'):'';if(!allRuns.length){document.getElementById('po_total').textContent='0';document.getElementById('po_success').textContent='0%';document.getElementById('po_failed').textContent='0';document.getElementById('po_reruns').textContent='0';document.getElementById('po_avg').textContent='0';document.getElementById('po_status').innerHTML='';document.getElementById('po_split').innerHTML='';document.getElementById('po_hist').innerHTML='';if(note){const errs=(D.pipeline_run_errors||[]).filter(e=>a.includes(e.workspace));let h='<h3>No pipeline run history collected</h3><p>The inventory queried run history but received no data for the selected workspaces. Common causes:</p><ul><li><b>Permissions</b> — the scanning identity needs the <b>Synapse Monitoring Operator</b> (or Contributor) role on the workspace to read pipeline runs.</li><li><b>No recent executions</b> — widen the window via <code>pipeline_run_history_days</code> (default 30).</li><li><b>Network</b> — private endpoints/firewall can reset the run query.</li></ul>';if(errs.length){h+='<table><thead><tr><th>workspace</th><th>collection issue</th></tr></thead><tbody>'+errs.map(e=>'<tr><td>'+esc(e.workspace)+'</td><td>'+esc(e.issue)+'</td></tr>').join('')+'</tbody></table>';}note.innerHTML=h;note.style.display='';}return;}if(note)note.style.display='none';const ok=runs.filter(r=>r.status==='Succeeded').length;const fail=runs.filter(r=>r.status==='Failed').length;const rer=st.reduce((s,x)=>s+(x.reruns||0),0);const durs=runs.map(r=>r.duration_ms).filter(x=>x>0);document.getElementById('po_total').textContent=runs.length;document.getElementById('po_success').textContent=(runs.length?100*ok/runs.length:0).toFixed(0)+'%';document.getElementById('po_failed').textContent=fail;document.getElementById('po_reruns').textContent=rer;document.getElementById('po_avg').textContent=fmtDur(durs.length?durs.reduce((a,b)=>a+b,0)/durs.length:0);const status={};runs.forEach(r=>status[r.status||'Unknown']=(status[r.status||'Unknown']||0)+1);bars(document.getElementById('po_status'),status,['#107c10','#c4314b','#888','#c47f00']);const batch=st.reduce((s,x)=>s+(x.batch_runs||0),0),rt=st.reduce((s,x)=>s+(x.realtime_runs||0),0);bars(document.getElementById('po_split'),{'Batch (scheduled/window)':batch,'Real-time (event/manual)':rt},['#1F4E78','#0b6cad'],k=>showPipelinesBy(k.indexOf('Batch')===0?'batch':'realtime'));const byDay={};runs.forEach(r=>{const d=(r.run_start||'').slice(0,10);if(d)byDay[d]=(byDay[d]||0)+1;});poLineChart(document.getElementById('po_hist'),byDay);}
sync();spider();trigSpider();pipelineOps();overviewCharts();fabReady();
</script></body></html>"""
