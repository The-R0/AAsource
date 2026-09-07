from __future__ import annotations

import tempfile
from pathlib import Path
from aasource.domain.enums import AuditStatus
from aasource.pit.auditor import MainBoardAuditor
from aasource.pit.master import get_pit_master
from aasource.pit.pipeline import IngestionPipeline
from aasource.pit.storage import DataHubStorage


def test_storage_and_pipeline_execution() -> None:
    """Verify hierarchical storage, hashing, resumability, and manifest generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DataHubStorage(root_dir=tmpdir)
        pipeline = IngestionPipeline(storage=storage)

        # 1. Security master snapshot
        sec_res = pipeline.build_security_master_snapshot()
        assert sec_res["record_count"] >= 3195
        assert len(sec_res["raw_sha256"]) == 64
        assert len(sec_res["normalized_sha256"]) == 64

        # 2. Corporate actions and adjustment factors
        act_res = pipeline.build_corporate_actions_and_factors([2021, 2022, 2023, 2024, 2025, 2026])
        assert len(act_res["years"]) == 6

        # 3. Daily bars partitions
        bars_res = pipeline.build_daily_bars_partitions([2021, 2022, 2023, 2024, 2025, 2026])
        assert bars_res["partition_count"] == 6
        assert bars_res["failed_count"] == 0

        # Verify directories exist
        assert (storage.raw_dir / "security_master" / "master_records.json").exists()
        assert (storage.normalized_dir / "security_master" / "pit_securities.json").exists()
        assert (storage.manifests_dir / "failed_symbols.json").exists()

        # 4. Audit execution
        auditor = MainBoardAuditor(storage=storage)
        report = auditor.run_full_audit()

        assert report["status"] == AuditStatus.MAIN_BOARD_DAILY_PIT_READY
        assert report["summary"]["actual_covered_securities"] >= 3195
        assert report["summary"]["listing_date_coverage_pct"] == 100.0
        assert report["summary"]["delisting_date_coverage_pct"] == 100.0
        assert report["summary"]["st_pit_coverage_pct"] == 100.0

        # Check output report files
        assert (storage.reports_dir / "main_board_pit_report.json").exists()
        assert (storage.reports_dir / "MAIN_BOARD_QUALITY_REPORT.md").exists()


def test_incremental_update_reuses_history() -> None:
    """Verify incremental updates add new stocks and update latest session without re-downloading past years."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DataHubStorage(root_dir=tmpdir)
        pipeline = IngestionPipeline(storage=storage)

        # Baseline partitions
        pipeline.build_daily_bars_partitions([2021, 2022, 2023, 2024, 2025, 2026])

        # Incremental addition of 2 new stocks
        new_stocks = [
            {"symbol": "SH605599", "name": "永安期货", "listed_date": "2021-12-23"},
            {"symbol": "SZ001399", "name": "广合科技", "listed_date": "2024-04-02"},
        ]
        inc_res = pipeline.incremental_update(new_securities=new_stocks, latest_trade_date="2026-08-23")

        assert inc_res["mode"] == "INCREMENTAL"
        assert inc_res["historical_partitions_reused"] == [2021, 2022, 2023, 2024, 2025]
        assert inc_res["new_securities_added"] == 2
        assert inc_res["updated_year"] == 2026

        # Check master now includes the 2 new stocks
        master = pipeline.pit_master
        assert master.is_listed_at("SH605599", "2024-01-01") is True
        assert master.is_tradable_at("SH605599", "2024-01-01") is True
        assert master.is_listed_at("SZ001399", "2024-05-01") is True
        assert master.is_tradable_at("SZ001399", "2024-05-01") is True

