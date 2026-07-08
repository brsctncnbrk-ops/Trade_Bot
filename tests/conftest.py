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
    "MAX_HOURLY_LOSS",
    "MAX_OPEN_POSITIONS",
    "MAX_DAILY_TRADES",
    "MAX_CAPITAL_USDT",
    "MAX_NOTIONAL_PER_TRADE_USDT",
    "MAX_TOTAL_OPEN_RISK_USDT",
    "MAX_CONCURRENT_ORDERS",
    "MAX_API_ERRORS",
    "ORDER_TYPE",
    "OPEN_ORDER_TIMEOUT_SECONDS",
    "STATE_FILE",
    "STOP_LOSS_PERCENT",
    "STOP_ATR_MULTIPLIER",
    "MIN_STOP_DISTANCE_PERCENT",
    "MAX_STOP_DISTANCE_PERCENT",
    "TAKE_PROFIT_PERCENT",
    "MIN_RISK_REWARD",
    "BREAK_EVEN_TRIGGER_R",
    "TRAILING_STOP_ACTIVATION_R",
    "TRAILING_STOP_ATR_MULTIPLIER",
    "ENABLE_TRADE_FILTERS",
    "MAX_SPREAD_PERCENT",
    "MIN_VOLUME_USDT",
    "MIN_ATR_PERCENT",
    "MAX_ATR_PERCENT",
    "TREND_FILTER_ENABLED",
    "TREND_EMA_PERIOD",
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
