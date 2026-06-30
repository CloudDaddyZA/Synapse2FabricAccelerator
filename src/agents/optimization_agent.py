"""Optimization Agent.

Builds a GitHub Copilot optimization pack (prompts + source artifacts + review
index) for notebooks, pipelines, SQL, and Spark. Does NOT call any Copilot API;
generates files consultants open in VS Code with Copilot Chat / Agent Mode.
"""
from __future__ import annotations

from ..exporters.excel_writer import write_workbook
from ..exporters.json_writer import read_json
from ..exporters.markdown_writer import write_markdown
from .base_agent import BaseAgent

NOTEBOOK_PROMPT = """# Copilot Review: Notebook `{name}` ({workspace})
Review this Synapse notebook for Fabric migration. Cover: Spark performance, partitioning, caching, joins, shuffles, repeated reads/writes, hardcoded paths, secrets, mssparkutils/Synapse APIs, Fabric compatibility, Delta optimization, maintainability. Then produce optimized Fabric notebook code using OneLake paths."""
PIPELINE_PROMPT = """# Copilot Review: Pipeline `{name}` ({workspace})
Review activity design, dependency chains, retry policies, failure handling, parameters, hardcoded linked services, trigger design, copy patterns, unsupported Fabric patterns. Suggest a Fabric Data Factory pipeline design."""
SQL_PROMPT = """# Copilot Review: SQL `{name}` ({workspace})
Review dedicated SQL pool objects, stored procedures, views, distribution, materialized views, CTAS, PolyBase, external tables. Assess Fabric Warehouse vs Lakehouse SQL endpoint fit."""


class OptimizationAgent(BaseAgent):
    name = "optimization"
    output_subdir = "copilot_optimization_pack"

    def _inv(self):
        p = self.settings.subdir("inventory") / "synapse_inventory.json"
        return read_json(p) if p.exists() else {"workspaces": []}

    def run(self) -> dict:
        self.logger.info("Optimization pack starting")
        inv = self._inv()
        out = self.output_dir
        for d in ["notebook_prompts", "pipeline_prompts", "sql_prompts", "spark_prompts", "source_artifacts"]:
            (out / d).mkdir(exist_ok=True)
        index = []
        for w in inv.get("workspaces", []):
            wn = w["workspace"]["name"]
            for n in w.get("notebooks", []):
                f = out / "notebook_prompts" / f"{n['name']}.md"
                write_markdown(NOTEBOOK_PROMPT.format(name=n["name"], workspace=wn), f)
                index.append({"artifact": n["name"], "type": "Notebook", "workspace": wn, "complexity_score": 0, "priority": "High" if n.get("uses_synapse_utils") else "Medium", "target": "Fabric Notebook", "prompt_file": str(f), "review_status": "Pending", "notes": ""})
            for p in w.get("pipelines", []):
                f = out / "pipeline_prompts" / f"{p['name']}.md"
                write_markdown(PIPELINE_PROMPT.format(name=p["name"], workspace=wn), f)
                index.append({"artifact": p["name"], "type": "Pipeline", "workspace": wn, "complexity_score": p.get("activity_count", 0), "priority": "High" if p.get("activity_count", 0) > 10 else "Medium", "target": "Fabric Data Pipeline", "prompt_file": str(f), "review_status": "Pending", "notes": ""})
            for sp in w.get("sql_pools", []):
                f = out / "sql_prompts" / f"{sp['name']}.md"
                write_markdown(SQL_PROMPT.format(name=sp["name"], workspace=wn), f)
                index.append({"artifact": sp["name"], "type": "SQL Pool", "workspace": wn, "complexity_score": 0, "priority": "High", "target": "Fabric Warehouse", "prompt_file": str(f), "review_status": "Pending", "notes": ""})
        write_workbook({"Copilot Review Index": index}, out / "copilot_review_index.xlsx")
        write_markdown("# Copilot Optimization Pack\n\nOpen prompts in VS Code and run with GitHub Copilot Chat/Agent Mode. See copilot_review_index.xlsx.", out / "README.md")
        self.save_errors("optimization_errors.json")
        self.logger.info("Optimization pack complete: %d prompts", len(index))
        return {"prompts": len(index)}
