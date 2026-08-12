from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = PACKAGE_ROOT / "resources"


def resource_path(name: str) -> Path:
    path = RESOURCE_ROOT / name
    if not path.is_file():
        raise FileNotFoundError(f"packaged resource not found: {name}")
    return path


@lru_cache(maxsize=None)
def load_yaml_resource(name: str) -> dict[str, Any]:
    payload = yaml.safe_load(resource_path(name).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
