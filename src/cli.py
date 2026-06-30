"""Typer CLI orchestrating the Synapse to Fabric Migration Accelerator.

Commands: discover, inventory, assess, migrate, report, dashboard, optimize, run-all.
Run with: python -m src.cli <command>
"""
from __future__ import annotations

import typer
from rich.console import Console

from .agents.assessment_agent import AssessmentAgent
from .agents.dashboard_agent import DashboardAgent
from .agents.discovery_agent import DiscoveryAgent
from .agents.inventory_agent import InventoryAgent
from .agents.migration_agent import MigrationAgent
from .agents.optimization_agent import OptimizationAgent
from .agents.reporting_agent import ReportingAgent
from .utils.config import load_settings

app = typer.Typer(help="Synapse to Fabric Migration Accelerator", add_completion=False)
console = Console()

_CONFIG = typer.Option(None, "--config", "-c", help="Path to settings.yaml")


def _run(agent_cls, config):
    settings = load_settings(config)
    result = agent_cls(settings).run()
    console.print(f"[green]{agent_cls.__name__} done:[/green] {result}")
    return result


@app.command()
def discover(config: str = _CONFIG):
    """Discover subscriptions, resource groups, and Synapse workspaces."""
    _run(DiscoveryAgent, config)


@app.command()
def inventory(config: str = _CONFIG):
    """Inventory all Synapse artifacts."""
    _run(InventoryAgent, config)


@app.command()
def assess(config: str = _CONFIG):
    """Assess complexity, risk, and Fabric readiness."""
    _run(AssessmentAgent, config)


@app.command()
def migrate(config: str = _CONFIG):
    """Recommend Fabric targets and build wave plan."""
    _run(MigrationAgent, config)


@app.command()
def report(config: str = _CONFIG):
    """Generate executive and technical reports."""
    _run(ReportingAgent, config)


@app.command()
def dashboard(config: str = _CONFIG):
    """Generate HTML dashboard and Power BI datasets."""
    _run(DashboardAgent, config)


@app.command()
def optimize(config: str = _CONFIG):
    """Build the Copilot optimization pack."""
    _run(OptimizationAgent, config)


@app.command(name="run-all")
def run_all(config: str = _CONFIG):
    """Run the full pipeline in order."""
    for cls in (DiscoveryAgent, InventoryAgent, AssessmentAgent, MigrationAgent, ReportingAgent, DashboardAgent, OptimizationAgent):
        _run(cls, config)


@app.command()
def serve(config: str = _CONFIG, host: str = "127.0.0.1", port: int = 8050):
    """Launch the web UI to configure, run, and browse outputs."""
    from .webapp.app import create_app

    console.print(f"[green]Web UI:[/green] http://{host}:{port}")
    create_app(config).run(host=host, port=port, debug=False)


if __name__ == "__main__":
    app()
