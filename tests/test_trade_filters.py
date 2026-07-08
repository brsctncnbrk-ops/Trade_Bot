"""Trade filter system tests."""

from __future__ import annotations

import pandas as pd
import pytest

from bot.trade_filters import TradeFilterManager
from tests.conftest import make_settings


def make_df(close=100.0, volume=2000.0, atr=1.0, ema200=90.0):
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-01")],
            "open": [close],
            "high": [close + 1.0],
            "low": [close - 1.0],
            "close": [close],
            "volume": [volume],
            "atr_14": [atr],
            "ema_200": [ema200],
        }
    )


def make_manager(**overrides):
    defaults = dict(
        ENABLE_TRADE_FILTERS=True,
        MAX_SPREAD_PERCENT=0.10,
        MIN_VOLUME_USDT=100000,
        MIN_ATR_PERCENT=0.20,
        MAX_ATR_PERCENT=5.00,
        TREND_FILTER_ENABLED=True,
        TREND_EMA_PERIOD=200,
    )
    defaults.update(overrides)
    return TradeFilterManager(make_settings(**defaults))


def test_high_spread_blocks_trade():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(), bid=99.0, ask=101.0)
    assert not result.passed
    assert result.reason == "SPREAD BLOCKED"
    assert result.value > result.threshold


def test_acceptable_spread_passes_when_other_filters_ok():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(), bid=99.96, ask=100.04)
    assert result.passed


def test_low_volume_blocks_trade():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(volume=100.0), bid=99.96, ask=100.04)
    assert not result.passed
    assert result.reason == "VOLUME BLOCKED"
    assert result.value < result.threshold


def test_atr_too_low_blocks_trade():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(atr=0.1), bid=99.96, ask=100.04)
    assert not result.passed
    assert result.reason == "ATR BLOCKED"
    assert result.value < result.threshold


def test_atr_too_high_blocks_trade():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(atr=6.0), bid=99.96, ask=100.04)
    assert not result.passed
    assert result.reason == "ATR BLOCKED"
    assert result.value > result.threshold


def test_trend_filter_blocks_buy_below_ema200():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(close=100.0, ema200=101.0), bid=99.96, ask=100.04)
    assert not result.passed
    assert result.reason == "TREND BLOCKED"


def test_all_filters_pass_when_market_is_healthy():
    result = make_manager().evaluate("BTC/USDT", "BUY", make_df(close=100.0, volume=2000, atr=1.0, ema200=90.0), bid=99.96, ask=100.04)
    assert result.passed
    assert result.reason == "FILTER PASSED"


def test_filters_disabled_skips_all_filters():
    result = make_manager(ENABLE_TRADE_FILTERS=False).evaluate(
        "BTC/USDT",
        "BUY",
        make_df(close=100.0, volume=1.0, atr=100.0, ema200=999.0),
        bid=90.0,
        ask=110.0,
    )
    assert result.passed
    assert result.reason == "FILTER PASSED"
    assert result.skipped


def test_trade_filter_settings_are_configurable():
    settings = make_settings(
        ENABLE_TRADE_FILTERS=False,
        MAX_SPREAD_PERCENT=0.2,
        MIN_VOLUME_USDT=123,
        MIN_ATR_PERCENT=0.3,
        MAX_ATR_PERCENT=4.0,
        TREND_FILTER_ENABLED=False,
        TREND_EMA_PERIOD=150,
    )
    assert settings.enable_trade_filters is False
    assert settings.max_spread_percent == 0.2
    assert settings.min_volume_usdt == 123
    assert settings.min_atr_percent == 0.3
    assert settings.max_atr_percent == 4.0
    assert settings.trend_filter_enabled is False
    assert settings.trend_ema_period == 150
