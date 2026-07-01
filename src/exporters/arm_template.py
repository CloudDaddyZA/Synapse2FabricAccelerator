"""ARM template exporter for the Fabric Data Factory Migration Assistant (FDFMA).

FDFMA (https://github.com/microsoft/fabric-toolbox/tree/main/tools/
FabricDataFactoryMigrationAssistant) is a browser SPA that ingests an ADF/Synapse
ARM template JSON, profiles it, and deploys the supported artifacts (pipelines,
datasets, linked services, triggers) to Microsoft Fabric Data Pipelines. This
module turns the raw artifact definitions captured during inventory into exactly
that input — a faithful Synapse workspace ARM template the tool can profile
directly, with no manual "Export ARM template" step in Synapse Studio.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_writer import write_json

_ARM_SCHEMA = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
_API_VERSION = "2019-06-01-preview"
_RESOURCE_PREFIX = "Microsoft.Synapse/workspaces"

# Raw artifact collection name -> ARM child-resource folder segment.
_RESOURCE_TYPES: dict[str, str] = {
    "linkedservices": "linkedServices",
    "datasets": "datasets",
    "dataflows": "dataflows",
    "notebooks": "notebooks",
    "pipelines": "pipelines",
    "triggers": "triggers",
}

# Deployment order: a resource may only depend on kinds that appear earlier here,
# which guarantees the generated ``dependsOn`` graph is a DAG (no ARM cycles).
_ORDER: list[str] = ["linkedservices", "datasets", "dataflows", "notebooks", "pipelines", "triggers"]


def _reference_names(obj: Any) -> set[str]:
    """Recursively collect every ``referenceName`` value in an artifact body."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "referenceName" and isinstance(val, str):
                found.add(val)
            else:
                found |= _reference_names(val)
    elif isinstance(obj, list):
        for item in obj:
            found |= _reference_names(item)
    return found


def build_arm_template(
    workspace_name: str,
    raw_defs: dict[str, list[dict[str, Any]]],
    *,
    include: list[str] | None = None,
    resource_prefix: str = _RESOURCE_PREFIX,
) -> dict[str, Any]:
    """Assemble a Synapse/ADF ARM template from captured raw artifact definitions.

    ``raw_defs`` maps a collection name (``pipelines``, ``datasets``,
    ``linkedservices``, ``triggers``, ``dataflows``, ``notebooks``) to the list of
    raw REST payloads (each ``{"name": ..., "properties": {...}}``). The result is
    a deployment-template dict ready to serialize and feed to FDFMA.
    """
    include = include or _ORDER

    # Map every artifact name to its kind so cross-references become dependsOn.
    name_kind: dict[str, str] = {}
    for kind in _ORDER:
        for raw in raw_defs.get(kind, []) or []:
            name = raw.get("name")
            if name:
                name_kind[name] = kind

    resources: list[dict[str, Any]] = []
    for kind in _ORDER:
        if kind not in include:
            continue
        folder = _RESOURCE_TYPES[kind]
        for raw in raw_defs.get(kind, []) or []:
            name = raw.get("name")
            if not name:
                continue
            props = raw.get("properties", {}) or {}
            depends = sorted({
                f"[concat(variables('workspaceId'), '/{_RESOURCE_TYPES[name_kind[ref]]}/{ref}')]"
                for ref in _reference_names(props)
                if ref in name_kind and _ORDER.index(name_kind[ref]) < _ORDER.index(kind)
            })
            resources.append({
                "name": f"[concat(parameters('workspaceName'), '/{name}')]",
                "type": f"{resource_prefix}/{folder}",
                "apiVersion": _API_VERSION,
                "properties": props,
                "dependsOn": depends,
            })

    return {
        "$schema": _ARM_SCHEMA,
        "contentVersion": "1.0.0.0",
        "parameters": {
            "workspaceName": {
                "type": "string",
                "defaultValue": workspace_name,
                "metadata": {"description": "Source Synapse / target Fabric workspace name"},
            }
        },
        "variables": {
            "workspaceId": f"[concat('{resource_prefix}/', parameters('workspaceName'))]"
        },
        "resources": resources,
    }


def write_arm_template(
    workspace_name: str,
    raw_defs: dict[str, list[dict[str, Any]]],
    path: str | Path,
    *,
    include: list[str] | None = None,
) -> Path:
    """Build and write a single-workspace ARM template to ``path``."""
    template = build_arm_template(workspace_name, raw_defs, include=include)
    return write_json(template, path)
