# Inventory Agent
Collect artifacts from discovered workspaces: Spark/SQL pools, pipelines + activities, triggers, linked services, datasets, integration runtimes, notebooks, Spark jobs, SQL scripts, storage/Key Vault/identity deps, Git, networking.

Outputs: `synapse_inventory.{json,xlsx}`, `artifact_index.csv`, `dependency_map.json`, `output/logs/inventory_errors.json`.
Excel sheets: Workspaces, Spark/SQL Pools, Pipelines, Activities, Triggers, Linked Services, Datasets, IRs, Notebooks, Spark Usage, Storage, Security, Networking, Migration Complexity, Recommendations. Continue on per-artifact failure.
