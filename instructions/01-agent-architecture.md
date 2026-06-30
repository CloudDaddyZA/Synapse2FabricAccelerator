# Specialized Agent Architecture
Seven agents run in order: Discovery → Inventory → Assessment → Migration → Reporting → Dashboard → Optimization.

## Shared Components
Authentication, configuration, logging, retry, REST + Azure SDK clients, Excel/JSON/CSV/Markdown/HTML writers, data + scoring models.

## CLI
`python -m src.cli {discover|inventory|assess|migrate|report|dashboard|optimize|run-all}`

## Agent Rules
Read only required inputs; write to own folder; log progress; capture errors; continue on partial failure; emit machine- and human-readable outputs; use shared models/utils.
