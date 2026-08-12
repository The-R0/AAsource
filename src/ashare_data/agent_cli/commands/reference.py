from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.services import reference as reference_service


def run_reference(dataset: str, **kwargs):
    data, sources, warnings, degraded = reference_service.dispatch(dataset, **kwargs)
    return ok(
        f"reference.{dataset}",
        data,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
    )
