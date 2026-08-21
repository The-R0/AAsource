"""External adapters and fact modules."""

from aasource.providers.eastmoney import get_eastmoney_provider
from aasource.providers.tdx import get_tdx_provider
from aasource.providers.tencent import get_tencent_provider

__all__ = [
    "get_eastmoney_provider",
    "get_tdx_provider",
    "get_tencent_provider",
]
