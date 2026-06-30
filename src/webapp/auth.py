"""Interactive Azure authentication helpers for the web UI.

Wraps the Azure CLI (`az login` / `az account`) so a consultant can sign in to
a specific tenant/subscription from the browser. Interactive login runs in a
background thread; status is read via `az account show`. No secrets handled.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from dataclasses import dataclass

_AZ = shutil.which("az") or "az"


@dataclass
class LoginState:
    status: str = "idle"  # idle | running | success | error
    message: str = ""


class AzureAuth:
    """Tracks an interactive `az login` and reports the active account."""

    def __init__(self) -> None:
        self.state = LoginState()
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self.state.status == "running"

    def account(self) -> dict:
        """Return the active subscription/tenant, or signed-out state."""
        try:
            out = subprocess.run(
                [_AZ, "account", "show", "-o", "json"],
                capture_output=True, text=True, timeout=20,
            )
            if out.returncode != 0:
                return {"signed_in": False}
            data = json.loads(out.stdout)
            return {
                "signed_in": True,
                "subscription": data.get("name", ""),
                "subscription_id": data.get("id", ""),
                "tenant_id": data.get("tenantId", ""),
                "user": (data.get("user") or {}).get("name", ""),
            }
        except Exception as exc:  # noqa: BLE001
            return {"signed_in": False, "error": str(exc)}

    def login(self, tenant: str = "", subscription: str = "") -> bool:
        """Start interactive `az login`. Returns False if already running."""
        with self._lock:
            if self.busy:
                return False
            self.state = LoginState(status="running", message="Browser sign-in opened…")
        threading.Thread(target=self._run, args=(tenant, subscription), daemon=True).start()
        return True

    def _run(self, tenant: str, subscription: str) -> None:
        try:
            cmd = [_AZ, "login", "-o", "none"]
            if tenant:
                cmd += ["--tenant", tenant]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                self.state = LoginState("error", res.stderr.strip()[:400] or "Login failed")
                return
            if subscription:
                subprocess.run([_AZ, "account", "set", "--subscription", subscription], capture_output=True, text=True, timeout=30)
            acct = self.account()
            self.state = LoginState("success", f"Signed in as {acct.get('user', '')} ({acct.get('subscription', '')})")
        except FileNotFoundError:
            self.state = LoginState("error", "Azure CLI (az) not found. Install it or use DefaultAzureCredential.")
        except Exception as exc:  # noqa: BLE001
            self.state = LoginState("error", str(exc)[:400])
