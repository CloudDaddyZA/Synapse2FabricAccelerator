"""Shared enums for risk levels, scoring categories, and Fabric targets."""
from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    """Ordinal risk / complexity rating used across all assessments."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

    @property
    def weight(self) -> int:
        return {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}[self.value]

    @classmethod
    def from_score(cls, score: int) -> RiskLevel:
        """Map a numeric score (0-100) to a band."""
        if score >= 75:
            return cls.CRITICAL
        if score >= 50:
            return cls.HIGH
        if score >= 25:
            return cls.MEDIUM
        return cls.LOW


class ScoreCategory(StrEnum):
    MIGRATION_COMPLEXITY = "Migration Complexity"
    PERFORMANCE_RISK = "Performance Risk"
    SECURITY_RISK = "Security Risk"
    OPERATIONAL_RISK = "Operational Risk"
    FABRIC_COMPATIBILITY_RISK = "Fabric Compatibility Risk"
    MODERNIZATION_OPPORTUNITY = "Modernization Opportunity"


class ArtifactType(StrEnum):
    WORKSPACE = "Workspace"
    SPARK_POOL = "Spark Pool"
    SQL_POOL = "SQL Pool"
    PIPELINE = "Pipeline"
    DATAFLOW = "Dataflow"
    NOTEBOOK = "Notebook"
    SQL_SCRIPT = "SQL Script"
    SPARK_JOB_DEFINITION = "Spark Job Definition"
    TRIGGER = "Trigger"
    LINKED_SERVICE = "Linked Service"
    DATASET = "Dataset"
    INTEGRATION_RUNTIME = "Integration Runtime"


class FabricTarget(StrEnum):
    FABRIC_WORKSPACE = "Fabric Workspace"
    DATA_PIPELINE = "Fabric Data Factory Pipeline"
    DATAFLOW_GEN2 = "Dataflow Gen2"
    FABRIC_NOTEBOOK = "Fabric Notebook"
    FABRIC_SPARK = "Fabric Spark Compute"
    WAREHOUSE = "Fabric Warehouse"
    LAKEHOUSE = "Fabric Lakehouse"
    SQL_ENDPOINT = "Lakehouse SQL Endpoint"
    ONELAKE = "OneLake"
    CONNECTION = "Fabric Connection"
    GATEWAY = "Fabric Gateway"
    SEMANTIC_MODEL = "Semantic Model"
