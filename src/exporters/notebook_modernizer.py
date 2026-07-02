"""Notebook modernization: Synapse -> Fabric notebook best-practice rewriter.

Assesses each Synapse Spark notebook and produces a modernized, Fabric-ready
notebook (`.ipynb`) plus a per-notebook report. Safe, deterministic rewrites are
applied automatically (e.g. the deprecated ``mssparkutils`` module is renamed to
Fabric's ``notebookutils``); code that needs a human decision (hardcoded ADLS
paths, inline secrets, dedicated-SQL connectors, hardcoded Spark configs,
filesystem mounts, Synapse magics) is detected, scored, and surfaced as an
actionable checklist embedded in the modernized notebook.

Pure functions; no Azure calls. Works on full notebook cells when a live
inventory captured them (``raw_definitions.json``) and gracefully falls back to
the truncated ``code_preview`` otherwise.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models.inventory import Inventory
from .csv_writer import write_csv
from .json_writer import write_json
from .markdown_writer import write_markdown

TOOL_NAME = "Fabric Notebook Modernizer"


# --- Rule catalog ---------------------------------------------------------


@dataclass(frozen=True)
class _AutoRule:
    id: str
    description: str
    pattern: re.Pattern[str]
    repl: str


@dataclass(frozen=True)
class _ManualRule:
    id: str
    description: str
    pattern: re.Pattern[str]
    guidance: str
    penalty: int


# Safe, deterministic rewrites applied to code cells.
_AUTO_RULES: list[_AutoRule] = [
    _AutoRule(
        "mssparkutils-to-notebookutils",
        "Renamed the deprecated `mssparkutils` module to Fabric's `notebookutils`.",
        re.compile(r"\bmssparkutils\b"),
        "notebookutils",
    ),
]

# Detected and surfaced for manual review; each present rule lowers the
# post-modernization Fabric readiness score by its penalty.
_MANUAL_RULES: list[_ManualRule] = [
    _ManualRule(
        "inline-secret",
        "Possible inline secret, account key, SAS token, or connection string.",
        re.compile(
            r"AccountKey=|SharedAccessSignature|[?&]sig=|password\s*=\s*['\"]"
            r"|['\"][A-Za-z0-9+/]{40,}={0,2}['\"]",
            re.I,
        ),
        "Move secrets to Azure Key Vault and read them with "
        "`notebookutils.credentials.getSecret(akvName, secretName)`. Never hardcode keys.",
        25,
    ),
    _ManualRule(
        "dedicated-sql-connector",
        "Dedicated SQL pool connector (`synapsesql`) is not available in Fabric.",
        re.compile(r"synapsesql|com\.microsoft\.spark\.sqlanalytics|sqlanalytics", re.I),
        "Read/write through the Fabric Warehouse or Lakehouse SQL endpoint instead of the "
        "`synapsesql` connector (e.g. Warehouse T-SQL or Lakehouse Delta tables).",
        15,
    ),
    _ManualRule(
        "synapse-linked-service",
        "Synapse linked-service credential lookup.",
        re.compile(r"getConnectionStringOrCreds|getSecretWithLS|linkedService|LinkedService", re.I),
        "Recreate the linked service as a Fabric connection and reference it through the "
        "Fabric connection / managed-identity model.",
        12,
    ),
    _ManualRule(
        "hardcoded-adls-path",
        "Hardcoded ADLS Gen2 path (`abfss://`).",
        re.compile(r"abfss://[^\s'\"]+", re.I),
        "Replace `abfss://<container>@<account>.dfs.core.windows.net/...` with a Lakehouse-relative "
        "path (`Files/...` or `Tables/...`), a OneLake shortcut, or a notebook parameter.",
        10,
    ),
    _ManualRule(
        "filesystem-mount",
        "Filesystem mount. Fabric prefers Lakehouse shortcuts over mounts.",
        re.compile(r"\.fs\.mount\s*\(|\bmount\s*\(", re.I),
        "Replace `fs.mount(...)` with a Lakehouse shortcut, or use `notebookutils.fs` with OneLake paths.",
        10,
    ),
    _ManualRule(
        "legacy-wasbs-path",
        "Legacy WASB(S) blob path. Fabric uses OneLake / ADLS Gen2.",
        re.compile(r"wasbs?://[^\s'\"]+", re.I),
        "Migrate `wasb(s)://` storage to a OneLake lakehouse path or a shortcut.",
        8,
    ),
    _ManualRule(
        "hardcoded-spark-config",
        "Hardcoded Spark session / cluster config. Fabric autoscales pools.",
        re.compile(
            r"spark\.conf\.set\s*\(|SparkSession\.builder|spark\.executor\.|spark\.sql\.shuffle",
            re.I,
        ),
        "Remove executor / cluster-sizing configs (Fabric manages compute). Keep only functional "
        "settings and prefer `%%configure` or the Fabric environment.",
        6,
    ),
    _ManualRule(
        "synapse-magic",
        "Synapse-specific magic command.",
        re.compile(r"^\s*%{1,2}(?:synapse|pyspark)\b", re.M),
        "Review Synapse-only magics. Fabric supports `%%configure`, `%%sql`, and `%run`; "
        "remove Synapse-specific magics.",
        5,
    ),
]


# --- Core transform -------------------------------------------------------


@dataclass
class ModernizationResult:
    """Outcome of modernizing a single notebook's combined source."""

    source: str
    applied: list[dict[str, Any]] = field(default_factory=list)
    manual: list[dict[str, Any]] = field(default_factory=list)
    readiness: int = 100

    @property
    def band(self) -> str:
        if self.readiness >= 80:
            return "Fabric-ready"
        if self.readiness >= 50:
            return "Minor changes"
        return "Major changes"


def _scan(pattern: re.Pattern[str], text: str) -> tuple[int, str]:
    matches = list(pattern.finditer(text))
    if not matches:
        return 0, ""
    return len(matches), matches[0].group(0).strip()[:120]


def apply_auto_rules(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Apply the safe auto-rewrites to a block of code, returning (text, applied)."""
    applied: list[dict[str, Any]] = []
    for rule in _AUTO_RULES:
        new, n = rule.pattern.subn(rule.repl, text)
        if n:
            text = new
            applied.append({"rule": rule.id, "description": rule.description, "count": n})
    return text, applied


def modernize_source(source: str) -> ModernizationResult:
    """Assess and auto-rewrite a notebook's combined source for Fabric."""
    text, applied = apply_auto_rules(source or "")
    manual: list[dict[str, Any]] = []
    penalty = 0
    for rule in _MANUAL_RULES:
        count, sample = _scan(rule.pattern, text)
        if count:
            manual.append({
                "rule": rule.id,
                "description": rule.description,
                "guidance": rule.guidance,
                "count": count,
                "sample": sample,
            })
            penalty += rule.penalty
    return ModernizationResult(
        source=text, applied=applied, manual=manual, readiness=max(0, 100 - penalty),
    )


# --- Notebook (.ipynb) assembly ------------------------------------------


def _cells_from_raw(raw: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    props = raw.get("properties", {}) or {}
    lang = (props.get("metadata", {}) or {}).get("language_info", {}).get("name", "python")
    cells: list[tuple[str, str]] = []
    for c in props.get("cells", []) or []:
        src = c.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        cells.append((c.get("cell_type", "code"), src))
    return lang or "python", cells


def _summary_markdown(name: str, workspace: str, result: ModernizationResult, full: bool) -> str:
    lines = [
        "# \U0001f527 Modernized for Microsoft Fabric",
        "",
        f"**Notebook:** `{name}`  \u00b7  **Workspace:** `{workspace}`  ",
        f"**Fabric readiness after auto-fixes:** {result.readiness}/100 \u2014 **{result.band}**",
        "",
        "## Auto-applied changes",
    ]
    if result.applied:
        lines += [f"- \u2705 {a['description']} (\u00d7{a['count']})" for a in result.applied]
    else:
        lines.append("- None required.")
    lines += ["", "## Manual actions required"]
    if result.manual:
        for m in result.manual:
            sample = f" \u2014 e.g. `{m['sample']}`" if m["sample"] else ""
            lines.append(f"- [ ] **{m['rule']}** ({m['count']}): {m['guidance']}{sample}")
    else:
        lines.append("- None \u2014 this notebook looks Fabric-ready.")
    fidelity = "full notebook cells" if full else "truncated code preview (re-run a live inventory for full fidelity)"
    lines += [
        "",
        f"> Generated by the {TOOL_NAME}. Source fidelity: {fidelity}.",
        "> Review every change before running in Fabric.",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def build_fabric_notebook(
    name: str, workspace: str, language: str, cells: list[tuple[str, str]], result: ModernizationResult,
) -> dict[str, Any]:
    """Assemble a Fabric-ready `.ipynb` document (summary cell + rewritten cells)."""
    nb_cells: list[dict[str, Any]] = [{
        "cell_type": "markdown",
        "metadata": {},
        "source": _summary_markdown(name, workspace, result, full=bool(cells)).splitlines(keepends=True),
    }]
    for cell_type, src in cells:
        if cell_type == "markdown":
            nb_cells.append({"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)})
        else:
            rewritten, _ = apply_auto_rules(src)
            nb_cells.append({
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": rewritten.splitlines(keepends=True),
            })
    lang = (language or "python").lower()
    return {
        "cells": nb_cells,
        "metadata": {
            "language_info": {"name": lang},
            "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": lang},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


# --- Writer ---------------------------------------------------------------


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "unnamed"


def _band_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in reports:
        out[r["band"]] = out.get(r["band"], 0) + 1
    return out


def _readme(manifest: dict[str, Any]) -> str:
    bands = manifest["readiness_bands"]
    band_lines = "".join(f"- **{b}**: {n}\n" for b, n in sorted(bands.items())) or "- (none)\n"
    return (
        f"# {TOOL_NAME}\n\n"
        f"Modernized **{manifest['notebooks']}** Synapse notebook(s) for Microsoft Fabric, "
        f"auto-applying **{manifest['auto_changes_applied']}** safe rewrite(s).\n\n"
        "Each `<workspace>/<notebook>.ipynb` is a Fabric-ready notebook whose first cell summarizes "
        "the automatic fixes and lists the remaining manual actions as a checklist. Import it into a "
        "Fabric workspace (Notebook > Import), attach a Lakehouse, and work through the checklist.\n\n"
        "## Fabric readiness after auto-fixes\n"
        f"{band_lines}\n"
        "## What is auto-fixed vs. manual\n"
        "- **Auto:** `mssparkutils` \u2192 `notebookutils`.\n"
        "- **Manual (flagged in each notebook):** inline secrets \u2192 Key Vault, `abfss://` paths \u2192 "
        "OneLake/Lakehouse, `synapsesql` \u2192 Warehouse/Lakehouse SQL, filesystem mounts \u2192 shortcuts, "
        "hardcoded Spark configs, and Synapse-only magics.\n\n"
        "See `notebook_modernization.csv` for the per-notebook readiness scores and "
        "`modernization_manifest.json` for full detail.\n"
    )


def write_notebook_modernization(
    out_dir: str | Path,
    inventory: Inventory,
    raw_by_workspace: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Modernize every notebook in ``inventory`` and write the Fabric pack.

    Returns a manifest dict. Writes per-workspace ``.ipynb`` notebooks, a
    ``modernization_manifest.json``, a ``notebook_modernization.csv``, and a
    ``README.md`` under ``out_dir``.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_by_workspace = raw_by_workspace or {}
    reports: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    total_auto = 0

    for w in inventory.workspaces:
        wn = w.workspace.name
        raw_nbs = {
            r.get("name", ""): r
            for r in (raw_by_workspace.get(wn, {}) or {}).get("notebooks", [])
        }
        for nb in w.notebooks:
            raw = raw_nbs.get(nb.name)
            if raw:
                language, cells = _cells_from_raw(raw)
            else:
                language, cells = (nb.language or "python"), [("code", nb.code_preview or "")]
            combined = "\n".join(src for _ct, src in cells)
            result = modernize_source(combined)
            total_auto += sum(a["count"] for a in result.applied)

            ws_dir = out / _safe_name(wn)
            ws_dir.mkdir(parents=True, exist_ok=True)
            nb_json = build_fabric_notebook(nb.name, wn, language, cells, result)
            nb_path = ws_dir / f"{_safe_name(nb.name)}.ipynb"
            nb_path.write_text(json.dumps(nb_json, indent=1), encoding="utf-8")

            reports.append({
                "workspace": wn,
                "notebook": nb.name,
                "source_fidelity": "full" if raw else "preview",
                "readiness": result.readiness,
                "band": result.band,
                "auto_changes": result.applied,
                "manual_actions": result.manual,
                "modernized_notebook": str(nb_path.relative_to(out)).replace("\\", "/"),
            })
            rows.append({
                "workspace": wn,
                "notebook": nb.name,
                "readiness": result.readiness,
                "band": result.band,
                "auto_changes": len(result.applied),
                "manual_actions": len(result.manual),
                "source_fidelity": "full" if raw else "preview",
            })

    manifest = {
        "tool": TOOL_NAME,
        "notebooks": len(reports),
        "auto_changes_applied": total_auto,
        "readiness_bands": _band_counts(reports),
        "reports": reports,
    }
    write_json(manifest, out / "modernization_manifest.json")
    write_csv(rows, out / "notebook_modernization.csv",
              ["workspace", "notebook", "readiness", "band",
               "auto_changes", "manual_actions", "source_fidelity"])
    write_markdown(_readme(manifest), out / "README.md")
    return manifest
