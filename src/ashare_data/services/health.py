from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ashare_data.providers.tdx import get_tdx_provider
from ashare_data.providers.tencent import get_tencent_provider

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _reference_status() -> tuple[str, dict[str, Any]]:
    # Reference facts are optional; their outage must not hide price-plane health.
    try:
        from ashare_data.services.reference import reference_status

        reference = reference_status()
        status = str(reference.get("status", "")).upper()
        if status in {"OK", "READY", "AVAILABLE"}:
            return "ok", reference
        if status in {"UNAVAILABLE", "ERROR"}:
            return "unavailable", reference
        return str(reference.get("status") or "unknown").lower(), reference
    except Exception as exc:  # noqa: BLE001
        return "unavailable", {"error": str(exc)}


def get_health() -> dict[str, Any]:
    tdx = get_tdx_provider().status()
    tencent = get_tencent_provider().status()
    reference_norm, reference = _reference_status()

    components = {
        "tencent": {"status": tencent.get("status", "unknown"), "details": tencent},
        "tdx": {"status": tdx.get("status", "unknown"), "details": tdx},
        "reference": {"status": reference_norm, "details": reference},
    }

    # Overall reflects price plane; reference-only outage → degraded not dead.
    price_ok = components["tencent"]["status"] == "ok" or components["tdx"]["status"] == "ok"
    if price_ok and reference_norm == "ok":
        overall = "ok"
    elif price_ok:
        overall = "degraded"
    else:
        overall = "unavailable"

    return {
        "status": overall,
        "components": components,
        "providers": {
            "tdx": components["tdx"]["status"],
            "tencent": components["tencent"]["status"],
            "reference": components["reference"]["status"],
        },
        "as_of": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
    }
