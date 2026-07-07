"""Yapilandirma testleri."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings
from tests.conftest import make_settings


def test_default_mode_is_backtest():
    settings = make_settings()
    assert settings.mode == "backtest"
    assert settings.is_backtest


def test_backtest_mode_requires_no_api_keys():
    settings = make_settings(MODE="backtest")
    assert settings.binance_api_key == ""
    assert settings.binance_testnet_api_key == ""


def test_live_mode_blocked_without_allow_flag():
    # pydantic, dogrulayicidan firlatilan LiveTradingNotAllowedError'i
    # ValidationError icine sarar; mesajin acik olmasi yeterlidir.
    with pytest.raises(ValidationError, match="ALLOW_LIVE_TRADING"):
        make_settings(MODE="live")


def test_live_mode_blocked_with_allow_false():
    with pytest.raises(ValidationError, match="canli islem"):
        make_settings(MODE="live", ALLOW_LIVE_TRADING="false")


def test_live_mode_allowed_with_explicit_flag():
    settings = make_settings(MODE="live", ALLOW_LIVE_TRADING="true")
    assert settings.is_live
    assert settings.allow_live_trading


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        make_settings(MODE="yolo")


def test_mode_is_case_insensitive():
    settings = make_settings(MODE="BACKTEST")
    assert settings.mode == "backtest"


def test_mode_read_from_environment(monkeypatch):
    monkeypatch.setenv("MODE", "testnet")
    settings = Settings(_env_file=None)
    assert settings.is_testnet


def test_symbols_parsed_from_csv_string():
    settings = make_settings(SYMBOLS="BTC/USDT, ETH/USDT ,SOL/USDT")
    assert settings.symbols == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def test_masked_summary_hides_secrets():
    settings = make_settings(
        BINANCE_API_KEY="supersecretkey123", TELEGRAM_BOT_TOKEN="tokentokentoken"
    )
    summary = str(settings.masked_summary())
    assert "supersecretkey123" not in summary
    assert "tokentokentoken" not in summary
