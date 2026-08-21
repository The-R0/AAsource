from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services import reference as reference_service


def run_reference(dataset: str, **kwargs):
    data, sources, warnings, degraded = reference_service.dispatch(dataset, **kwargs)
    return ok(
        f"reference.{dataset}",
        data,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
    )
