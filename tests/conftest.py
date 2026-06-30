"""Shared pytest fixtures: a minimal synthetic inventory + tmp settings."""
from __future__ import annotations

import pytest

from src.exporters.json_writer import write_json
from src.utils.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(output_path=str(tmp_path / "output"))


@pytest.fixture
def sample_inventory():
    return {
        "workspaces": [
            {
                "workspace": {"name": "synw-demo", "location": "eastus", "resource_group": "rg-demo", "subscription_id": "sub1", "dev_endpoint": "https://x.dev.azuresynapse.net"},
                "spark_pools": [{"name": "sp1", "workspace": "synw-demo", "node_size": "Medium", "autoscale_enabled": True, "auto_pause_enabled": False}],
                "sql_pools": [{"name": "dwh", "workspace": "synw-demo", "sku": "DW100c", "is_serverless": False}],
                "pipelines": [{"name": "pl1", "workspace": "synw-demo", "activity_count": 12, "activity_types": ["Copy", "ExecuteDataFlow"], "has_nested_activities": True, "parameter_count": 3, "linked_service_refs": ["ls1"], "dataset_refs": []}],
                "pipeline_activities": [{"pipeline": "pl1", "workspace": "synw-demo", "name": "a", "activity_type": "Copy"}],
                "notebooks": [{"name": "nb1", "workspace": "synw-demo", "language": "python", "line_count": 200, "imports": ["pyspark"], "uses_spark": True, "uses_synapse_utils": True, "has_secrets": True, "uses_delta": False}],
                "dataflows": [{"name": "df1", "workspace": "synw-demo", "dataflow_type": "MappingDataFlow", "source_count": 1, "sink_count": 1, "transformation_count": 3, "transformation_types": ["join", "derive", "select"], "sources": ["src1"], "sinks": ["sink1"], "linked_service_refs": [], "dataset_refs": ["ds1"], "parameter_count": 0, "script_line_count": 5, "folder": ""}],
                "triggers": [], "linked_services": [{"name": "ls1", "workspace": "synw-demo", "service_type": "AzureBlobFS"}], "datasets": [], "integration_runtimes": [], "storage_dependencies": [],
            }
        ]
    }


@pytest.fixture
def seeded(settings, sample_inventory):
    write_json(sample_inventory, settings.subdir("inventory") / "synapse_inventory.json")
    write_json([sample_inventory["workspaces"][0]["workspace"]], settings.subdir("discovery") / "workspaces.json")
    return settings
