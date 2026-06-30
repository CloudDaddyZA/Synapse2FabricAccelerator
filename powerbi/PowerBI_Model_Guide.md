# Power BI Model Guide

A ready-to-open Power BI Project (`SynapseMigration.pbip`) is generated alongside
the CSVs. Enable **File > Options > Preview features > Power BI Project save**,
then open `SynapseMigration.pbip` in Power BI Desktop.

## Data source
All tables import from the CSV extracts via the `DataFolder` parameter (defaults
to this folder). Move the CSVs? Update `DataFolder` under Transform data.

## Tables
workspaces, pipelines, pipeline_activities, notebooks, spark_pools, sql_pools,
linked_services, datasets, dataflows, security_findings, migration_complexity,
fabric_recommendations.

## Relationships
Link each child table to `workspaces[name]` via its `workspace` column. Link
security_findings / migration_complexity / fabric_recommendations on `artifact`.

## Key measures (pre-built)
- Workspace Count, Regions, Pipeline Count, Notebook Count, Delta Notebooks %
- Spark Pool Count, SQL Pool Count, Open Findings, Avg Complexity

## Slicers
region (workspaces[location]), workspace, severity, fabric_target.

## Report pages
Overview, Estate Inventory, Spark & SQL, Migration Risk, Fabric Targets.
Add visuals on each page from the pre-built measures and dimension columns.
