from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "ashare_data"
RETIRED = {
    "ashare_data.mcp_server",
    "ashare_data.cli",
    "ashare_data.realtime",
    "ashare_data.release",
    "ashare_data.tdx",
    "ashare_data.views",
    "ashare_data.services.limits",
    "ashare_data.storage.release_store",
    "ashare_data.storage.cache_store",
    "ashare_data.storage.manifests",
    "ashare_data.storage.parquet_store",
    "ashare_data.pipelines.releases",
    "ashare_data.releases",
    "ashare_data.services.universes",
    "ashare_data.pipelines.symbols",
    "ashare_data.pipelines.views",
    "ashare_data.pipelines.security_master",
    "ashare_data.storage.runtime_store",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_retired_modules_are_absent_and_unreferenced() -> None:
    expected_absent = [
        PACKAGE / "mcp_server.py",
        PACKAGE / "cli.py",
        PACKAGE / "realtime.py",
        PACKAGE / "release.py",
        PACKAGE / "tdx.py",
        PACKAGE / "views.py",
        PACKAGE / "services" / "limits.py",
        PACKAGE / "storage" / "release_store.py",
        PACKAGE / "storage" / "cache_store.py",
        PACKAGE / "storage" / "manifests.py",
        PACKAGE / "storage" / "parquet_store.py",
        PACKAGE / "pipelines" / "releases.py",
        PACKAGE / "releases.py",
        PACKAGE / "services" / "universes.py",
        PACKAGE / "pipelines",
        PACKAGE / "storage",
    ]
    assert not [str(path) for path in expected_absent if path.exists()]
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        leaked = _imports(path) & RETIRED
        if leaked:
            offenders.append(f"{path.relative_to(PACKAGE)}: {sorted(leaked)}")
    assert offenders == []


def test_features_do_not_import_provider_or_storage_modules() -> None:
    offenders: list[str] = []
    for path in (PACKAGE / "features").glob("*.py"):
        leaked = {
            name
            for name in _imports(path)
            if name.startswith("ashare_data.providers") or name.startswith("ashare_data.storage")
        }
        if leaked:
            offenders.append(f"{path.name}: {sorted(leaked)}")
    assert offenders == []


def test_cli_and_normalize_do_not_cross_fact_seams() -> None:
    roots = [PACKAGE / "agent_cli", PACKAGE / "normalize"]
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            leaked = {
                name
                for name in _imports(path)
                if name.startswith("ashare_data.providers") or name.startswith("ashare_data.storage")
            }
            if leaked:
                offenders.append(f"{path.relative_to(PACKAGE)}: {sorted(leaked)}")
    assert offenders == []


def test_agent_cli_is_independent_of_the_historical_database() -> None:
    """The query CLI is only an adapter over upstream fact providers."""
    forbidden_imports = {
        "ashare_data.releases",
        "ashare_data.services.universes",
        "ashare_data.pipelines.symbols",
        "ashare_data.pipelines.views",
    }
    offenders: list[str] = []
    roots = [PACKAGE / "agent_cli", PACKAGE / "services"]
    for root in roots:
        for path in root.rglob("*.py"):
            leaked = _imports(path) & forbidden_imports
            if leaked:
                offenders.append(f"{path.relative_to(PACKAGE)}: {sorted(leaked)}")

    main_source = (PACKAGE / "agent_cli" / "main.py").read_text(encoding="utf-8")
    catalog_source = (PACKAGE / "services" / "catalog.py").read_text(encoding="utf-8")
    public_surface_leaks = {
        token
        for token in (
            'add("admin"',
            'add("universes"',
            'add_argument("--release"',
            '"release_pinning": True',
            '"universes"',
            '"releases"',
            '"bootstrap-symbols"',
        )
        if token in main_source or token in catalog_source
    }

    assert offenders == []
    assert public_surface_leaks == set()


def test_package_has_no_local_database_paths_or_persistent_cache() -> None:
    offenders: list[str] = []
    forbidden_tokens = {
        "data_root(",
        "storage_root(",
        "symbols_root(",
        "universes_root(",
        "live_security_master.json",
        '"cache_root"',
        "/ \"symbols\" /",
    }
    for path in PACKAGE.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        leaked = sorted(token for token in forbidden_tokens if token in source)
        imports_storage = any(name.startswith("ashare_data.storage") for name in _imports(path))
        if leaked or imports_storage:
            offenders.append(
                f"{path.relative_to(PACKAGE)}: tokens={leaked}, imports_storage={imports_storage}"
            )
    assert offenders == []
