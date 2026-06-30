"""Markdown and HTML rendering helpers (Jinja2-based)."""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, select_autoescape
from markupsafe import Markup

_HTML_SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
 body{font-family:Segoe UI,Arial,sans-serif;margin:0;color:#222;line-height:1.5}
 nav{background:#1F4E78;padding:.7rem 2rem;display:flex;gap:1.2rem}nav a{color:#cfe;text-decoration:none;font-size:.9rem}nav a:hover{color:#fff;text-decoration:underline}
 main{margin:2rem}h1,h2,h3{color:#1F4E78} table{border-collapse:collapse;width:100%;margin:1rem 0}
 th,td{border:1px solid #ddd;padding:8px;text-align:left} th{background:#1F4E78;color:#fff}
 tbody tr:hover,tr:hover{background:#eef4fb} code{background:#f4f4f4;padding:2px 4px} .crit{color:#b00020;font-weight:bold}
</style></head><body>
<nav><a href="executive_migration_summary.html">Executive Summary</a><a href="technical_assessment_report.html">Technical Report</a><a href="admin_report.html">Admin</a><a href="data_engineering_report.html">Data Engineering</a><a href="data_warehousing_report.html">Data Warehousing</a><a href="data_integration_report.html">Data Integration</a><a href="fabric_recommendations_report.html">Fabric Targets</a><a href="synapse_audit_report.html">Full Audit</a><a href="../dashboard/index.html">Dashboard ↗</a></nav>
<main>{{ body }}</main></body></html>"""


def write_markdown(text: str, path: str | Path) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def markdown_to_html_body(md: str) -> str:
    """Minimal MD->HTML for headings, lists, tables, paragraphs (offline)."""
    def _inline(t: str) -> str:
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        return re.sub(r"`(.+?)`", r"<code>\1</code>", t)

    lines = md.splitlines()
    out: list[str] = []
    in_table = False
    in_list = False
    for line in lines:
        s = line.strip()
        if s.startswith("|") and "|" in s[1:]:
            if in_list:
                out.append("</ul>")
                in_list = False
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set("".join(cells)) <= {"-", " ", ":"}:
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if s.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(s[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if s.startswith("### "):
            out.append(f"<h3>{s[4:]}</h3>")
        elif s.startswith("## "):
            out.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("# "):
            out.append(f"<h1>{s[2:]}</h1>")
        elif s:
            out.append(f"<p>{_inline(s)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def write_html(title: str, markdown_body: str, path: str | Path) -> Path:
    env = Environment(autoescape=select_autoescape())
    tmpl = env.from_string(_HTML_SHELL)
    html = tmpl.render(title=title, body=Markup(markdown_to_html_body(markdown_body)))
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    return dest
