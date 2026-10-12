"""The documented container config writes to its persistent volume."""

from datetime import date
from decimal import Decimal
from pathlib import Path, PurePosixPath

import pytest
import yaml

from prahari.core.config import Config, load
from prahari.core.fx import FxError

REPO = Path(__file__).resolve().parents[1]


def test_store_environment_override_preserves_yaml(monkeypatch, tmp_path):
    config_path = tmp_path / "prahari.yaml"
    source = "store:\n  path: local.duckdb\n"
    config_path.write_text(source, encoding="utf-8")
    monkeypatch.setenv("PRAHARI_DUCKDB_PATH", "/data/prahari.duckdb")

    assert load(config_path).store.path == "/data/prahari.duckdb"
    assert config_path.read_text(encoding="utf-8") == source


def test_unset_or_empty_store_override_preserves_local_path(monkeypatch, tmp_path):
    config_path = tmp_path / "prahari.yaml"
    config_path.write_text("store:\n  path: local.duckdb\n", encoding="utf-8")
    monkeypatch.delenv("PRAHARI_DUCKDB_PATH", raising=False)
    assert load(config_path).store.path == "local.duckdb"
    monkeypatch.setenv("PRAHARI_DUCKDB_PATH", "")
    assert load(config_path).store.path == "local.duckdb"


def test_compose_overrides_env_file_path_with_persistent_volume(monkeypatch):
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    collector = compose["services"]["collector"]
    store_path = collector["environment"]["PRAHARI_DUCKDB_PATH"]
    monkeypatch.setenv("PRAHARI_DUCKDB_PATH", store_path)

    effective = load(REPO / "prahari.example.yaml").store.path
    assert PurePosixPath(effective).is_relative_to(PurePosixPath("/data"))
    assert "prahari-data:/data" in collector["volumes"]
    assert collector["read_only"] is True


def test_runtime_code_stays_root_owned():
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split(" AS runtime", maxsplit=1)[1]
    assert "USER prahari" in runtime
    assert "chown -R prahari:prahari /data" in runtime
    assert "--chown=prahari:prahari" not in runtime


def test_compose_does_not_force_a_service_account_key_file():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["collector"]["environment"]
    assert environment["GOOGLE_APPLICATION_CREDENTIALS"] == "${GOOGLE_APPLICATION_CREDENTIALS:-}"


def test_build_context_excludes_credentials_and_customer_data():
    excluded = set((REPO / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {".env", ".env.*", "secrets", "data", "out", "*.duckdb", "prahari.yaml"} <= excluded


def test_fx_rates_parse_from_customer_yaml_with_provenance(monkeypatch, tmp_path):
    monkeypatch.delenv("PRAHARI_DUCKDB_PATH", raising=False)
    path = tmp_path / "prahari.yaml"
    path.write_text(
        "fx_rates:\n"
        "  - base: USD\n"
        "    quote: INR\n"
        "    rate: '85.50'\n"
        "    as_of: 2026-10-01\n"
        "    source: customer-invoice\n",
        encoding="utf-8",
    )
    config = load(path)
    rate = config.fx_table().rate_on("USD", "INR", date(2026, 10, 12))
    assert rate.rate == Decimal("85.50")
    assert rate.as_of == date(2026, 10, 1)
    assert rate.source == "customer-invoice"


def test_empty_config_fx_table_has_no_placeholder_fallback():
    table = Config().fx_table()
    assert table.convert(Decimal("10"), "INR", "INR", date(2026, 10, 12)) == Decimal("10")
    with pytest.raises(FxError, match="no USD->INR rate"):
        table.convert(Decimal("10"), "USD", "INR", date(2026, 10, 12))
