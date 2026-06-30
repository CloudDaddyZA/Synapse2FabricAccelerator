"""Inventory data models describing the Synapse estate."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Subscription(BaseModel):
    subscription_id: str
    display_name: str = ""
    state: str = ""
    tenant_id: str = ""


class ResourceGroup(BaseModel):
    name: str
    subscription_id: str
    location: str = ""
    tags: dict[str, str] = Field(default_factory=dict)


class Workspace(BaseModel):
    name: str
    workspace_id: str = ""
    subscription_id: str = ""
    resource_group: str = ""
    location: str = ""
    tags: dict[str, str] = Field(default_factory=dict)
    managed_resource_group: str = ""
    dev_endpoint: str = ""
    sql_endpoint: str = ""
    sql_ondemand_endpoint: str = ""
    default_storage_account: str = ""
    default_filesystem: str = ""
    git_provider: str = ""
    git_repo: str = ""
    managed_vnet: bool = False
    public_network_access: str = ""


class SparkPool(BaseModel):
    name: str
    workspace: str
    node_size: str = ""
    node_size_family: str = ""
    node_count: int = 0
    autoscale_enabled: bool = False
    min_nodes: int = 0
    max_nodes: int = 0
    auto_pause_enabled: bool = False
    auto_pause_minutes: int = 0
    spark_version: str = ""
    library_count: int = 0


class SqlPool(BaseModel):
    name: str
    workspace: str
    sku: str = ""
    tier: str = ""
    status: str = ""
    is_serverless: bool = False
    collation: str = ""
    table_count: int = 0
    total_size_mb: float = 0.0
    largest_table: str = ""
    largest_table_mb: float = 0.0
    sizes_collected: bool = False


class PipelineActivity(BaseModel):
    pipeline: str
    workspace: str
    name: str
    activity_type: str
    has_retry: bool = False
    depends_on_count: int = 0
    depends_on: list[str] = Field(default_factory=list)


class Pipeline(BaseModel):
    name: str
    workspace: str
    activity_count: int = 0
    activity_types: list[str] = Field(default_factory=list)
    parameter_count: int = 0
    has_nested_activities: bool = False
    linked_service_refs: list[str] = Field(default_factory=list)
    dataset_refs: list[str] = Field(default_factory=list)


class PipelineRun(BaseModel):
    """A single historical pipeline run from queryPipelineRuns."""

    run_id: str
    pipeline: str
    workspace: str
    status: str = ""
    invoked_by: str = ""
    invoked_type: str = ""  # Manual / ScheduleTrigger / BlobEventsTrigger / Rerun
    is_rerun: bool = False
    run_start: str = ""
    run_end: str = ""
    duration_ms: int = 0


class PipelineRunStats(BaseModel):
    """Aggregated execution statistics per pipeline (and estate rollup)."""

    pipeline: str
    workspace: str
    total_runs: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    in_progress: int = 0
    reruns: int = 0
    batch_runs: int = 0     # scheduled / tumbling-window
    realtime_runs: int = 0  # event / manual triggered
    success_rate: float = 0.0
    avg_duration_ms: int = 0
    max_duration_ms: int = 0
    min_duration_ms: int = 0
    first_run: str = ""
    last_run: str = ""


class Trigger(BaseModel):
    name: str
    workspace: str
    trigger_type: str = ""
    runtime_state: str = ""
    init_method: str = ""      # Schedule / Tumbling window / Storage event / Custom event / Manual
    recurrence: str = ""       # human-readable, e.g. "Every 1 Hour"
    frequency: str = ""
    interval: int = 0
    start_time: str = ""
    end_time: str = ""
    time_zone: str = ""
    event_scope: str = ""      # storage account / topic for event triggers
    pipeline_count: int = 0
    pipelines: list[str] = Field(default_factory=list)


class LinkedService(BaseModel):
    name: str
    workspace: str
    service_type: str = ""
    references_key_vault: bool = False
    target: str = ""


class Dataset(BaseModel):
    name: str
    workspace: str
    dataset_type: str = ""
    linked_service: str = ""


class Dataflow(BaseModel):
    """A Synapse Mapping/Wrangling Data Flow artifact."""

    name: str
    workspace: str
    dataflow_type: str = ""          # MappingDataFlow / WranglingDataFlow
    source_count: int = 0
    sink_count: int = 0
    transformation_count: int = 0
    transformation_types: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    sinks: list[str] = Field(default_factory=list)
    linked_service_refs: list[str] = Field(default_factory=list)
    dataset_refs: list[str] = Field(default_factory=list)
    parameter_count: int = 0
    script_line_count: int = 0
    folder: str = ""


class IntegrationRuntime(BaseModel):
    name: str
    workspace: str
    ir_type: str = ""
    is_managed_vnet: bool = False


class Notebook(BaseModel):
    name: str
    workspace: str
    language: str = ""
    cell_count: int = 0
    line_count: int = 0
    imports: list[str] = Field(default_factory=list)
    uses_spark: bool = False
    has_hardcoded_paths: bool = False
    has_secrets: bool = False
    uses_synapse_utils: bool = False
    uses_delta: bool = False
    uses_spark_config: bool = False
    code_preview: str = ""


class StorageDependency(BaseModel):
    workspace: str
    storage_account: str
    filesystem: str = ""
    source: str = ""


class WorkspaceInventory(BaseModel):
    """All artifacts collected for a single workspace."""

    workspace: Workspace
    spark_pools: list[SparkPool] = Field(default_factory=list)
    sql_pools: list[SqlPool] = Field(default_factory=list)
    pipelines: list[Pipeline] = Field(default_factory=list)
    pipeline_activities: list[PipelineActivity] = Field(default_factory=list)
    pipeline_runs: list[PipelineRun] = Field(default_factory=list)
    pipeline_run_stats: list[PipelineRunStats] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    linked_services: list[LinkedService] = Field(default_factory=list)
    datasets: list[Dataset] = Field(default_factory=list)
    dataflows: list[Dataflow] = Field(default_factory=list)
    integration_runtimes: list[IntegrationRuntime] = Field(default_factory=list)
    notebooks: list[Notebook] = Field(default_factory=list)
    storage_dependencies: list[StorageDependency] = Field(default_factory=list)
    assessment_status: str = "Accessible"
    inaccessible_artifacts: list[str] = Field(default_factory=list)


class Inventory(BaseModel):
    """Top-level inventory across all workspaces."""

    workspaces: list[WorkspaceInventory] = Field(default_factory=list)
