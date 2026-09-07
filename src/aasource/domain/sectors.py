"""Sector identity helpers (BK#### board codes)."""

from __future__ import annotations

import re

from aasource.domain.errors import AshareDataError, ErrorCode

_BK = re.compile(r"^BK\d+$", re.IGNORECASE)
_EM_SECTOR = re.compile(r"^90\.(BK\d+)$", re.IGNORECASE)
_EM_BOARD_NUMBER = re.compile(r"^\d{1,6}$")


def is_sector_id(raw: str) -> bool:
    value = str(raw or "").strip()
    return bool(_BK.fullmatch(value) or _EM_SECTOR.fullmatch(value))


def canonicalize_em_board_code(raw: str) -> str:
    """Normalize an Eastmoney F10 numeric board code (e.g. "1432") to BK#### form.

    Eastmoney F10 (CoreConception) reports board codes as bare numbers while the
    quote-side clist API uses the same numbers zero-padded behind a BK prefix
    (verified: F10 "172" -> BK0172 浙江板块, "1432" -> BK1432 氮肥).
    """
    value = str(raw or "").strip()
    if _BK.fullmatch(value):
        return value.upper()
    if _EM_BOARD_NUMBER.fullmatch(value):
        return f"BK{value.zfill(4)}"
    raise AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, f"Unknown Eastmoney board code: {raw!r}")


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
