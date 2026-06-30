"""Background job runner for agents, with captured logs and status.

Runs each agent (or the full pipeline) in a worker thread so the web UI stays
responsive. Captures log output per job and tracks status for polling.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..agents.assessment_agent import AssessmentAgent
from ..agents.dashboard_agent import DashboardAgent
from ..agents.discovery_agent import DiscoveryAgent
from ..agents.inventory_agent import InventoryAgent
from ..agents.migration_agent import MigrationAgent
from ..agents.optimization_agent import OptimizationAgent
from ..agents.reporting_agent import ReportingAgent
from ..utils.config import load_settings

AGENTS: dict[str, Any] = {
    "discover": DiscoveryAgent,
    "inventory": InventoryAgent,
    "assess": AssessmentAgent,
    "migrate": MigrationAgent,
    "report": ReportingAgent,
    "dashboard": DashboardAgent,
    "optimize": OptimizationAgent,
}
PIPELINE_ORDER = ["discover", "inventory", "assess", "migrate", "report", "dashboard", "optimize"]


@dataclass
class Step:
    name: str
    status: str = "pending"  # pending | running | success | error
    started: float | None = None
    finished: float | None = None


@dataclass
class Job:
    name: str
    status: str = "idle"  # idle | running | success | error
    logs: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    started: float | None = None
    finished: float | None = None
    steps: list[Step] = field(default_factory=list)


class _ListHandler(logging.Handler):
    def __init__(self, job: Job) -> None:
        super().__init__()
        self.job = job

    def emit(self, record: logging.LogRecord) -> None:
        self.job.logs.append(self.format(record))


class JobRunner:
    """Tracks the current job and runs agents in a worker thread."""

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path
        self.job = Job(name="none")
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self.job.status == "running"

    def start(self, target: str) -> bool:
        """Start an agent ('discover'...) or 'run-all'. Returns False if busy."""
        with self._lock:
            if self.busy:
                return False
            names = PIPELINE_ORDER if target == "run-all" else [target]
            self.job = Job(
                name=target,
                status="running",
                started=time.time(),
                steps=[Step(name=n) for n in names],
            )
        threading.Thread(target=self._run, args=(target,), daemon=True).start()
        return True

    def _run(self, target: str) -> None:
        handler = _ListHandler(self.job)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%H:%M:%S"))
        try:
            for step in self.job.steps:
                logger = logging.getLogger(step.name)
                logger.addHandler(handler)
                step.status = "running"
                step.started = time.time()
                try:
                    settings = load_settings(self.config_path)
                    self.job.result = AGENTS[step.name](settings).run()
                    step.status = "success"
                except Exception:
                    step.status = "error"
                    raise
                finally:
                    step.finished = time.time()
                    logger.removeHandler(handler)
            self.job.status = "success"
        except Exception as exc:  # noqa: BLE001
            self.job.status = "error"
            self.job.error = f"{type(exc).__name__}: {exc}"
            self.job.logs.append(f"ERROR: {self.job.error}")
        finally:
            self.job.finished = time.time()

    def snapshot(self) -> dict:
        j = self.job
        now = time.time()
        steps = [
            {
                "name": s.name,
                "status": s.status,
                "elapsed": round((s.finished or now) - s.started, 1) if s.started else 0,
            }
            for s in j.steps
        ]
        done = sum(1 for s in j.steps if s.status in ("success", "error"))
        return {
            "name": j.name,
            "status": j.status,
            "logs": j.logs[-200:],
            "result": j.result,
            "error": j.error,
            "elapsed": round((j.finished or now) - j.started, 1) if j.started else 0,
            "steps": steps,
            "progress": round(100 * done / len(j.steps)) if j.steps else 0,
        }
