# Discovery Agent
Discover tenants, subscriptions, resource groups, Synapse workspaces, regions, tags, managed RGs, endpoints, Git metadata, access status. No deep artifact analysis.

Inputs: `config/settings.yaml`, `.env`, Azure auth context.
Outputs: `output/discovery/{subscriptions,resource_groups,workspaces}.json`, `discovery_summary.md`, `output/logs/discovery_errors.json`.
Filters: tenant_id, subscriptions, resource_groups, workspace_names, regions.
