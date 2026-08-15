from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd


@dataclass(frozen=True)
class FeatureDefinition:
    id: str
    version: int
    required_fields: tuple[str, ...]
    params: tuple[str, ...]
    compute: Callable[[pd.DataFrame, dict[str, Any]], Any]


_REGISTRY: dict[str, FeatureDefinition] = {}


def register(defn: FeatureDefinition) -> None:
    _REGISTRY[defn.id] = defn


def get_feature(feature_id: str) -> FeatureDefinition:
    if feature_id not in _REGISTRY:
        raise KeyError(feature_id)
    return _REGISTRY[feature_id]


def all_features() -> list[FeatureDefinition]:
    return list(_REGISTRY.values())
