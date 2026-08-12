from __future__ import annotations

import argparse
import sys

from ashare_data.agent_cli.commands import bars as bars_cmd
from ashare_data.agent_cli.commands import auction as auction_cmd
from ashare_data.agent_cli.commands import bars_batch as bars_batch_cmd
from ashare_data.agent_cli.commands import catalog as catalog_cmd
from ashare_data.agent_cli.commands import features as features_cmd
from ashare_data.agent_cli.commands import health as health_cmd
from ashare_data.agent_cli.commands import limit_history as limit_history_cmd
from ashare_data.agent_cli.commands import market as market_cmd
from ashare_data.agent_cli.commands import quotes as quotes_cmd
from ashare_data.agent_cli.commands import reference as reference_cmd
from ashare_data.agent_cli.commands import sectors as sectors_cmd
from ashare_data.agent_cli.commands import securities as securities_cmd
from ashare_data.agent_cli.commands import trades as trades_cmd
from ashare_data.agent_cli.envelope import fail
from ashare_data.agent_cli.serializers import emit, read_stdin_json
from ashare_data.domain.errors import AshareDataError, ErrorCode



class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, message)


def _symbols_from_args(args) -> list[str]:
    symbols = list(getattr(args, "symbols", None) or [])
    if getattr(args, "stdin", False):
        payload = read_stdin_json()
        symbols.extend(payload.get("symbols") or [])
    if getattr(args, "symbol", None):
        symbols.append(args.symbol)
    # comma-separated support on --symbols for features
    if getattr(args, "symbols_csv", None):
        symbols.extend([p.strip() for p in str(args.symbols_csv).split(",") if p.strip()])
    symbols = [s for s in symbols if s]
    if not symbols:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "No symbols provided")
    return symbols


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pretty", action="store_true", help="indent JSON for humans")

    parser = ContractArgumentParser(
        prog="ashare-data",
        description="A-share Agent fact-layer CLI",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, **kwargs):
        return sub.add_parser(name, parents=[common], **kwargs)

    add("catalog", help="list capabilities")
    add("health", help="upstream provider health")

    sec = add("securities", help="security master facts")
    sec.add_argument("symbols", nargs="*")
    sec.add_argument("--stdin", action="store_true")

    q = add("quotes", help="batch realtime quotes")
    q.add_argument("symbols", nargs="*")
    q.add_argument("--stdin", action="store_true")

    auction = add("auction", help="opening call-auction snapshot from Tencent order book")
    auction.add_argument("symbols", nargs="*")
    auction.add_argument("--stdin", action="store_true")

    b = add("bars", help="OHLCV bars")
    b.add_argument("symbol")
    b.add_argument("--tf", default="1d", dest="timeframe")
    b.add_argument("--limit", type=int, default=120)
    b.add_argument("--start")
    b.add_argument("--end")
    b.add_argument("--adjust", default="none")

    lh = add("limit-history", help="per-stock sealed/broken/consecutive price-limit history")
    lh.add_argument("symbol")
    lh.add_argument("--start")
    lh.add_argument("--end")
    lh.add_argument("--limit", type=int, default=1200)

    bb = add("bars-batch", help="batch OHLCV bars (item-level status)")
    bb.add_argument("--symbols", required=True, help="comma-separated symbols")
    bb.add_argument("--tf", default="1m", dest="timeframe")
    bb.add_argument("--limit", type=int, default=240)
    bb.add_argument("--start")
    bb.add_argument("--end")
    bb.add_argument("--adjust", default="none")

    t = add("trades", help="tick / transaction facts")
    t.add_argument("symbol")
    t.add_argument("--trade-date", required=True)
    t.add_argument("--limit", type=int, default=2000)

    f = add("features", help="deterministic feature sets")
    f.add_argument("symbol", nargs="?")
    f.add_argument("--symbols", dest="symbols_csv")
    f.add_argument("--set", dest="feature_set", required=True)
    f.add_argument("--tf", default="1d", dest="timeframe")
    f.add_argument("--include-provisional", action="store_true")
    f.add_argument("--stdin", action="store_true")

    m = add("market", help="market facts")
    m_sub = m.add_subparsers(dest="market_command", required=True)
    m_sub.add_parser("snapshot", parents=[common])
    m_sub.add_parser("cross-section", parents=[common], help="full-A quote cross-section")
    m_sub.add_parser("stock-signals", parents=[common], help="full-A stock discovery dimensions")
    movers = m_sub.add_parser("movers", parents=[common])
    movers.add_argument("--sort-by", default="change_pct")
    movers.add_argument("--limit", type=int, default=50)
    movers.add_argument("--ascending", action="store_true")
    m_sub.add_parser("breadth", parents=[common])
    limits = m_sub.add_parser("limits", parents=[common], help="limit-up/down/broken pools")
    limits.add_argument("--trade-date", default=None, help="YYYY-MM-DD (optional)")

    s = add("sectors", help="sector identity/membership/rankings")
    s_sub = s.add_subparsers(dest="sectors_command", required=True)
    sl = s_sub.add_parser("list", parents=[common])
    sl.add_argument("--kind", default="all", choices=("all", "industry", "concept"))
    sl.add_argument("--limit", type=int, default=100)
    sr = s_sub.add_parser("rankings", parents=[common])
    sr.add_argument("--kind", default="industry", choices=("industry", "concept"))
    sr.add_argument("--limit", type=int, default=50)
    sm = s_sub.add_parser("members", parents=[common])
    sm.add_argument("sector_id")
    sm.add_argument("--limit", type=int, default=500)
    sms = s_sub.add_parser("memberships", parents=[common], help="reverse stock-to-sector memberships")
    sms.add_argument("symbols", nargs="*")
    sms.add_argument("--stdin", action="store_true")
    ss = s_sub.add_parser("search", parents=[common])
    ss.add_argument("query")
    ss.add_argument("--limit", type=int, default=20)
    sres = s_sub.add_parser("resolve", parents=[common])
    sres.add_argument("query")
    smin = s_sub.add_parser("minute", parents=[common], help="sector 1m trends")
    smin.add_argument("sector_id")
    smin.add_argument("--trade-date", default=None)

    r = add("reference", help="canonical reference datasets")
    r.add_argument(
        "dataset",
        choices=[
            "dragon-tiger",
            "dragon-tiger-seats",
            "institutional-dragon-tiger",
            "block-trades",
            "money-flow",
            "shareholders",
            "fund-holdings",
        ],
    )
    r.add_argument("symbol", nargs="?")
    r.add_argument("--trade-date")
    r.add_argument("--start-date")
    r.add_argument("--end-date")
    r.add_argument("--report-date")
    r.add_argument("--category", default="A股", choices=["A股", "B股", "基金", "债券"])
    r.add_argument("--limit", type=int, default=100)

    return parser


def dispatch(args) -> tuple[dict, int]:
    cmd = args.command
    if cmd == "catalog":
        return catalog_cmd.run_catalog()
    if cmd == "health":
        return health_cmd.run_health()
    if cmd == "securities":
        return securities_cmd.run_securities(_symbols_from_args(args))
    if cmd == "quotes":
        return quotes_cmd.run_quotes(_symbols_from_args(args))
    if cmd == "auction":
        return auction_cmd.run_auction(_symbols_from_args(args))
    if cmd == "bars":
        return bars_cmd.run_bars(
            args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
            start=args.start,
            end=args.end,
            adjust=args.adjust,
        )
    if cmd == "bars-batch":
        symbols = [p.strip() for p in str(args.symbols).split(",") if p.strip()]
        if not symbols:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, "bars-batch requires --symbols")
        return bars_batch_cmd.run_bars_batch(
            symbols,
            timeframe=args.timeframe,
            limit=args.limit,
            start=args.start,
            end=args.end,
            adjust=args.adjust,
        )
    if cmd == "limit-history":
        return limit_history_cmd.run_limit_history(
            args.symbol, start=args.start, end=args.end, limit=args.limit
        )
    if cmd == "trades":
        return trades_cmd.run_trades(args.symbol, trade_date=args.trade_date, limit=args.limit)
    if cmd == "features":
        symbols = []
        if args.symbol:
            symbols.append(args.symbol)
        if args.symbols_csv:
            symbols.extend([p.strip() for p in args.symbols_csv.split(",") if p.strip()])
        if args.stdin:
            symbols.extend(read_stdin_json().get("symbols") or [])
        if not symbols:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, "No symbols provided for features")
        return features_cmd.run_features(
            symbols,
            set_name=args.feature_set,
            timeframe=args.timeframe,
            include_provisional=bool(args.include_provisional),
        )
    if cmd == "market":
        return market_cmd.run_market(
            args.market_command,
            sort_by=getattr(args, "sort_by", "change_pct"),
            limit=getattr(args, "limit", 50),
            descending=not getattr(args, "ascending", False),
            trade_date=getattr(args, "trade_date", None),
        )
    if cmd == "sectors":
        symbols = _symbols_from_args(args) if args.sectors_command == "memberships" else None
        return sectors_cmd.run_sectors(
            args.sectors_command,
            sector_id=getattr(args, "sector_id", None),
            query=getattr(args, "query", None),
            kind=getattr(args, "kind", "all"),
            limit=getattr(args, "limit", 100),
            trade_date=getattr(args, "trade_date", None),
            symbols=symbols,
        )
    if cmd == "reference":
        kwargs = {"limit": args.limit}
        if args.dataset in {"dragon-tiger"}:
            if not args.trade_date:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "--trade-date required")
            return reference_cmd.run_reference(args.dataset, symbol=args.symbol, trade_date=args.trade_date, limit=args.limit)
        if args.dataset == "dragon-tiger-seats":
            if not args.symbol or not args.trade_date:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "symbol and --trade-date required")
            return reference_cmd.run_reference(
                args.dataset, symbol=args.symbol, trade_date=args.trade_date, limit=args.limit
            )
        if args.dataset == "institutional-dragon-tiger":
            if not args.start_date or not args.end_date:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "--start-date and --end-date required")
            return reference_cmd.run_reference(
                args.dataset,
                symbol=args.symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                limit=args.limit,
            )
        if args.dataset == "block-trades":
            if not args.start_date or not args.end_date:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "--start-date and --end-date required")
            return reference_cmd.run_reference(
                args.dataset,
                symbol=args.symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                category=args.category,
                limit=args.limit,
            )
        if args.dataset == "money-flow":
            if not args.symbol:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "symbol required")
            return reference_cmd.run_reference(args.dataset, symbol=args.symbol, limit=args.limit)
        if args.dataset == "shareholders":
            if not args.symbol or not args.report_date:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "symbol and --report-date required")
            return reference_cmd.run_reference(
                args.dataset, symbol=args.symbol, report_date=args.report_date, limit=args.limit
            )
        if args.dataset == "fund-holdings":
            if not args.report_date:
                raise AshareDataError(ErrorCode.INVALID_REQUEST, "--report-date required")
            return reference_cmd.run_reference(
                args.dataset, report_date=args.report_date, symbol=args.symbol, limit=args.limit
            )
    raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Unknown command: {cmd}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = None
    pretty = False
    try:
        args = parser.parse_args(argv)
        pretty = bool(args.pretty)
        payload, code = dispatch(args)
        return emit(payload, pretty=pretty, exit_code=code)
    except AshareDataError as exc:
        payload, code = fail(getattr(args, "command", "unknown"), exc)
        return emit(payload, pretty=pretty, exit_code=code)
    except Exception as exc:  # noqa: BLE001
        payload, code = fail(getattr(args, "command", "unknown"), exc)
        print(f"internal error: {exc}", file=sys.stderr)
        return emit(payload, pretty=pretty, exit_code=code)


if __name__ == "__main__":
    raise SystemExit(main())
