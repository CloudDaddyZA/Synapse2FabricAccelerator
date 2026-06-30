"""Assessment and migration data models."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import ArtifactType, FabricTarget, RiskLevel


class Finding(BaseModel):
    """A single security/performance/operational observation."""

    artifact: str
    artifact_type: ArtifactType
    workspace: str
    category: str
    severity: RiskLevel
    message: str


class ArtifactScore(BaseModel):
    """Per-artifact assessment across all score categories."""

    artifact: str
    artifact_type: ArtifactType
    workspace: str
    migration_complexity: RiskLevel = RiskLevel.LOW
    performance_risk: RiskLevel = RiskLevel.LOW
    security_risk: RiskLevel = RiskLevel.LOW
    operational_risk: RiskLevel = RiskLevel.LOW
    fabric_compatibility_risk: RiskLevel = RiskLevel.LOW
    modernization_opportunity: RiskLevel = RiskLevel.LOW
    score: int = 0
    notes: list[str] = Field(default_factory=list)


class MigrationComplexity(BaseModel):
    """Detailed migration-complexity breakdown for a pipeline or notebook."""

    artifact: str
    artifact_type: ArtifactType
    workspace: str
    score: int = 0
    complexity: RiskLevel = RiskLevel.LOW
    estimated_effort_days: float = 0.0
    factors: list[str] = Field(default_factory=list)
    fabric_target: str = ""


class FabricOptimization(BaseModel):
    """A concrete optimization opportunity when moving an artifact to Fabric."""

    artifact: str
    artifact_type: ArtifactType
    workspace: str
    category: str  # Performance / Cost / Security / Modernization / Maintainability / Operational
    recommendation: str
    fabric_feature: str = ""
    impact: RiskLevel = RiskLevel.MEDIUM


class Assessment(BaseModel):
    scores: list[ArtifactScore] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    complexity: list[MigrationComplexity] = Field(default_factory=list)
    optimizations: list[FabricOptimization] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class FabricRecommendation(BaseModel):
    source_artifact: str
    source_type: ArtifactType
    workspace: str
    fabric_target: FabricTarget
    effort_band: RiskLevel = RiskLevel.MEDIUM
    rationale: str = ""


class MigrationWaveItem(BaseModel):
    wave: int
    phase: str
    artifact: str
    artifact_type: ArtifactType
    workspace: str
    effort_band: RiskLevel
    fabric_target: FabricTarget


class MigrationPlan(BaseModel):
    recommendations: list[FabricRecommendation] = Field(default_factory=list)
    waves: list[MigrationWaveItem] = Field(default_factory=list)
