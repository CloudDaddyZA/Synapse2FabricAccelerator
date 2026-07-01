# `src/agents/` — the seven pipeline agents

Each agent extends `base_agent.py`, reads only the inputs it needs, writes to its own output folder, logs progress, and continues on partial failure (recording errors rather than aborting the run). They execute in the order below; `python -m src.cli run-all` chains them.

| # | File | Agent | Inputs | Key outputs |
|---|---|---|---|---|
| 1 | `discovery_agent.py` | Discovery | Azure subscriptions | `output/discovery/` |
| 2 | `inventory_agent.py` | Inventory | workspaces (REST + DMVs) | `output/inventory/` |
| 3 | `assessment_agent.py` | Assessment | inventory | `output/assessment/` |
| 4 | `migration_agent.py` | Migration | inventory + assessment | `output/migration/` |
| 5 | `reporting_agent.py` | Reporting | inventory + assessment + migration | `output/reports/` |
| 6 | `dashboard_agent.py` | Dashboard | all of the above | `output/dashboard/` + `powerbi/*.csv` |
| 7 | `optimization_agent.py` | Optimization | inventory + assessment | `output/copilot_optimization_pack/` |

---

## 1. Discovery — `discovery_agent.py`
Enumerates accessible subscriptions, resource groups, and Synapse workspaces (honoring `subscription_ids` / `resource_group_names` / `workspace_names` filters). Writes `subscriptions.json`, `resource_groups.json`, `workspaces.json`, and a Markdown summary.

## 2. Inventory — `inventory_agent.py`
For each workspace, collects via the Synapse data-plane REST API and SQL DMVs:

- **Pipelines** (activities, nesting, parameters, dataset/linked-service refs) and **run history** (`queryPipelineRuns`, aggregated to per-pipeline stats: success rate, reruns, batch vs. real-time, durations).
- **Mapping & Wrangling Data Flows** — parses `typeProperties` for sources, sinks, transformation types (join, lookup, aggregate, window, pivot, surrogate key, …), parameters, and dataset/linked-service references.
- **Notebooks** (language, cells, Spark/Delta/MSSparkUtils/Spark-config flags, secret detection, code preview).
- **Spark pools**, **SQL pools** (with best-effort table sizing), **triggers**, **linked services**, **datasets**, **integration runtimes**, **storage dependencies**, and **Git config**.

Writes `synapse_inventory.json`, a multi-sheet Excel workbook (one sheet per artifact type, incl. **Dataflows**), an `artifact_index.csv`, a `dependency_map.json`, and per-artifact errors to `output/logs/`. Records an access status per workspace (Accessible / Partial / Forbidden).

## 3. Assessment — `assessment_agent.py`
Scores every artifact and computes Fabric readiness:

- `assess_pipeline` / `assess_notebook` / `assess_spark` / `assess_sql` / **`assess_dataflow`** → `ArtifactScore` (complexity, compatibility risk, modernization opportunity).
- `*_complexity` → `MigrationComplexity` (band, effort-days, complexity drivers, Fabric target). Data flows map to **Dataflow Gen2**.
- `*_optimizations` → `FabricOptimization` (modernization / performance / cost / security recommendations).

Writes `assessment_summary.json`, `complexity_scores.json`, `migration_complexity.json`, `fabric_optimizations.json`, `performance_findings.json`, `security_findings.json`, and `fabric_readiness.md`.

## 4. Migration — `migration_agent.py`
Maps each source artifact to a Fabric target (`FabricRecommendation`) and builds a phased **wave plan** (workspaces → SQL pools → pipelines/**data flows** → notebooks/Spark). Writes `fabric_recommendations.json`, `migration_waves.json`, `synapse_to_fabric_mapping.md`, `migration_path.md`, and cutover / validation / decommission checklists.

## 5. Reporting — `reporting_agent.py`
Generates 13 Markdown + HTML reports from saved JSON:

- **Executive** (KPIs incl. data flows, complexity bands, top risks, waves).
- **Technical** (workspace inventory, notebooks, **data flows**, SQL pools, findings, Fabric targets, validation plan).
- **Role-aligned**: Admin, Data Engineering (incl. data flows), Data Warehousing, Data Integration (incl. data flows), plus risk register, dependency, and Fabric recommendations.

## 6. Dashboard — `dashboard_agent.py`
Assembles a single data dict from inventory/assessment/migration and renders the self-contained HTML dashboard via `templates/dashboard_template.py`. Also writes the Power BI CSV datasets (incl. `dataflows.csv`) and refreshes the model guide. The dashboard groups its dependency visualizations (Workspace Diagram, Trigger Dependency Diagram, Dependency Diagram, and Lineage) under a **Diagrams** dropdown, and the Fabric Readiness view embeds a delivery-team & timeline planner that converts per-artifact effort estimates into a calendar duration based on team head-counts and a GitHub Copilot productivity tier, and re-scopes its KPIs when a complexity band is selected.

## 7. Optimization — `optimization_agent.py`
Produces the **Copilot optimization pack**: per-artifact review prompts (pipeline / notebook / spark / SQL) plus source artifacts and an index `README.md`. No Copilot API calls are made — these are prompts for engineers to run in VS Code.

---

## Conventions

- New artifact fields require a fresh **`inventory`** run against Azure (older JSON lacks them).
- Changes to assessment outputs require **`assess`** then **`dashboard`** / **`report`** (the latter two read saved JSON and need no Azure access).
- All agents log to `output/logs/` and never abort the whole run on a single artifact failure.
