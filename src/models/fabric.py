"""Data models describing the target Microsoft Fabric environment.

These describe what actually exists in the destination tenant (capacities,
workspaces, items) plus a readiness/capability assessment judging whether the
provisioned estate can run the migrated Synapse workloads.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FabricCapacity(BaseModel):
    """A Fabric (F-SKU) or Power BI Premium capacity."""

    id: str = ""
    display_name: str = ""
    sku: str = ""            # e.g. F2, F64, P1
    region: str = ""
    state: str = ""         # Active / Paused / Provisioning / ...
    admins: list[str] = Field(default_factory=list)
    capacity_units: int = 0  # resolved from SKU (F64 -> 64)


class FabricRoleAssignment(BaseModel):
    principal: str = ""
    principal_type: str = ""  # User / Group / ServicePrincipal
    role: str = ""            # Admin / Member / Contributor / Viewer


class FabricWorkspace(BaseModel):
    """A Fabric workspace and its capacity assignment."""

    id: str = ""
    name: str = ""
    description: str = ""
    type: str = ""                     # Workspace / AdminInsights / ...
    capacity_id: str = ""
    capacity_sku: str = ""
    capacity_region: str = ""
    on_dedicated_capacity: bool = False
    item_count: int = 0
    roles: list[FabricRoleAssignment] = Field(default_factory=list)
    accessible: bool = True


class FabricItem(BaseModel):
    """An item inside a Fabric workspace (Lakehouse, Warehouse, Notebook, ...)."""

    id: str = ""
    name: str = ""
    type: str = ""            # Lakehouse / Warehouse / Notebook / DataPipeline / Dataflow / SemanticModel / Report / ...
    workspace_id: str = ""
    workspace_name: str = ""
    description: str = ""


class FabricEstate(BaseModel):
    """The full discovered target-Fabric estate."""

    tenant_id: str = ""
    accessible: bool = False
    capacities: list[FabricCapacity] = Field(default_factory=list)
    workspaces: list[FabricWorkspace] = Field(default_factory=list)
    items: list[FabricItem] = Field(default_factory=list)
    item_type_counts: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class CapabilityFinding(BaseModel):
    """A single readiness/capability observation about the target estate."""

    category: str            # Capacity / Region / Workspace / Coverage / Security / Governance
    severity: str            # Critical / High / Medium / Low / Info / Pass
    target: str = ""         # capacity or workspace name the finding is about
    message: str = ""
    recommendation: str = ""


class WorkloadDemand(BaseModel):
    """Source-side workload scale used to size the target capacity."""

    workspaces: int = 0
    pipelines: int = 0
    notebooks: int = 0
    dataflows: int = 0
    spark_pools: int = 0
    sql_pools: int = 0
    spark_vcores: int = 0            # peak provisioned Spark vCores across pools
    sql_dwu: int = 0                 # summed dedicated SQL pool DWU
    recommended_sku: str = ""        # smallest F-SKU judged sufficient
    required_capacity_units: int = 0


class FabricReadinessAssessment(BaseModel):
    """Verdict on whether the provisioned Fabric estate can run the workloads."""

    verdict: str = "Unknown"         # Ready / Ready with actions / Not ready / Unknown (no access)
    demand: WorkloadDemand = Field(default_factory=WorkloadDemand)
    largest_capacity_sku: str = ""
    largest_capacity_units: int = 0
    findings: list[CapabilityFinding] = Field(default_factory=list)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    coverage: list[dict] = Field(default_factory=list)  # per source workspace -> target match + item gap
