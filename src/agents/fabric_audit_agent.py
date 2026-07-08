"""Fabric Audit Agent.

Audits the *target* Microsoft Fabric environment and judges whether the
provisioned estate (capacities, workspaces, items) can actually run the
migrated Synapse workloads.

Two parts:
  1. Estate discovery  - enumerate capacities, workspaces, items, roles via the
     Fabric REST API (best-effort; degrades gracefully with no access).
  2. Readiness audit   - size the source workload, compare it to the largest
     available capacity, check region alignment / dedicated-capacity / coverage,
     and emit a verdict plus actionable findings.

Outputs (output/fabric_audit/):
  fabric_estate.json, fabric_readiness_assessment.json, fabric_audit_summary.md
"""
from __future__ import annotations

import math
import re

from ..exporters.json_writer import read_json, write_json
from ..exporters.markdown_writer import write_html, write_markdown
from ..models.fabric import (
    CapabilityFinding,
    FabricCapacity,
    FabricEstate,
    FabricItem,
    FabricReadinessAssessment,
    FabricRoleAssignment,
    FabricWorkspace,
    WorkloadDemand,
)
from ..services.auth import get_credential
from ..services.fabric_rest import FabricRestClient
from .base_agent import BaseAgent

# Synapse Spark node size -> vCores per node (used to size the source workload).
_NODE_VCORES = {"small": 4, "medium": 8, "large": 16, "xlarge": 32, "xxlarge": 64}
# Fraction of non-peak Spark pools assumed to run concurrently with the largest.
_SPARK_CONCURRENCY = 0.3
# Effective Fabric Spark vCores served per capacity unit (2 base, ~3x burst).
_SPARK_VCORES_PER_CU = 3
# Fabric F-SKU capacity-unit ladder.
_F_SKUS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
# Power BI Premium P-SKU -> approximate Fabric capacity units.
_P_SKU_CU = {"P1": 64, "P2": 128, "P3": 256, "P4": 512, "P5": 1024}
# Source artifact -> expected Fabric item type in the target workspace.
_EXPECTED_ITEM = {
    "pipelines": "DataPipeline",
    "notebooks": "Notebook",
    "dataflows": "Dataflow",
    "sql_pools": "Warehouse",
    "spark_pools": "Lakehouse",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def sku_to_cu(sku: str) -> int:
    """Resolve a capacity SKU string to its capacity-unit count."""
    s = (sku or "").strip().upper()
    if not s:
        return 0
    if s in _P_SKU_CU:
        return _P_SKU_CU[s]
    m = re.match(r"F(?:T)?(\d+)", s)  # F64, FT1 (trial)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else 0


class FabricAuditAgent(BaseAgent):
    name = "fabric_audit"
    output_subdir = "fabric_audit"

    def __init__(self, settings=None):
        super().__init__(settings)
        self.credential = get_credential(self.settings)

    # ---- estate discovery -------------------------------------------------
    def discover_estate(self) -> FabricEstate:
        estate = FabricEstate(tenant_id=self.settings.tenant_id)
        client = FabricRestClient(self.credential, self.settings)
        cap_filter = {n for n in self.settings.fabric_capacity_names}
        ws_filter = {n for n in self.settings.fabric_workspace_names}

        # Capacities
        cap_by_id: dict[str, FabricCapacity] = {}
        try:
            for c in client.capacities():
                name = c.get("displayName", "") or c.get("name", "")
                if cap_filter and name not in cap_filter:
                    continue
                sku = c.get("sku", "") or ((c.get("properties") or {}).get("sku") or "")
                cap = FabricCapacity(
                    id=c.get("id", ""), display_name=name, sku=sku,
                    region=c.get("region", ""), state=c.get("state", ""),
                    admins=list(c.get("admins") or []),
                    capacity_units=sku_to_cu(sku),
                )
                estate.capacities.append(cap)
                cap_by_id[cap.id] = cap
            estate.accessible = True
        except Exception as exc:  # noqa: BLE001
            self.errors.add("fabric_capacities", exc)
            estate.errors.append(f"capacities: {exc}")
            self.logger.warning("Fabric capacity discovery failed: %s", exc)

        # Workspaces
        try:
            for w in client.workspaces():
                name = w.get("displayName", "") or w.get("name", "")
                if ws_filter and name not in ws_filter:
                    continue
                cid = w.get("capacityId", "") or ""
                # When a capacity filter is set, only audit workspaces on those capacities.
                if cap_filter and cid not in cap_by_id:
                    continue
                cap = cap_by_id.get(cid)
                ws = FabricWorkspace(
                    id=w.get("id", ""), name=name, description=w.get("description", ""),
                    type=w.get("type", ""), capacity_id=cid,
                    capacity_sku=cap.sku if cap else "",
                    capacity_region=cap.region if cap else "",
                    on_dedicated_capacity=bool(cid),
                )
                estate.workspaces.append(ws)
            estate.accessible = True
        except Exception as exc:  # noqa: BLE001
            self.errors.add("fabric_workspaces", exc)
            estate.errors.append(f"workspaces: {exc}")
            self.logger.warning("Fabric workspace discovery failed: %s", exc)

        # Items + roles per workspace (best-effort per workspace)
        for ws in estate.workspaces:
            if not ws.id:
                continue
            try:
                items = client.workspace_items(ws.id)
                for it in items:
                    estate.items.append(FabricItem(
                        id=it.get("id", ""), name=it.get("displayName", "") or it.get("name", ""),
                        type=it.get("type", ""), workspace_id=ws.id, workspace_name=ws.name,
                        description=it.get("description", ""),
                    ))
                ws.item_count = len(items)
            except Exception as exc:  # noqa: BLE001
                ws.accessible = False
                self.errors.add(f"fabric_items:{ws.name}", exc)
                estate.errors.append(f"items[{ws.name}]: {exc}")
            try:
                for ra in client.workspace_role_assignments(ws.id):
                    principal = ra.get("principal") or {}
                    ws.roles.append(FabricRoleAssignment(
                        principal=principal.get("displayName", "") or principal.get("id", ""),
                        principal_type=principal.get("type", ""),
                        role=ra.get("role", ""),
                    ))
            except Exception as exc:  # noqa: BLE001
                self.errors.add(f"fabric_roles:{ws.name}", exc)

        counts: dict[str, int] = {}
        for it in estate.items:
            counts[it.type] = counts.get(it.type, 0) + 1
        estate.item_type_counts = dict(sorted(counts.items()))
        return estate

    # ---- workload sizing --------------------------------------------------
    def _demand(self, inv: dict) -> WorkloadDemand:
        ws = inv.get("workspaces", [])
        d = WorkloadDemand(workspaces=len(ws))
        peak_pool = 0
        for w in ws:
            d.pipelines += len(w.get("pipelines", []))
            d.notebooks += len(w.get("notebooks", []))
            d.dataflows += len(w.get("dataflows", []))
            for sp in w.get("spark_pools", []):
                d.spark_pools += 1
                per = _NODE_VCORES.get(str(sp.get("node_size", "")).lower(), 8)
                nodes = sp.get("max_nodes") if sp.get("autoscale_enabled") else sp.get("node_count")
                nodes = int(nodes or sp.get("max_nodes") or sp.get("node_count") or 3)
                pool_vcores = per * max(nodes, 1)
                d.spark_vcores += pool_vcores
                peak_pool = max(peak_pool, pool_vcores)
            for sq in w.get("sql_pools", []):
                d.sql_pools += 1
                if not sq.get("is_serverless"):
                    m = re.search(r"(\d+)", str(sq.get("sku", "")))
                    d.sql_dwu += int(m.group(1)) if m else 0
        d.spark_peak_pool_vcores = peak_pool
        # Concurrency-adjusted demand: the largest single pool bounds one job's
        # parallelism; assume only a fraction of the *other* pools' provisioned
        # capacity runs concurrently (Synapse pools are provisioned for burst but
        # rarely all peak at once). This avoids sizing for an unrealistic worst case.
        concurrent = peak_pool + int(round(_SPARK_CONCURRENCY * (d.spark_vcores - peak_pool)))
        d.concurrent_spark_vcores = concurrent
        # Fabric provides ~2 base Spark vCores per CU, burstable ~3x; size on the
        # effective burst rate so a capacity's autoscale/bursting is accounted for.
        cu_spark = math.ceil(concurrent / _SPARK_VCORES_PER_CU) if concurrent else 0
        cu_general = 8 if (d.pipelines or d.notebooks or d.dataflows or d.sql_pools) else 0
        required = max(cu_spark, cu_general)
        d.required_capacity_units = required
        d.recommended_sku = "F" + str(next((s for s in _F_SKUS if s >= required), _F_SKUS[-1])) if required else ""
        return d

    # ---- coverage / gap ---------------------------------------------------
    def _coverage(self, inv: dict, estate: FabricEstate) -> list[dict]:
        by_norm: dict[str, FabricWorkspace] = {_norm(w.name): w for w in estate.workspaces}
        items_by_ws: dict[str, set[str]] = {}
        for it in estate.items:
            items_by_ws.setdefault(it.workspace_id, set()).add(it.type)
        rows: list[dict] = []
        for w in inv.get("workspaces", []):
            src = w.get("workspace", {}).get("name", "")
            tgt = by_norm.get(_norm(src))
            expected = sorted({_EXPECTED_ITEM[k] for k in _EXPECTED_ITEM if w.get(k)})
            present = sorted(items_by_ws.get(tgt.id, set()) & set(expected)) if tgt else []
            missing = sorted(set(expected) - set(present))
            rows.append({
                "source_workspace": src,
                "target_workspace": tgt.name if tgt else "",
                "matched": bool(tgt),
                "target_item_count": tgt.item_count if tgt else 0,
                "expected_item_types": expected,
                "present_item_types": present,
                "missing_item_types": missing,
            })
        return rows

    # ---- readiness verdict ------------------------------------------------
    def _assess(self, inv: dict, estate: FabricEstate) -> FabricReadinessAssessment:
        demand = self._demand(inv)
        coverage = self._coverage(inv, estate)
        findings: list[CapabilityFinding] = []
        active_caps = [c for c in estate.capacities if str(c.state).lower() in ("active", "")]
        largest = max(active_caps, key=lambda c: c.capacity_units, default=None)
        largest_cu = largest.capacity_units if largest else 0

        if not estate.accessible:
            findings.append(CapabilityFinding(
                category="Capacity", severity="Info", target="",
                message="No access to the Fabric REST API (unprovisioned tenant or missing permission).",
                recommendation="Authenticate with a principal that has Fabric admin / capacity permissions, then re-run."))
            return FabricReadinessAssessment(verdict="Unknown", demand=demand, findings=findings,
                                             coverage=coverage, severity_counts=_sev_counts(findings))

        # Capacity present
        if not estate.capacities:
            findings.append(CapabilityFinding(
                category="Capacity", severity="Critical",
                message="No Fabric capacity is visible in the target tenant.",
                recommendation="Provision an F-SKU capacity (Fabric) sized at or above the recommended SKU."))
        else:
            paused = [c for c in estate.capacities if str(c.state).lower() == "paused"]
            for c in paused:
                findings.append(CapabilityFinding(
                    category="Capacity", severity="High", target=c.display_name,
                    message=f"Capacity '{c.display_name}' ({c.sku}) is {c.state}.",
                    recommendation="Resume the capacity before running migrated workloads."))

        # Sizing
        if demand.required_capacity_units:
            basis = (f"est. {demand.required_capacity_units} CU ({demand.recommended_sku}); "
                     f"provisioned Spark {demand.spark_vcores} vCores across {demand.spark_pools} pools, "
                     f"largest pool {demand.spark_peak_pool_vcores} vCores, concurrency-adjusted "
                     f"~{demand.concurrent_spark_vcores} vCores")
            caveat = ("Estimate is from *provisioned* pool maxima, not observed utilisation \u2014 "
                      "validate against actual Spark usage / the Fabric Capacity Metrics app.")
            if largest_cu >= demand.required_capacity_units:
                findings.append(CapabilityFinding(
                    category="Capacity", severity="Pass",
                    target=largest.display_name if largest else "",
                    message=(f"Largest active capacity {largest.sku if largest else '?'} "
                             f"({largest_cu} CU) meets the estimated demand ({basis})."),
                    recommendation="Monitor utilisation after cutover; enable the Fabric Capacity Metrics app."))
            else:
                findings.append(CapabilityFinding(
                    category="Capacity", severity="High",
                    target=largest.display_name if largest else "",
                    message=(f"Largest active capacity ({largest_cu} CU) is below the estimated demand \u2014 {basis}. "
                             f"{caveat}"),
                    recommendation=(f"If real utilisation approaches this, scale toward {demand.recommended_sku} or "
                                    f"use capacity autoscale / stagger heavy Spark jobs; otherwise right-size from metrics.")))

        # Region alignment
        src_regions = {str(w.get("workspace", {}).get("location", "")).lower().replace(" ", "")
                       for w in inv.get("workspaces", []) if w.get("workspace", {}).get("location")}
        cap_regions = {str(c.region).lower().replace(" ", "") for c in estate.capacities if c.region}
        if src_regions and cap_regions and not (src_regions & cap_regions):
            findings.append(CapabilityFinding(
                category="Region", severity="Medium",
                message=(f"Source regions {sorted(src_regions)} do not overlap Fabric capacity regions "
                         f"{sorted(cap_regions)}."),
                recommendation="Confirm data-residency requirements and cross-region egress cost/latency."))

        # Dedicated capacity
        no_cap = [w for w in estate.workspaces if not w.on_dedicated_capacity
                  and str(w.type).lower() in ("workspace", "")]
        for w in no_cap:
            findings.append(CapabilityFinding(
                category="Workspace", severity="Medium", target=w.name,
                message=f"Workspace '{w.name}' is not assigned to a Fabric capacity.",
                recommendation="Assign it to an F-SKU capacity so it can host Fabric items."))

        # Coverage gaps
        unmatched = [r for r in coverage if not r["matched"]]
        for r in unmatched:
            findings.append(CapabilityFinding(
                category="Coverage", severity="Medium", target=r["source_workspace"],
                message=f"No target Fabric workspace matches source workspace '{r['source_workspace']}'.",
                recommendation="Create the destination workspace (or map it explicitly) before migrating its artifacts."))
        for r in coverage:
            if r["matched"] and r["missing_item_types"]:
                findings.append(CapabilityFinding(
                    category="Coverage", severity="Low", target=r["target_workspace"],
                    message=(f"Target '{r['target_workspace']}' is missing expected item types: "
                             f"{', '.join(r['missing_item_types'])}."),
                    recommendation="Create the corresponding Fabric items during migration (Lakehouse/Warehouse/Notebook/Pipeline/Dataflow Gen2)."))

        sev = _sev_counts(findings)
        if sev.get("Critical"):
            verdict = "Not ready"
        elif sev.get("High"):
            verdict = "Ready with actions"
        elif sev.get("Medium") or sev.get("Low"):
            verdict = "Ready with actions"
        else:
            verdict = "Ready"
        return FabricReadinessAssessment(
            verdict=verdict, demand=demand,
            largest_capacity_sku=largest.sku if largest else "",
            largest_capacity_units=largest_cu,
            findings=findings, severity_counts=sev, coverage=coverage)

    # ---- run --------------------------------------------------------------
    def _inv(self) -> dict:
        p = self.settings.subdir("inventory") / "synapse_inventory.json"
        return read_json(p) if p.exists() else {"workspaces": []}

    def run(self) -> dict:
        self.logger.info("Fabric audit starting")
        inv = self._inv()
        estate = self.discover_estate()
        assessment = self._assess(inv, estate)
        out = self.output_dir
        write_json(estate.model_dump(), out / "fabric_estate.json")
        write_json(assessment.model_dump(), out / "fabric_readiness_assessment.json")
        md = _summary_md(estate, assessment)
        write_markdown(md, out / "fabric_audit_summary.md")
        write_html("Fabric Environment Audit", md, out / "fabric_audit_summary.html")
        self.save_errors("fabric_audit_errors.json")
        self.logger.info("Fabric audit complete (verdict=%s)", assessment.verdict)
        return {
            "accessible": estate.accessible,
            "capacities": len(estate.capacities),
            "workspaces": len(estate.workspaces),
            "items": len(estate.items),
            "verdict": assessment.verdict,
            "findings": len(assessment.findings),
        }


def _sev_counts(findings: list[CapabilityFinding]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.severity] = out.get(f.severity, 0) + 1
    return out


def _summary_md(estate: FabricEstate, a: FabricReadinessAssessment) -> str:
    d = a.demand
    lines: list[str] = ["# Target Microsoft Fabric — Environment Audit", ""]
    lines.append(f"**Readiness verdict:** {a.verdict}")
    lines.append("")
    if not estate.accessible:
        lines.append("_No access to the Fabric REST API. Authenticate with a Fabric-admin capable "
                     "principal and re-run `fabric-audit` to populate this report._")
        return "\n".join(lines)
    lines.append("## Estate summary")
    lines.append("")
    lines.append(f"- Capacities: **{len(estate.capacities)}** "
                 f"(largest active: {a.largest_capacity_sku or 'n/a'}, {a.largest_capacity_units} CU)")
    lines.append(f"- Workspaces: **{len(estate.workspaces)}**")
    lines.append(f"- Items: **{len(estate.items)}**")
    if estate.item_type_counts:
        lines.append("- Item mix: " + ", ".join(f"{k} × {v}" for k, v in estate.item_type_counts.items()))
    lines.append("")
    lines.append("## Estimated source workload demand")
    lines.append("")
    lines.append(f"- Pipelines {d.pipelines} · Notebooks {d.notebooks} · Dataflows {d.dataflows} · "
                 f"Spark pools {d.spark_pools} · SQL pools {d.sql_pools}")
    lines.append(f"- Provisioned Spark **{d.spark_vcores}** vCores (largest pool {d.spark_peak_pool_vcores}); "
                 f"concurrency-adjusted ~**{d.concurrent_spark_vcores}** vCores · dedicated SQL DWU {d.sql_dwu}")
    lines.append(f"- Estimated capacity requirement: **{d.required_capacity_units} CU** "
                 f"→ recommended **{d.recommended_sku or 'n/a'}**")
    lines.append("- _Based on provisioned pool maxima, not observed utilisation — validate against actual "
                 "Spark usage / the Fabric Capacity Metrics app before committing to an SKU._")
    lines.append("")
    if estate.capacities:
        lines.append("## Capacities")
        lines.append("")
        lines.append("| Capacity | SKU | CU | Region | State |")
        lines.append("|---|---|---|---|---|")
        for c in estate.capacities:
            lines.append(f"| {c.display_name} | {c.sku} | {c.capacity_units} | {c.region} | {c.state} |")
        lines.append("")
    lines.append("## Readiness findings")
    lines.append("")
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4, "Pass": 5}
    fs = sorted(a.findings, key=lambda f: order.get(f.severity, 9))
    if fs:
        lines.append("| Severity | Category | Target | Finding | Recommendation |")
        lines.append("|---|---|---|---|---|")
        for f in fs:
            lines.append(f"| {f.severity} | {f.category} | {f.target} | {f.message} | {f.recommendation} |")
    else:
        lines.append("_No findings._")
    lines.append("")
    lines.append("## Migration coverage (source → target)")
    lines.append("")
    lines.append("| Source workspace | Target workspace | Matched | Target items | Missing item types |")
    lines.append("|---|---|---|---|---|")
    for r in a.coverage:
        lines.append(f"| {r['source_workspace']} | {r['target_workspace'] or '—'} | "
                     f"{'yes' if r['matched'] else 'no'} | {r['target_item_count']} | "
                     f"{', '.join(r['missing_item_types']) or '—'} |")
    return "\n".join(lines)
