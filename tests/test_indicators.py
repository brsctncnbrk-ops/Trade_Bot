"""Gosterge testleri."""

from __future__ import annotations

import pandas as pd
import pytest

from bot.indicators import add_indicators, calculate_ema, calculate_rsi


def test_ema_is_calculated(sample_ohlcv):
    ema = calculate_ema(sample_ohlcv, 20)
    assert len(ema) == len(sample_ohlcv)
    assert ema.notna().all()


def test_rsi_is_calculated(sample_ohlcv):
    rsi = calculate_rsi(sample_ohlcv, 14)
    valid = rsi.dropna()
    assert len(valid) > 0
    assert ((valid >= 0) & (valid <= 100)).all()


def test_add_indicators_creates_columns(sample_ohlcv):
    df = add_indicators(sample_ohlcv)
    for column in ("ema_20", "ema_50", "rsi_14"):
        assert column in df.columns


def test_add_indicators_does_not_mutate_input(sample_ohlcv):
    add_indicators(sample_ohlcv)
    assert "ema_20" not in sample_ohlcv.columns


def test_small_dataset_does_not_crash():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="1h"),
            "open": [1.0, 2.0, 3.0, 4.0, 5.0],
            "high": [1.1, 2.1, 3.1, 4.1, 5.1],
            "low": [0.9, 1.9, 2.9, 3.9, 4.9],
            "close": [1.0, 2.0, 3.0, 4.0, 5.0],
            "volume": [10, 10, 10, 10, 10],
        }
    )
    result = add_indicators(df)
    assert len(result) == 5
    # RSI icin veri yetersiz: NaN kalmali ama cokmemeli
    assert result["rsi_14"].isna().all()


def test_empty_dataframe_does_not_crash():
    df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    result = add_indicators(df)
    assert "ema_20" in result.columns
    assert len(result) == 0


def test_none_input_raises():
    with pytest.raises(ValueError):
        add_indicators(None)


def test_missing_close_column_raises():
    df = pd.DataFrame({"open": [1, 2, 3]})
    with pytest.raises(ValueError):
        add_indicators(df)


def test_invalid_period_raises(sample_ohlcv):
    with pytest.raises(ValueError):
        calculate_ema(sample_ohlcv, 0)
    with pytest.raises(ValueError):
        calculate_rsi(sample_ohlcv, -5)
