from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services.health import get_health


def run_health():
    data = get_health()
    degraded = data.get("status") != "ok"
    return ok("health", data, degraded=degraded)
