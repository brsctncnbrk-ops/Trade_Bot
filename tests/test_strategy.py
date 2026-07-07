"""Strateji testleri.

Sinyal kosullarini dogrudan kontrol edebilmek icin gosterge kolonlari
elle kurgulanmis DataFrame'ler kullanilir.
"""

from __future__ import annotations

import pandas as pd

from bot.state import Position
from bot.strategy import EmaRsiStrategy


def make_df(close=100.0, ema20=110.0, ema50=100.0, rsi=50.0, low=None, high=None):
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-01")],
            "open": [close],
            "high": [high if high is not None else close * 1.01],
            "low": [low if low is not None else close * 0.99],
            "close": [close],
            "volume": [10.0],
            "ema_20": [ema20],
            "ema_50": [ema50],
            "rsi_14": [rsi],
        }
    )


def make_position(entry=100.0, stop=98.0, take=104.0):
    return Position(
        symbol="BTC/USDT",
        side="long",
        entry_price=entry,
        quantity=1.0,
        stop_loss=stop,
        take_profit=take,
    )


def test_buy_signal_generated_correctly():
    strategy = EmaRsiStrategy(stop_loss_percent=0.02, take_profit_percent=0.04)
    df = make_df(close=100.0, ema20=110.0, ema50=100.0, rsi=50.0)
    signal = strategy.generate_signal(df, "BTC/USDT", open_position=None)
    assert signal.action == "BUY"
    assert signal.price == 100.0
    assert signal.stop_loss == 100.0 * 0.98
    assert signal.take_profit == 100.0 * 1.04


def test_buy_signal_always_has_stop_loss_and_take_profit():
    strategy = EmaRsiStrategy()
    df = make_df()
    signal = strategy.generate_signal(df, "BTC/USDT")
    assert signal.action == "BUY"
    assert signal.stop_loss is not None and signal.stop_loss > 0
    assert signal.take_profit is not None and signal.take_profit > 0


def test_no_buy_when_rsi_too_high():
    strategy = EmaRsiStrategy()
    df = make_df(rsi=75.0)
    signal = strategy.generate_signal(df, "BTC/USDT")
    assert signal.action == "HOLD"
    assert "RSI" in signal.reason


def test_no_buy_when_ema_condition_fails():
    strategy = EmaRsiStrategy()
    df = make_df(ema20=95.0, ema50=100.0)
    signal = strategy.generate_signal(df, "BTC/USDT")
    assert signal.action == "HOLD"
    assert "EMA" in signal.reason


def test_no_buy_when_position_already_open():
    strategy = EmaRsiStrategy()
    df = make_df()  # alis kosullari saglansa bile
    position = make_position()
    signal = strategy.generate_signal(df, "BTC/USDT", open_position=position)
    assert signal.action != "BUY"


def test_sell_on_stop_loss_hit():
    strategy = EmaRsiStrategy()
    df = make_df(close=99.0, low=97.0)  # low, stop'un (98) altina indi
    position = make_position(stop=98.0)
    signal = strategy.generate_signal(df, "BTC/USDT", open_position=position)
    assert signal.action == "SELL"
    assert "Stop-loss" in signal.reason


def test_sell_on_take_profit_hit():
    strategy = EmaRsiStrategy()
    df = make_df(close=103.0, high=105.0)  # high, TP'nin (104) ustune cikti
    position = make_position(take=104.0)
    signal = strategy.generate_signal(df, "BTC/USDT", open_position=position)
    assert signal.action == "SELL"
    assert "Take-profit" in signal.reason


def test_sell_on_trend_reversal():
    strategy = EmaRsiStrategy()
    df = make_df(close=100.0, ema20=95.0, ema50=100.0, low=99.0, high=101.0)
    position = make_position(stop=90.0, take=120.0)
    signal = strategy.generate_signal(df, "BTC/USDT", open_position=position)
    assert signal.action == "SELL"
    assert "EMA" in signal.reason


def test_hold_when_indicators_are_nan():
    strategy = EmaRsiStrategy()
    df = make_df(rsi=float("nan"))
    signal = strategy.generate_signal(df, "BTC/USDT")
    assert signal.action == "HOLD"


def test_hold_on_empty_data():
    strategy = EmaRsiStrategy()
    signal = strategy.generate_signal(pd.DataFrame(), "BTC/USDT")
    assert signal.action == "HOLD"
