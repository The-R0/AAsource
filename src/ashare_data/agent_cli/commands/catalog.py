from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.services.catalog import get_catalog


def run_catalog():
    return ok("catalog", get_catalog())
