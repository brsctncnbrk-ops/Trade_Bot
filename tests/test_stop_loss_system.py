"""Professional Stop Loss system tests."""

from __future__ import annotations

import pandas as pd
import pytest

from bot.execution import ExecutionEngine
from bot.indicators import add_indicators, calculate_atr
from bot.risk_manager import RiskManager
from bot.state import BotState
from bot.strategy import EmaRsiStrategy, Signal
from tests.conftest import make_settings


def make_df(close=100.0, atr=2.0):
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-01")],
            "open": [close],
            "high": [close + 1.0],
            "low": [close - 1.0],
            "close": [close],
            "volume": [100.0],
            "ema_20": [110.0],
            "ema_50": [100.0],
            "rsi_14": [50.0],
            "atr_14": [atr],
        }
    )


def test_atr_is_calculated(sample_ohlcv):
    atr = calculate_atr(sample_ohlcv, 14)
    valid = atr.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()


def test_add_indicators_creates_atr_column(sample_ohlcv):
    df = add_indicators(sample_ohlcv)
    assert "atr_14" in df.columns


def test_atr_stop_loss_created_for_buy_signal():
    strategy = EmaRsiStrategy(
        stop_atr_multiplier=2.0,
        min_stop_distance_percent=0.003,
        max_stop_distance_percent=0.05,
    )
    signal = strategy.generate_signal(make_df(close=100.0, atr=2.0), "BTC/USDT")
    assert signal.action == "BUY"
    assert signal.stop_loss == pytest.approx(96.0)
    assert signal.stop_distance == pytest.approx(4.0)


def test_stop_loss_invalid_when_atr_missing():
    df = make_df(close=100.0, atr=float("nan"))
    signal = EmaRsiStrategy().generate_signal(df, "BTC/USDT")
    assert signal.action == "HOLD"
    assert "Stop" in signal.reason


def test_stop_loss_invalid_when_too_close():
    strategy = EmaRsiStrategy(stop_atr_multiplier=2.0, min_stop_distance_percent=0.003)
    # ATR 0.05 * 2 = 0.10, only 0.1% of price; min is 0.3%.
    signal = strategy.generate_signal(make_df(close=100.0, atr=0.05), "BTC/USDT")
    assert signal.action == "HOLD"
    assert "yakin" in signal.reason.lower()


def test_stop_loss_invalid_when_too_far():
    strategy = EmaRsiStrategy(stop_atr_multiplier=2.0, max_stop_distance_percent=0.05)
    # ATR 4 * 2 = 8%, above max 5%.
    signal = strategy.generate_signal(make_df(close=100.0, atr=4.0), "BTC/USDT")
    assert signal.action == "HOLD"
    assert "uzak" in signal.reason.lower()


def test_position_size_uses_effective_balance_risk_and_stop_distance():
    settings = make_settings(
        INITIAL_BALANCE=100,
        MAX_CAPITAL_USDT=100,
        MAX_RISK_PER_TRADE=0.01,
        MAX_NOTIONAL_PER_TRADE_USDT=10,
    )
    signal = Signal(
        action="BUY",
        symbol="BTC/USDT",
        reason="test",
        price=100.0,
        stop_loss=98.0,
        take_profit=104.0,
        stop_distance=2.0,
    )
    decision = RiskManager(settings).evaluate(signal, BotState(), balance=1_000_000.0)
    assert decision.approved
    # 100 * 1% = 1 USDT risk; stop distance 2 -> 0.5 units raw;
    # notional cap 10 USDT clamps to 0.1 units.
    assert decision.position_size == pytest.approx(0.1)
    assert decision.notional == pytest.approx(10.0)
    assert decision.risk_amount <= 1.0


def test_buy_order_without_stop_loss_is_blocked_with_runtime_error():
    settings = make_settings(MODE="backtest")
    engine = ExecutionEngine(settings)
    with pytest.raises(RuntimeError, match="Stop Loss is required before opening a position"):
        engine.place_order("BTC/USDT", "buy", 0.1, 100.0, stop_loss=None, take_profit=104.0)


def test_risk_manager_blocks_signal_without_stop_loss():
    settings = make_settings()
    signal = Signal("BUY", "BTC/USDT", "test", price=100.0, stop_loss=None, take_profit=104.0)
    decision = RiskManager(settings).evaluate(signal, BotState(), balance=100.0)
    assert not decision.approved
    assert "Stop-loss" in decision.reason
