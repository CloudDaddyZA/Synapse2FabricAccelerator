# Access Request — Synapse → Fabric Migration Audit

**Purpose:** Read-only assessment of Azure Synapse Analytics estate to plan a Microsoft Fabric migration.
**Requested by:** _<your name>_ — Entra ID (UPN): _<you@domain.com>_ — Object ID: _<run `az ad signed-in-user show --query id -o tsv`>_
**Access type:** Read-only. No data is modified, deleted, or moved. No pipelines are triggered.
**Duration:** Length of assessment engagement (suggest time-boxed / PIM eligible).

## Why current access is insufficient
Discovery (control plane via Azure Resource Manager) already works — workspaces are listed. But every **data-plane** call returns **403 Forbidden**, so no pipelines, notebooks, triggers, linked services, or datasets can be read. This requires a **Synapse RBAC role** on each workspace, which is separate from Azure subscription roles.

## Workspaces in scope
- <workspace-1>
- <workspace-2>
- <workspace-3>
- <workspace-4>
- <workspace-5>

## Required access (least privilege)

| # | Scope | Role | Why |
|---|-------|------|-----|
| 1 | Each Synapse workspace (data plane) | **Synapse Artifact User** | List/read pipelines, notebooks, triggers, linked services, datasets |
| 2 | Subscription / resource groups | **Reader** | Inventory workspaces, Spark/SQL pools, networking, config |
| 3 | Default ADLS Gen2 storage (optional) | **Storage Blob Data Reader** | Inspect storage dependencies/sizing |
| 4 | Network / firewall | Add my IP to allow-list, or workspace **Managed VNet** access | Reach `*.dev.azuresynapse.net` endpoints |

> Higher roles (Synapse Administrator, Contributor) are **not** required. Artifact User is read-only.

## Commands for the platform/admin team

```powershell
# 1. My object id
$me = "<my-object-id>"   # az ad signed-in-user show --query id -o tsv

# 2. Synapse Artifact User on each workspace
foreach ($ws in '<workspace-1>','<workspace-2>','<workspace-3>','<workspace-4>','<workspace-5>') {
  az synapse role assignment create --workspace-name $ws --role "Synapse Artifact User" --assignee $me
}

# 3. Reader at subscription scope
az role assignment create --assignee $me --role "Reader" --scope "/subscriptions/<sub-id>"

# 4. (optional) Storage read on default data lakes
az role assignment create --assignee $me --role "Storage Blob Data Reader" --scope "<storage-account-resource-id>"
```

## Networking
If workspaces restrict public access, also allow my client IP on each workspace firewall, or route via the approved network. Confirm Spark/SQL pool firewalls permit the same.

## Verification
After grants, the audit reruns and previously-empty datasets populate. Confirm with:

```powershell
az synapse pipeline list --workspace-name <workspace-1> -o table
```

## Security notes
- Read-only roles; no write/delete/execute. No secrets accessed. Output stays in the engagement workspace.
- Service principal alternative: assign the same roles to the SP object id instead of my user.
