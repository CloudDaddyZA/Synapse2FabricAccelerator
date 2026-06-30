# Architecture

```
Discovery → Inventory → Assessment → Migration → Reporting → Dashboard → Optimization
```

- **agents/** — one module per agent, all extend `BaseAgent` (settings, logger, error collector, output dir).
- **services/** — `auth` (DefaultAzureCredential / SP), `azure_clients` (mgmt SDKs), `synapse_rest` (data-plane artifacts).
- **models/** — Pydantic inventory + assessment models, `enums` (RiskLevel/FabricTarget/ArtifactType).
- **utils/** — config loader, logging, tenacity retry, scoring.
- **exporters/** — JSON/CSV/Excel/Markdown/HTML writers.
- **templates/** — offline Chart.js dashboard.

Each agent isolates failures per artifact and records them in `output/logs/<agent>_errors.json`. Management plane uses Azure SDKs; data plane uses REST where SDK coverage is thin.
