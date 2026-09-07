from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Iterable

from aasource.domain.enums import BoardType, CoverageGrade, ExecutionRole, ProviderName, SecurityType
from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.identifiers import (
    canonicalize_symbol,
    classify_board,
    is_mainboard_executable,
    is_market_observation_anchor,
    is_non_executable_board,
)
from aasource.domain.models import Security, SecurityPITEvent


def _parse_date(d: str | datetime.date | datetime.datetime | None) -> datetime.date | None:
    if d is None:
        return None
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    text = str(d).strip()[:10]
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        # try YYYYMMDD
        digits = "".join(c for c in text if c.isdigit())
        if len(digits) == 8:
            return datetime.date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        return None


@dataclass
class STInterval:
    valid_from: datetime.date
    valid_to: datetime.date | None
    is_st: bool
    name: str
    reason: str = ""


@dataclass
class SuspensionInterval:
    valid_from: datetime.date
    valid_to: datetime.date | None
    reason: str = ""


@dataclass
class MasterSecurityEntry:
    symbol: str
    code: str
    exchange: str
    name: str
    board: str
    listed_date: datetime.date
    delisted_date: datetime.date | None = None
    st_intervals: list[STInterval] = field(default_factory=list)
    suspension_intervals: list[SuspensionInterval] = field(default_factory=list)
    coverage_grade: str = CoverageGrade.A
    source: str = ProviderName.TDX


class PITSecurityMaster:
    """Point-in-Time Security Master for Shanghai and Shenzhen Main Board."""

    def __init__(self) -> None:
        self._entries: dict[str, MasterSecurityEntry] = {}
        self._bootstrap_mainboard_registry()

    def _bootstrap_mainboard_registry(self) -> None:
        """Seed high-fidelity historical universe covering active, delisted, ST, and new IPO stocks."""
        from aasource.pit._seed_universe import SEED_MAINBOARD_UNIVERSE, SEED_DELISTED_UNIVERSE, SEED_ST_TRANSITIONS
        
        # Load active and recent mainboard stocks
        for row in SEED_MAINBOARD_UNIVERSE:
            symbol = row["symbol"]
            listed = _parse_date(row.get("listed_date")) or datetime.date(2000, 1, 1)
            delisted = _parse_date(row.get("delisted_date"))
            entry = MasterSecurityEntry(
                symbol=symbol,
                code=symbol[2:],
                exchange=symbol[:2],
                name=row["name"],
                board=classify_board(symbol),
                listed_date=listed,
                delisted_date=delisted,
                coverage_grade=row.get("coverage_grade", CoverageGrade.A),
                source=row.get("source", ProviderName.TDX),
            )
            self._entries[symbol] = entry

        # Load historical delisted mainboard stocks (prevent survivorship bias)
        for row in SEED_DELISTED_UNIVERSE:
            symbol = row["symbol"]
            listed = _parse_date(row.get("listed_date")) or datetime.date(1995, 1, 1)
            delisted = _parse_date(row.get("delisted_date")) or datetime.date(2021, 6, 1)
            entry = MasterSecurityEntry(
                symbol=symbol,
                code=symbol[2:],
                exchange=symbol[:2],
                name=row["name"],
                board=classify_board(symbol),
                listed_date=listed,
                delisted_date=delisted,
                coverage_grade=CoverageGrade.A,
                source=ProviderName.TDX,
            )
            self._entries[symbol] = entry

        # Load historical ST / destatting transitions
        for item in SEED_ST_TRANSITIONS:
            symbol = item["symbol"]
            if symbol in self._entries:
                v_from = _parse_date(item["valid_from"]) or datetime.date(2021, 1, 1)
                v_to = _parse_date(item.get("valid_to"))
                self._entries[symbol].st_intervals.append(
                    STInterval(
                        valid_from=v_from,
                        valid_to=v_to,
                        is_st=item["is_st"],
                        name=item["name"],
                        reason=item.get("reason", ""),
                    )
                )

    def register_security(self, entry: MasterSecurityEntry) -> None:
        self._entries[entry.symbol] = entry

    def is_st(self, symbol: str, as_of: str | datetime.date | datetime.datetime) -> bool | None:
        """Point-in-Time ST status. NEVER uses today's status for historical dates.
        
        Returns:
            True if stock was ST on as_of
            False if stock was normal on as_of
            None if ST status is unconfirmed/missing (automatically degrades coverage grade)
        """
        canonical = canonicalize_symbol(symbol)
        date_val = _parse_date(as_of)
        if date_val is None:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Invalid as_of date: {as_of}")

        entry = self._entries.get(canonical)
        if not entry:
            return None

        # Check explicit ST intervals
        for interval in entry.st_intervals:
            if interval.valid_from <= date_val and (interval.valid_to is None or date_val <= interval.valid_to):
                return interval.is_st

        # If listed on that date and no ST interval was ever flagged for a known clean stock
        if entry.listed_date <= date_val and (entry.delisted_date is None or date_val <= entry.delisted_date):
            # Check default name ST marker for active period if no granular transition exists
            return "ST" in entry.name.upper()

        return None

    def is_listed_at(self, symbol: str, as_of: str | datetime.date | datetime.datetime) -> bool:
        canonical = canonicalize_symbol(symbol)
        date_val = _parse_date(as_of)
        if date_val is None:
            return False
        entry = self._entries.get(canonical)
        if not entry:
            return False
        if date_val < entry.listed_date:
            return False
        if entry.delisted_date is not None and date_val > entry.delisted_date:
            return False
        return True

    def is_suspended_at(self, symbol: str, as_of: str | datetime.date | datetime.datetime) -> bool:
        canonical = canonicalize_symbol(symbol)
        date_val = _parse_date(as_of)
        if date_val is None:
            return False
        entry = self._entries.get(canonical)
        if not entry:
            return False
        for susp in entry.suspension_intervals:
            if susp.valid_from <= date_val and (susp.valid_to is None or date_val <= susp.valid_to):
                return True
        return False

    def is_tradable_at(self, symbol: str, as_of: str | datetime.date | datetime.datetime) -> bool:
        """Determines if a security is genuinely tradable at Point-in-Time as_of.
        
        Requires:
        1. Main Board executable (SH600/601/603/605, SZ000/001/002/003)
        2. Already listed and not delisted as of that date
        3. NOT ST at as_of (is_st(as_of) is False)
        4. NOT suspended at as_of
        """
        canonical = canonicalize_symbol(symbol)
        if not is_mainboard_executable(canonical):
            return False
        if not self.is_listed_at(canonical, as_of):
            return False
        st_state = self.is_st(canonical, as_of)
        if st_state is not False:  # If ST or unconfirmed, cannot trade
            return False
        if self.is_suspended_at(canonical, as_of):
            return False
        return True

    def get_security_at(self, symbol: str, as_of: str | datetime.date | datetime.datetime) -> Security:
        """Reconstruct the exact PIT Security model at as_of."""
        canonical = canonicalize_symbol(symbol)
        date_val = _parse_date(as_of)
        if date_val is None:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Invalid as_of date: {as_of}")

        entry = self._entries.get(canonical)
        if not entry:
            # Check non-executable or anchor
            board = classify_board(canonical)
            role = (
                ExecutionRole.NON_EXECUTABLE_MARKET_ANCHOR
                if is_market_observation_anchor(canonical)
                else ExecutionRole.EXCLUDED_NON_EXECUTABLE
            )
            return Security(
                symbol=canonical,
                code=canonical[2:],
                exchange=canonical[:2],
                name=None,
                security_type=SecurityType.INDEX if board == "INDEX" else SecurityType.UNKNOWN,
                board=board,
                is_listed=False,
                tradable=False,
                is_st=None,
                is_suspended=None,
                price_limit_pct=None,
                coverage_grade=CoverageGrade.UNAVAILABLE,
                execution_role=role,
                source=ProviderName.TDX,
            )

        is_listed = self.is_listed_at(canonical, date_val)
        is_st_val = self.is_st(canonical, date_val)
        is_susp = self.is_suspended_at(canonical, date_val)
        tradable = (
            is_mainboard_executable(canonical)
            and is_listed
            and (is_st_val is False)
            and not is_susp
        )

        # Name at PIT date
        name = entry.name
        for interval in entry.st_intervals:
            if interval.valid_from <= date_val and (interval.valid_to is None or date_val <= interval.valid_to):
                name = interval.name
                break

        limit_pct = 5.0 if is_st_val else 10.0
        role = ExecutionRole.ACCESSIBLE if is_mainboard_executable(canonical) else ExecutionRole.EXCLUDED_NON_EXECUTABLE

        coverage = entry.coverage_grade
        if is_st_val is None and is_listed:
            coverage = CoverageGrade.DEGRADED

        return Security(
            symbol=canonical,
            code=canonical[2:],
            exchange=canonical[:2],
            name=name,
            security_type=SecurityType.STOCK,
            board=entry.board,
            listed_date=entry.listed_date.isoformat(),
            delisted_date=entry.delisted_date.isoformat() if entry.delisted_date else None,
            is_st=is_st_val,
            is_suspended=is_susp,
            price_limit_pct=limit_pct,
            is_listed=is_listed,
            tradable=tradable,
            valid_from=date_val.isoformat(),
            valid_to=date_val.isoformat(),
            event_time=date_val.isoformat(),
            publish_time=date_val.isoformat(),
            source=entry.source,
            coverage_grade=coverage,
            execution_role=role,
        )

    def get_tradable_mainboard_universe(self, as_of: str | datetime.date | datetime.datetime) -> list[Security]:
        """Reconstruct the entire tradable Main Board universe as of a specific trade date."""
        date_val = _parse_date(as_of)
        if date_val is None:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Invalid as_of date: {as_of}")

        results: list[Security] = []
        for symbol in self._entries:
            if self.is_tradable_at(symbol, date_val):
                results.append(self.get_security_at(symbol, date_val))
        results.sort(key=lambda s: s.symbol)
        return results

    def get_full_mainboard_registry(self) -> list[MasterSecurityEntry]:
        """Returns the entire historical Main Board master list (active + delisted)."""
        return list(self._entries.values())

    def filter_candidates_before_alpha(
        self,
        candidates: Iterable[str | dict[str, Any]],
        as_of: str | datetime.date | datetime.datetime | None = None,
    ) -> list[Any]:
        """Hard filter: removes non-executable boards (SH688, SH689, SZ300, SZ301, BJ, ETF, Index)
        and non-tradable stocks BEFORE any factor ranking or Alpha calculation.
        """
        filtered: list[Any] = []
        for item in candidates:
            if isinstance(item, str):
                sym = canonicalize_symbol(item)
                if not is_mainboard_executable(sym):
                    continue
                if as_of is not None and not self.is_tradable_at(sym, as_of):
                    continue
                filtered.append(item)
            elif isinstance(item, dict) and "symbol" in item:
                sym = canonicalize_symbol(item["symbol"])
                if not is_mainboard_executable(sym):
                    continue
                if as_of is not None and not self.is_tradable_at(sym, as_of):
                    continue
                filtered.append(item)
        return filtered

    def validate_order(
        self,
        symbol: str,
        as_of: str | datetime.date | datetime.datetime | None = None,
    ) -> tuple[bool, str]:
        """Hard order validation gatekeeper. Enforces account permission and tradability rules."""
        try:
            canonical = canonicalize_symbol(symbol)
        except Exception as exc:
            return False, f"ORDER_REJECTED_INVALID_SYMBOL: {exc}"

        # Board permission checks
        if canonical.startswith(("SH688", "SH689")):
            return False, "ORDER_REJECTED_STAR_BOARD_FORBIDDEN"
        if canonical.startswith(("SZ300", "SZ301")):
            return False, "ORDER_REJECTED_CHINEXT_BOARD_FORBIDDEN"
        if canonical.startswith("BJ"):
            return False, "ORDER_REJECTED_BSE_BOARD_FORBIDDEN"
        if not is_mainboard_executable(canonical):
            return False, "ORDER_REJECTED_NON_MAINBOARD_FORBIDDEN"

        if as_of is not None:
            date_val = _parse_date(as_of)
            if date_val:
                if not self.is_listed_at(canonical, date_val):
                    return False, "ORDER_REJECTED_NOT_LISTED_OR_DELISTED_AT_DATE"
                st_state = self.is_st(canonical, date_val)
                if st_state is True:
                    return False, "ORDER_REJECTED_ST_STOCK_FORBIDDEN"
                if st_state is None:
                    return False, "ORDER_REJECTED_ST_STATUS_UNCONFIRMED"
                if self.is_suspended_at(canonical, date_val):
                    return False, "ORDER_REJECTED_STOCK_SUSPENDED_AT_DATE"

        return True, "ORDER_PERMITTED_MAINBOARD"


_GLOBAL_PIT_MASTER: PITSecurityMaster | None = None


def get_pit_master() -> PITSecurityMaster:
    global _GLOBAL_PIT_MASTER
    if _GLOBAL_PIT_MASTER is None:
        _GLOBAL_PIT_MASTER = PITSecurityMaster()
    return _GLOBAL_PIT_MASTER
