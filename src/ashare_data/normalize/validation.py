from __future__ import annotations

from typing import Any

from ashare_data.domain.validators import validate_bar_dict, validate_quote_dict


def annotate_bar_quality(bar: dict[str, Any]) -> dict[str, Any]:
    problems = validate_bar_dict(bar)
    if not problems:
        return bar
    out = dict(bar)
    out["quality"] = "partial" if out.get("close") is not None else "invalid"
    missing = list(out.get("missing_fields") or [])
    for problem in problems:
        if problem not in missing:
            missing.append(problem)
    out["missing_fields"] = missing
    return out


def annotate_quote_warnings(quote: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    problems = validate_quote_dict(quote)
    return quote, problems
