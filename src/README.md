# `src/` — module tour

The accelerator is a small, modular Python package. Each subpackage has a single responsibility.

| Path | Responsibility |
|---|---|
| `cli.py` | Command-line entry point. Defines `discover`, `inventory`, `assess`, `migrate`, `report`, `dashboard`, `optimize`, `run-all`, and `serve`. Each command instantiates one agent (or the full chain) with the resolved config. |
| `agents/` | The seven pipeline agents. See [`agents/README.md`](agents/README.md). |
| `models/` | Pydantic data models and enums shared across agents. |
| `services/` | Azure connectivity: credential resolution, ARM/SDK clients, and the Synapse data-plane REST client. |
| `exporters/` | Output writers: JSON, CSV, Excel, Markdown→HTML, and the Power BI `.pbip` generator. |
| `templates/` | The self-contained HTML dashboard template (inline SVG charts and JS). |
| `utils/` | Cross-cutting helpers: config loading, logging setup, retry/backoff, and scoring math. |
| `webapp/` | Flask web UI: configuration, workspace selection, background job runner, and output browser. |

## `models/`

- `enums.py` — `ArtifactType` (Workspace, Pipeline, **Dataflow**, Notebook, SparkPool, SqlPool, …), `FabricTarget` (Lakehouse, Warehouse, Fabric Notebook, **Dataflow Gen2**, Data Factory, …), `RiskLevel`.
- `inventory.py` — `Workspace`, `Pipeline`, `PipelineActivity`, `PipelineRun(Stats)`, **`Dataflow`**, `Notebook`, `SparkPool`, `SqlPool`, `Trigger`, `LinkedService`, `Dataset`, `IntegrationRuntime`, and `WorkspaceInventory` / `Inventory` aggregates.
- `assessment.py` — `ArtifactScore`, `MigrationComplexity`, `FabricOptimization`, `FabricRecommendation`, and security findings.

## `services/`

- `auth.py` — resolves a `DefaultAzureCredential` / `ClientSecretCredential` from environment (Azure CLI, Managed Identity, or Service Principal).
- `azure_clients.py` — ARM/SDK clients for subscriptions, resource groups, and Synapse control-plane resources.
- `synapse_rest.py` — thin Synapse data-plane REST client (`list_all`) used for pipelines, **dataflows**, notebooks, datasets, linked services, triggers, and pipeline run queries.

## `exporters/`

- `json_writer.py`, `csv_writer.py`, `excel_writer.py` — structured data writers.
- `markdown_writer.py` — Markdown plus `write_html` (autoescape on; bodies are wrapped in `Markup`, with inline `**bold**` / `` `code` `` support).
- `powerbi_pbip.py` — generates `powerbi/SynapseMigration.pbip`; table column lists must match the CSV headers exactly.

## `templates/`

- `dashboard_template.py` — renders `output/dashboard/index.html`. All charts are inline SVG (no CDN). Views: Overview, Admin, Data Engineering, Data Warehousing, Data Integration, Pipeline Ops, Fabric Readiness, and Spider, plus a shared workspace filter and a drill-down drawer. The Fabric Readiness view adds a client-side **delivery-team & timeline planner** (`recalcTeam()`): role head-count inputs (`.teamc`, each carrying a `data-alloc` allocation factor) and a **GitHub Copilot** productivity selector combine to turn the band-aware rebuild effort (`mcEffort`) into an effective-FTE-based calendar duration. Selecting a complexity band re-scopes the KPI cards, effort, optimizations, and planner — not just the tables.

## `webapp/`

- `app.py` — Flask routes (config, `/workspaces`, run triggers, `/status`, output browser).
- `jobs.py` — background job runner with per-step progress.
- `auth.py` — UI-side helpers for connection settings.

Run via `python -m src.cli serve` or `python -m src.webapp` (http://127.0.0.1:8050).
