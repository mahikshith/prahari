"""Keyless ADC must not be rejected by an environment-only startup check."""

import pytest

from prahari.core.config import Config


@pytest.mark.parametrize("credential_path", [None, ""])
def test_gcp_does_not_require_a_credential_file_for_adc(monkeypatch, credential_path):
    if credential_path is None:
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    else:
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", credential_path)
    config = Config.model_validate({
        "collectors": [{"provider": "gcp_vertex", "account_id": "billing-account"}],
    })
    assert config.missing_env() == []


def test_api_admin_keys_remain_required_alongside_keyless_gcp(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
    config = Config.model_validate({
        "collectors": [
            {"provider": "gcp_vertex", "account_id": "billing-account"},
            {"provider": "openai", "account_id": "openai-org"},
            {"provider": "anthropic", "account_id": "anthropic-org"},
        ],
    })
    assert config.missing_env() == ["ANTHROPIC_ADMIN_KEY", "OPENAI_ADMIN_KEY"]
