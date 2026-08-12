"""External adapters and fact modules."""

from ashare_data.providers.eastmoney import get_eastmoney_provider
from ashare_data.providers.tdx import get_tdx_provider
from ashare_data.providers.tencent import get_tencent_provider

__all__ = [
    "get_eastmoney_provider",
    "get_tdx_provider",
    "get_tencent_provider",
]
