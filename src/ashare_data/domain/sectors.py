"""Sector identity helpers (BK#### board codes)."""

from __future__ import annotations

import re

from ashare_data.domain.errors import AshareDataError, ErrorCode

_BK = re.compile(r"^BK\d+$", re.IGNORECASE)
_EM_SECTOR = re.compile(r"^90\.(BK\d+)$", re.IGNORECASE)


def is_sector_id(raw: str) -> bool:
    value = str(raw or "").strip()
    return bool(_BK.fullmatch(value) or _EM_SECTOR.fullmatch(value))


def canonicalize_sector_id(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "Empty sector id")
    m = _EM_SECTOR.fullmatch(value)
    if m:
        return m.group(1).upper()
    if _BK.fullmatch(value):
        return value.upper()
    raise AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, f"Unknown sector id: {raw}")


def eastmoney_sector_secid(sector_id: str) -> str:
    return f"90.{canonicalize_sector_id(sector_id)}"
