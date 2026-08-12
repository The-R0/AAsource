from __future__ import annotations

import json
import math
import sys
from typing import Any

from ashare_data.domain.errors import AshareDataError, ErrorCode


def sanitize_for_json(value: Any) -> Any:
    """Guarantee strict JSON: no NaN/Infinity; convert to null."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(v) for v in value]
    return value


def configure_stdio() -> None:
    """Force UTF-8 on Windows so Chinese index names survive subprocess capture."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def emit(payload: dict[str, Any], *, pretty: bool = False, exit_code: int = 0) -> int:
    configure_stdio()
    clean = sanitize_for_json(payload)
    if pretty:
        text = json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False)
    else:
        text = json.dumps(clean, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    return exit_code


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"invalid stdin JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "stdin JSON must be an object")
    return payload
