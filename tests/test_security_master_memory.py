from __future__ import annotations

import pytest

from ashare_data.providers.tdx import TdxHost, TdxProvider


def test_security_master_cache_is_process_local(monkeypatch) -> None:
    provider = TdxProvider([TdxHost("example.test")])
    calls = 0
    payload = {
        "status": "PASS",
        "source": "test",
        "count": 1,
        "symbols": [{"code": "600000", "exchange": "SH", "name": "test"}],
    }

    def fetch_remote():
        nonlocal calls
        calls += 1
        return payload

    monkeypatch.setattr(provider, "_fetch_security_master_remote", fetch_remote)

    assert provider.fetch_security_master() == payload
    assert provider.fetch_security_master() == payload
    assert calls == 1


def test_security_master_provider_failure_has_no_local_pool_fallback(monkeypatch) -> None:
    provider = TdxProvider([TdxHost("example.test")])

    def fail_remote():
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(provider, "_fetch_security_master_remote", fail_remote)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        provider.fetch_security_master()
