"""Ortak test fixture'lari.

Testler ortamdan ve .env dosyasindan bagimsiz calisir: tum ilgili
ortam degiskenleri temizlenir ve Settings `_env_file=None` ile kurulur.
"""

from __future__ import annotations

import pandas as pd
import pytest

from config.settings import Settings

ENV_VARS = [
    "MODE",
    "ALLOW_LIVE_TRADING",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BINANCE_TESTNET_API_KEY",
    "BINANCE_TESTNET_API_SECRET",
    "BASE_CURRENCY",
    "SYMBOLS",
    "TIMEFRAME",
    "INITIAL_BALANCE",
    "MAX_RISK_PER_TRADE",
    "MAX_DAILY_LOSS",
    "MAX_OPEN_POSITIONS",
    "MAX_DAILY_TRADES",
    "STOP_LOSS_PERCENT",
    "TAKE_PROFIT_PERCENT",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Testleri makinedeki gercek ortam degiskenlerinden izole eder."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


def make_settings(**overrides) -> Settings:
    """Test icin .env dosyasini yok sayan Settings kurar."""
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Kucuk, deterministik OHLCV verisi."""
    from bot.data_provider import generate_sample_data

    return generate_sample_data(periods=200, seed=7)
