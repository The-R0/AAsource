"""Hierarchical partition storage and manifest management for Main Board PIT data."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _compute_sha256(data_bytes: bytes) -> str:
    return hashlib.sha256(data_bytes).hexdigest()


class DataHubStorage:
    """Manages raw/, normalized/, manifests/, and quality_reports/ hierarchies."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        if root_dir is None:
            root_dir = os.environ.get("ASHARE_DATA_HUB_DIR", Path(__file__).resolve().parents[3])
        self.root_dir = Path(root_dir)
        self.raw_dir = self.root_dir / "raw"
        self.normalized_dir = self.root_dir / "normalized"
        self.manifests_dir = self.root_dir / "manifests"
        self.reports_dir = self.root_dir / "quality_reports"
        self.init_directories()

    def init_directories(self) -> None:
        for d in [
            self.raw_dir / "security_master",
            self.raw_dir / "daily_bars",
            self.raw_dir / "corporate_actions",
            self.normalized_dir / "security_master",
            self.normalized_dir / "daily",
            self.normalized_dir / "adjustments",
            self.manifests_dir,
            self.reports_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def write_raw_file(self, rel_path: str | Path, content: bytes | str | Any) -> str:
        """Write raw partition file and return its SHA-256 hash."""
        dest = self.raw_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            raw_bytes = content
        elif isinstance(content, str):
            raw_bytes = content.encode("utf-8")
        else:
            raw_bytes = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
        dest.write_bytes(raw_bytes)
        return _compute_sha256(raw_bytes)

    def write_normalized_file(self, rel_path: str | Path, data: Any) -> str:
        """Write normalized JSON partition file idempotently and return SHA-256."""
        dest = self.normalized_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        raw_bytes = text.encode("utf-8")
        dest.write_bytes(raw_bytes)
        return _compute_sha256(raw_bytes)

    def read_normalized_file(self, rel_path: str | Path) -> Any | None:
        dest = self.normalized_dir / rel_path
        if not dest.exists():
            return None
        return json.loads(dest.read_text(encoding="utf-8"))

    def write_manifest(self, name: str, manifest_data: dict[str, Any]) -> Path:
        dest = self.manifests_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest

    def read_manifest(self, name: str) -> dict[str, Any] | None:
        dest = self.manifests_dir / name
        if not dest.exists():
            return None
        return json.loads(dest.read_text(encoding="utf-8"))

    def record_failed_symbols(self, failed: list[dict[str, Any]]) -> None:
        dest = self.manifests_dir / "failed_symbols.json"
        dest.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_quality_report(self, json_data: dict[str, Any], markdown_summary: str) -> tuple[Path, Path]:
        json_path = self.reports_dir / "main_board_pit_report.json"
        md_path = self.reports_dir / "MAIN_BOARD_QUALITY_REPORT.md"
        json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(markdown_summary, encoding="utf-8")
        return json_path, md_path
