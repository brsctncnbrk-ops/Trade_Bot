"""Professional Take Profit system tests."""

from __future__ import annotations

import pytest

from bot.execution import ExecutionEngine
from bot.risk_manager import RiskManager
from bot.state import BotState
from bot.strategy import EmaRsiStrategy, Signal
from bot.take_profit import TakeProfitManager
from tests.conftest import make_settings
from tests.test_stop_loss_system import make_df


def test_take_profit_created_from_stop_distance_and_min_rr():
    manager = TakeProfitManager(min_risk_reward=2.0)
    plan = manager.create_plan("buy", entry_price=100.0, stop_loss=96.0, stop_distance=4.0)
    assert plan.take_profit == pytest.approx(108.0)
    assert plan.risk_reward == pytest.approx(2.0)
    assert plan.levels[0].percent == 1.0


def test_take_profit_for_sell_is_below_entry():
    manager = TakeProfitManager(min_risk_reward=2.0)
    plan = manager.create_plan("sell", entry_price=100.0, stop_loss=104.0, stop_distance=4.0)
    assert plan.take_profit == pytest.approx(92.0)
    assert plan.risk_reward == pytest.approx(2.0)


def test_take_profit_invalid_when_same_side_as_stop_for_buy():
    manager = TakeProfitManager(min_risk_reward=2.0)
    with pytest.raises(RuntimeError, match="Take Profit invalid"):
        manager.validate("buy", entry_price=100.0, stop_loss=96.0, take_profit=98.0)


def test_take_profit_invalid_when_rr_too_low():
    manager = TakeProfitManager(min_risk_reward=2.0)
    with pytest.raises(RuntimeError, match="Risk/Reward"):
        manager.validate("buy", entry_price=100.0, stop_loss=96.0, take_profit=104.0)


def test_strategy_uses_min_risk_reward_for_take_profit():
    strategy = EmaRsiStrategy(
        stop_atr_multiplier=2.0,
        min_stop_distance_percent=0.003,
        max_stop_distance_percent=0.05,
        min_risk_reward=2.0,
    )
    # ATR 2 * 2 = 4 stop distance -> TP distance 8.
    signal = strategy.generate_signal(make_df(close=100.0, atr=2.0), "BTC/USDT")
    assert signal.action == "BUY"
    assert signal.stop_loss == pytest.approx(96.0)
    assert signal.take_profit == pytest.approx(108.0)
    assert signal.risk_reward == pytest.approx(2.0)


def test_execution_blocks_buy_without_take_profit():
    engine = ExecutionEngine(make_settings(MODE="backtest"))
    with pytest.raises(RuntimeError, match="Take Profit is required before opening a position"):
        engine.place_order("BTC/USDT", "buy", 0.1, 100.0, stop_loss=96.0, take_profit=None)


def test_execution_blocks_invalid_take_profit_side():
    engine = ExecutionEngine(make_settings(MODE="backtest", MIN_RISK_REWARD=2.0))
    with pytest.raises(RuntimeError, match="Take Profit invalid"):
        engine.place_order("BTC/USDT", "buy", 0.1, 100.0, stop_loss=96.0, take_profit=98.0)


def test_risk_manager_blocks_low_risk_reward_signal():
    settings = make_settings(MIN_RISK_REWARD=2.0)
    signal = Signal(
        action="BUY",
        symbol="BTC/USDT",
        reason="test",
        price=100.0,
        stop_loss=96.0,
        take_profit=104.0,
        stop_distance=4.0,
    )
    decision = RiskManager(settings).evaluate(signal, BotState(), balance=100.0)
    assert not decision.approved
    assert "Risk/Reward" in decision.reason


def test_min_risk_reward_is_configurable():
    settings = make_settings(MIN_RISK_REWARD=3.0)
    assert settings.min_risk_reward == 3.0
