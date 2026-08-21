from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services.catalog import get_catalog


def run_catalog():
    return ok("catalog", get_catalog())
